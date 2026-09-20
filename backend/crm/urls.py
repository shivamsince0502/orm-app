from django.urls import path

from crm import auth_views, views

urlpatterns = [
    # auth (open)
    path("auth/request-otp/", auth_views.request_otp),
    path("auth/verify-otp/", auth_views.verify_otp),
    path("auth/logout/", auth_views.logout),
    path("auth/me/", auth_views.me),
    # crm (cookie-session protected, except health)
    path("accounts/", views.accounts_list),
    path("accounts/<str:customer_id>/", views.account_detail),
    path("accounts/<str:customer_id>/interactions/", views.interaction_create),
    path("accounts/<str:customer_id>/draft/", views.draft),
    path("accounts/<str:customer_id>/send-email/", views.send_email),
    path("accounts/<str:customer_id>/actions/", views.action_apply),
    path("health/", views.health),
]
