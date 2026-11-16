from django import forms
from django.utils.translation import gettext_lazy as _

from core.formhelpers import TailwindFormMixin, UniqueNamePerFarmMixin
from .models import InventoryItem, StockMovement


class InventoryItemForm(UniqueNamePerFarmMixin, TailwindFormMixin, forms.ModelForm):
    class Meta:
        model = InventoryItem
        fields = ['name', 'category', 'unit', 'current_stock', 'reorder_level']
        widgets = {
            'name': forms.TextInput(attrs={'placeholder': _('e.g. Dairy meal')}),
        }

    def __init__(self, *args, lock_stock=False, **kwargs):
        super().__init__(*args, **kwargs)
        if lock_stock:
            # Once an item exists, its stock only moves through logged
            # StockMovement entries, so the running total stays auditable.
            del self.fields['current_stock']


class CalfChoiceField(forms.ModelMultipleChoiceField):
    def label_from_instance(self, obj):
        return f'{obj.tag_id} \u00b7 {obj.name}' if obj.name else obj.tag_id


class CalfPickerMixin:
    """Adds the optional "Which calves?" tick-list to a form. The list is
    only relevant for one answer of another field (calves_trigger_field ==
    calves_trigger_value): templates/inventory/_calf_picker_script.html hides
    it otherwise, and clean() drops any ticks that came with a different
    answer so a stale selection is never saved."""

    calves_trigger_field = ''
    calves_trigger_value = ''

    def _setup_calf_picker(self, farm):
        from cows.models import Cow

        self.fields['calves'] = CalfChoiceField(
            queryset=Cow.objects.none(), required=False, widget=forms.CheckboxSelectMultiple,
            label=_('Which calves? (optional)'),
            help_text=_('Tick the calves it went to, or leave them all unticked for the calves in general.'),
        )
        if farm is not None:
            self.fields['calves'].queryset = farm.cows.filter(
                category=Cow.Category.CALF, status=Cow.Status.ACTIVE,
            ).order_by('tag_id')
        self.fields[self.calves_trigger_field].widget.attrs['data-calves-trigger'] = self.calves_trigger_value
        self.order_fields(self.field_order)

    def picked_calves(self):
        if self.cleaned_data.get(self.calves_trigger_field) != self.calves_trigger_value:
            return []
        return list(self.cleaned_data.get('calves') or [])


class StockMovementForm(CalfPickerMixin, TailwindFormMixin, forms.ModelForm):
    # Who the stock went to, in general terms - Calves, Staff or Home (see
    # StockMovement.UsedByGroup). A plain ChoiceField, deliberately not in
    # Meta.fields: save() below writes it to the model's used_by_group, and
    # the view saves the ticked calves once the movement has an id.
    used_by = forms.ChoiceField(required=False, label=_('Used by (optional)'), widget=forms.Select)

    calves_trigger_field = 'used_by'
    calves_trigger_value = StockMovement.UsedByGroup.CALVES.value

    class Meta:
        model = StockMovement
        fields = ['item', 'date', 'movement_type', 'quantity', 'note']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'note': forms.TextInput(attrs={'placeholder': _('Optional')}),
        }

    field_order = ['item', 'date', 'movement_type', 'quantity', 'used_by', 'calves', 'note']

    def __init__(self, *args, farm=None, **kwargs):
        super().__init__(*args, **kwargs)
        if farm is not None:
            self.fields['item'].queryset = farm.inventory_items.all()
        self.fields['used_by'].choices = [('', '---------')] + list(StockMovement.UsedByGroup.choices)
        self._setup_calf_picker(farm)

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.used_by_group = self.cleaned_data.get('used_by') or ''
        instance.used_by = None
        if commit:
            instance.save()
            instance.used_by_calves.set(self.picked_calves())
        return instance


class MilkUsageForm(CalfPickerMixin, TailwindFormMixin, forms.Form):
    PURPOSE_CHOICES = [
        ('calf', _('Calf feeding')),
        ('staff', _('Staff consumption')),
        ('home', _('Home consumption')),
        ('other', _('Other internal use')),
    ]
    # Which StockMovement.UsedByGroup each purpose is recorded under.
    PURPOSE_GROUPS = {
        'calf': StockMovement.UsedByGroup.CALVES,
        'staff': StockMovement.UsedByGroup.STAFF,
        'home': StockMovement.UsedByGroup.HOME,
    }

    calves_trigger_field = 'purpose'
    calves_trigger_value = 'calf'
    field_order = ['date', 'liters', 'purpose', 'calves', 'note']

    date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    liters = forms.DecimalField(max_digits=7, decimal_places=2, min_value=0.01, label=_('Liters used'))
    purpose = forms.ChoiceField(choices=PURPOSE_CHOICES)
    note = forms.CharField(required=False, widget=forms.TextInput(attrs={'placeholder': _('Optional')}))

    def __init__(self, *args, farm=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._setup_calf_picker(farm)
