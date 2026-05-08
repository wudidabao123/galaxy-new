"""All enumerations used across Galaxy New."""

from enum import Enum


class ChatStyle(str, Enum):
    ROUND = "round"
    FREE = "free"
    PARALLEL = "parallel"


class PermissionMode(str, Enum):
    ASK = "ask"
    GUARD = "guard"
    AUTO = "auto"


class AgentStatus(str, Enum):
    DONE = "done"
    NEEDS_RETRY = "needs_retry"
    BLOCKED = "blocked"
    FAILED = "failed"


class TestStatus(str, Enum):
    PASSED = "passed"
    FAILED = "failed"
    NOT_RUN = "not_run"
    UNKNOWN = "unknown"


class GuardDecision(str, Enum):
    PASS = "pass"
    RETRY = "retry"
    BLOCK = "block"


class AuditStatus(str, Enum):
    OK = "ok"
    ERROR = "error"
    DENIED = "denied"
    CONFLICT = "conflict"
    UNKNOWN = "unknown"
