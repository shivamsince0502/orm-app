"""AI error → HTTP response mapping (one place).

Lives in its own leaf module (not views.py) so DRF's lazy
`EXCEPTION_HANDLER = "crm.exceptions.exception_handler"` import can never hit a
circular import (views.py imports DRF decorators, which resolve api_settings).
"""

from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_exception_handler

from crm.services import ai


def exception_handler(exc, context):
    response = drf_exception_handler(exc, context)
    if response is not None:
        return response
    if isinstance(exc, ai.AIServiceUnavailable):
        return Response({"detail": "AI service unavailable"}, status=503)
    if isinstance(exc, ai.AIUnparseableResponse):
        return Response({"detail": "AI returned unparseable output"}, status=502)
    return None
