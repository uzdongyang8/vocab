import time

import requests
from django.conf import settings
from requests.exceptions import ConnectionError, Timeout


def _proxies():
    p = settings.TELEGRAM_PROXY
    if p.lower() == "none":
        return {"http": None, "https": None}
    return {"http": p, "https": p} if p else None


def call(method, **params):
    """Call the Telegram API; retries when the proxy/network fails (e.g. 503 tunnel errors)."""
    if not settings.TELEGRAM_BOT_TOKEN:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is not set")
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/{method}"
    for attempt in range(4):
        try:
            data = requests.post(url, json=params, timeout=params.get("timeout", 0) + 15,
                                 proxies=_proxies()).json()
            break
        except (ConnectionError, Timeout):
            if attempt == 3:
                raise
            time.sleep(1.5 * (attempt + 1))
    if not data.get("ok"):
        raise RuntimeError(data.get("description", "Telegram API error"))
    return data["result"]


def send(chat_id, text, markup=None):
    params = {"chat_id": chat_id, "text": text}
    if markup:
        params["reply_markup"] = markup
    return call("sendMessage", **params)
