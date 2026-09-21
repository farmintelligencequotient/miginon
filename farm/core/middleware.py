from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import urlencode
from django.urls import Resolver404, resolve
from django.utils.translation import gettext as _

from .demo import is_demo_user

# The only views the demo account may still POST to: establishing a
# DIFFERENT identity (login/signup/logout) has to keep working while
# viewing the demo, and theme/language are harmless per-visitor prefs, not
# farm data. Everything else the demo account tries to mutate - its own
# fake account settings included - gets blocked below.
_ALWAYS_ALLOWED_VIEWS = {
    'accounts:login_farm', 'accounts:login_email', 'accounts:login_otp', 'accounts:resend_login_otp',
    'accounts:admin_login', 'accounts:admin_login_otp', 'accounts:resend_admin_otp',
    'accounts:logout',
    'accounts:signup_account', 'accounts:signup_farm', 'accounts:signup_review',
    'accounts:signup_otp', 'accounts:resend_signup_otp',
    'core:set_theme', 'core:set_language',
}


class DemoModeMiddleware:
    """Makes the public /demo/ walkthrough safe to leave open to anyone:
    the demo account (core.demo.DEMO_USER_EMAIL, only ever reachable via
    core.views.demo_login) can navigate every real page, but any unsafe
    request it makes - other than the auth/prefs views above - is bounced
    back with a message instead of reaching the view. A single
    cross-cutting check rather than touching every view in every app: the
    whole point of this demo is that it's the real, unmodified app."""

    UNSAFE_METHODS = {'POST', 'PUT', 'PATCH', 'DELETE'}

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method in self.UNSAFE_METHODS and is_demo_user(request.user):
            try:
                view_name = resolve(request.path_info).view_name
            except Resolver404:
                view_name = None
            if view_name not in _ALWAYS_ALLOWED_VIEWS:
                messages.info(request, _("This is a read-only demo - sign up for your own farm to save changes."))
                return redirect(request.META.get('HTTP_REFERER') or 'farms:dashboard')
        return self.get_response(request)


# Views a signed-in user can still reach before accepting: the acceptance page
# itself, the documents they're being asked to accept, and the basics needed to
# back out (log out), switch language/theme, and keep the PWA shell working.
_TERMS_EXEMPT_VIEWS = {
    'accounts:accept_terms', 'accounts:logout',
    'core:terms', 'core:privacy', 'core:set_theme', 'core:set_language', 'core:landing',
    'serviceworker', 'manifest', 'offline',
}


class TermsAcceptanceMiddleware:
    """Asks signed-in users to accept the current Terms of Service and Privacy
    Policy (settings.TERMS_VERSION) before they carry on. Covers accounts that
    predate acceptance being recorded, team members added by a farm owner,
    and every user again whenever the version is bumped. The read-only demo
    account is exempt - it isn't a real person's account."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if (
            settings.REQUIRE_TERMS_ACCEPTANCE
            and user.is_authenticated
            and not is_demo_user(user)
            and user.terms_version != settings.TERMS_VERSION
            and not request.path_info.startswith(('/static/', '/media/'))
        ):
            try:
                view_name = resolve(request.path_info).view_name
            except Resolver404:
                view_name = None
            if view_name not in _TERMS_EXEMPT_VIEWS:
                target = reverse('accounts:accept_terms')
                if request.method == 'GET':
                    target += '?' + urlencode({'next': request.get_full_path()})
                return redirect(target)
        return self.get_response(request)
