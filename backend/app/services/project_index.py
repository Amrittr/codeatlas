"""Read-side index over one analyzed project: subtree slices, reveal paths and search.

Nodes are stored once, normalised (``id → node`` plus ``id → ordered child ids``). Each
response is a slice of that index, so the frontend can load the tree lazily rather than
receive the whole repository at once.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from app.schemas.project import Classification
from app.services.nodes import DirectoryRecord, FileRecord
from app.services.statistics_service import NO_EXTENSION


@dataclass
class TreeSlice:
    nodes: list[FileRecord | DirectoryRecord]
    children: dict[str, list[str]]


@dataclass
class SearchResult(TreeSlice):
    match_ids: list[str] = field(default_factory=list)
    total_matches: int = 0
    truncated: bool = False


class ProjectIndex:
    def __init__(self, nodes: dict[str, FileRecord | DirectoryRecord], children: dict[str, list[str]], root_id: str):
        self.nodes = nodes
        self.children = children
        self.root_id = root_id
        self.order = self._preorder()

    def _preorder(self) -> dict[str, int]:
        order: dict[str, int] = {}
        stack = [self.root_id]
        while stack:
            current = stack.pop()
            order[current] = len(order)
            stack.extend(reversed(self.children.get(current, ())))
        return order

    def get(self, node_id: str) -> FileRecord | DirectoryRecord | None:
        return self.nodes.get(node_id)

    def ancestors(self, node_id: str) -> list[str]:
        """Ancestor ids from the root down to the direct parent."""
        chain: list[str] = []
        parent = self.nodes[node_id].parent_id
        while parent is not None:
            chain.append(parent)
            parent = self.nodes[parent].parent_id
        chain.reverse()
        return chain

    def subtree(self, node_id: str, depth: int, *, reveal: bool = False, max_nodes: int | None = None) -> TreeSlice | None:
        """``node_id`` plus descendants up to ``depth`` levels below it.

        With ``reveal``, also returns every ancestor and the ancestors' children, so the
        client can show the node in context in the full tree. Returns ``None`` when the slice
        would exceed ``max_nodes``: a partial slice would break the "complete child lists" contract.
        """
        included: dict[str, None] = {}
        children: dict[str, list[str]] = {}

        if reveal:
            for ancestor in self.ancestors(node_id):
                included[ancestor] = None
                children[ancestor] = list(self.children[ancestor])
                included.update(dict.fromkeys(children[ancestor]))

        included[node_id] = None
        frontier = [node_id]
        for _ in range(depth):
            next_frontier: list[str] = []
            for current in frontier:
                if current not in self.children:
                    continue
                kids = self.children[current]
                children[current] = list(kids)
                included.update(dict.fromkeys(kids))
                next_frontier.extend(kids)
                if max_nodes is not None and len(included) > max_nodes:
                    return None
            if not next_frontier:
                break
            frontier = next_frontier

        ordered = sorted(included, key=self.order.__getitem__)
        return TreeSlice(nodes=[self.nodes[item] for item in ordered], children=children)

    def search(
        self,
        query: str,
        extensions: set[str],
        classifications: set[Classification],
        node_type: str,
        limit: int,
    ) -> SearchResult:
        """Case-insensitive substring match on names, or on paths when the query contains '/'.

        Returns the matches plus all their ancestors, with pruned child lists, so the client
        can render the results as a filtered tree.
        """
        needle = query.casefold()
        match_path = "/" in needle
        matches: list[str] = []
        total = 0

        for current in self.order:  # insertion order is pre-order
            if current == self.root_id:
                continue
            node = self.nodes[current]
            if node_type != "all" and node.type != node_type:
                continue
            if extensions or classifications:
                if not isinstance(node, FileRecord):
                    continue
                if extensions and (node.extension or NO_EXTENSION) not in extensions:
                    continue
                if classifications and node.classification not in classifications:
                    continue
            if needle:
                haystack = node.path if match_path else node.name
                if needle not in haystack.casefold():
                    continue
            total += 1
            if len(matches) < limit:
                matches.append(current)

        included: dict[str, None] = {self.root_id: None}
        for match in matches:
            for ancestor in self.ancestors(match):
                included[ancestor] = None
            included[match] = None

        children: dict[str, list[str]] = {}
        for item in included:
            parent = self.nodes[item].parent_id
            if parent is not None:
                children.setdefault(parent, []).append(item)
        for kids in children.values():
            kids.sort(key=self.order.__getitem__)

        ordered = sorted(included, key=self.order.__getitem__)
        return SearchResult(
            nodes=[self.nodes[item] for item in ordered],
            children=children,
            match_ids=matches,
            total_matches=total,
            truncated=total > len(matches),
        )
