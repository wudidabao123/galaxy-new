"""Pydantic data models for Galaxy New."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal
import uuid

from core.enums import AgentStatus, AuditStatus, GuardDecision, TestStatus


# ── Command Result ─────────────────────────────────────
@dataclass
class CommandResult:
    command: str
    result: TestStatus = TestStatus.UNKNOWN
    evidence: str = ""
    exit_code: int | None = None


# ── Agent Stage Result ─────────────────────────────────
@dataclass
class AgentStageResult:
    role: str
    status: AgentStatus = AgentStatus.DONE
    task_scope: str = ""
    summary: str = ""
    files_read: list[str] = field(default_factory=list)
    files_changed: list[str] = field(default_factory=list)
    commands_run: list[CommandResult] = field(default_factory=list)
    tests: list[CommandResult] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    handoff_summary: str = ""
    raw_output: str = ""
    parsed_json_ok: bool = False  # True if the agent output contained valid structured JSON


# ── Guard Result ───────────────────────────────────────
@dataclass
class GuardResult:
    decision: GuardDecision
    score: int
    pass_: bool  # derived from decision==PASS; kept for backward compat — prefer checking decision directly
    blocking_issues: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    retry_instruction: str = ""
    evidence: str = ""


# ── Tool Audit Log ─────────────────────────────────────
@dataclass
class ToolAuditLog:
    run_id: str
    agent_name: str
    tool_name: str
    args_preview: str
    target_path: str = ""
    allowed: bool = True
    result_status: AuditStatus = AuditStatus.UNKNOWN
    error: str = ""
    duration_ms: int = 0
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


# ── Stage State ────────────────────────────────────────
@dataclass
class StageState:
    name: str
    roles: list[str] = field(default_factory=list)
    results: dict[str, AgentStageResult] = field(default_factory=dict)
    guard_results: dict[str, GuardResult] = field(default_factory=dict)
    started_at: str = ""
    finished_at: str = ""


# ── Run State ──────────────────────────────────────────
@dataclass
class RunState:
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:24])  # 24 hex = 96 bits, low collision risk
    task: str = ""
    team_id: str = ""
    mode: str = ""
    current_stage: str = ""
    stages: list[StageState] = field(default_factory=list)
    artifacts: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict
        return asdict(self)


# ── Task Contract ──────────────────────────────────────
@dataclass
class AgentContract:
    name: str
    responsibilities: str = ""
    allowed_paths: list[str] = field(default_factory=list)
    forbidden_paths: list[str] = field(default_factory=list)
    required_outputs: list[str] = field(default_factory=list)


@dataclass
class TaskContract:
    run_id: str
    goal: str = ""
    global_constraints: list[str] = field(default_factory=list)
    agents: list[AgentContract] = field(default_factory=list)
    integration_points: list[str] = field(default_factory=list)
    test_commands: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


# ── Handoff Document ───────────────────────────────────
@dataclass
class HandoffDoc:
    run_id: str
    stage_name: str
    agent_results: dict[str, dict[str, Any]] = field(default_factory=dict)
    next_stage_notes: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
