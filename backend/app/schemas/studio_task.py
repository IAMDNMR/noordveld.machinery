"""Private, server-owned conversation state; never part of an exported application."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class TaskMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    text: str = Field(max_length=4000)
    request_id: str = Field(max_length=80)


class TaskReceipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_id: str = Field(max_length=80)
    fingerprint: str
    status: Literal["running", "completed", "failed"]
    turn: dict | None = None


class StudioTask(BaseModel):
    model_config = ConfigDict(extra="forbid")
    version: int = Field(default=0, ge=0)
    blocked_before_turn: bool = False
    history: list[TaskMessage] = Field(default_factory=list, max_length=24)
    receipts: list[TaskReceipt] = Field(default_factory=list, max_length=8)
    selected: str | None = None
    asked_question_id: str | None = None
    original_request: str | None = None
    pending_proposal: dict | None = None
    pending_operation: Literal["frontend", "compile", "continue", "test"] | None = None
    status: Literal[
        "working",
        "awaiting_answer",
        "awaiting_review",
        "awaiting_execution",
        "completed",
        "blocked",
    ] = "completed"
