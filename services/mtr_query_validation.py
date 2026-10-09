"""Redact request values in validation errors for selected MTR query routes."""

from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute


class SafeMtrQueryRoute(APIRoute):
    def get_route_handler(self):
        handler = super().get_route_handler()

        async def safe_handler(request):
            try:
                return await handler(request)
            except RequestValidationError as error:
                details = [{key: value for key, value in item.items() if key in {"loc", "msg", "type"}}
                           for item in error.errors()]
                return JSONResponse(status_code=422, content={"detail": details})

        return safe_handler


def safe_mtr_query_post(app, path):
    def register(endpoint):
        app.router.add_api_route(path, endpoint, methods=["POST"], route_class_override=SafeMtrQueryRoute)
        return endpoint

    return register
