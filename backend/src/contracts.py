from datetime import date, datetime
from enum import StrEnum
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class Role(StrEnum):
    ANALYST = 'analyst'
    ADMIN = 'admin'
    VIEWER = 'viewer'


class Slot(StrEnum):
    MORNING = 'morning'
    MIDDAY = 'midday'
    EVENING = 'evening'


class TaskState(StrEnum):
    ASSIGNED = 'assigned'
    RETESTING = 'retesting'
    IMPROVED = 'improved'
    FOLLOWUP = 'followup'
    OBSOLETE = 'obsolete'


class RunState(StrEnum):
    QUEUED = 'queued'
    PAUSED = 'paused'
    REVIEW = 'review'
    CONFIRMED = 'confirmed'
    FAILED = 'failed'


def local_day():
    return datetime.now(ZoneInfo('Asia/Shanghai')).date()


class Form(BaseModel):
    model_config = ConfigDict(extra='forbid', str_strip_whitespace=True)


class Login(Form):
    username: str = Field(min_length=1, max_length=40)
    password: str = Field(min_length=1, max_length=128)


class RegisterPoint(Form):
    code: str = Field(pattern=r'^[A-Z][A-Z0-9-]{2,15}$')
    name: str = Field(min_length=2, max_length=64)
    sector: str = Field(min_length=2, max_length=40)
    location: str = Field(min_length=4, max_length=160)


class Note(Form):
    note: str = Field(min_length=4, max_length=240)


class Relocation(Note):
    location: str = Field(min_length=4, max_length=160)


class Window(Form):
    point_id: int = Field(gt=0)
    sample_day: date
    slot: Slot
    total: int = Field(ge=5, le=1000)
    correct: int = Field(ge=0)
    overflow: int = Field(ge=0)
    task_id: int | None = Field(default=None, gt=0)

    @model_validator(mode='after')
    def valid_counts(self):
        if self.correct > self.total or self.overflow > self.total:
            raise ValueError('正确数和满溢记录数不能超过观察总数')
        if self.sample_day > local_day():
            raise ValueError('采样日期不能在未来')
        return self


class RunRequest(Form):
    from_day: date
    through_day: date
    clusters: int = Field(default=3, ge=2, le=4)

    @model_validator(mode='after')
    def valid_period(self):
        if not 0 <= (self.through_day - self.from_day).days <= 30 or self.through_day > local_day():
            raise ValueError('基线须为截至今日的连续 1–31 天')
        return self


class Delivery(Note):
    delivered_day: date

    @field_validator('delivered_day')
    @classmethod
    def not_future(cls, delivered_day):
        if delivered_day > local_day():
            raise ValueError('宣教日期不能在未来')
        return delivered_day
