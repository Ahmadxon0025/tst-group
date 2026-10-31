from django.urls import include, path

from bot.views import telegram_page
from vazifalar.pwa import manifest, service_worker

urlpatterns = [
    path("telegram/", telegram_page, name="telegram"),
    path("manifest.webmanifest", manifest, name="manifest"),
    path("sw.js", service_worker, name="sw"),
    path("", include("vazifalar.urls")),
    path("", include("accounts.urls")),
]
