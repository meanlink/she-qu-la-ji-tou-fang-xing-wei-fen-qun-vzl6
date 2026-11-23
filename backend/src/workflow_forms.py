from datetime import date
from typing import Literal

from pydantic import Field, model_validator

from src.contracts import Note, local_day


class ObservationCondition(Note):
    condition_type: Literal['rain', 'access', 'signage', 'staffing']


class ConditionDecision(Note):
    decision: Literal['verified', 'dismissed']


class Appointment(Note):
    first_day: date
    second_day: date

    @model_validator(mode='after')
    def chronological(self):
        if self.first_day >= self.second_day:
            raise ValueError('请选择两个不同且依次递增的复测日期')
        return self


class IssueHandoff(Note):
    tactic: Literal['replace_signs', 'guided_sorting', 'stagger_window', 'alternate_point']
    due_day: date
    condition_window_id: int | None = Field(default=None, gt=0)


class HandoffOutcome(Note):
    outcome: Literal['implemented', 'relocated']
    event_day: date

    @model_validator(mode='after')
    def occurred(self):
        if self.event_day > local_day():
            raise ValueError('现场结果日期不能在未来')
        return self
