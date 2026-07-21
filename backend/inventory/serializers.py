"""DRF serializers for inventory models."""

from rest_framework import serializers

from core.managers import get_current_organization
from core.serializers import CustomFieldsMixin
from .models import Category, Product, Warehouse, StockLevel, StockMovement
from . import services


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name', 'parent', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class ProductSerializer(CustomFieldsMixin, serializers.ModelSerializer):
    MODEL_NAME = 'product'

    class Meta:
        model = Product
        fields = ['id', 'sku', 'name', 'description', 'cost', 'price', 'category', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']

    def validate_sku(self, value):
        """Per-org SKU uniqueness (spec I1)."""
        org_id = get_current_organization()
        if org_id:
            existing = Product.objects.filter(
                sku=value, organization_id=org_id,
            )
            if self.instance:
                existing = existing.exclude(pk=self.instance.pk)
            if existing.exists():
                raise serializers.ValidationError(
                    f'Product with SKU "{value}" already exists in this organization.',
                )
        return value


class WarehouseSerializer(serializers.ModelSerializer):
    class Meta:
        model = Warehouse
        fields = ['id', 'name', 'location', 'created_at', 'updated_at']
        read_only_fields = ['id', 'created_at', 'updated_at']


class StockLevelSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)

    class Meta:
        model = StockLevel
        fields = [
            'id', 'product', 'product_name', 'warehouse', 'warehouse_name',
            'quantity', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class StockMovementSerializer(serializers.ModelSerializer):
    product_name = serializers.CharField(source='product.name', read_only=True)
    warehouse_name = serializers.CharField(source='warehouse.name', read_only=True)

    class Meta:
        model = StockMovement
        fields = [
            'id', 'product', 'product_name', 'warehouse', 'warehouse_name',
            'movement_type', 'quantity', 'reason', 'reference', 'timestamp',
        ]
        read_only_fields = ['id', 'timestamp']


# -- Action serializers for stock mutation endpoints --

class AddStockSerializer(serializers.Serializer):
    warehouse_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=255)

    def create(self, validated_data):
        # Not used — the view calls the service layer.
        pass

    def update(self, instance, validated_data):
        pass


class RemoveStockSerializer(serializers.Serializer):
    warehouse_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=255)

    def create(self, validated_data):
        pass

    def update(self, instance, validated_data):
        pass


class TransferStockSerializer(serializers.Serializer):
    from_warehouse_id = serializers.UUIDField()
    to_warehouse_id = serializers.UUIDField()
    quantity = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(max_length=255, required=False, default='manual transfer')

    def create(self, validated_data):
        pass

    def update(self, instance, validated_data):
        pass
