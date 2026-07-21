from django.contrib import admin
from django.urls import path, include
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include('core.urls')),
    path('api/v1/inventory/', include('inventory.urls')),
    path('api/v1/purchasing/', include('purchasing.urls')),
    path('api/v1/sales/', include('sales.urls')),
    path('api/v1/invoicing/', include('invoicing.urls')),
    # OpenAPI 3.0 schema (spec X4)
    path('api/v1/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/v1/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
]
