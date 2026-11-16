import logging

from django.conf import settings
from django.contrib import messages
from django.core.exceptions import BadRequest, PermissionDenied, SuspiciousOperation
from django.http import Http404
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import urlencode
from django.urls import Resolver404, resolve
from django.utils.translation import gettext as _

from .demo import is_demo_user

logger = logging.getLogger(__name__)

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


class ExceptionSafetyNetMiddleware:
    """The last line of defence for the whole app: any exception a view lets
    escape is logged with its traceback (so it's diagnosable in the server
    logs) and answered with FarmIQ's own "something went wrong" page - or a
    JSON error for fetch/API callers - instead of a bare server error.

    Deliberately answers with a real 500 rather than a redirect: the offline
    queue (static/js/offline-queue.js) treats a redirected response as "the
    record was saved" and would drop a queued record that actually failed.

    Left alone on purpose: Http404/PermissionDenied/bad-request errors
    (Django already turns those into 404/403/400 responses), and everything
    while DEBUG is on, so the developer still gets Django's debug page."""

    _HANDLED_BY_DJANGO = (Http404, PermissionDenied, SuspiciousOperation, BadRequest)

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        return self.get_response(request)

    def process_exception(self, request, exception):
        if settings.DEBUG or isinstance(exception, self._HANDLED_BY_DJANGO):
            return None
        user = getattr(request, 'user', None)
        logger.error(
            'Unhandled %s on %s %s (user=%s)',
            type(exception).__name__, request.method, request.get_full_path(),
            user if user is not None and user.is_authenticated else 'anonymous',
            exc_info=(type(exception), exception, exception.__traceback__),
        )
        from .views import server_error_response
        return server_error_response(request)
