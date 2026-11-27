"""Retrospective Rulebook Audit & Lessons Learnt API router (Unit U8)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Depends, Request

from app.config import RulesConfig, load_rules_config
from app.services.retrospective import (
    LessonCreateRequest,
    create_lesson,
    list_lessons,
    run_rulebook_audit,
)

router = APIRouter(prefix="/api", tags=["retrospective"])


def get_rules(request: Request) -> RulesConfig:
    """Return loaded RulesConfig from app state or load from YAML."""
    return getattr(request.app.state, "rules", load_rules_config())


def get_db_path(request: Request) -> str | Path | None:
    """Return configured db_path from app state if present."""
    return getattr(request.app.state, "db_path", None)


@router.get("/retrospective/audit")
def get_retrospective_audit(
    rules: RulesConfig = Depends(get_rules),
    db_path: str | Path | None = Depends(get_db_path),
) -> dict[str, Any]:
    """Run rulebook audit across trades_history, positions, staged_orders, and lessons_log."""
    return run_rulebook_audit(db_path=db_path, rules=rules)


@router.get("/lessons")
def get_lessons(
    db_path: str | Path | None = Depends(get_db_path),
) -> dict[str, Any]:
    """List all logged lessons and Decay Lock overrides."""
    lessons = list_lessons(db_path=db_path)
    return {"count": len(lessons), "lessons": lessons}


@router.post("/lessons")
def post_lesson(
    payload: LessonCreateRequest,
    db_path: str | Path | None = Depends(get_db_path),
) -> dict[str, Any]:
    """Create a new lesson in SQLite and optionally append to docs/LESSONS_LEARNT.md."""
    lesson = create_lesson(req=payload, db_path=db_path)
    return {"status": "created", "lesson": lesson}
