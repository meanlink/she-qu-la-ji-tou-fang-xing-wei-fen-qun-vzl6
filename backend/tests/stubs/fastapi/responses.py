class Request:
    pass


class RequestValidationError(Exception):
    pass


class Response:
    def __init__(self, *args, **kwargs):
        self.headers = {}


class JSONResponse(Response):
    def __init__(self, content, status_code=200, headers=None):
        super().__init__()
        self.content = content
        self.status_code = status_code
        if headers:
            self.headers.update(headers)
