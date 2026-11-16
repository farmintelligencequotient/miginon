from django import forms
from django.utils.translation import gettext_lazy as _

from core.formhelpers import TailwindFormMixin, UniqueNamePerFarmMixin
from farms.models import FarmMembership

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


class StockMovementForm(TailwindFormMixin, forms.ModelForm):
    # One "Used by" dropdown covering both kinds of user: an animal group
    # (Calves) or a staff member. It is a plain ChoiceField, deliberately not
    # in Meta.fields - save() below splits the answer into the model's
    # used_by_group / used_by columns.
    used_by = forms.ChoiceField(required=False, label=_('Used by (optional)'), widget=forms.Select)

    class Meta:
        model = StockMovement
        fields = ['item', 'date', 'movement_type', 'quantity', 'note']
        widgets = {
            'date': forms.DateInput(attrs={'type': 'date'}),
            'note': forms.TextInput(attrs={'placeholder': _('Optional')}),
        }

    field_order = ['item', 'date', 'movement_type', 'quantity', 'used_by', 'note']

    def __init__(self, *args, farm=None, **kwargs):
        super().__init__(*args, **kwargs)
        self._members = {}
        if farm is not None:
            self.fields['item'].queryset = farm.inventory_items.all()
            members = farm.memberships.filter(status=FarmMembership.Status.ACTIVE).select_related('user')
            self._members = {str(m.pk): m for m in members}
        staff = [
            (key, f'{m.user.get_full_name() or m.user.email} ({m.get_role_display()})')
            for key, m in self._members.items()
        ]
        choices = [('', '---------')]
        choices.append((_('Animals'), [(value, label) for value, label in StockMovement.UsedByGroup.choices]))
        if staff:
            choices.append((_('Staff'), staff))
        self.fields['used_by'].choices = choices
        if self.instance.pk:
            self.fields['used_by'].initial = self.instance.used_by_group or (
                str(self.instance.used_by_id) if self.instance.used_by_id else ''
            )

    def save(self, commit=True):
        instance = super().save(commit=False)
        choice = self.cleaned_data.get('used_by') or ''
        if choice in StockMovement.UsedByGroup.values:
            instance.used_by_group, instance.used_by = choice, None
        else:
            instance.used_by_group, instance.used_by = '', self._members.get(choice)
        if commit:
            instance.save()
        return instance


class MilkUsageForm(TailwindFormMixin, forms.Form):
    PURPOSE_CHOICES = [
        ('calf', _('Calf feeding')),
        ('staff', _('Staff consumption')),
        ('other', _('Other internal use')),
    ]

    date = forms.DateField(widget=forms.DateInput(attrs={'type': 'date'}))
    liters = forms.DecimalField(max_digits=7, decimal_places=2, min_value=0.01, label=_('Liters used'))
    purpose = forms.ChoiceField(choices=PURPOSE_CHOICES)
    used_by = forms.ModelChoiceField(
        queryset=FarmMembership.objects.none(), required=False, label=_('Staff member (if applicable)')
    )
    note = forms.CharField(
        required=False, widget=forms.TextInput(attrs={'placeholder': _('Optional, e.g. which calves')})
    )

    def __init__(self, *args, farm=None, **kwargs):
        super().__init__(*args, **kwargs)
        if farm is not None:
            self.fields['used_by'].queryset = farm.memberships.filter(
                status=FarmMembership.Status.ACTIVE
            ).select_related('user')
