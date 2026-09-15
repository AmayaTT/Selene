"""Shared quick-action routes for both REST entry points."""
from typing import Literal
from fastapi import HTTPException
from pydantic import BaseModel, Field

import db
import period_actions


class PeriodActionBody(BaseModel):
    action: Literal["start", "end"]
    date: str
    request_id: str = Field(min_length=1, max_length=120)
    period_id: int | None = None


class UndoBody(BaseModel):
    request_id: str = Field(min_length=1, max_length=120)


def register(app):
    @app.get('/calendar')
    def calendar(month: str):
        from datetime import date
        from calendar import monthrange
        import cycle
        try:
            first = date.fromisoformat(month + '-01')
            if first.strftime('%Y-%m') != month:
                raise ValueError()
        except ValueError:
            raise HTTPException(status_code=422, detail='月份格式应为 YYYY-MM')
        conn = db.get_db()
        try:
            periods = [dict(row) for row in conn.execute('SELECT * FROM periods ORDER BY start_date,id')]
        finally:
            conn.close()
        configured = db.get_config('cycle_length')
        length = int(configured) if configured else None
        days = {}
        for day in range(1, monthrange(first.year, first.month)[1] + 1):
            value = first.replace(day=day)
            key = value.isoformat()
            past = [p for p in periods if p['start_date'] <= key]
            last = past[-1] if past else {}
            status = cycle.current_phase(past, value, length)
            description = cycle.describe_status(past, value, length)
            days[key] = {**status, 'label': description['phase_label'],
                         'recorded': not description['phase_is_estimated'],
                         'periodId': last.get('id'), 'periodStart': last.get('start_date', ''),
                         'periodEnd': last.get('end_date', '') or '',
                         'isStart': last.get('start_date') == key,
                         'isEnd': last.get('end_date') == key}
        return {'month': month, 'days': days}

    @app.post("/period/action")
    def period_action(body: PeriodActionBody):
        try:
            result = period_actions.apply(body.action, body.date, body.request_id, body.period_id)
        except period_actions.ActionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {**result, **db.get_cycle_config()}

    @app.post("/period/undo")
    def period_undo(body: UndoBody):
        try:
            result = period_actions.undo(body.request_id)
        except period_actions.ActionConflict as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {**result, **db.get_cycle_config()}
