"""Common errors and a task-local, two-attempt network budget."""
import time
from dataclasses import dataclass, field
from typing import Callable


class ServiceError(Exception):
    def __init__(self, message, status=503, *, retryable=None, code="service_error"):
        super().__init__(message)
        self.status = status
        self.retryable = (status in {429, 502, 503, 504}) if retryable is None else retryable
        self.code = code


@dataclass
class RunContext:
    """Shared by every tool in one task; never nest independent retry loops."""
    timeout_seconds: float = 180
    on_event: Callable = lambda event: None
    attempts: dict = field(default_factory=dict)
    cache: dict = field(default_factory=dict)
    events: list = field(default_factory=list)
    started: float = field(default_factory=time.monotonic)

    def remaining(self):
        remaining = self.timeout_seconds - (time.monotonic() - self.started)
        if remaining <= 0:
            raise ServiceError("Research reached its time limit. Start a new run to try again.",
                               504, retryable=False, code="task_timeout")
        return remaining

    def emit(self, step, status, message, **details):
        event = {"step": step, "status": status, "message": message,
                 "elapsed_seconds": round(time.monotonic() - self.started, 2), **details}
        self.events.append(event)
        self.on_event(event)

    def execute(self, key, step, operation, *, refresh=False):
        if key in self.cache and not refresh:
            return self.cache[key]
        while self.attempts.get(key, 0) < 2:
            self.remaining()
            self.attempts[key] = self.attempts.get(key, 0) + 1
            attempt = self.attempts[key]
            self.emit(step, "running", "Request started.", operation=key, attempt=attempt, max_attempts=2)
            try:
                result = operation()
            except ServiceError as error:
                self.emit(step, "retrying" if error.retryable and attempt < 2 else "failed",
                          "The graph request timed out." if str(error) == "__TIMEOUT__" else str(error),
                          operation=key, attempt=attempt, max_attempts=2, code=error.code)
                if not error.retryable or attempt >= 2:
                    raise
            else:
                self.cache[key] = result
                self.emit(step, "complete", "Request completed.", operation=key, attempt=attempt, max_attempts=2)
                return result
        raise ServiceError("This operation has used both allowed attempts.", 502,
                           retryable=False, code="attempt_limit")
