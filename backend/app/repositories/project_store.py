"""In-memory, time-limited store for analysis results.

Results hold only metadata (names, paths, sizes, classifications), never file contents.
They expire after ``ttl_seconds``. Oldest results are evicted first when more than
``max_projects`` are stored, or when the stored projects together exceed ``max_nodes``. Memory
grows with nodes, not projects (about 0.67 KB per node, measured; see docs/TESTING.md), so the node budget
is what bounds memory. The newest project is always kept. Everything is lost on restart, which
is intended until persistent storage is introduced.
"""

from __future__ import annotations

import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass

from app.analyzers.architecture.builder import ArchitectureResult
from app.schemas.project import ProjectDetails
from app.services.project_index import ProjectIndex


@dataclass
class StoredProject:
    details: ProjectDetails
    index: ProjectIndex
    expires_at: float
    architecture: ArchitectureResult | None = None


class ProjectStore:
    def __init__(
        self,
        ttl_seconds: float,
        max_projects: int,
        max_nodes: int | None = None,
        clock: Callable[[], float] = time.monotonic,
    ):
        self._ttl = ttl_seconds
        self._max = max_projects
        self._max_nodes = max_nodes
        self._clock = clock
        self._items: OrderedDict[str, StoredProject] = OrderedDict()
        self._lock = threading.Lock()

    def put(self, details: ProjectDetails, index: ProjectIndex, architecture: ArchitectureResult | None = None) -> StoredProject:
        with self._lock:
            self._purge_expired()
            stored = StoredProject(
                details=details, index=index, expires_at=self._clock() + self._ttl, architecture=architecture
            )
            self._items[details.project.id] = stored
            while len(self._items) > 1 and (len(self._items) > self._max or self._over_node_budget()):
                self._items.popitem(last=False)
            return stored

    def _over_node_budget(self) -> bool:
        if self._max_nodes is None:
            return False
        return sum(item.details.project.node_count for item in self._items.values()) > self._max_nodes

    def get(self, project_id: str) -> StoredProject | None:
        with self._lock:
            self._purge_expired()
            return self._items.get(project_id)

    def delete(self, project_id: str) -> bool:
        with self._lock:
            return self._items.pop(project_id, None) is not None

    def __len__(self) -> int:
        with self._lock:
            self._purge_expired()
            return len(self._items)

    def _purge_expired(self) -> None:
        now = self._clock()
        for project_id in [key for key, item in self._items.items() if item.expires_at <= now]:
            del self._items[project_id]
