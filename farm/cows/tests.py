from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from accounts.models import User
from advisory.models import DiseaseCatalog
from farms.models import Block, Farm, FarmMembership, FarmRole
from inventory.models import InventoryItem

from .models import Cow, CowHealthRecord, CowWeightRecord, FeedingRecord, MilkRecord, ReproductiveEvent
from .services import estimate_weight_from_girth


class CowsTestCase(TestCase):
    def setUp(self):
        self.farmer = User.objects.create_user(email='farmer@example.com', first_name='Fay')
        self.worker = User.objects.create_user(email='worker@example.com', first_name='Wes')
        self.farm = Farm.objects.create(name='Herd Farm', owner=self.farmer)
        FarmMembership.objects.create(user=self.farmer, farm=self.farm, role=FarmRole.FARMER)
        FarmMembership.objects.create(user=self.worker, farm=self.farm, role=FarmRole.WORKER)
        self.block_a = Block.objects.create(farm=self.farm, name='Block A')
        self.block_b = Block.objects.create(farm=self.farm, name='Block B')

    def _login(self, user):
        self.client.force_login(user)
        session = self.client.session
        session['active_farm_id'] = self.farm.id
        session.save()

    def _make_cow(self, tag_id='C-001', block=None, status=Cow.Status.ACTIVE):
        return Cow.objects.create(
            farm=self.farm, block=block or self.block_a, tag_id=tag_id,
            category=Cow.Category.COW, gender=Cow.Gender.FEMALE, status=status,
        )


