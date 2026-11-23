"""Offline stub: real PyJWT lives in the container image."""


def encode(payload, secret, algorithm=None):
    return 'stub-token'


def decode(token, secret, algorithms=None, options=None):
    return {'sub': 'field', 'exp': 0}


class InvalidTokenError(Exception):
    pass
