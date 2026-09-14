from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APIClient

from apps.catalog.models import Category, Product, ProductStatus, ProductType, ProductVariant
from apps.customers.models import CustomerProfile

from ..models import ProductReview, RecentlyViewedProduct, ReviewStatus, WishlistItem


@pytest.fixture
def customer(db):
    user = get_user_model().objects.create_user(
        email="shopper@example.com", password="SafePassword!493", is_active=True
    )
    CustomerProfile.objects.create(user=user)
    return user


@pytest.fixture
def product(db):
    category = Category.objects.create(name="Shoes", slug="shoes")
    item = Product.objects.create(
        category=category,
        name="Everyday Sneaker",
        slug="everyday-sneaker",
        description="Comfortable sneaker.",
        product_type=ProductType.SHOES,
        base_price=Decimal("2499.00"),
        status=ProductStatus.ACTIVE,
    )
    ProductVariant.objects.create(
        product=item,
        sku="SNEAKER-WHT-42",
        name="White / 42",
        stock_quantity=10,
    )
    return item


@pytest.fixture
def client(customer):
    api_client = APIClient()
    api_client.force_authenticate(customer)
    return api_client


@pytest.mark.django_db
def test_customer_can_manage_wishlist(client, customer, product):
    created = client.post(reverse("wishlist"), {"product_id": str(product.pk)}, format="json")
    duplicate = client.post(reverse("wishlist"), {"product_id": str(product.pk)}, format="json")
    listed = client.get(reverse("wishlist"))
    removed = client.delete(reverse("wishlist-item", kwargs={"product_id": product.pk}))

    assert created.status_code == 201
    assert duplicate.status_code == 400
    assert listed.data["results"][0]["product"]["slug"] == product.slug
    assert removed.status_code == 204
    assert not WishlistItem.objects.filter(user=customer).exists()


@pytest.mark.django_db
def test_product_detail_records_recent_views(client, customer, product):
    for _ in range(2):
        response = client.get(reverse("product-detail", kwargs={"slug": product.slug}))
        assert response.status_code == 200

    recent = client.get(reverse("recently-viewed"))
    record = RecentlyViewedProduct.objects.get(user=customer, product=product)

    assert record.view_count == 2
    assert recent.data["results"][0]["product"]["slug"] == product.slug


@pytest.mark.django_db
def test_reviews_require_moderation_before_publication(client, customer, product):
    created = client.post(
        reverse("product-reviews", kwargs={"slug": product.slug}),
        {"rating": 5, "title": "Great", "body": "Comfortable and well made."},
        format="json",
    )
    anonymous = APIClient()
    hidden = anonymous.get(reverse("product-reviews", kwargs={"slug": product.slug}))
    review = ProductReview.objects.get(user=customer, product=product)
    review.status = ReviewStatus.APPROVED
    review.save(update_fields=["status"])
    visible = anonymous.get(reverse("product-reviews", kwargs={"slug": product.slug}))

    assert created.status_code == 201
    assert created.data["status"] == ReviewStatus.PENDING
    assert hidden.data["results"] == []
    assert visible.data["results"][0]["rating"] == 5


@pytest.mark.django_db
def test_recommendations_use_recent_categories(client, customer, product):
    RecentlyViewedProduct.objects.create(user=customer, product=product)

    response = client.get(reverse("recommendations"))

    assert response.status_code == 200
    assert response.data[0]["slug"] == product.slug
