"""Inventory ViewSets — standard CRUD plus stock mutation endpoints."""

from django.core.exceptions import ValidationError
from rest_framework import viewsets, permissions, status
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import Category, Product, Warehouse, StockLevel, StockMovement
from .serializers import (
    CategorySerializer,
    ProductSerializer,
    WarehouseSerializer,
    StockLevelSerializer,
    StockMovementSerializer,
    AddStockSerializer,
    RemoveStockSerializer,
    TransferStockSerializer,
)
from . import services
from core.permissions import OrgRolePermission


class CategoryViewSet(viewsets.ModelViewSet):
    """CRUD for product categories — org-scoped via OrgAwareManager."""

    queryset = Category.objects.all()
    serializer_class = CategorySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Category.objects.all().order_by('name')

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [permissions.IsAuthenticated(), OrgRolePermission('inventory', 'read')]
        if self.action == 'destroy':
            return [permissions.IsAuthenticated(), OrgRolePermission('inventory', 'admin')]
        return [permissions.IsAuthenticated(), OrgRolePermission('inventory', 'write')]

    def perform_create(self, serializer):
        serializer.save(organization=self.request.organization)


class ProductViewSet(viewsets.ModelViewSet):
    """CRUD for products plus stock mutation actions — org-scoped."""

    queryset = Product.objects.all()
    serializer_class = ProductSerializer
    permission_classes = [permissions.IsAuthenticated]
    filterset_fields = ['name', 'category', 'sku']
    search_fields = ['name', 'sku']
    ordering_fields = ['name', 'sku', 'price', 'created_at']

    def get_queryset(self):
        return Product.objects.all().order_by('name')

    def get_permissions(self):
        if self.action in ('list', 'retrieve', 'stock'):
            return [permissions.IsAuthenticated(), OrgRolePermission('inventory', 'read')]
        if self.action == 'destroy':
            return [permissions.IsAuthenticated(), OrgRolePermission('inventory', 'admin')]
        return [permissions.IsAuthenticated(), OrgRolePermission('inventory', 'write')]

    def perform_create(self, serializer):
        serializer.save(organization=self.request.organization)

    @action(detail=True, methods=['post'], url_path='add-stock')
    def add_stock(self, request, pk=None):
        """POST /api/v1/inventory/products/{id}/add-stock/"""
        serializer = AddStockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        try:
            movement = services.add_stock(
                product_id=pk,
                warehouse_id=data['warehouse_id'],
                quantity=data['quantity'],
                reason=data['reason'],
            )
        except ValidationError as e:
            return Response({'errors': e.message_dict}, status=status.HTTP_400_BAD_REQUEST)

        return Response(StockMovementSerializer(movement).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='remove-stock')
    def remove_stock(self, request, pk=None):
        """POST /api/v1/inventory/products/{id}/remove-stock/"""
        serializer = RemoveStockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        try:
            movement = services.remove_stock(
                product_id=pk,
                warehouse_id=data['warehouse_id'],
                quantity=data['quantity'],
                reason=data['reason'],
            )
        except ValidationError as e:
            return Response({'errors': e.message_dict}, status=status.HTTP_400_BAD_REQUEST)

        return Response(StockMovementSerializer(movement).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='transfer-stock')
    def transfer_stock(self, request, pk=None):
        """POST /api/v1/inventory/products/{id}/transfer-stock/"""
        serializer = TransferStockSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        data = serializer.validated_data
        try:
            out_movement, in_movement = services.transfer_stock(
                product_id=pk,
                from_warehouse_id=data['from_warehouse_id'],
                to_warehouse_id=data['to_warehouse_id'],
                quantity=data['quantity'],
                reason=data.get('reason', 'manual transfer'),
            )
        except ValidationError as e:
            return Response({'errors': e.message_dict}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            {
                'transfer_out': StockMovementSerializer(out_movement).data,
                'transfer_in': StockMovementSerializer(in_movement).data,
            },
            status=status.HTTP_201_CREATED,
        )

    @action(detail=False, methods=['get'])
    def stock(self, request):
        """GET /api/v1/inventory/products/stock/ — current stock levels, org-scoped."""
        stock_levels = (
            StockLevel.objects
            .select_related('product', 'warehouse')
            .filter(product__organization=request.organization)
            .order_by('product__name', 'warehouse__name')
        )
        page = self.paginate_queryset(stock_levels)
        if page is not None:
            return self.get_paginated_response(StockLevelSerializer(page, many=True).data)
        return Response(StockLevelSerializer(stock_levels, many=True).data)


class WarehouseViewSet(viewsets.ModelViewSet):
    """CRUD for warehouses — org-scoped."""

    queryset = Warehouse.objects.all()
    serializer_class = WarehouseSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return Warehouse.objects.all().order_by('name')

    def get_permissions(self):
        if self.action in ('list', 'retrieve'):
            return [permissions.IsAuthenticated(), OrgRolePermission('inventory', 'read')]
        if self.action == 'destroy':
            return [permissions.IsAuthenticated(), OrgRolePermission('inventory', 'admin')]
        return [permissions.IsAuthenticated(), OrgRolePermission('inventory', 'write')]

    def perform_create(self, serializer):
        serializer.save(organization=self.request.organization)


class StockMovementViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only audit trail for stock movements — org-scoped via product FK."""

    queryset = StockMovement.objects.select_related('product', 'warehouse').order_by('-timestamp')
    serializer_class = StockMovementSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        qs = StockMovement.objects.select_related('product', 'warehouse').order_by('-timestamp')
        org = getattr(self.request, 'organization', None)
        if org:
            qs = qs.filter(product__organization=org)
        return qs
