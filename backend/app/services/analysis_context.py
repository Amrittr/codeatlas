"""State shared between a running analysis and the API: progress, cancellation and time budget.

The analysis thread calls ``checkpoint()`` between units of work (archive entries, extracted
files, scanned folders). That is where cancellation and the time limit take effect.
Progress counts are real: ``total`` is set only when the phase knows it.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass

from app.core.errors import AppError

PHASE_UNITS = {
    "queued": None,
    "inspecting": "entries",
    "planning": "entries",
    "extracting": "files",
    "scanning": "files",
    "parsing": "files",
    "mapping": None,
    "indexing": None,
    "done": None,
}


class AnalysisCancelled(Exception):
    """Raised at a checkpoint after cancellation was requested."""


@dataclass(frozen=True, slots=True)
class ProgressSnapshot:
    phase: str
    current: int
    total: int | None
    unit: str | None


class AnalysisContext:
    def __init__(self, max_seconds: float) -> None:
        self._max_seconds = max_seconds
        self._deadline: float | None = None
        self._cancel = threading.Event()
        self._lock = threading.Lock()
        self._phase = "queued"
        self._current = 0
        self._total: int | None = None

    @classmethod
    def started(cls, max_seconds: float) -> AnalysisContext:
        context = cls(max_seconds)
        context.start()
        return context

    def start(self) -> None:
        self._deadline = time.monotonic() + self._max_seconds

    def expire_now(self) -> None:
        """Test hook: make the next checkpoint fail with a timeout."""
        self._deadline = time.monotonic() - 1

    def cancel(self) -> None:
        self._cancel.set()

    @property
    def cancel_requested(self) -> bool:
        return self._cancel.is_set()

    def checkpoint(self) -> None:
        if self._cancel.is_set():
            raise AnalysisCancelled
        if self._deadline is not None and time.monotonic() > self._deadline:
            raise AppError("analysis_timeout", "Analysis took longer than the server time limit.", 408)

    def should_stop(self) -> bool:
        """Non-raising check for code that cannot raise mid-operation (e.g. inside a parser callback)."""
        return self._cancel.is_set() or (self._deadline is not None and time.monotonic() > self._deadline)

    def set_phase(self, phase: str, total: int | None = None) -> None:
        with self._lock:
            self._phase = phase
            self._current = 0
            self._total = total

    def advance(self, amount: int = 1) -> None:
        with self._lock:
            self._current += amount

    def snapshot(self) -> ProgressSnapshot:
        with self._lock:
            return ProgressSnapshot(self._phase, self._current, self._total, PHASE_UNITS.get(self._phase))
