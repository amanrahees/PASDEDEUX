from django.urls import path

from .views import (
    DashboardSummaryView,
    LowStockView,
    ReturnModerationView,
    ReviewModerationView,
    SalesReportView,
)

urlpatterns = [
    path("dashboard/", DashboardSummaryView.as_view(), name="backoffice-dashboard"),
    path("sales/", SalesReportView.as_view(), name="backoffice-sales"),
    path("low-stock/", LowStockView.as_view(), name="backoffice-low-stock"),
    path(
        "returns/<uuid:pk>/moderate/",
        ReturnModerationView.as_view(),
        name="backoffice-return-moderate",
    ),
    path(
        "reviews/<uuid:pk>/moderate/",
        ReviewModerationView.as_view(),
        name="backoffice-review-moderate",
    ),
]
