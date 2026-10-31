from django.urls import include, path

from bot.views import telegram_page

urlpatterns = [
    path("telegram/", telegram_page, name="telegram"),
    path("", include("vazifalar.urls")),
    path("", include("accounts.urls")),
]
