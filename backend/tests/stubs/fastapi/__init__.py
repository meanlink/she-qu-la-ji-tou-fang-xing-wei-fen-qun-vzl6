"""Minimal FastAPI stand-ins for offline lifecycle tests (no PyPI access here)."""


class Request:
    pass


class RequestValidationError(Exception):
    pass


class HTTPException(Exception):
    def __init__(self, status_code, detail):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class FastAPI:
    def __init__(self, *args, **kwargs):
        pass

    def include_router(self, *_args, **_kwargs):
        pass

    def middleware(self, *_args, **_kwargs):
        return lambda fn: fn

    def exception_handler(self, *_args, **_kwargs):
        return lambda fn: fn

    def get(self, *_args, **_kwargs):
        return lambda fn: fn

    def post(self, *_args, **_kwargs):
        return lambda fn: fn


class APIRouter:
    def get(self, *_args, **_kwargs):
        return lambda fn: fn

    def post(self, *_args, **_kwargs):
        return lambda fn: fn


def Depends(fn=None):
    return fn


def allow(*_roles):
    def authorized(staff=None):
        return staff
    return authorized
