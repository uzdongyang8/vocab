from django.utils import timezone

from words import services
from words import telegram as tg
from words.models import BotState, Profile, Word

HELP = (
    "Commands:\n"
    "/link CODE – connect this chat to your website account (code is on the dashboard)\n"
    "/add word | translation | meaning | example – add a word (meaning and example optional)\n"
    "/edit word | translation | meaning | example – change a word (empty = keep, - = clear meaning/example)\n"
    "/words – show your latest words\n"
    "/archive word – hide a word from quizzes; /unarchive word – bring it back\n"
    "/search text – find words (in word, translation, meaning or example)\n"
    "/quiz 20 or /quiz 30 – start a quiz"
)


def label(w):
    return ("🗄 " if w.archived else "") + f"{w.term} – {w.translation}"


def save(chat, st):
    BotState.objects.update_or_create(chat_id=chat, defaults={"data": st})


def ask(chat, user, st):
    while st["i"] < len(st["ids"]):
        word = Word.objects.filter(pk=st["ids"][st["i"]], user=user, archived=False).first()
        if word:
            break
        st["i"] += 1  # word was deleted meanwhile
    else:
        BotState.objects.filter(chat_id=chat).delete()
        return tg.send(chat, f"Finished! Score: {st['score']}/{len(st['ids'])} 🎉")
    st["q"], st["word"] = services.make_question(word, user), word.pk
    save(chat, st)
    text = f"{st['i'] + 1}/{len(st['ids'])}\n\n{services.prompt_of(word, st['q']['kind'])}"
    if st["q"]["kind"] == "choice":
        kb = {"inline_keyboard": [[{"text": o, "callback_data": f"a:{st['i']}:{k}"}]
                                  for k, o in enumerate(st["q"]["options"])]}
        tg.send(chat, text + "\n\nPick the translation:", kb)
    else:
        tg.send(chat, text + "\n\n✍️ Type the word in the language you learn:")


def answer(chat, user, st, given):
    word, kind = Word.objects.get(pk=st["word"], user=user), st["q"]["kind"]
    ok = services.is_correct(word, kind, given)
    word.review(ok)
    st["score"] += ok
    st["i"] += 1
    tg.send(chat, "✅ Correct!" if ok else f"❌ Right answer: {services.answer_of(word, kind)}")
    ask(chat, user, st)


def handle_message(chat, text):
    profile = Profile.objects.filter(telegram_id=chat).select_related("user").first()
    cmd, _, arg = text.partition(" ")
    cmd = cmd.split("@")[0].lower()
    if cmd == "/link":
        target = Profile.objects.filter(link_code=arg.strip().upper()).first()
        if not target:
            return tg.send(chat, "Code not found. Copy it from your dashboard.")
        Profile.objects.filter(telegram_id=chat).update(telegram_id=None)
        target.telegram_id = chat
        target.save()
        return tg.send(chat, f"Linked to {target.user.username} ✅\n\n{HELP}")
    if not profile:
        return tg.send(chat, "Welcome! Log in on the website, then send /link CODE here.")
    user = profile.user
    if cmd in ("/start", "/help"):
        return tg.send(chat, HELP)
    if cmd == "/add":
        parts = [p.strip() for p in arg.split("|")] + ["", ""]
        if not parts[0] or not parts[1]:
            return tg.send(chat, "Format: /add word | translation | meaning | example")
        _, created = Word.objects.get_or_create(user=user, term=parts[0], defaults={
            "translation": parts[1], "meaning": parts[2], "example": parts[3]})
        return tg.send(chat, f"Added “{parts[0]}” ✅" if created else "You already have this word.")
    if cmd == "/edit":
        parts = [p.strip() for p in arg.split("|")] + ["", "", ""]
        word = Word.objects.filter(user=user, term__iexact=parts[0]).first() if parts[0] else None
        if not word:
            return tg.send(chat, "Format: /edit word | translation | meaning | example\n"
                                 "Word must already exist. Empty part = keep, - = clear meaning/example.")
        for field, val in zip(("translation", "meaning", "example"), parts[1:4]):
            if not val:
                continue
            if val == "-":
                if field == "translation":
                    continue
                val = ""
            setattr(word, field, val)
        word.save()
        return tg.send(chat, f"Updated “{word.term}” ✅")
    if cmd in ("/archive", "/unarchive"):
        word = Word.objects.filter(user=user, term__iexact=arg.strip()).first() if arg.strip() else None
        if not word:
            return tg.send(chat, f"Format: {cmd} word (the word must already exist)")
        word.archived = cmd == "/archive"
        word.save(update_fields=["archived"])
        return tg.send(chat, f"{'Archived' if word.archived else 'Restored'} “{word.term}” ✅")
    if cmd == "/search":
        if not arg.strip():
            return tg.send(chat, "Format: /search text")
        found = services.search_words(user, arg)
        if not found:
            return tg.send(chat, f"No words match “{arg.strip()}”.")
        more = f"\n… and {len(found) - 20} more" if len(found) > 20 else ""
        return tg.send(chat, f"🔎 {len(found)} found\n\n" + "\n".join(label(w) for w in found[:20]) + more)
    if cmd == "/words":
        active = Word.objects.filter(user=user, archived=False)
        total, archived = active.count(), Word.objects.filter(user=user, archived=True).count()
        if not total and not archived:
            return tg.send(chat, "No words yet. Use /add.")
        due = active.filter(next_review__lte=timezone.localdate()).count()
        head = f"📚 {total} words ({due} due today" + (f", {archived} archived)" if archived else ")")
        more = f"\n… and {total - 20} more" if total > 20 else ""
        return tg.send(chat, head + "\n\n" + "\n".join(label(w) for w in active[:20]) + more)
    if cmd == "/quiz":
        ids = services.build_quiz(user, 30 if arg.strip() == "30" else 20)
        if not ids:
            return tg.send(chat, "Add some words first with /add.")
        return ask(chat, user, {"ids": ids, "i": 0, "score": 0, "q": None, "word": None})
    state = BotState.objects.filter(chat_id=chat).first()
    if state and state.data["q"]["kind"] == "type" and not text.startswith("/"):
        return answer(chat, user, state.data, text)
    tg.send(chat, HELP)


def handle_update(u):
    cq = u.get("callback_query")
    if cq:
        tg.call("answerCallbackQuery", callback_query_id=cq["id"])
        chat = cq["message"]["chat"]["id"]
        state = BotState.objects.filter(chat_id=chat).first()
        profile = Profile.objects.filter(telegram_id=chat).select_related("user").first()
        _, i, k = cq["data"].split(":")
        if state and profile and int(i) == state.data["i"] and state.data["q"]["kind"] == "choice":
            answer(chat, profile.user, state.data, state.data["q"]["options"][int(k)])
        return
    m = u.get("message") or {}
    if m.get("text"):
        handle_message(m["chat"]["id"], m["text"].strip())
