from django.contrib import admin

from .models import Supplier, PurchaseOrder, POLineItem


@admin.register(Supplier)
class SupplierAdmin(admin.ModelAdmin):
    list_display = ['name', 'contact', 'tax_id']
    search_fields = ['name', 'tax_id']


class POLineItemInline(admin.TabularInline):
    model = POLineItem
    extra = 0
    fields = ['product', 'quantity', 'unit_cost']


@admin.register(PurchaseOrder)
class PurchaseOrderAdmin(admin.ModelAdmin):
    list_display = ['id_short', 'supplier', 'status', 'order_date']
    list_filter = ['status']
    inlines = [POLineItemInline]

    def id_short(self, obj):
        return obj.id.hex[:8]
    id_short.short_description = 'ID'


@admin.register(POLineItem)
class POLineItemAdmin(admin.ModelAdmin):
    list_display = ['purchase_order_short', 'product', 'quantity', 'unit_cost']

    def purchase_order_short(self, obj):
        return obj.purchase_order.id.hex[:8]
    purchase_order_short.short_description = 'PO'
