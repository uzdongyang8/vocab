import time

from django.core.management.base import BaseCommand

from words import services
from words.models import Profile, Word
from words.telegram import call, send

HELP = (
    "Commands:\n"
    "/link CODE – connect this chat to your website account (code is on the dashboard)\n"
    "/add word | translation | meaning | example – add a word (meaning and example optional)\n"
    "/words – show your latest words\n"
    "/quiz 20 or /quiz 30 – start a quiz"
)
STATE = {}  # chat_id -> running quiz (in memory; a bot restart cancels running quizzes)


def ask(chat, st):
    if st["i"] >= len(st["ids"]):
        STATE.pop(chat, None)
        return send(chat, f"Finished! Score: {st['score']}/{len(st['ids'])} 🎉")
    word = Word.objects.get(pk=st["ids"][st["i"]])
    st["q"], st["word"] = services.make_question(word, st["user"]), word.pk
    text = f"{st['i'] + 1}/{len(st['ids'])}\n\n{services.prompt_of(word, st['q']['kind'])}"
    if st["q"]["kind"] == "choice":
        kb = {"inline_keyboard": [[{"text": o, "callback_data": f"a:{st['i']}:{k}"}]
                                  for k, o in enumerate(st["q"]["options"])]}
        send(chat, text + "\n\nPick the translation:", kb)
    else:
        send(chat, text + "\n\n✍️ Type the word in the language you learn:")


def answer(chat, given):
    st = STATE[chat]
    word, kind = Word.objects.get(pk=st["word"]), st["q"]["kind"]
    ok = services.is_correct(word, kind, given)
    word.review(ok)
    st["score"] += ok
    st["i"] += 1
    send(chat, "✅ Correct!" if ok else f"❌ Right answer: {services.answer_of(word, kind)}")
    ask(chat, st)


def handle_message(chat, text):
    profile = Profile.objects.filter(telegram_id=chat).select_related("user").first()
    cmd, _, arg = text.partition(" ")
    cmd = cmd.split("@")[0].lower()
    if cmd == "/link":
        target = Profile.objects.filter(link_code=arg.strip().upper()).first()
        if not target:
            return send(chat, "Code not found. Copy it from your dashboard.")
        Profile.objects.filter(telegram_id=chat).update(telegram_id=None)
        target.telegram_id = chat
        target.save()
        return send(chat, f"Linked to {target.user.username} ✅\n\n{HELP}")
    if cmd in ("/start", "/help") or not profile:
        return send(chat, HELP if profile else "Welcome! Log in on the website, then send /link CODE here.")
    user = profile.user
    if cmd == "/add":
        parts = [p.strip() for p in arg.split("|")] + ["", ""]
        if len(parts) < 4 or not parts[0] or not parts[1]:
            return send(chat, "Format: /add word | translation | meaning | example")
        _, created = Word.objects.get_or_create(user=user, term=parts[0], defaults={
            "translation": parts[1], "meaning": parts[2], "example": parts[3]})
        return send(chat, f"Added “{parts[0]}” ✅" if created else "You already have this word.")
    if cmd == "/words":
        words = Word.objects.filter(user=user)[:20]
        return send(chat, "\n".join(f"{w.term} – {w.translation}" for w in words) or "No words yet. Use /add.")
    if cmd == "/quiz":
        ids = services.build_quiz(user, 30 if arg.strip() == "30" else 20)
        if not ids:
            return send(chat, "Add some words first with /add.")
        STATE[chat] = {"ids": ids, "i": 0, "score": 0, "user": user}
        return ask(chat, STATE[chat])
    st = STATE.get(chat)
    if st and st["q"]["kind"] == "type" and not text.startswith("/"):
        return answer(chat, text)
    send(chat, HELP)


def handle_update(u):
    cq = u.get("callback_query")
    if cq:
        call("answerCallbackQuery", callback_query_id=cq["id"])
        chat, st = cq["message"]["chat"]["id"], STATE.get(cq["message"]["chat"]["id"])
        _, i, k = cq["data"].split(":")
        if st and int(i) == st["i"] and st["q"]["kind"] == "choice":
            answer(chat, st["q"]["options"][int(k)])
        return
    m = u.get("message") or {}
    if m.get("text"):
        handle_message(m["chat"]["id"], m["text"].strip())


class Command(BaseCommand):
    help = "Run the Telegram bot (long polling). Needs TELEGRAM_BOT_TOKEN."

    def handle(self, *args, **opts):
        offset = None
        self.stdout.write("Bot started. Press Ctrl+C to stop.")
        while True:
            try:
                for u in call("getUpdates", offset=offset, timeout=30) or []:
                    offset = u["update_id"] + 1
                    handle_update(u)
            except Exception as e:  # keep the bot alive on network/API errors
                self.stderr.write(f"error: {e}")
                time.sleep(3)
