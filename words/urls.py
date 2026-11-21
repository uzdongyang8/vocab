from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("register/", views.register, name="register"),
    path("add/", views.add_word, name="add_word"),
    path("words/", views.word_list, name="word_list"),
    path("words/<int:pk>/edit/", views.edit_word, name="edit_word"),
    path("words/<int:pk>/archive/", views.set_archived, {"value": True}, name="archive_word"),
    path("words/<int:pk>/unarchive/", views.set_archived, {"value": False}, name="unarchive_word"),
    path("words/<int:pk>/delete/", views.delete_word, name="delete_word"),
    path("quiz/", views.quiz_start, name="quiz_start"),
    path("quiz/play/", views.quiz, name="quiz"),
    path("telegram/webhook/", views.telegram_webhook),
]
