from django import forms
from django.utils.translation import gettext

INPUT_CLASSES = (
    'w-full rounded-xl border border-stone-300 bg-white px-4 py-3 text-sm '
    'text-stone-900 placeholder-stone-400 focus:border-emerald-600 '
    'focus:ring-2 focus:ring-emerald-100 focus:outline-none transition'
)
SELECT_CLASSES = INPUT_CLASSES
# Checkboxes render as sliding toggle switches (see partials/form_fields.html):
# the real <input> stays in the DOM for forms/JS but is visually hidden, and the
# sibling track span reacts to it via Tailwind's `peer-checked:` variants.
CHECKBOX_CLASSES = 'peer sr-only'
OTP_INPUT_CLASSES = (
    'w-full rounded-xl border border-stone-300 bg-white px-4 py-3 text-center '
    'text-2xl tracking-[0.6em] font-semibold text-stone-900 '
    'focus:border-emerald-600 focus:ring-2 focus:ring-emerald-100 focus:outline-none transition'
)


class TailwindFormMixin:
    """Applies consistent Tailwind classes to every field automatically so
    individual forms don't need to repeat widget attrs."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs.setdefault('class', CHECKBOX_CLASSES)
            elif isinstance(widget, forms.Select):
                widget.attrs.setdefault('class', SELECT_CLASSES)
            else:
                widget.attrs.setdefault('class', INPUT_CLASSES)
            widget.attrs.setdefault('autocomplete', 'off')


class UniqueNamePerFarmMixin:
    """For ModelForms on a model with unique_together = ('farm', 'name')
    where 'farm' isn't a form field (the view sets it after is_valid()).
    ModelForm's own uniqueness validation skips any constraint that involves
    an excluded field, so without this a duplicate name surfaces as a raw
    IntegrityError at save() instead of a form error. Pass farm=... when
    creating; when editing, the instance's own farm is used."""

    def __init__(self, *args, farm=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.farm = farm

    def clean_name(self):
        name = self.cleaned_data['name'].strip()
        farm_id = self.farm.pk if self.farm is not None else self.instance.farm_id
        if farm_id is not None:
            existing = self._meta.model.objects.filter(farm_id=farm_id, name=name)
            if self.instance.pk:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise forms.ValidationError(
                    gettext('"%(name)s" already exists on this farm. Pick a different name.') % {'name': name}
                )
        return name
