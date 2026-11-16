from decimal import Decimal

from django.test import TestCase

from accounts.models import User
from farms.models import Farm, FarmMembership, FarmRole

from .models import InventoryItem, StockMovement
from .services import apply_movement, movement_delta, reverse_movement


class LedgerServiceTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email='farmer@example.com', first_name='Fay')
        self.farm = Farm.objects.create(name='Stock Farm', owner=self.user)
        self.item = InventoryItem.objects.create(
            farm=self.farm, name='Dairy Meal', category=InventoryItem.Category.FEED,
            current_stock=Decimal('50.00'),
        )

    def _movement(self, movement_type, quantity):
        return StockMovement.objects.create(
            farm=self.farm, item=self.item, date='2026-01-05',
            movement_type=movement_type, quantity=quantity, recorded_by=self.user,
        )

    def test_restock_increases_stock_and_snapshots_before(self):
        movement = self._movement(StockMovement.MovementType.RESTOCK, Decimal('20.00'))
        apply_movement(movement)
        self.item.refresh_from_db()
        movement.refresh_from_db()
        self.assertEqual(self.item.current_stock, Decimal('70.00'))
        self.assertEqual(movement.stock_before, Decimal('50.00'))

    def test_usage_decreases_stock(self):
        movement = self._movement(StockMovement.MovementType.USAGE, Decimal('15.00'))
        apply_movement(movement)
        self.item.refresh_from_db()
        self.assertEqual(self.item.current_stock, Decimal('35.00'))

    def test_adjustment_sets_absolute_level(self):
        movement = self._movement(StockMovement.MovementType.ADJUSTMENT, Decimal('12.00'))
        apply_movement(movement)
        self.item.refresh_from_db()
        self.assertEqual(self.item.current_stock, Decimal('12.00'))
        self.assertEqual(movement_delta(movement), Decimal('12.00') - Decimal('50.00'))

    def test_reverse_movement_undoes_a_restock(self):
        movement = self._movement(StockMovement.MovementType.RESTOCK, Decimal('20.00'))
        apply_movement(movement)
        reverse_movement(movement)
        self.item.refresh_from_db()
        self.assertEqual(self.item.current_stock, Decimal('50.00'))

    def test_reverse_movement_undoes_a_usage(self):
        movement = self._movement(StockMovement.MovementType.USAGE, Decimal('15.00'))
        apply_movement(movement)
        reverse_movement(movement)
        self.item.refresh_from_db()
        self.assertEqual(self.item.current_stock, Decimal('50.00'))


