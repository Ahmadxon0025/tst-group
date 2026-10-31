from django.urls import path

from vazifalar import views

urlpatterns = [
    path("", views.hafta, name="hafta"),
    path("mening/", views.mening, name="mening"),
    path("shtab/", views.shtab, name="shtab"),
    path("yozuv/", views.set_script, name="script"),
    path("vazifa/yangi/", views.create, name="create"),
    path("vazifa/<int:pk>/", views.detail, name="detail"),
    path("vazifa/<int:pk>/belgi/", views.toggle, name="toggle"),
    path("vazifa/<int:pk>/bekor/", views.cancel, name="cancel"),
    path("vazifa/<int:pk>/muddat/", views.due, name="due"),
    path("vazifa/<int:pk>/kimga/", views.kimga, name="kimga"),
    path("vazifa/<int:pk>/kompaniya/", views.kompaniya, name="kompaniya"),
    path("vazifa/<int:pk>/izoh/", views.comment, name="comment"),
    path("vazifa/<int:pk>/saqlash/", views.save, name="save"),
    path("vazifa/<int:pk>/kunga/", views.move, name="move"),
]
