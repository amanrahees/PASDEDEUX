from django.contrib import admin

from .models import ProductReview, RecentlyViewedProduct, WishlistItem


@admin.register(ProductReview)
class ProductReviewAdmin(admin.ModelAdmin):
    list_display = (
        "product",
        "user",
        "rating",
        "is_verified_purchase",
        "status",
        "created_at",
    )
    list_filter = ("status", "rating", "is_verified_purchase")
    search_fields = ("product__name", "user__email", "title", "body")
    readonly_fields = ("is_verified_purchase", "created_at", "updated_at")
    actions = ("approve_reviews", "reject_reviews")

    @admin.action(description="Approve selected reviews")
    def approve_reviews(self, request, queryset):
        queryset.update(status="APPROVED")

    @admin.action(description="Reject selected reviews")
    def reject_reviews(self, request, queryset):
        queryset.update(status="REJECTED")


admin.site.register(WishlistItem)
admin.site.register(RecentlyViewedProduct)
