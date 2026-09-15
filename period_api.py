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