class CowCreateViewTests(CowsTestCase):
    @patch('cows.views.mint_cow_nft', return_value=None)
    def test_farmer_can_add_a_cow(self, mock_mint):
        self._login(self.farmer)
        response = self.client.post('/cows/add/', {
            'block': self.block_a.id, 'tag_id': 'C-010', 'name': '', 'category': Cow.Category.COW,
            'gender': Cow.Gender.FEMALE, 'breed': '', 'date_of_birth': '', 'last_calving_date': '',
            'status': Cow.Status.ACTIVE,
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        cow = Cow.objects.get(farm=self.farm, tag_id='C-010')
        self.assertEqual(cow.added_by, self.farmer)
        mock_mint.assert_called_once()

    def test_worker_cannot_add_a_cow(self):
        self._login(self.worker)
        self.client.post('/cows/add/', {
            'block': self.block_a.id, 'tag_id': 'C-011', 'name': '', 'category': Cow.Category.COW,
            'gender': Cow.Gender.FEMALE, 'breed': '', 'date_of_birth': '', 'last_calving_date': '',
            'status': Cow.Status.ACTIVE,
        })
        self.assertFalse(Cow.objects.filter(farm=self.farm, tag_id='C-011').exists())

    def test_duplicate_tag_id_on_same_farm_is_rejected(self):
        self._make_cow(tag_id='C-020')
        self._login(self.farmer)
        with patch('cows.views.mint_cow_nft', return_value=None):
            self.client.post('/cows/add/', {
                'block': self.block_a.id, 'tag_id': 'C-020', 'name': '', 'category': Cow.Category.COW,
                'gender': Cow.Gender.FEMALE, 'breed': '', 'date_of_birth': '', 'last_calving_date': '',
                'status': Cow.Status.ACTIVE,
            })
        self.assertEqual(Cow.objects.filter(farm=self.farm, tag_id='C-020').count(), 1)

    def test_bull_must_be_male(self):
        self._login(self.farmer)
        with patch('cows.views.mint_cow_nft', return_value=None):
            response = self.client.post('/cows/add/', {
                'block': self.block_a.id, 'tag_id': 'C-030', 'name': '', 'category': Cow.Category.BULL,
                'gender': Cow.Gender.FEMALE, 'breed': '', 'date_of_birth': '', 'last_calving_date': '',
                'status': Cow.Status.ACTIVE,
            })
        self.assertFalse(Cow.objects.filter(farm=self.farm, tag_id='C-030').exists())
        self.assertIn('gender', response.context['form'].errors)


class CowEditDeleteViewTests(CowsTestCase):
    def setUp(self):
        super().setUp()
        self.cow = self._make_cow(tag_id='C-040')

    def test_worker_cannot_edit(self):
        self._login(self.worker)
        self.client.post(f'/cows/{self.cow.id}/edit/', {
            'block': self.block_a.id, 'tag_id': 'C-040', 'name': 'Renamed', 'category': Cow.Category.COW,
            'gender': Cow.Gender.FEMALE, 'breed': '', 'date_of_birth': '', 'last_calving_date': '',
            'status': Cow.Status.ACTIVE,
        })
        self.cow.refresh_from_db()
        self.assertEqual(self.cow.name, '')

    def test_farmer_can_delete(self):
        self._login(self.farmer)
        self.client.post(f'/cows/{self.cow.id}/delete/')
        self.assertFalse(Cow.objects.filter(id=self.cow.id).exists())

    def test_worker_cannot_delete(self):
        self._login(self.worker)
        self.client.post(f'/cows/{self.cow.id}/delete/')
        self.assertTrue(Cow.objects.filter(id=self.cow.id).exists())


class CowTransferViewTests(CowsTestCase):
    def test_farmer_can_transfer_a_cow_between_blocks(self):
        cow = self._make_cow(tag_id='C-050', block=self.block_a)
        self._login(self.farmer)
        self.client.post(f'/cows/{cow.id}/transfer/', {'to_block': self.block_b.id, 'note': 'rebalancing'})
        cow.refresh_from_db()
        self.assertEqual(cow.block, self.block_b)
        self.assertEqual(cow.transfers.count(), 1)


class FeedingRecordViewTests(CowsTestCase):
    def test_worker_can_log_feeding_and_stock_is_drawn_down(self):
        cow1 = self._make_cow(tag_id='C-060', block=self.block_a)
        cow2 = self._make_cow(tag_id='C-061', block=self.block_a)
        self._login(self.worker)
        response = self.client.post('/cows/feeding/add/', {
            'block': self.block_a.id, 'date': '2026-01-05', 'session': 'AM',
            'dairy_meal_kg': '10.00', 'silage_hay_kg': '20.00',
            'cows': [cow1.id, cow2.id],
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        record = FeedingRecord.objects.get(farm=self.farm, block=self.block_a)
        self.assertEqual(record.cows_count, 2)
        self.assertEqual(record.allocations.count(), 2)
        for alloc in record.allocations.all():
            self.assertEqual(alloc.dairy_meal_kg, Decimal('5.00'))
            self.assertEqual(alloc.silage_hay_kg, Decimal('10.00'))

        dairy_item = InventoryItem.objects.get(farm=self.farm, name='Dairy Meal')
        self.assertEqual(dairy_item.current_stock, Decimal('-10.00'))
        silage_item = InventoryItem.objects.get(farm=self.farm, name='Silage/Hay')
        self.assertEqual(silage_item.current_stock, Decimal('-20.00'))

    def test_cow_from_a_different_block_is_rejected(self):
        cow_in_b = self._make_cow(tag_id='C-071', block=self.block_b)
        self._login(self.worker)
        response = self.client.post('/cows/feeding/add/', {
            'block': self.block_a.id, 'date': '2026-01-05', 'session': 'AM',
            'dairy_meal_kg': '10.00', 'silage_hay_kg': '20.00',
            'cows': [cow_in_b.id],
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(FeedingRecord.objects.filter(farm=self.farm).exists())


class MilkRecordViewTests(CowsTestCase):
    def test_worker_can_log_milk_and_stock_increases(self):
        cow = self._make_cow(tag_id='C-080')
        self._login(self.worker)
        response = self.client.post('/cows/milk/add/', {
            'cow': cow.id, 'date': '2026-01-05', 'liters': '12.5',
            'use_current_time': 'on',
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        record = MilkRecord.objects.get(farm=self.farm, cow=cow)
        self.assertEqual(record.liters, Decimal('12.50'))
        self.assertIsNotNone(record.stock_movement)
        milk_item = InventoryItem.objects.get(farm=self.farm, name='Milk')
        self.assertEqual(milk_item.current_stock, Decimal('12.50'))

    def test_editing_a_milk_record_reconciles_stock(self):
        cow = self._make_cow(tag_id='C-090')
        self._login(self.farmer)
        self.client.post('/cows/milk/add/', {
            'cow': cow.id, 'date': '2026-01-05', 'liters': '10.00', 'use_current_time': 'on',
        })
        record = MilkRecord.objects.get(farm=self.farm, cow=cow)
        self.client.post(f'/cows/milk/{record.id}/edit/', {
            'cow': cow.id, 'date': '2026-01-05', 'liters': '14.00', 'use_current_time': 'on',
        })
        milk_item = InventoryItem.objects.get(farm=self.farm, name='Milk')
        self.assertEqual(milk_item.current_stock, Decimal('14.00'))

    def test_liters_is_an_empty_field_with_a_placeholder_on_a_new_record(self):
        self._make_cow(tag_id='C-091')
        self._login(self.worker)
        response = self.client.get('/cows/milk/add/')
        liters = response.context['form']['liters']
        self.assertIsNone(liters.value())
        self.assertIn('placeholder="0"', str(liters))

    def test_duplicate_session_shows_a_form_error_instead_of_crashing(self):
        cow = self._make_cow(tag_id='C-092')
        self._login(self.worker)
        data = {
            'cow': cow.id, 'date': '2026-01-05', 'liters': '10.00', 'recorded_time': '06:30',
        }
        self.client.post('/cows/milk/add/', data)
        response = self.client.post('/cows/milk/add/', data)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].non_field_errors())
        self.assertEqual(MilkRecord.objects.filter(farm=self.farm, cow=cow).count(), 1)
        milk_item = InventoryItem.objects.get(farm=self.farm, name='Milk')
        self.assertEqual(milk_item.current_stock, Decimal('10.00'))

    def test_a_failed_save_rolls_back_and_shows_an_error(self):
        cow = self._make_cow(tag_id='C-093')
        self._login(self.worker)
        with patch('cows.views.record_milk_production', side_effect=RuntimeError('boom')):
            with self.assertLogs('cows.views', level='ERROR'):
                response = self.client.post('/cows/milk/add/', {
                    'cow': cow.id, 'date': '2026-01-05', 'liters': '10.00', 'use_current_time': 'on',
                })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form'].non_field_errors())
        self.assertFalse(MilkRecord.objects.filter(farm=self.farm, cow=cow).exists())

    def test_negative_liters_is_rejected(self):
        cow = self._make_cow(tag_id='C-094')
        self._login(self.worker)
        response = self.client.post('/cows/milk/add/', {
            'cow': cow.id, 'date': '2026-01-05', 'liters': '-3', 'use_current_time': 'on',
        })
        self.assertEqual(response.status_code, 200)
        self.assertFalse(MilkRecord.objects.filter(farm=self.farm, cow=cow).exists())

    def test_liters_above_the_15_liter_limit_is_rejected(self):
        cow = self._make_cow(tag_id='C-095')
        self._login(self.worker)
        response = self.client.post('/cows/milk/add/', {
            'cow': cow.id, 'date': '2026-01-05', 'liters': '15.01', 'use_current_time': 'on',
        })
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.context['form']['liters'].errors)
        self.assertFalse(MilkRecord.objects.filter(farm=self.farm, cow=cow).exists())

    def test_exactly_15_liters_is_accepted(self):
        cow = self._make_cow(tag_id='C-096')
        self._login(self.worker)
        self.client.post('/cows/milk/add/', {
            'cow': cow.id, 'date': '2026-01-05', 'liters': '15', 'use_current_time': 'on',
        })
        self.assertEqual(MilkRecord.objects.get(farm=self.farm, cow=cow).liters, Decimal('15.00'))

    def _log(self, cow, day, time, liters):
        return self.client.post('/cows/milk/add/', {
            'cow': cow.id, 'date': day, 'liters': liters, 'recorded_time': time,
        })

    def test_milk_page_shows_session_totals_for_today(self):
        from django.utils import timezone
        today = timezone.localdate().isoformat()
        cow_a, cow_b = self._make_cow(tag_id='C-201'), self._make_cow(tag_id='C-202')
        self._login(self.worker)
        self._log(cow_a, today, '06:00', '8.5')
        self._log(cow_b, today, '06:10', '7')
        self._log(cow_a, today, '12:30', '5')
        self._log(cow_a, '2026-01-05', '18:00', '9')  # another day - not counted
        totals = self.client.get('/cows/milk/').context['totals']
        by_key = {row['key']: row for row in totals['sessions']}
        self.assertEqual(by_key['AM']['liters'], Decimal('15.50'))
        self.assertEqual(by_key['NOON']['liters'], Decimal('5.00'))
        self.assertFalse(by_key['PM']['logged'])
        self.assertEqual(totals['total'], Decimal('20.50'))
        self.assertEqual(totals['logged_count'], 2)

    def test_milk_page_totals_can_be_shown_for_another_day(self):
        cow = self._make_cow(tag_id='C-203')
        self._login(self.worker)
        self._log(cow, '2026-01-05', '18:00', '9')
        response = self.client.get('/cows/milk/?date=2026-01-05')
        self.assertEqual(response.context['totals']['total'], Decimal('9.00'))
        self.assertFalse(response.context['totals_is_today'])

    def test_milk_page_ignores_a_bad_or_future_date(self):
        from django.utils import timezone
        self._make_cow(tag_id='C-204')
        self._login(self.worker)
        for value in ('not-a-date', '2999-01-01', ''):
            response = self.client.get('/cows/milk/', {'date': value})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.context['totals']['date'], timezone.localdate())

    def test_dashboard_milk_tile_shows_session_totals(self):
        from django.utils import timezone
        today = timezone.localdate().isoformat()
        cow = self._make_cow(tag_id='C-205')
        self._login(self.worker)
        self._log(cow, today, '06:00', '8.5')
        self._log(cow, today, '17:00', '6')
        response = self.client.get('/farm/')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.context['milk_today'], Decimal('14.50'))
        by_key = {row['key']: row for row in response.context['milk_totals']['sessions']}
        self.assertEqual(by_key['AM']['liters'], Decimal('8.50'))
        self.assertEqual(by_key['PM']['liters'], Decimal('6.00'))
        self.assertFalse(by_key['NOON']['logged'])

    def test_milk_page_lists_which_cows_were_milked_with_totals(self):
        from django.utils import timezone
        today = timezone.localdate().isoformat()
        cow_a, cow_b = self._make_cow(tag_id='C-301'), self._make_cow(tag_id='C-302')
        idle = self._make_cow(tag_id='C-303')
        self._login(self.worker)
        self._log(cow_a, today, '06:00', '8.5')
        self._log(cow_a, today, '17:00', '6')
        self._log(cow_b, today, '06:10', '7')
        response = self.client.get('/cows/milk/')
        breakdown = response.context['cow_breakdown']
        rows = {row['cow'].tag_id: row for row in breakdown['milked']}
        self.assertEqual(set(rows), {'C-301', 'C-302'})
        self.assertEqual(rows['C-301']['sessions'], [Decimal('8.50'), None, Decimal('6.00')])
        self.assertEqual(rows['C-301']['total'], Decimal('14.50'))
        self.assertEqual(rows['C-301']['category'], 'Cow')
        self.assertContains(response, 'Category')
        self.assertEqual(breakdown['session_totals'], [Decimal('15.50'), Decimal('0'), Decimal('6.00')])
        self.assertEqual(breakdown['total'], Decimal('21.50'))
        dry = self._make_cow(tag_id='C-306', status=Cow.Status.DRY)
        sold = self._make_cow(tag_id='C-307', status=Cow.Status.SOLD)
        bull = Cow.objects.create(
            farm=self.farm, block=self.block_a, tag_id='C-308',
            category=Cow.Category.BULL, gender=Cow.Gender.MALE,
        )
        not_milked = {
            cow.tag_id: cow.note for cow in self.client.get('/cows/milk/').context['cow_breakdown']['not_milked']
        }
        self.assertEqual(not_milked, {'C-303': '', 'C-306': 'Dry', 'C-308': 'Bull'})
        self.assertNotIn(sold.tag_id, not_milked)
        totals = response.context['totals']
        self.assertEqual(totals['cows_milked'], 2)
        self.assertEqual({row['key']: row['cows'] for row in totals['sessions']}, {'AM': 2, 'NOON': 0, 'PM': 1})
        self.assertContains(response, 'Cows milked')
        self.assertContains(response, 'C-303')

    def test_milk_page_with_nothing_milked(self):
        self._make_cow(tag_id='C-304')
        self._login(self.worker)
        response = self.client.get('/cows/milk/')
        self.assertContains(response, 'No cows were milked on this day.')
        self.assertEqual(response.context['cow_breakdown']['total'], Decimal('0'))

    def test_milk_page_renders_in_swahili(self):
        from django.utils import timezone
        cow = self._make_cow(tag_id='C-305')
        self._login(self.worker)
        self._log(cow, timezone.localdate().isoformat(), '06:00', '8')
        self.client.cookies['django_language'] = 'sw'
        self.assertEqual(self.client.get('/cows/milk/').status_code, 200)
        self.assertEqual(self.client.get('/farm/').status_code, 200)

    def test_worker_cannot_delete_a_milk_record(self):
        cow = self._make_cow(tag_id='C-100')
        self._login(self.farmer)
        self.client.post('/cows/milk/add/', {
            'cow': cow.id, 'date': '2026-01-05', 'liters': '10.00', 'use_current_time': 'on',
        })
        record = MilkRecord.objects.get(farm=self.farm, cow=cow)
        self._login(self.worker)
        self.client.post(f'/cows/milk/{record.id}/delete/')
        self.assertTrue(MilkRecord.objects.filter(id=record.id).exists())


class CowHealthRecordViewTests(CowsTestCase):
    def test_worker_can_log_a_health_record(self):
        cow = self._make_cow(tag_id='C-110')
        self._login(self.worker)
        response = self.client.post('/cows/health/add/', {
            'cow': cow.id, 'record_type': CowHealthRecord.RecordType.VACCINATION,
            'disease': '', 'description': 'FMD vaccine', 'date': '2026-01-05', 'next_due_date': '',
        }, follow=True)
        self.assertEqual(response.status_code, 200)
        record = CowHealthRecord.objects.get(farm=self.farm, cow=cow)
        self.assertEqual(record.recorded_by, self.worker)
        self.assertIsNone(record.disease)

    def test_health_record_can_link_a_dairy_disease(self):
        disease = DiseaseCatalog.objects.create(
            category=DiseaseCatalog.Category.DAIRY, name='Mastitis', affected='Dairy cattle',
            symptoms='x', prevention='x', treatment='x',
        )
        cow = self._make_cow(tag_id='C-111')
        self._login(self.farmer)
        self.client.post('/cows/health/add/', {
            'cow': cow.id, 'record_type': CowHealthRecord.RecordType.TREATMENT,
            'disease': disease.id, 'description': 'Antibiotic course', 'date': '2026-01-05', 'next_due_date': '',
        })
        record = CowHealthRecord.objects.get(farm=self.farm, cow=cow)
        self.assertEqual(record.disease, disease)

    def test_worker_cannot_delete_a_health_record(self):
        cow = self._make_cow(tag_id='C-112')
        record = CowHealthRecord.objects.create(
            farm=self.farm, cow=cow, record_type=CowHealthRecord.RecordType.CHECKUP,
            description='Routine checkup', date='2026-01-05', recorded_by=self.farmer,
        )
        self._login(self.worker)
        self.client.post(f'/cows/health/{record.id}/delete/')
        self.assertTrue(CowHealthRecord.objects.filter(id=record.id).exists())

    def test_farmer_can_delete_a_health_record(self):
        cow = self._make_cow(tag_id='C-113')
        record = CowHealthRecord.objects.create(
            farm=self.farm, cow=cow, record_type=CowHealthRecord.RecordType.CHECKUP,
            description='Routine checkup', date='2026-01-05', recorded_by=self.farmer,
        )
        self._login(self.farmer)
        self.client.post(f'/cows/health/{record.id}/delete/')
        self.assertFalse(CowHealthRecord.objects.filter(id=record.id).exists())


class EstimateWeightFromGirthTests(TestCase):
    def test_known_girth_gives_a_sane_estimate(self):
        # A ~178cm heart girth is typical for a mature dairy cow - the
        # girth-cubed formula should land in a plausible liveweight range.
        self.assertAlmostEqual(float(estimate_weight_from_girth(Decimal('178'))), 478, delta=15)


class CowWeightRecordViewTests(CowsTestCase):
    def test_weight_auto_estimated_from_heart_girth(self):
        cow = self._make_cow(tag_id='C-120')
        self._login(self.worker)
        self.client.post('/cows/weight/add/', {
            'cow': cow.id, 'date': '2026-01-05', 'method': CowWeightRecord.Method.TAPE,
            'heart_girth_cm': '178', 'weight_kg': '', 'body_condition_score': '', 'notes': '',
        })
        record = CowWeightRecord.objects.get(farm=self.farm, cow=cow)
        self.assertEqual(record.weight_kg, estimate_weight_from_girth(Decimal('178')))
        self.assertEqual(record.recorded_by, self.worker)

    def test_weight_required_without_a_girth_estimate(self):
        cow = self._make_cow(tag_id='C-121')
        self._login(self.worker)
        response = self.client.post('/cows/weight/add/', {
            'cow': cow.id, 'date': '2026-01-05', 'method': CowWeightRecord.Method.SCALE,
            'heart_girth_cm': '', 'weight_kg': '', 'body_condition_score': '', 'notes': '',
        })
        self.assertFalse(CowWeightRecord.objects.filter(farm=self.farm, cow=cow).exists())
        self.assertIn('weight_kg', response.context['form'].errors)

    def test_worker_cannot_delete_a_weight_record(self):
        cow = self._make_cow(tag_id='C-122')
        record = CowWeightRecord.objects.create(farm=self.farm, cow=cow, date='2026-01-05', weight_kg=Decimal('320'))
        self._login(self.worker)
        self.client.post(f'/cows/weight/{record.id}/delete/')
        self.assertTrue(CowWeightRecord.objects.filter(id=record.id).exists())


class ReproductiveEventViewTests(CowsTestCase):
    def test_calved_event_updates_cow_status_and_last_calving_date(self):
        cow = self._make_cow(tag_id='C-130', status=Cow.Status.DRY)
        self._make_cow(tag_id='C-130B')  # keeps the "add an active cow first" guard satisfied
        self._login(self.worker)
        self.client.post('/cows/reproduction/add/', {
            'cow': cow.id, 'event_type': ReproductiveEvent.EventType.CALVED, 'date': '2026-02-01',
            'sire': '', 'sire_name': '', 'notes': '',
        })
        cow.refresh_from_db()
        self.assertEqual(cow.status, Cow.Status.ACTIVE)
        self.assertEqual(str(cow.last_calving_date), '2026-02-01')

    def test_dry_off_event_sets_cow_status_dry(self):
        cow = self._make_cow(tag_id='C-131', status=Cow.Status.ACTIVE)
        self._login(self.worker)
        self.client.post('/cows/reproduction/add/', {
            'cow': cow.id, 'event_type': ReproductiveEvent.EventType.DRY_OFF, 'date': '2026-02-01',
            'sire': '', 'sire_name': '', 'notes': '',
        })
        cow.refresh_from_db()
        self.assertEqual(cow.status, Cow.Status.DRY)

    def test_worker_cannot_delete_a_reproductive_event(self):
        cow = self._make_cow(tag_id='C-132')
        record = ReproductiveEvent.objects.create(
            farm=self.farm, cow=cow, event_type=ReproductiveEvent.EventType.HEAT, date='2026-01-05',
        )
        self._login(self.worker)
        self.client.post(f'/cows/reproduction/{record.id}/delete/')
        self.assertTrue(ReproductiveEvent.objects.filter(id=record.id).exists())


class CowReproductiveHelperTests(CowsTestCase):
    def test_expected_calving_date_from_insemination(self):
        cow = self._make_cow(tag_id='C-140')
        ReproductiveEvent.objects.create(
            farm=self.farm, cow=cow, event_type=ReproductiveEvent.EventType.INSEMINATION, date='2026-01-01',
        )
        self.assertEqual(str(cow.expected_calving_date), '2026-10-11')
        self.assertEqual(str(cow.expected_dry_off_date), '2026-08-12')

    def test_expected_calving_date_clears_after_calving(self):
        cow = self._make_cow(tag_id='C-141')
        ReproductiveEvent.objects.create(
            farm=self.farm, cow=cow, event_type=ReproductiveEvent.EventType.INSEMINATION, date='2026-01-01',
        )
        ReproductiveEvent.objects.create(
            farm=self.farm, cow=cow, event_type=ReproductiveEvent.EventType.CALVED, date='2026-10-11',
        )
        self.assertIsNone(cow.expected_calving_date)
