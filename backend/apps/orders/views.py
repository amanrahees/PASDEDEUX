from django.core.exceptions import ValidationError as DjangoValidationError
from django.shortcuts import get_object_or_404
from rest_framework import decorators, response, status, viewsets
from rest_framework.exceptions import ValidationError
from rest_framework.views import APIView

from apps.users.permissions import IsCustomer

from .models import Cart, CartItem, Order
from .serializers import (
    AddCartItemSerializer,
    CartItemSerializer,
    CartSerializer,
    CheckoutSerializer,
    OrderSerializer,
    UpdateCartItemSerializer,
)
from .services import add_to_cart, cancel_order, checkout, set_cart_item_quantity


def _service_error(error):
    messages = getattr(error, "messages", [str(error)])
    return ValidationError({"detail": messages})


class CartView(APIView):
    permission_classes = [IsCustomer]

    def get(self, request):
        cart, _ = Cart.objects.get_or_create(user=request.user)
        cart = Cart.objects.prefetch_related("items__variant__product").get(pk=cart.pk)
        return response.Response(CartSerializer(cart).data)


class CartItemCollectionView(APIView):
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


class CartItemDetailView(APIView):
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


class CheckoutView(APIView):
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
