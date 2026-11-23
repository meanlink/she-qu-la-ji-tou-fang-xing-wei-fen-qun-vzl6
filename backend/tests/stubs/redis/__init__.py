"""Offline stub for redis client surface used at import time."""


class RedisError(Exception):
    pass


class Redis:
    @classmethod
    def from_url(cls, *args, **kwargs):
        return cls()

    def ping(self):
        return True

    def eval(self, *args, **kwargs):
        return 1
