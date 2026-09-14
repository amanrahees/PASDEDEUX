from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from django.db.models import Count, F, Q, Sum
from django.db.models.functions import TruncDate
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date
from rest_framework import response
from rest_framework.exceptions import ValidationError
from rest_framework.generics import GenericAPIView, ListAPIView

from apps.catalog.models import Product, ProductStatus, ProductVariant
from apps.engagement.models import ProductReview, ReviewStatus
from apps.orders.models import (
    Order,
    OrderStatus,
    Refund,
    RefundStatus,
    ReturnRequest,
    ReturnStatus,
    Shipment,
)
from apps.orders.serializers import ReturnRequestSerializer
from apps.orders.tasks import process_return_refund

from .permissions import IsSuperuser
from .serializers import (
    BackofficeOrderSerializer,
    FulfillmentSerializer,
    ReturnModerationSerializer,
    ReviewModerationSerializer,
)

SALE_STATUSES = (
    OrderStatus.PAID,
    OrderStatus.PROCESSING,
    OrderStatus.SHIPPED,
    OrderStatus.DELIVERED,
)


def _low_stock_queryset():
    return (
        ProductVariant.objects.filter(
            is_active=True,
            product__status=ProductStatus.ACTIVE,
        )
        .annotate(available=F("stock_quantity") - F("reserved_quantity"))
        .filter(available__lte=settings.LOW_STOCK_THRESHOLD)
    )


class DashboardSummaryView(GenericAPIView):
    permission_classes = [IsSuperuser]

    def get(self, request):
        sales = Order.objects.filter(status__in=SALE_STATUSES).aggregate(
            orders=Count("id"), gross_sales=Sum("total")
        )
        refunded = Refund.objects.filter(status=RefundStatus.PROCESSED).aggregate(
            total=Sum("amount")
        )["total"]
        return response.Response(
            {
                "customers": get_user_model().objects.filter(is_staff=False).count(),
                "active_products": Product.objects.filter(status=ProductStatus.ACTIVE).count(),
                "orders": sales["orders"],
                "gross_sales": sales["gross_sales"] or 0,
                "refunds": refunded or 0,
                "pending_returns": ReturnRequest.objects.filter(
                    status=ReturnStatus.REQUESTED
                ).count(),
                "pending_reviews": ProductReview.objects.filter(
                    status=ReviewStatus.PENDING
                ).count(),
                "low_stock_variants": _low_stock_queryset().count(),
            }
        )


class SalesReportView(GenericAPIView):
    permission_classes = [IsSuperuser]

    def get(self, request):
        queryset = Order.objects.filter(status__in=SALE_STATUSES)
        for parameter, lookup in (
            ("date_from", "placed_at__date__gte"),
            ("date_to", "placed_at__date__lte"),
        ):
            value = request.query_params.get(parameter)
            if value:
                parsed = parse_date(value)
                if parsed is None:
                    raise ValidationError({parameter: "Use YYYY-MM-DD format."})
                queryset = queryset.filter(**{lookup: parsed})
        rows = (
            queryset.annotate(date=TruncDate("placed_at"))
            .values("date")
            .annotate(orders=Count("id"), gross_sales=Sum("total"))
            .order_by("date")
        )
        return response.Response(list(rows))


class BackofficeOrderListView(ListAPIView):
    permission_classes = [IsSuperuser]
    serializer_class = BackofficeOrderSerializer

    def get_queryset(self):
        queryset = Order.objects.select_related("user").prefetch_related(
            "items", "addresses", "payments", "shipments"
        )
        order_status = self.request.query_params.get("status")
        if order_status:
            if order_status not in OrderStatus.values:
                raise ValidationError({"status": "Unknown order status."})
            queryset = queryset.filter(status=order_status)
        search = self.request.query_params.get("search", "").strip()
        if search:
            queryset = queryset.filter(
                Q(order_number__icontains=search) | Q(user__email__icontains=search)
            )
        return queryset


class FulfillmentView(GenericAPIView):
    permission_classes = [IsSuperuser]
    serializer_class = FulfillmentSerializer

    @transaction.atomic
    def post(self, request, order_number):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = get_object_or_404(
            Order.objects.select_for_update().prefetch_related(
                "items", "addresses", "payments", "shipments"
            ),
            order_number=order_number,
        )
        target = serializer.validated_data["status"]
        allowed = {
            OrderStatus.PAID: OrderStatus.PROCESSING,
            OrderStatus.PROCESSING: OrderStatus.SHIPPED,
            OrderStatus.SHIPPED: OrderStatus.DELIVERED,
        }
        if allowed.get(order.status) != target:
            raise ValidationError(f"Order cannot move from {order.status} to {target}.")
        if target == OrderStatus.SHIPPED:
            try:
                Shipment.objects.create(
                    order=order,
                    carrier=serializer.validated_data["carrier"],
                    tracking_number=serializer.validated_data["tracking_number"],
                    shipped_at=timezone.now(),
                )
            except IntegrityError as error:
                raise ValidationError("That tracking number is already in use.") from error
        elif target == OrderStatus.DELIVERED:
            shipment = (
                order.shipments.filter(shipped_at__isnull=False).order_by("-shipped_at").first()
            )
            if shipment is None:
                raise ValidationError("A shipped order must have shipment details.")
            shipment.delivered_at = timezone.now()
            shipment.save(update_fields=["delivered_at", "updated_at"])
        order.status = target
        order.save(update_fields=["status", "updated_at"])
        order = (
            Order.objects.select_related("user")
            .prefetch_related("items", "addresses", "payments", "shipments")
            .get(pk=order.pk)
        )
        return response.Response(BackofficeOrderSerializer(order).data)


class LowStockView(GenericAPIView):
    permission_classes = [IsSuperuser]

    def get(self, request):
        rows = _low_stock_queryset().select_related("product").order_by("available")
        return response.Response(
            [
                {
                    "variant_id": variant.pk,
                    "product": variant.product.name,
                    "sku": variant.sku,
                    "stock_quantity": variant.stock_quantity,
                    "reserved_quantity": variant.reserved_quantity,
                    "available_quantity": variant.available,
                }
                for variant in rows
            ]
        )


class ReturnModerationView(GenericAPIView):
    permission_classes = [IsSuperuser]
    serializer_class = ReturnModerationSerializer

    @transaction.atomic
    def post(self, request, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return_request = get_object_or_404(
            ReturnRequest.objects.select_for_update().select_related("order", "order_item"),
            pk=pk,
        )
        if return_request.status != ReturnStatus.REQUESTED:
            raise ValidationError("Only requested returns can be moderated.")
        return_request.status = serializer.validated_data["status"]
        return_request.admin_note = serializer.validated_data.get("admin_note", "")
        fields = ["status", "admin_note", "updated_at"]
        if return_request.status == ReturnStatus.REJECTED:
            return_request.resolved_at = timezone.now()
            fields.append("resolved_at")
        return_request.save(update_fields=fields)
        if return_request.status == ReturnStatus.APPROVED:
            transaction.on_commit(lambda: process_return_refund.delay(str(return_request.pk)))
        return response.Response(ReturnRequestSerializer(return_request).data)


class ReviewModerationView(GenericAPIView):
    permission_classes = [IsSuperuser]
    serializer_class = ReviewModerationSerializer

    def post(self, request, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        review = get_object_or_404(ProductReview, pk=pk)
        review.status = serializer.validated_data["status"]
        review.save(update_fields=["status", "updated_at"])
        return response.Response({"id": review.pk, "status": review.status})
