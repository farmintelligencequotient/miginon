"""Django email backend that sends through the Resend HTTP API.

Enable it with

    EMAIL_BACKEND=core.resend_backend.ResendEmailBackend
    RESEND_API_KEY=<API key from resend.com/api-keys>

The sender address (DEFAULT_FROM_EMAIL) must belong to a domain verified in
Resend. Plain SMTP stays available by pointing EMAIL_BACKEND back at Django's
SMTP backend.
"""
import base64
import json
import logging
import urllib.error
import urllib.request

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

SEND_TIMEOUT_SECONDS = 15
API_URL = 'https://api.resend.com/emails'


class ResendError(Exception):
    """Resend rejected the request or could not be reached."""


class ResendEmailBackend(BaseEmailBackend):
    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.api_key = getattr(settings, 'RESEND_API_KEY', '')

    def send_messages(self, email_messages):
        if not email_messages:
            return 0
        sent = 0
        for message in email_messages:
            try:
                self._send(message)
                sent += 1
            except Exception:
                if not self.fail_silently:
                    raise
        return sent

    def _payload(self, message):
        payload = {
            'from': message.from_email or settings.DEFAULT_FROM_EMAIL,
            'to': list(message.to),
            'subject': message.subject,
        }
        if message.cc:
            payload['cc'] = list(message.cc)
        if message.bcc:
            payload['bcc'] = list(message.bcc)
        if message.reply_to:
            payload['reply_to'] = list(message.reply_to)

        html = next((body for body, mimetype in getattr(message, 'alternatives', []) if mimetype == 'text/html'), None)
        if html is not None:
            payload['html'] = html
            if message.body:
                payload['text'] = message.body
        elif getattr(message, 'content_subtype', 'plain') == 'html':
            payload['html'] = message.body
        else:
            payload['text'] = message.body

        attachments = []
        for attachment in message.attachments:
            if isinstance(attachment, tuple):
                filename, content, _mimetype = attachment
                if isinstance(content, str):
                    content = content.encode('utf-8')
                attachments.append({'filename': filename, 'content': base64.b64encode(content).decode('ascii')})
        if attachments:
            payload['attachments'] = attachments
        return payload

    def _send(self, message):
        if not self.api_key:
            raise ResendError('RESEND_API_KEY is not set.')
        if not message.recipients():
            return
        request = urllib.request.Request(
            API_URL,
            data=json.dumps(self._payload(message)).encode('utf-8'),
            method='POST',
            headers={
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                # Resend sits behind Cloudflare, which blocks urllib's default User-Agent.
                'User-Agent': 'FarmIQ/1.0 (+https://www.farmiq.solutions)',
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=SEND_TIMEOUT_SECONDS) as response:
                response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode('utf-8', 'replace')[:500]
            logger.error('Resend rejected the email (HTTP %s): %s', exc.code, detail)
            raise ResendError(f'Resend API error {exc.code}: {detail}') from exc
        except urllib.error.URLError as exc:
            logger.error('Could not reach Resend: %s', exc.reason)
            raise ResendError(f'Could not reach Resend: {exc.reason}') from exc
