from rest_framework import serializers
from .models import User


class UserSerializer(serializers.ModelSerializer):
    """Serialize User model for API responses.

    Password is write-only and never exposed in responses.
    """

    class Meta:
        model = User
        fields = [
            'id', 'email', 'full_name', 'role',
            'is_active', 'created_at', 'updated_at',
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']
        extra_kwargs = {
            'email': {'required': True},
        }
