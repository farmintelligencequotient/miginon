"""Django email backend that sends through ZeptoMail's HTTP API.

Why not SMTP: the API needs only an HTTPS call (no SMTP port/TLS handshake,
which is slower and more fragile from serverless functions) and one
credential, the agent's "Send Mail token". Enable it with

    EMAIL_BACKEND=core.zeptomail.ZeptoMailAPIEmailBackend
    ZEPTOMAIL_API_TOKEN=<Send Mail token from the agent's API tab>

ZEPTOMAIL_API_HOST defaults to api.zeptomail.com; use the regional host
(.eu, .in, .com.au, ...) if the account lives in another data centre.
Plain SMTP stays available by leaving EMAIL_BACKEND on the SMTP backend.
"""
import base64
import json
import logging
import urllib.error
import urllib.request
from email.utils import parseaddr

from django.conf import settings
from django.core.mail.backends.base import BaseEmailBackend

logger = logging.getLogger(__name__)

SEND_TIMEOUT_SECONDS = 15


class ZeptoMailError(Exception):
    """ZeptoMail rejected the request or could not be reached."""


def _address(value):
    name, addr = parseaddr(value)
    entry = {'address': addr}
    if name:
        entry['name'] = name
    return entry


def _recipients(values):
    return [{'email_address': _address(v)} for v in values]


class ZeptoMailAPIEmailBackend(BaseEmailBackend):
    def __init__(self, fail_silently=False, **kwargs):
        super().__init__(fail_silently=fail_silently, **kwargs)
        self.token = getattr(settings, 'ZEPTOMAIL_API_TOKEN', '')
        host = getattr(settings, 'ZEPTOMAIL_API_HOST', 'api.zeptomail.com')
        self.url = f'https://{host}/v1.1/email'

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
            'from': _address(message.from_email or settings.DEFAULT_FROM_EMAIL),
            'to': _recipients(message.to),
            'subject': message.subject,
        }
        if message.cc:
            payload['cc'] = _recipients(message.cc)
        if message.bcc:
            payload['bcc'] = _recipients(message.bcc)
        if message.reply_to:
            payload['reply_to'] = [_address(v) for v in message.reply_to]

        html = next((body for body, mimetype in getattr(message, 'alternatives', []) if mimetype == 'text/html'), None)
        if html is not None:
            payload['htmlbody'] = html
            if message.body:
                payload['textbody'] = message.body
        elif getattr(message, 'content_subtype', 'plain') == 'html':
            payload['htmlbody'] = message.body
        else:
            payload['textbody'] = message.body

        attachments = []
        for attachment in message.attachments:
            if isinstance(attachment, tuple):
                filename, content, mimetype = attachment
                if isinstance(content, str):
                    content = content.encode('utf-8')
                attachments.append({
                    'name': filename,
                    'mime_type': mimetype or 'application/octet-stream',
                    'content': base64.b64encode(content).decode('ascii'),
                })
        if attachments:
            payload['attachments'] = attachments
        return payload

    def _send(self, message):
        if not self.token:
            raise ZeptoMailError('ZEPTOMAIL_API_TOKEN is not set.')
        if not message.recipients():
            return
        request = urllib.request.Request(
            self.url,
            data=json.dumps(self._payload(message)).encode('utf-8'),
            method='POST',
            headers={
                'Authorization': f'Zoho-enczapikey {self.token}',
                'Content-Type': 'application/json',
                'Accept': 'application/json',
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=SEND_TIMEOUT_SECONDS) as response:
                response.read()
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode('utf-8', 'replace')[:500]
            logger.error('ZeptoMail API rejected the email (HTTP %s): %s', exc.code, detail)
            raise ZeptoMailError(f'ZeptoMail API error {exc.code}: {detail}') from exc
        except urllib.error.URLError as exc:
            logger.error('Could not reach ZeptoMail API: %s', exc.reason)
            raise ZeptoMailError(f'Could not reach ZeptoMail API: {exc.reason}') from exc
