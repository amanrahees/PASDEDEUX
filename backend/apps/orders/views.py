import json

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import decorators, response, status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.generics import GenericAPIView
from rest_framework.permissions import AllowAny

from apps.users.permissions import IsCustomer

from .models import Cart, CartItem, Order, Payment, PaymentStatus
from .razorpay import (
    RazorpayError,
    capture_payment,
    create_razorpay_order,
    record_webhook,
    verify_payment_signature,
    verify_webhook_signature,
)
from .serializers import (
    AddCartItemSerializer,
    CartItemSerializer,
    CartSerializer,
    CheckoutSerializer,
    OrderSerializer,
    RazorpayConfirmSerializer,
    RazorpayOrderSerializer,
    UpdateCartItemSerializer,
)
from .services import add_to_cart, cancel_order, checkout, set_cart_item_quantity


def _service_error(error):
    messages = getattr(error, "messages", [str(error)])
    return ValidationError({"detail": messages})


class CartView(GenericAPIView):
    serializer_class = CartSerializer
    permission_classes = [IsCustomer]

    def get(self, request):
        cart, _ = Cart.objects.get_or_create(user=request.user)
        cart = Cart.objects.prefetch_related("items__variant__product").get(pk=cart.pk)
        return response.Response(CartSerializer(cart).data)


class CartItemCollectionView(GenericAPIView):
    serializer_class = AddCartItemSerializer
    permission_classes = [IsCustomer]

    def post(self, request):
        serializer = AddCartItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            item = add_to_cart(
                user=request.user,
                variant_id=serializer.validated_data["variant"].pk,
                quantity=serializer.validated_data["quantity"],
            )
        except DjangoValidationError as error:
            raise _service_error(error) from error
        return response.Response(CartItemSerializer(item).data, status=status.HTTP_201_CREATED)


class CartItemDetailView(GenericAPIView):
    serializer_class = UpdateCartItemSerializer
    permission_classes = [IsCustomer]

    def patch(self, request, item_id):
        serializer = UpdateCartItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            item = set_cart_item_quantity(
                user=request.user,
                item_id=item_id,
                quantity=serializer.validated_data["quantity"],
            )
        except DjangoValidationError as error:
            raise _service_error(error) from error
        return response.Response(CartItemSerializer(item).data)

    def delete(self, request, item_id):
        item = get_object_or_404(CartItem, pk=item_id, cart__user=request.user)
        item.delete()
        return response.Response(status=status.HTTP_204_NO_CONTENT)


class CheckoutView(GenericAPIView):
    serializer_class = CheckoutSerializer
    permission_classes = [IsCustomer]

    def post(self, request):
        idempotency_key = request.headers.get("Idempotency-Key", "").strip()
        if not idempotency_key or len(idempotency_key) > 100:
            raise ValidationError(
                {"idempotency_key": "A valid Idempotency-Key header is required."}
            )
        serializer = CheckoutSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        try:
            order, created = checkout(
                user=request.user,
                shipping_address_id=serializer.validated_data["shipping_address"].pk,
                billing_address_id=serializer.validated_data["billing_address"].pk,
                idempotency_key=idempotency_key,
            )
        except DjangoValidationError as error:
            raise _service_error(error) from error
        order = Order.objects.prefetch_related("items", "addresses", "payments", "shipments").get(
            pk=order.pk
        )
        return response.Response(
            OrderSerializer(order).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )


class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = Order.objects.all()
    serializer_class = OrderSerializer
    permission_classes = [IsCustomer]
    lookup_field = "order_number"

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user).prefetch_related(
            "items", "addresses", "payments", "shipments"
        )

    @decorators.action(detail=True, methods=["post"])
    def cancel(self, request, order_number=None):
        try:
            order = cancel_order(order=self.get_object())
        except DjangoValidationError as error:
            raise _service_error(error) from error
        return response.Response(self.get_serializer(order).data)


class RazorpayOrderView(GenericAPIView):
    serializer_class = RazorpayOrderSerializer
    permission_classes = [IsCustomer]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        order = get_object_or_404(
            Order,
            user=request.user,
            order_number=serializer.validated_data["order_number"],
        )
        payment = order.payments.filter(status=PaymentStatus.PENDING).first()
        if payment is None:
            raise ValidationError({"detail": "No payable balance exists."})
        try:
            payment = create_razorpay_order(payment)
        except (RazorpayError, ImproperlyConfigured) as error:
            raise ValidationError({"detail": str(error)}) from error
        return response.Response(
            {
                "key_id": settings.RAZORPAY_KEY_ID,
                "razorpay_order_id": payment.provider_order_id,
                "amount": int(payment.amount * 100),
                "currency": payment.currency,
                "internal_order_number": order.order_number,
            }
        )


class RazorpayConfirmView(GenericAPIView):
    serializer_class = RazorpayConfirmSerializer
    permission_classes = [IsCustomer]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        payment = get_object_or_404(
            Payment,
            order__user=request.user,
            provider_order_id=data["razorpay_order_id"],
        )
        if not verify_payment_signature(
            order_id=payment.provider_order_id,
            payment_id=data["razorpay_payment_id"],
            signature=data["razorpay_signature"],
        ):
            raise ValidationError({"detail": "Invalid payment signature."})
        capture_payment(
            provider_order_id=payment.provider_order_id,
            provider_payment_id=data["razorpay_payment_id"],
        )
        return response.Response({"detail": "Payment confirmed."})


class RazorpayWebhookView(GenericAPIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        signature = request.headers.get("X-Razorpay-Signature", "")
        event_id = request.headers.get("X-Razorpay-Event-Id", "")
        if (
            not signature
            or not event_id
            or not verify_webhook_signature(raw_body=request.body, signature=signature)
        ):
            return response.Response(status=status.HTTP_400_BAD_REQUEST)
        try:
            payload = json.loads(request.body)
        except json.JSONDecodeError:
            return response.Response(status=status.HTTP_400_BAD_REQUEST)
        _, created = record_webhook(event_id=event_id, payload=payload)
        if created and payload.get("event") == "payment.captured":
            entity = payload["payload"]["payment"]["entity"]
            capture_payment(
                provider_order_id=entity["order_id"],
                provider_payment_id=entity["id"],
            )
        return response.Response(status=status.HTTP_200_OK)
