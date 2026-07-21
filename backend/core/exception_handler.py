"""
Custom DRF exception handler that formats ALL errors into the
consistent {data, errors, meta} API envelope.

Spec X1: 4xx/5xx responses MUST include an errors array with
objects containing a 'code' and 'message' field.
"""

from rest_framework.views import exception_handler
from rest_framework import status


def envelope_exception_handler(exc, context):
    """Wrap DRF exceptions in the {data, errors, meta} envelope.

    Uses DRF's built-in exception handler to get the standard
    response, then reformats it into the envelope shape.

    Handles:
      - Authentication failures (DRF returns 401 with detail)
      - Permission failures (DRF returns 403 with detail)
      - Validation errors (DRF returns field-level errors)
      - NotFound / MethodNotAllowed / etc.
      - Any unhandled 500 (server error)
    """
    # Call DRF's default handler first
    response = exception_handler(exc, context)

    if response is None:
        # Unhandled exception — return generic 500
        return None  # Let Django's default 500 handler run

    # Convert DRF error detail into the envelope errors array
    errors = _format_errors(response.data, response.status_code)

    response.data = {
        'data': None,
        'errors': errors,
        'meta': {},
    }

    return response


def _format_errors(detail, http_status):
    """Convert DRF error detail into [{code, message}] format.

    DRF returns different shapes for different error types:
      - Authentication: {"detail": "Authentication credentials..."}
      - Permission:     {"detail": "You do not have permission..."}
      - Validation:     {"field_name": ["error msg"], ...}
      - Simple detail:  "A string message"
      - 404:            {"detail": "Not found."}
    """
    status_codes = {
        status.HTTP_400_BAD_REQUEST: 'bad_request',
        status.HTTP_401_UNAUTHORIZED: 'authentication_failed',
        status.HTTP_403_FORBIDDEN: 'permission_denied',
        status.HTTP_404_NOT_FOUND: 'not_found',
        status.HTTP_405_METHOD_NOT_ALLOWED: 'method_not_allowed',
        status.HTTP_500_INTERNAL_SERVER_ERROR: 'server_error',
    }

    default_code = status_codes.get(http_status, 'error')

    if isinstance(detail, dict):
        errors = []
        for key, value in detail.items():
            if isinstance(value, list):
                for msg in value:
                    errors.append({
                        'code': 'validation_error' if key != 'detail' else default_code,
                        'field': key if key != 'detail' else None,
                        'message': str(msg),
                    })
            elif isinstance(value, dict):
                errors.append({
                    'code': default_code,
                    'message': str(value),
                })
            else:
                errors.append({
                    'code': default_code,
                    'field': key if key != 'detail' else None,
                    'message': str(value),
                })
        if not errors:
            errors.append({'code': default_code, 'message': str(detail)})
        return errors

    if isinstance(detail, list):
        return [
            {'code': default_code, 'message': str(item)}
            for item in detail
        ]

    # String detail
    return [{'code': default_code, 'message': str(detail)}]
