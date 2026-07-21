from django.contrib import admin

from .models import Category, Product, Warehouse, StockLevel, StockMovement


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'parent']
    search_fields = ['name']


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ['sku', 'name', 'cost', 'price', 'category']
    search_fields = ['sku', 'name']
    list_filter = ['category']


@admin.register(Warehouse)
class WarehouseAdmin(admin.ModelAdmin):
    list_display = ['name', 'location']
    search_fields = ['name', 'location']


@admin.register(StockLevel)
class StockLevelAdmin(admin.ModelAdmin):
    list_display = ['product', 'warehouse', 'quantity']
    list_filter = ['warehouse']
    search_fields = ['product__name', 'product__sku']


@admin.register(StockMovement)
class StockMovementAdmin(admin.ModelAdmin):
    list_display = ['product', 'warehouse', 'movement_type', 'quantity', 'reason', 'timestamp']
    list_filter = ['movement_type', 'warehouse']
    search_fields = ['product__name', 'reason']
    readonly_fields = ['timestamp']
