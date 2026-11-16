from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils.translation import gettext_lazy as _


class InventoryItem(models.Model):
    class Category(models.TextChoices):
        FEED = 'feed', _('Feed')
        VETERINARY = 'veterinary', _('Veterinary & Medicine')
        EQUIPMENT = 'equipment', _('Equipment')
        PRODUCE = 'produce', _('Produce')
        OTHER = 'other', _('Other')

    class Unit(models.TextChoices):
        KG = 'kg', _('Kilograms')
        LITRES = 'l', _('Litres')
        BAGS = 'bags', _('Bags')
        PIECES = 'pcs', _('Pieces')
        BOXES = 'boxes', _('Boxes')

    farm = models.ForeignKey('farms.Farm', on_delete=models.CASCADE, related_name='inventory_items')
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=15, choices=Category.choices, default=Category.OTHER)
    unit = models.CharField(max_length=10, choices=Unit.choices, default=Unit.KG)
    current_stock = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0'))
    reorder_level = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('0'),
        help_text=_('Get a low-stock warning at or below this level. Leave at 0 to disable.')
    )
    added_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='added_inventory_items'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('farm', 'name')
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.farm.name})'

    @property
    def is_low_stock(self):
        return self.reorder_level > 0 and self.current_stock <= self.reorder_level


class StockMovement(models.Model):
    class MovementType(models.TextChoices):
        RESTOCK = 'in', _('Restock (in)')
        USAGE = 'out', _('Usage (out)')
        ADJUSTMENT = 'adjust', _('Correction')

    class UsedByGroup(models.TextChoices):
        CALVES = 'calves', _('Calves')
        STAFF = 'staff', _('Staff')
        HOME = 'home', _('Home')

    farm = models.ForeignKey('farms.Farm', on_delete=models.CASCADE, related_name='stock_movements')
    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name='movements')
    date = models.DateField()
    movement_type = models.CharField(max_length=10, choices=MovementType.choices)
    quantity = models.DecimalField(
        max_digits=10, decimal_places=2,
        help_text=_('For a correction, this is the new stock level. Otherwise the amount moved.')
    )
    stock_before = models.DecimalField(
        max_digits=10, decimal_places=2, default=Decimal('0'), editable=False,
        help_text=_('Snapshot of current_stock right before this movement was applied.')
    )
    note = models.CharField(max_length=255, blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='stock_movements'
    )
    used_by = models.ForeignKey(
        'farms.FarmMembership', null=True, blank=True,
        on_delete=models.SET_NULL, related_name='equipment_usage',
        help_text=_('Who used/consumed this (most relevant for equipment) - separate from '
                    'recorded_by, who logged the entry.')
    )
    # db_default (not just default): the database itself fills in '' when a
    # row is inserted without this column, so a deployment still running the
    # previous code keeps working after the migration has been applied.
    used_by_group = models.CharField(
        max_length=10, choices=UsedByGroup.choices, blank=True, db_default='',
        help_text=_('Who the stock went to, in general terms: the calves, the staff or the home.')
    )
    used_by_calves = models.ManyToManyField(
        'cows.Cow', blank=True, related_name='stock_usage',
        help_text=_('The individual calves, when used_by_group is Calves and they were picked out. '
                    'Empty means the calves in general.')
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-date', '-created_at']

    def __str__(self):
        return f'{self.item.name} - {self.get_movement_type_display()} - {self.quantity}'

    @property
    def used_by_display(self):
        """Who used this, for lists: "Calves: C-01, C-02" when individual
        calves were picked, otherwise the group (Calves / Staff / Home).
        Older entries that named one staff member still show that name."""
        if self.used_by_group == self.UsedByGroup.CALVES:
            # .all() so a prefetch_related('used_by_calves') on the list is used.
            tags = sorted(calf.tag_id for calf in self.used_by_calves.all())
            if tags:
                return f'{self.get_used_by_group_display()}: {", ".join(tags)}'
        if self.used_by_group:
            return self.get_used_by_group_display()
        if self.used_by_id:
            return self.used_by.user.get_short_name()
        return ''


class FeedComposition(models.Model):
    """Ingredient breakdown + crude protein % for a feed item (typically the
    auto-created 'Dairy Meal' item, see inventory.services.record_feed_usage)
    - entered by hand, or pre-filled from inventory.feed_reference's
    rule-based suggestion and then edited/confirmed. Used as a feature by
    the production analytics/prediction models (see analysis.ml)."""

    item = models.OneToOneField(InventoryItem, on_delete=models.CASCADE, related_name='composition')
    ingredients = models.JSONField(default=list, blank=True, help_text=_('List of {"name": ..., "percent": ...}.'))
    crude_protein_pct = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, help_text=_('Overall crude protein %, e.g. 16.0')
    )
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f'Composition for {self.item.name}'
