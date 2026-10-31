"""
bot/api.py — the only code that talks to api.telegram.org.
# CORE: reusable — stdlib only; the token comes from settings (env TST_BOT_TOKEN), never from code or chat.
Tests replace `call` with a fake. A failure never raises into the caller; the text is never logged.
"""
import json
import logging
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)
TIMEOUT = 35


def has_token() -> bool:
    return bool((getattr(settings, "TST_BOT_TOKEN", "") or "").strip())


def call(method: str, **payload):  # CORE: reusable — returns Telegram's "result" or None
    token = (getattr(settings, "TST_BOT_TOKEN", "") or "").strip()
    if not token:
        logger.info("bot: no token — %s skipped", method)
        return None
    req = urllib.request.Request(
        f"https://api.telegram.org/bot{token}/{method}",
        data=json.dumps(payload).encode(), headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = json.loads(resp.read().decode())
            return body.get("result") if body.get("ok") else None
    except urllib.error.HTTPError as e:
        logger.warning("bot: %s failed with HTTP %s", method, e.code)
        raise SendError(f"HTTP {e.code}")
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        logger.warning("bot: %s network error %s", method, type(e).__name__)
        raise SendError(type(e).__name__)


class SendError(Exception):
    pass


def send_document(chat_id: int, path: str, caption: str = ""):  # CORE: reusable — multipart upload, stdlib only
    import os
    import uuid
    token = (getattr(settings, "TST_BOT_TOKEN", "") or "").strip()
    if not token:
        return None
    boundary = uuid.uuid4().hex
    with open(path, "rb") as f:
        data = f.read()
    parts = []
    for name, value in (("chat_id", str(chat_id)), ("caption", caption)):
        parts.append(f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{value}\r\n".encode())
    fname = os.path.basename(path)
    parts.append((f"--{boundary}\r\nContent-Disposition: form-data; name=\"document\"; filename=\"{fname}\"\r\n"
                  "Content-Type: application/gzip\r\n\r\n").encode() + data + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    req = urllib.request.Request(f"https://api.telegram.org/bot{token}/sendDocument", data=b"".join(parts),
                                 headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode())
            return body.get("result") if body.get("ok") else None
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        logger.warning("bot: sendDocument failed %s", type(e).__name__)
        raise SendError(type(e).__name__)
