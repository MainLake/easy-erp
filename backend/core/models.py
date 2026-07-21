import uuid
from django.core.exceptions import ValidationError
from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin


class BaseModel(models.Model):
    """Abstract base with UUID primary key and auto timestamps.

    All domain models across every app inherit from this base.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# ---------------------------------------------------------------------------
# Permission validation — shared by Role.clean()
# ---------------------------------------------------------------------------

VALID_MODULES = {'core', 'inventory', 'purchasing', 'sales', 'invoicing'}
VALID_ACTIONS = {'read', 'write', 'admin'}


def validate_permissions_schema(value):
    """Validate that the permissions dict only contains known modules and actions.

    Expected shape:  {"inventory": ["read","write"], "sales": ["read"]}
    """
    if not isinstance(value, dict):
        raise ValidationError('Permissions must be a JSON object (dict).')

    for module, actions in value.items():
        if module not in VALID_MODULES:
            raise ValidationError(
                f'Invalid module "{module}". '
                f'Valid modules: {sorted(VALID_MODULES)}.'
            )
        if not isinstance(actions, list):
            raise ValidationError(
                f'Actions for module "{module}" must be a list.'
            )
        for action in actions:
            if action not in VALID_ACTIONS:
                raise ValidationError(
                    f'Invalid action "{action}" for module "{module}". '
                    f'Valid actions: {sorted(VALID_ACTIONS)}.'
                )


# ---------------------------------------------------------------------------
# User + UserManager
# ---------------------------------------------------------------------------

class UserManager(BaseUserManager):
    """Custom manager that uses email as the unique identifier."""

    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError('The Email field must be set')
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('role', User.Role.ADMIN)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    """Custom user model: email as login, role-based access control.

    Roles (deprecated — kept for Phase 6 cleanup):
        admin    — full CRUD across all modules, manage users
        operator — daily operations (CRUD orders, products, etc.)
        viewer   — read-only access to all modules

    Multi-org support: a user belongs to one or more organizations via
    OrganizationMembership.  The ``active_membership`` property returns
    the default membership (or the first membership if no default is set).
    """

    class Role(models.TextChoices):
        ADMIN = 'admin', 'Admin'
        OPERATOR = 'operator', 'Operator'
        VIEWER = 'viewer', 'Viewer'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=255)
    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.VIEWER,
    )
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Multi-org: convenience M2M through OrganizationMembership.
    # The through model is defined below so the reference is a string.
    organizations = models.ManyToManyField(
        'Organization',
        through='OrganizationMembership',
        related_name='users',
    )

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['full_name']

    objects = UserManager()

    def __str__(self):
        return self.email

    @property
    def active_membership(self):
        """Return the user's default membership, or the first available.

        In Phase 2 the middleware will inject the current request org so this
        property can scope by the active org instead of relying on is_default.
        """
        return (
            self.memberships.filter(is_default=True)
            .select_related('role', 'organization')
            .first()
            or self.memberships.select_related('role', 'organization').first()
        )

    def get_active_membership(self, org_id=None):
        """Return the membership for the given *org_id*, or for the
        thread-local org, or the default membership.

        This method is the preferred way for permission checks to
        locate the user's role in the current request scope (spec R3).
        """
        if org_id is None:
            from .managers import get_current_organization
            org_id = get_current_organization()

        if org_id:
            member = (
                self.memberships
                .filter(organization_id=org_id)
                .select_related('role', 'organization')
                .first()
            )
            if member is not None:
                return member

        # Fallback to default / first membership
        return self.active_membership


# ---------------------------------------------------------------------------
# Multi-org models
# ---------------------------------------------------------------------------

class Organization(BaseModel):
    """Multi-tenant organization / business entity.

    Each organization is an independent tenant.  All domain data (products,
    orders, invoices) is scoped to one organization.
    """
    name = models.CharField(max_length=255, unique=True)
    tax_id = models.CharField(max_length=50, unique=True)
    is_active = models.BooleanField(default=True)
    settings = models.JSONField(default=dict, blank=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Branch(BaseModel):
    """Physical location belonging to an organization.

    A branch may contain multiple warehouses.
    """
    name = models.CharField(max_length=255)
    address = models.TextField(blank=True, default='')
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='branches',
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ['organization', 'name']
        ordering = ['organization', 'name']
        verbose_name_plural = 'branches'

    def __str__(self):
        return f'{self.name} ({self.organization.name})'


class Role(BaseModel):
    """Custom role per organization with a JSON permission map.

    Permissions shape (spec R1, R2):
        {"inventory": ["read","write"], "sales": ["read"]}

    Validation is performed by ``validate_permissions_schema`` which is
    registered as a field validator AND called on clean() so admin forms
    catch bad data too.
    """
    name = models.CharField(max_length=100)
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='roles',
    )
    permissions = models.JSONField(
        default=dict,
        blank=True,
        validators=[validate_permissions_schema],
    )

    class Meta:
        unique_together = ['organization', 'name']
        ordering = ['organization', 'name']

    def __str__(self):
        return f'{self.name} ({self.organization.name})'

    def clean(self):
        """Run JSONField validators so model-level validation catches bad data."""
        super().clean()
        validate_permissions_schema(self.permissions)


class OrganizationMembership(BaseModel):
    """Links a User to an Organization with a specific Role.

    Only one membership per (user, organization) pair.  The ``is_default``
    flag determines which membership is used when the user has no explicit
    active-org selection.
    """
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='memberships',
    )
    organization = models.ForeignKey(
        Organization,
        on_delete=models.CASCADE,
        related_name='memberships',
    )
    role = models.ForeignKey(
        Role,
        on_delete=models.PROTECT,
        related_name='memberships',
    )
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(
        default=False,
        help_text='Automatically selected when no active org is chosen.',
    )

    class Meta:
        unique_together = ['user', 'organization']
        ordering = ['user', 'organization']

    def __str__(self):
        return f'{self.user.email} → {self.organization.name} ({self.role.name})'

    def save(self, *args, **kwargs):
        """If is_default is set, clear is_default on other memberships of the same user."""
        if self.is_default:
            OrganizationMembership.objects.filter(
                user=self.user,
                is_default=True,
            ).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)
