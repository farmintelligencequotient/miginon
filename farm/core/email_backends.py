"""Email backend that tries several providers in order.

    EMAIL_BACKEND=core.email_backends.FallbackEmailBackend
    EMAIL_FALLBACK_BACKENDS=core.resend_backend.ResendEmailBackend,core.zeptomail.ZeptoMailAPIEmailBackend

Each message goes to the first backend; if that raises (provider down, key
revoked, credits exhausted, domain not verified, ...) the next one is tried.
Only when every backend fails does the error surface, so callers such as OTP
delivery still fail loudly instead of silently dropping the email.
"""
import logging

from django.conf import settings
from django.core.mail import get_connection
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

DEFAULT_CHAIN = [
    'core.resend_backend.ResendEmailBackend',
    'core.zeptomail.ZeptoMailAPIEmailBackend',
]


class FallbackEmailBackend(BaseEmailBackend):
    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.chain = list(getattr(settings, 'EMAIL_FALLBACK_BACKENDS', None) or DEFAULT_CHAIN)

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        sent = 0
        for message in email_messages:
            try:
                self._send_one(message)
                sent += 1
            except Exception:
                if not self.fail_silently:
                    raise
        return sent

    def _send_one(self, message):
        last_error = None
        for path in self.chain:
            try:
                connection = get_connection(path, fail_silently=False)
                if connection.send_messages([message]):
                    return
                last_error = RuntimeError(f'{path} did not send the message')
            except Exception as exc:
                last_error = exc
                logger.warning('Email backend %s failed (%s); trying the next provider.', path, exc)
        logger.error('All email providers failed for "%s".', message.subject)
        raise last_error
