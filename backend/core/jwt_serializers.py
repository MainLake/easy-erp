"""Custom JWT serializer that injects the active organization claim.

Overrides ``TokenObtainPairSerializer`` so every access token carries
the user's default (or first) membership organization ID as the
``active_organization_id`` claim (spec A1).

Configure via ``SIMPLE_JWT``::

    SIMPLE_JWT = {
        ...,
        'TOKEN_OBTAIN_SERIALIZER': 'core.jwt_serializers.CustomTokenObtainPairSerializer',
    }
"""

from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Add ``active_organization_id`` to the access token payload.

    If the user has no memberships the claim is omitted; the middleware
    and permission classes will handle the "no org" case (spec X4).
    """

    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        membership = (
            user.memberships.filter(is_default=True)
            .select_related('organization')
            .first()
            or user.memberships.select_related('organization').first()
        )
        if membership:
            token['active_organization_id'] = str(membership.organization_id)
        return token
