"""DRF serializers for purchasing models."""

from rest_framework import serializers

from core.managers import get_current_organization
from .models import Supplier, PurchaseOrder, POLineItem


class SupplierSerializer(serializers.ModelSerializer):
    class Meta:
        model = Supplier
        fields = ['id', 'name', 'contact', 'tax_id', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_tax_id(self, value):
        """Per-org tax_id uniqueness (spec P1)."""
        org_id = get_current_organization()
        if org_id:
            existing = Supplier.objects.filter(
                tax_id=value, organization_id=org_id,
            )
            if self.instance:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise serializers.ValidationError(
                    f'Supplier with tax ID "{value}" already exists in this organization.',
                )
        return value


class POLineItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)

    class Meta:
        model = POLineItem
        fields = [
            'id', 'purchase_order', 'product', 'product_name',
            'quantity', 'unit_cost', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class POLineItemCreateSerializer(serializers.ModelSerializer):
    """Used for nested writes when creating/updating a PO with line items."""

    class Meta:
        model = POLineItem
        fields = ['product', 'quantity', 'unit_cost']


class PurchaseOrderSerializer(serializers.ModelSerializer):
    supplier_name = serializers.CharField(source='supplier.name', read_only=True)
    line_items = POLineItemSerializer(many=True, read_only=True)
    line_items_write = POLineItemCreateSerializer(
        many=True, write_only=True, required=False,
    )

    class Meta:
        model = PurchaseOrder
        fields = [
            'id', 'supplier', 'supplier_name', 'status',
            'order_date', 'notes', 'line_items', 'line_items_write',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'status', 'order_date', 'created_at', 'updated_at']

    def create(self, validated_data):
        line_items_data = validated_data.pop('line_items_write', [])
        po = PurchaseOrder.objects.create(**validated_data)
        for item_data in line_items_data:
            POLineItem.objects.create(purchase_order=po, **item_data)
        return po


class PurchaseOrderStatusSerializer(serializers.Serializer):
    """Used for status transition @action endpoints (send, receive)."""

    def create(self, validated_data):
        pass

    def update(self, instance, validated_data):
        pass
