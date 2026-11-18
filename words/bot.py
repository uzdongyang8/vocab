from words import services
from words import telegram as tg
from words.models import BotState, Profile, Word

HELP = (
    "Commands:\n"
    "/link CODE – connect this chat to your website account (code is on the dashboard)\n"
    "/add word | translation | meaning | example – add a word (meaning and example optional)\n"
    "/words – show your latest words\n"
    "/quiz 20 or /quiz 30 – start a quiz"
)


def save(chat, st):
    BotState.objects.update_or_create(chat_id=chat, defaults={"data": st})


def ask(chat, user, st):
    while st["i"] < len(st["ids"]):
        word = Word.objects.filter(pk=st["ids"][st["i"]], user=user).first()
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
    if cmd == "/words":
        words = Word.objects.filter(user=user)[:20]
        return tg.send(chat, "\n".join(f"{w.term} – {w.translation}" for w in words) or "No words yet. Use /add.")
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
