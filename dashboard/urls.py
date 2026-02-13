from django.urls import path

from .views import dashboard


urlpatterns = [
    path('', dashboard, {"state_filter": "open"}, name="dashboard"),
    path('unresolved/', dashboard, {"state_filter": "unresolved"}, name="dashboard_unresolved"),
    path('resolved/', dashboard, {"state_filter": "resolved"}, name="dashboard_resolved"),
    path('muted/', dashboard, {"state_filter": "muted"}, name="dashboard_muted"),
    path('all/', dashboard, {"state_filter": "all"}, name="dashboard_all"),
]
