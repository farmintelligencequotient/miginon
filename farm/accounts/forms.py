from django import forms
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext as _
from django.utils.translation import gettext_lazy as _l

from core.formhelpers import OTP_INPUT_CLASSES, TailwindFormMixin
from farms.forms import KenyaLocationFieldsMixin


class FarmCodeForm(TailwindFormMixin, forms.Form):
    code = forms.CharField(
        label=_l('Farm ID'),
        max_length=8,
        min_length=6,
        widget=forms.TextInput(attrs={
            'placeholder': 'e.g. GR7K9QAB',
            'class': 'w-full rounded-xl border border-stone-300 bg-white px-4 py-3 text-center '
                     'text-lg tracking-[0.3em] font-semibold uppercase text-stone-900 '
                     'placeholder-stone-400 focus:border-emerald-600 focus:ring-2 '
                     'focus:ring-emerald-100 focus:outline-none transition '
                     'dark:border-stone-600 dark:bg-stone-800 dark:text-stone-100 dark:placeholder-stone-500',
            'autocapitalize': 'characters',
        }),
    )

    def clean_code(self):
        return self.cleaned_data['code'].strip().upper()


class EmailLoginForm(TailwindFormMixin, forms.Form):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={'placeholder': 'you@example.com'})
    )

    def clean_email(self):
        return self.cleaned_data['email'].strip().lower()


class OTPForm(TailwindFormMixin, forms.Form):
    code = forms.CharField(
        label=_l('6-digit code'),
        max_length=6,
        min_length=6,
        widget=forms.TextInput(attrs={
            'placeholder': '000000',
            'class': OTP_INPUT_CLASSES,
            'inputmode': 'numeric',
            'autocomplete': 'one-time-code',
        }),
    )

    def clean_code(self):
        code = self.cleaned_data['code'].strip()
        if not code.isdigit():
            raise forms.ValidationError(_('Enter the 6-digit numeric code.'))
        return code


class TermsConsentForm(TailwindFormMixin, forms.Form):
    """Base for any form that asks the user to accept the Terms of Service and
    Privacy Policy (signup, and the re-acceptance prompt shown to existing
    users), so the wording, links and error message live in one place."""
    accept_terms = forms.BooleanField(
        required=True,
        error_messages={'required': _l('You must accept the Terms of Service and Privacy Policy to continue.')},
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['accept_terms'].label = format_html(
            _('I have read and agree to the <a href="{}" target="_blank" rel="noopener" class="font-bold text-emerald-700 underline dark:text-emerald-400">Terms of Service</a> '
              'and the <a href="{}" target="_blank" rel="noopener" class="font-bold text-emerald-700 underline dark:text-emerald-400">Privacy Policy</a>.'),
            reverse('core:terms'), reverse('core:privacy'),
        )


class SignupAccountForm(TermsConsentForm):
    first_name = forms.CharField(max_length=60)
    last_name = forms.CharField(max_length=60, required=False)
    email = forms.EmailField()
    phone = forms.CharField(max_length=20, required=False, widget=forms.TextInput(
        attrs={'placeholder': '07XX XXX XXX'}
    ))
    field_order = ['first_name', 'last_name', 'email', 'phone', 'accept_terms']

    def clean_email(self):
        from .models import User
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError(
                _('An account with this email already exists. Try logging in instead.')
            )
        return email


class SignupFarmForm(TailwindFormMixin, KenyaLocationFieldsMixin, forms.Form):
    farm_name = forms.CharField(label=_l('Farm name'), max_length=150, widget=forms.TextInput(
        attrs={'placeholder': 'e.g. Green Valley Dairy Farm'}
    ))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_location_fields()


class ProfileForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        from .models import User
        model = User
        fields = ['first_name', 'last_name', 'phone']
        widgets = {
            'phone': forms.TextInput(attrs={'placeholder': '07XX XXX XXX'}),
        }


class NotificationPreferenceForm(TailwindFormMixin, forms.ModelForm):
    class Meta:
        from .models import User
        model = User
        fields = ['notification_delivery', 'whatsapp_notifications_enabled', 'whatsapp_number']
        labels = {
            'notification_delivery': _l('Notify me via'),
            'whatsapp_notifications_enabled': _l('Also notify me on WhatsApp'),
            'whatsapp_number': _l('WhatsApp number'),
        }
        widgets = {
            'whatsapp_number': forms.TextInput(attrs={'placeholder': '+2547XXXXXXXX'}),
        }


class EmailChangeForm(TailwindFormMixin, forms.Form):
    new_email = forms.EmailField(label=_l('New email address'))

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.user = user

    def clean_new_email(self):
        from .models import User
        email = self.cleaned_data['new_email'].strip().lower()
        if self.user and email == self.user.email:
            raise forms.ValidationError(_('That is already your current email address.'))
        if User.objects.filter(email=email).exists():
            raise forms.ValidationError(_('An account with this email already exists.'))
        return email
