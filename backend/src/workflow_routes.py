from fastapi import APIRouter, Depends

from src.cohort_handoffs import close_handoff, cohort_board, issue_handoff, record_outcome
from src.contracts import Note, Role
from src.observation_context import decide_condition, list_conditions, report_condition
from src.retest_appointments import appointment_board, save_appointment
from src.security import allow, signed_in
from src.workflow_forms import Appointment, ConditionDecision, HandoffOutcome, IssueHandoff, ObservationCondition

router = APIRouter()
field = allow(Role.ANALYST, Role.ADMIN)
operations = allow(Role.ADMIN)


@router.get('/observation-conditions')
def conditions(window: int | None = None, _staff=Depends(signed_in)):
    return list_conditions(window)


@router.post('/observation-conditions/{window_id}', status_code=201)
def report(window_id: int, form: ObservationCondition, staff=Depends(field)):
    return report_condition(window_id, form, staff['username'])


@router.post('/observation-conditions/{window_id}/decision')
def decide(window_id: int, form: ConditionDecision, staff=Depends(operations)):
    return decide_condition(window_id, form, staff['username'])


@router.get('/retest-appointments')
def appointments(task: int | None = None, _staff=Depends(signed_in)):
    return appointment_board(task)


@router.post('/retest-appointments/{task_id}')
def appointment(task_id: int, form: Appointment, staff=Depends(field)):
    return save_appointment(task_id, form, staff['username'])


@router.get('/cohort-handoffs')
def handoffs(task: int | None = None, handoff: int | None = None, _staff=Depends(signed_in)):
    return cohort_board(task, handoff)


@router.post('/cohort-handoffs/from-task/{task_id}', status_code=201)
def issue(task_id: int, form: IssueHandoff, staff=Depends(operations)):
    return issue_handoff(task_id, form, staff['username'])


@router.post('/cohort-handoffs/{handoff_id}/members/{task_id}')
def outcome(handoff_id: int, task_id: int, form: HandoffOutcome, staff=Depends(field)):
    return record_outcome(handoff_id, task_id, form, staff)


@router.post('/cohort-handoffs/{handoff_id}/close')
def close(handoff_id: int, form: Note, staff=Depends(operations)):
    return close_handoff(handoff_id, form, staff['username'])
