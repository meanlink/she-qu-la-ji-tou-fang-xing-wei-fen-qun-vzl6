class RequestValidationError(Exception):
    def __init__(self, errors=None):
        self.errors = errors or []
