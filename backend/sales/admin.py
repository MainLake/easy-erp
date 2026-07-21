from django.contrib import admin

from .models import Customer, SalesOrder, SOLineItem


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ['name', 'contact', 'tax_id']
    search_fields = ['name', 'tax_id']


class SOLineItemInline(admin.TabularInline):
    model = SOLineItem
    extra = 0
    fields = ['product', 'warehouse', 'quantity', 'unit_price']


@admin.register(SalesOrder)
class SalesOrderAdmin(admin.ModelAdmin):
    list_display = ['id_short', 'customer', 'status', 'order_date']
    list_filter = ['status']
    inlines = [SOLineItemInline]

    def id_short(self, obj):
        return obj.id.hex[:8]
    id_short.short_description = 'ID'


@admin.register(SOLineItem)
class SOLineItemAdmin(admin.ModelAdmin):
    list_display = ['sales_order_short', 'product', 'warehouse', 'quantity', 'unit_price']

    def sales_order_short(self, obj):
        return obj.sales_order.id.hex[:8]
    sales_order_short.short_description = 'SO'
