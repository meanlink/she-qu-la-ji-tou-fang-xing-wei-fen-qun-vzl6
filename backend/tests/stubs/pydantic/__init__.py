"""Tiny pydantic-compatible surface for offline tests."""
from enum import Enum


class StrEnum(str, Enum):
    def __str__(self):
        return self.value


def Field(default=None, gt=None, ge=None, le=None, pattern=None, min_length=None, max_length=None):
    return default


class ConfigDict(dict):
    pass


def field_validator(*_fields, **_kwargs):
    def decorate(fn):
        fn.__field_validator__ = True
        return fn
    return decorate


def model_validator(*_args, **_kwargs):
    def decorate(fn):
        fn.__model_validator__ = True
        return fn
    return decorate


class BaseModel:
    model_config = ConfigDict()

    def __init__(self, **data):
        for key, value in data.items():
            setattr(self, key, value)

    def model_dump(self, mode=None):
        return {key: value for key, value in vars(self).items() if not key.startswith('_')}
