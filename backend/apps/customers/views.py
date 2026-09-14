from rest_framework import decorators, response, viewsets
from rest_framework.generics import RetrieveUpdateAPIView

from apps.users.permissions import IsCustomer

from .models import Address, CustomerProfile
from .serializers import AddressSerializer, CustomerProfileSerializer


class CustomerProfileView(RetrieveUpdateAPIView):
    serializer_class = CustomerProfileSerializer
    permission_classes = [IsCustomer]

    def get_object(self):
        return CustomerProfile.objects.select_related("user").get(user=self.request.user)


class AddressViewSet(viewsets.ModelViewSet):
    queryset = Address.objects.all()
    serializer_class = AddressSerializer
    permission_classes = [IsCustomer]

    def get_queryset(self):
        return Address.objects.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)

    @decorators.action(detail=True, methods=["post"])
    def default_shipping(self, request, pk=None):
        address = self.get_object()
        address.make_default_shipping()
        return response.Response(self.get_serializer(address).data)

    @decorators.action(detail=True, methods=["post"])
    def default_billing(self, request, pk=None):
        address = self.get_object()
        address.make_default_billing()
        return response.Response(self.get_serializer(address).data)
