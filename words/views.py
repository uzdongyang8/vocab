from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import UserCreationForm
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import services
from .forms import WordForm
from .models import Profile, Word


def register(request):
    form = UserCreationForm(request.POST or None)
    if form.is_valid():
        login(request, form.save())
        return redirect("dashboard")
    return render(request, "registration/register.html", {"form": form})


@login_required
def dashboard(request):
    qs = Word.objects.filter(user=request.user)
    return render(request, "dashboard.html", {
        "total": qs.count(),
        "due": qs.filter(next_review__lte=timezone.localdate()).count(),
        "mastered": qs.filter(stage__gte=5).count(),
        "profile": Profile.objects.get_or_create(user=request.user)[0],
    })


@login_required
def add_word(request):
    form = WordForm(request.POST or None)
    if form.is_valid():
        word = form.save(commit=False)
        word.user = request.user
        if Word.objects.filter(user=request.user, term__iexact=word.term).exists():
            form.add_error("term", "You already have this word.")
        else:
            word.save()
            messages.success(request, f"Added “{word.term}”.")
            return redirect("add_word")
    return render(request, "add_word.html", {"form": form})


@login_required
def word_list(request):
    return render(request, "word_list.html", {"words": Word.objects.filter(user=request.user)})


@login_required
@require_POST
def delete_word(request, pk):
    get_object_or_404(Word, pk=pk, user=request.user).delete()
    return redirect("word_list")


@login_required
def quiz_start(request):
    if request.method == "POST":
        size = 30 if request.POST.get("size") == "30" else 20
        ids = services.build_quiz(request.user, size)
        if not ids:
            messages.error(request, "Add some words first.")
            return redirect("add_word")
        request.session["quiz"] = {"ids": ids, "i": 0, "score": 0, "q": None, "fb": None}
        return redirect("quiz")
    return render(request, "quiz_start.html", {"count": Word.objects.filter(user=request.user).count()})


@login_required
def quiz(request):
    st = request.session.get("quiz")
    if not st:
        return redirect("quiz_start")
    if st["i"] >= len(st["ids"]):
        request.session.pop("quiz")
        return render(request, "quiz_result.html", {"score": st["score"], "total": len(st["ids"]), "fb": st["fb"]})
    word = get_object_or_404(Word, pk=st["ids"][st["i"]], user=request.user)
    if st["q"] is None:
        st["q"] = services.make_question(word, request.user)
    q = st["q"]
    if request.method == "POST":
        ok = services.is_correct(word, q["kind"], request.POST.get("answer", ""))
        word.review(ok)
        st.update(score=st["score"] + ok, i=st["i"] + 1, q=None,
                  fb={"ok": ok, "answer": services.answer_of(word, q["kind"])})
        request.session["quiz"] = st
        return redirect("quiz")
    fb, st["fb"] = st["fb"], None
    request.session["quiz"] = st
    return render(request, "quiz.html", {
        "q": q, "prompt": services.prompt_of(word, q["kind"]), "word": word,
        "n": st["i"] + 1, "total": len(st["ids"]), "fb": fb,
    })
