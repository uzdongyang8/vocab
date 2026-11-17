from django import forms

from .models import Word


class WordForm(forms.ModelForm):
    class Meta:
        model = Word
        fields = ["term", "translation", "meaning", "example"]
        widgets = {"meaning": forms.Textarea(attrs={"rows": 2}), "example": forms.Textarea(attrs={"rows": 2})}