class InventoryPermissionTests(TestCase):
    def setUp(self):
        self.farmer = User.objects.create_user(email='farmer@example.com', first_name='Fay')
        self.worker = User.objects.create_user(email='worker@example.com', first_name='Wes')
        self.farm = Farm.objects.create(name='Stock Farm', owner=self.farmer)
        FarmMembership.objects.create(user=self.farmer, farm=self.farm, role=FarmRole.FARMER)
        FarmMembership.objects.create(user=self.worker, farm=self.farm, role=FarmRole.WORKER)
        self.item = InventoryItem.objects.create(
            farm=self.farm, name='Dairy Meal', category=InventoryItem.Category.FEED,
            current_stock=Decimal('50.00'),
        )

    def _login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session['active_farm_id'] = self.farm.id
        session.save()

    def test_worker_cannot_create_an_item(self):
        self._login(self.worker)
        self.client.post('/inventory/add/', {
            'name': 'New Item', 'category': InventoryItem.Category.OTHER,
            'unit': InventoryItem.Unit.KG, 'current_stock': '0', 'reorder_level': '0',
        })
        self.assertFalse(InventoryItem.objects.filter(farm=self.farm, name='New Item').exists())

    def test_duplicate_item_name_shows_a_form_error_instead_of_crashing(self):
        self._login(self.farmer)
        response = self.client.post('/inventory/add/', {
            'name': 'Dairy Meal', 'category': InventoryItem.Category.FEED,
            'unit': InventoryItem.Unit.KG, 'current_stock': '0', 'reorder_level': '0',
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form']['name'].errors)
        self.assertEqual(InventoryItem.objects.filter(farm=self.farm, name='Dairy Meal').count(), 1)

    def test_an_item_can_be_saved_again_under_its_own_name(self):
        self._login(self.farmer)
        response = self.client.post(f'/inventory/{self.item.id}/edit/', {
            'name': 'Dairy Meal', 'category': InventoryItem.Category.FEED,
            'unit': InventoryItem.Unit.KG, 'reorder_level': '5',
        })
        self.assertEqual(response.status_code, 302)

    def test_worker_can_log_a_stock_movement(self):
        self._login(self.worker)
        response = self.client.post('/inventory/movements/add/', {
            'item': self.item.id, 'date': '2026-01-05', 'movement_type': StockMovement.MovementType.RESTOCK,
            'quantity': '10.00', 'used_by': '', 'note': '',
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        self.item.refresh_from_db()
        self.assertEqual(self.item.current_stock, Decimal('60.00'))

    def _use(self, used_by):
        return self.client.post('/inventory/movements/add/', {
            'item': self.item.id, 'date': '2026-01-05', 'movement_type': StockMovement.MovementType.USAGE,
            'quantity': '4.00', 'used_by': used_by, 'note': '',
        })

    def test_a_movement_can_be_recorded_as_used_by_calves(self):
        self._login(self.worker)
        self.assertEqual(self._use('calves').status_code, 302)
        movement = StockMovement.objects.get(farm=self.farm, movement_type=StockMovement.MovementType.USAGE)
        self.assertEqual(movement.used_by_group, 'calves')
        self.assertIsNone(movement.used_by)
        self.assertEqual(movement.used_by_display, 'Calves')
        self.assertContains(self.client.get('/inventory/movements/'), 'Calves')
        self.assertContains(self.client.get(f'/inventory/{self.item.id}/'), 'Calves')

    def _make_calf(self, tag_id, farm=None, **extra):
        from cows.models import Cow
        from farms.models import Block
        farm = farm or self.farm
        block, _created = Block.objects.get_or_create(farm=farm, name='Calf pen')
        return Cow.objects.create(farm=farm, block=block, tag_id=tag_id, category=Cow.Category.CALF, **extra)

    def test_a_movement_can_be_recorded_as_used_by_staff_or_home(self):
        self._login(self.worker)
        for group, label in (('staff', 'Staff'), ('home', 'Home')):
            self.assertEqual(self._use(group).status_code, 302)
            movement = StockMovement.objects.filter(farm=self.farm).order_by('-id').first()
            self.assertEqual(movement.used_by_group, group)
            self.assertIsNone(movement.used_by)
            self.assertEqual(movement.used_by_display, label)

    def test_individual_calves_can_be_picked(self):
        calf_a, calf_b = self._make_calf('K-1'), self._make_calf('K-2')
        self._make_calf('K-3')
        self._login(self.worker)
        response = self.client.post('/inventory/movements/add/', {
            'item': self.item.id, 'date': '2026-01-05', 'movement_type': StockMovement.MovementType.USAGE,
            'quantity': '4.00', 'used_by': 'calves', 'calves': [calf_a.id, calf_b.id], 'note': '',
        })
        self.assertEqual(response.status_code, 302)
        movement = StockMovement.objects.get(farm=self.farm, movement_type=StockMovement.MovementType.USAGE)
        self.assertEqual(set(movement.used_by_calves.all()), {calf_a, calf_b})
        self.assertEqual(movement.used_by_display, 'Calves: K-1, K-2')
        self.assertContains(self.client.get('/inventory/movements/'), 'Calves: K-1, K-2')

    def test_ticked_calves_are_ignored_when_not_used_by_calves(self):
        calf = self._make_calf('K-4')
        self._login(self.worker)
        self.client.post('/inventory/movements/add/', {
            'item': self.item.id, 'date': '2026-01-05', 'movement_type': StockMovement.MovementType.USAGE,
            'quantity': '4.00', 'used_by': 'home', 'calves': [calf.id], 'note': '',
        })
        movement = StockMovement.objects.get(farm=self.farm, movement_type=StockMovement.MovementType.USAGE)
        self.assertEqual(movement.used_by_calves.count(), 0)
        self.assertEqual(movement.used_by_display, 'Home')

    def test_calves_from_another_farm_or_older_animals_cannot_be_picked(self):
        from cows.models import Cow
        other_owner = User.objects.create_user(email='other@example.com', first_name='Oz')
        other_farm = Farm.objects.create(name='Other Farm', owner=other_owner)
        foreign_calf = self._make_calf('X-1', farm=other_farm)
        grown = self._make_calf('K-5')
        Cow.objects.filter(pk=grown.pk).update(category=Cow.Category.COW)
        self._login(self.worker)
        for bad in (foreign_calf.id, grown.id):
            response = self.client.post('/inventory/movements/add/', {
                'item': self.item.id, 'date': '2026-01-05', 'movement_type': StockMovement.MovementType.USAGE,
                'quantity': '4.00', 'used_by': 'calves', 'calves': [bad], 'note': '',
            })
            self.assertEqual(response.status_code, 200)
            self.assertTrue(response.context['form']['calves'].errors)
        self.assertFalse(StockMovement.objects.filter(farm=self.farm).exists())

    def test_used_by_rejects_anything_that_is_not_a_group(self):
        member = FarmMembership.objects.get(user=self.worker, farm=self.farm)
        self._login(self.worker)
        response = self._use(str(member.pk))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form']['used_by'].errors)

    def test_movement_form_offers_calves_staff_and_home_but_no_staff_names(self):
        self._make_calf('K-6', name='Daisy')
        self._login(self.worker)
        html = self.client.get('/inventory/movements/add/').content.decode()
        for value, label in (('calves', 'Calves'), ('staff', 'Staff'), ('home', 'Home')):
            self.assertIn(f'<option value="{value}">{label}</option>', html)
        self.assertNotIn('Wes', html.split('id="field-used_by"')[1].split('id="field-note"')[0])
        self.assertIn('K-6', html)
        self.assertIn('Daisy', html)

    def test_an_old_entry_naming_a_staff_member_still_shows_the_name(self):
        member = FarmMembership.objects.get(user=self.worker, farm=self.farm)
        movement = StockMovement.objects.create(
            farm=self.farm, item=self.item, date='2026-01-05', movement_type=StockMovement.MovementType.USAGE,
            quantity=Decimal('1.00'), used_by=member,
        )
        self.assertEqual(movement.used_by_display, 'Wes')

    def test_milk_usage_for_calves_records_the_calves(self):
        calf = self._make_calf('K-7')
        self._login(self.farmer)
        response = self.client.post('/inventory/milk-usage/', {
            'date': '2026-01-05', 'liters': '3', 'purpose': 'calf', 'calves': [calf.id], 'note': '',
        })
        self.assertEqual(response.status_code, 302)
        movement = StockMovement.objects.get(farm=self.farm, item__name='Milk')
        self.assertEqual(movement.used_by_display, 'Calves: K-7')

    def test_milk_usage_for_home(self):
        self._login(self.farmer)
        self.client.post('/inventory/milk-usage/', {
            'date': '2026-01-05', 'liters': '2', 'purpose': 'home', 'note': '',
        })
        movement = StockMovement.objects.get(farm=self.farm, item__name='Milk')
        self.assertEqual(movement.used_by_display, 'Home')

    def test_worker_cannot_delete_a_movement(self):
        movement = StockMovement.objects.create(
            farm=self.farm, item=self.item, date='2026-01-05',
            movement_type=StockMovement.MovementType.RESTOCK, quantity=Decimal('10.00'),
        )
        apply_movement(movement)
        self._login(self.worker)
        self.client.post(f'/inventory/movements/{movement.id}/delete/')
        self.assertTrue(StockMovement.objects.filter(id=movement.id).exists())

    def test_low_stock_notifies_managers_not_the_actor(self):
        from notifications.models import Notification

        self.item.reorder_level = Decimal('45.00')
        self.item.save(update_fields=['reorder_level'])
        self._login(self.farmer)
        self.client.post('/inventory/movements/add/', {
            'item': self.item.id, 'date': '2026-01-05', 'movement_type': StockMovement.MovementType.USAGE,
            'quantity': '10.00', 'used_by': '', 'note': '',
        })
        low_stock_notifs = Notification.objects.filter(farm=self.farm, kind='inventory item', recipient=self.farmer)
        # The actor themself is excluded (m.user_id != request.user.id in
        # inventory.views.movement_create) - farmer triggered it and manages
        # workers, but shouldn't get notified about their own action.
        self.assertFalse(low_stock_notifs.exists())
