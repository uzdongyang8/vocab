import requests
from django.conf import settings


def call(method, **params):
    url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/{method}"
    return requests.post(url, json=params, timeout=40).json().get("result")


def send(chat_id, text, markup=None):
    params = {"chat_id": chat_id, "text": text}
    if markup:
        params["reply_markup"] = markup
    return call("sendMessage", **params)
