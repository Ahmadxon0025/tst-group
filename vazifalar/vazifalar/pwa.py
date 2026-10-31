# CORE: reusable — "add to home screen": the app manifest and a minimal service worker (served from the site root,
# so its scope is the whole site). Nothing is cached offline: tasks must always be fresh from the server.
from django.http import HttpResponse, JsonResponse
from django.templatetags.static import static
from django.views.decorators.cache import cache_control

from config import values as cfg


@cache_control(max_age=3600)
def manifest(request):
    return JsonResponse({
        "name": cfg.PRODUCT_TITLE, "short_name": "Vazifalar", "lang": "uz",
        "start_url": "/", "scope": "/", "display": "standalone",
        "background_color": "#1F1F1F", "theme_color": "#26348B",
        "icons": [
            {"src": static("icons/icon-192.png"), "sizes": "192x192", "type": "image/png"},
            {"src": static("icons/icon-512.png"), "sizes": "512x512", "type": "image/png"},
            {"src": static("icons/maskable-512.png"), "sizes": "512x512", "type": "image/png", "purpose": "maskable"},
        ],
    }, content_type="application/manifest+json")


SW = """// TST Vazifalar — minimal service worker: makes the site installable; always goes to the network.
self.addEventListener('install', e => self.skipWaiting());
self.addEventListener('activate', e => e.waitUntil(self.clients.claim()));
self.addEventListener('fetch', () => {});
"""


@cache_control(max_age=0, no_cache=True)
def service_worker(request):
    resp = HttpResponse(SW, content_type="application/javascript")
    resp["Service-Worker-Allowed"] = "/"
    return resp
