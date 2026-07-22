"""
Order-approval gate and authority resolution.

``evaluate_gate`` is invoked from ``sales.services.confirm_so`` and
``purchasing.services.send_po`` (wired in a later phase — see
sdd/order-approval-rules design D5). It is deliberately **non-raising**:
raising an exception here would roll back the ``approval_status='pending'``
stamp because the caller wraps the transition in ``transaction.atomic()``.
Instead the gate returns a status string and the caller decides whether to
continue the transition (early return on 'pending').

Zero-rules-configured orgs get a pure no-op: the first query returns None,
``evaluate_gate`` returns 'not_required', and no field is ever touched.
"""

from core.models import ApprovalRule, OrganizationMembership


def evaluate_gate(*, order, order_type: str, user) -> str:
    """Resolve whether *order* may proceed through its confirm/send gate.

    Returns one of:
      - 'not_required': no active rule matches, or the order total is
        below the rule's min_amount. If the order was previously stamped
        'pending' (rule deactivated/deleted since), it is reset to 'none'.
      - 'approved': the order was already approved; the transition may proceed.
      - 'pending': an active rule requires approval; the order is stamped
        'pending' with `requested_by` set, and the caller MUST NOT proceed
        with the transition.
    """
    if order.approval_status == 'approved':
        return 'approved'

    rule = ApprovalRule.objects.filter(
        organization=order.organization,
        order_type=order_type,
        is_active=True,
    ).first()

    if rule is None or order.total < rule.min_amount:
        if order.approval_status == 'pending':
            order.approval_status = 'none'
            order.save(update_fields=['approval_status'])
        return 'not_required'

    order.approval_status = 'pending'
    order.requested_by = user
    order.save(update_fields=['approval_status', 'requested_by'])
    return 'pending'


def can_approve(user, org, rule) -> bool:
    """True if *user* is authorized to approve/reject orders under *rule*.

    Authority holds when the user is org owner, OR the user's membership
    role in *org* equals ``rule.approver_role``, OR the user is listed in
    ``rule.approver_users``.
    """
    membership = OrganizationMembership.objects.filter(
        user=user, organization=org,
    ).first()

    if membership is None:
        return False

    if membership.is_owner:
        return True

    if rule.approver_role_id is not None and membership.role_id == rule.approver_role_id:
        return True

    return rule.approver_users.filter(pk=user.pk).exists()


def approve_order(*, order, order_type: str, user):
    """Mark *order* approved and record audit fields.

    Raises ``django.core.exceptions.PermissionDenied`` if *user* is not
    authorized under the matching active rule.
    """
    from django.core.exceptions import PermissionDenied
    from django.utils import timezone

    rule = ApprovalRule.objects.filter(
        organization=order.organization,
        order_type=order_type,
        is_active=True,
    ).first()

    if rule is None or not can_approve(user, order.organization, rule):
        raise PermissionDenied('You are not authorized to approve this order.')

    order.approval_status = 'approved'
    order.approved_by = user
    order.approved_at = timezone.now()
    order.save(update_fields=['approval_status', 'approved_by', 'approved_at'])
    return order


def reject_order(*, order, order_type: str, user):
    """Mark *order* rejected. Does NOT auto-retry the blocked transition.

    Raises ``django.core.exceptions.PermissionDenied`` if *user* is not
    authorized under the matching active rule.
    """
    from django.core.exceptions import PermissionDenied

    rule = ApprovalRule.objects.filter(
        organization=order.organization,
        order_type=order_type,
        is_active=True,
    ).first()

    if rule is None or not can_approve(user, order.organization, rule):
        raise PermissionDenied('You are not authorized to reject this order.')

    order.approval_status = 'rejected'
    order.save(update_fields=['approval_status'])
    return order
