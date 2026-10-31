from django.urls import path

from accounts import views

urlpatterns = [
    path("kirish/", views.login_view, name="login"),
    path("chiqish/", views.logout_view, name="logout"),
    path("parol/", views.password_view, name="password"),
]
