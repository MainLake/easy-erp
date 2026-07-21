"""DRF serializers for sales models."""

from rest_framework import serializers

from core.managers import get_current_organization
from core.serializers import CustomFieldsMixin
from .models import Customer, SalesOrder, SOLineItem


class CustomerSerializer(CustomFieldsMixin, serializers.ModelSerializer):
    MODEL_NAME = 'customer'

    class Meta:
        model = Customer
        fields = ['id', 'name', 'contact', 'tax_id', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_tax_id(self, value):
        """Per-org tax_id uniqueness (spec S1)."""
        org_id = get_current_organization()
        if org_id:
            existing = Customer.objects.filter(
                tax_id=value, organization_id=org_id,
            )
            if self.instance:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise serializers.ValidationError(
                    f'Customer with tax ID "{value}" already exists in this organization.',
                )
        return value


class SOLineItemSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)

    class Meta:
        model = SOLineItem
        fields = [
            'id', 'sales_order', 'product', 'product_name',
            'warehouse', 'warehouse_name', 'quantity', 'unit_price',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class SOLineItemCreateSerializer(serializers.ModelSerializer):
    """Used for nested writes when creating/updating a SO with line items."""

    class Meta:
        model = SOLineItem
        fields = ['product', 'warehouse', 'quantity', 'unit_price']


class SalesOrderSerializer(serializers.ModelSerializer):
    customer_name = serializers.CharField(source='customer.name', read_only=True)
    line_items = SOLineItemSerializer(many=True, read_only=True)
    line_items_write = SOLineItemCreateSerializer(
        many=True, write_only=True, required=False,
    )

    class Meta:
        model = SalesOrder
        fields = [
            'id', 'customer', 'customer_name', 'status',
            'order_date', 'notes', 'line_items', 'line_items_write',
            'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'status', 'order_date', 'created_at', 'updated_at']

    def create(self, validated_data):
        line_items_data = validated_data.pop('line_items_write', [])
        so = SalesOrder.objects.create(**validated_data)
        for item_data in line_items_data:
            SOLineItem.objects.create(sales_order=so, **item_data)
        return so


class SalesOrderStatusSerializer(serializers.Serializer):
    """Used for status transition @action endpoints (confirm, fulfill)."""

    def create(self, validated_data):
        pass

    def update(self, instance, validated_data):
        pass
