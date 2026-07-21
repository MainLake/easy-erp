from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/', include('core.urls')),
    path('api/v1/inventory/', include('inventory.urls')),
    path('api/v1/purchasing/', include('purchasing.urls')),
    path('api/v1/sales/', include('sales.urls')),
]
