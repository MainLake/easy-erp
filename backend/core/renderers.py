"""
Custom DRF renderer that wraps ALL API responses in a consistent envelope.

Spec X1: Every response MUST be {data, errors, meta}.
  - 2xx → data populated, errors: []
  - 4xx/5xx → data: null, errors: [{code, message}], meta: {}

Paginated responses (spec X2) include pagination metadata in meta:
  - count, next, previous (from DRF pagination).
"""

from rest_framework.renderers import JSONRenderer
from rest_framework.utils.serializer_helpers import ReturnDict, ReturnList


class EnvelopeRenderer(JSONRenderer):
    """DRF renderer that wraps every response in {data, errors, meta}.

    Preserves DRF's paginated response structure by detecting the
    standard pagination keys (count, next, previous, results) and
    nesting results under 'data' while moving pagination fields to 'meta'.

    Non-paginated responses: the entire response goes under 'data'.
    """

    media_type = 'application/json'
    format = 'json'

    def render(self, data, accepted_media_type=None, renderer_context=None):
        """Wrap the rendered data in the API envelope.

        Uses the response status code from renderer_context to decide
        whether this is a success or error envelope.  Error responses
        are handled by the custom exception handler, not here, so by
        the time data reaches this renderer for a non-2xx response,
        it should already be in the {data, errors, meta} shape.
        """
        response = renderer_context.get('response') if renderer_context else None

        # If the data is already in envelope shape (e.g. from our custom
        # exception handler or a view that manually returns it), pass through.
        if isinstance(data, dict) and 'data' in data and 'errors' in data:
            return super().render(data, accepted_media_type, renderer_context)

        # Build meta from pagination keys (spec X2)
        meta = {}
        if isinstance(data, dict):
            pagination_keys = {'count', 'next', 'previous', 'results'}
            if pagination_keys & data.keys() and 'results' in data:
                # Paginated response: move results to data, rest to meta
                results = data.pop('results')
                meta = {
                    'count': data.pop('count', None),
                    'next': data.pop('next', None),
                    'previous': data.pop('previous', None),
                }
                # Any leftover keys (custom pagination fields) go to meta too
                for key in list(data.keys()):
                    meta[key] = data.pop(key)
                envelope = {
                    'data': results,
                    'errors': [],
                    'meta': meta,
                }
                return super().render(envelope, accepted_media_type, renderer_context)

        # Default: standard (non-paginated) success envelope
        envelope = {
            'data': data,
            'errors': [],
            'meta': meta if meta else {},
        }

        return super().render(envelope, accepted_media_type, renderer_context)
