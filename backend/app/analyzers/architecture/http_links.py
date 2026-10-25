"""Link components that call HTTP paths to components that declare those routes.

Static analysis cannot prove where a request goes at runtime (base URLs, proxies, gateways), so
these links are inferred by matching URL paths: the leading literal segments of a client path
(``/api/projects/*/tree`` → ``api/projects``) against declared route paths and prefixes
(``APIRouter(prefix="/api/projects")``, ``app.use("/api/projects", …)``). Matches on two
segments are medium confidence; looser matches (leading ``api``/version segments stripped) are low.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.schemas.project import Confidence

_GENERIC = {"api", "v1", "v2", "v3", "rest", "graphql"}


@dataclass(frozen=True, slots=True)
class RouteRef:
    component: str
    path: str
    line: int
    url: str


@dataclass(frozen=True, slots=True)
class HttpLink:
    client: RouteRef
    server: RouteRef
    confidence: Confidence


def segments(url: str) -> list[str]:
    url = url.split("?", 1)[0].split("#", 1)[0]
    result = []
    for part in url.strip("/").split("/"):
        if not part:
            continue
        part = part.lower()
        if part[0] in ":{<*$" or "*" in part:
            result.append("*")
        else:
            result.append(part)
    return result


def _literal_prefix(parts: list[str]) -> tuple[str, ...]:
    prefix = []
    for part in parts:
        if part == "*":
            break
        prefix.append(part)
    return tuple(prefix)


def link_http(routes: list[RouteRef], clients: list[RouteRef]) -> list[HttpLink]:
    index: dict[tuple[str, ...], list[RouteRef]] = {}
    for route in routes:
        prefix = _literal_prefix(segments(route.url))
        for size in (2, 1):
            if len(prefix) >= size:
                index.setdefault(prefix[:size], []).append(route)

    links: list[HttpLink] = []
    seen: set[tuple[str, str]] = set()
    for client in clients:
        prefix = _literal_prefix(segments(client.url))
        matches: list[RouteRef] = []
        confidence = Confidence.MEDIUM
        if len(prefix) >= 2:
            matches = index.get(prefix[:2], [])
        if not matches:
            # Mounted routers often declare only the tail (/orders) under a /api prefix set elsewhere.
            stripped = tuple(part for part in prefix if part not in _GENERIC)
            if stripped:
                matches = [r for r in index.get(stripped[:1], []) if _literal_prefix(segments(r.url))[:1] == stripped[:1]]
                confidence = Confidence.LOW
        for server in matches:
            if server.component == client.component:
                continue
            key = (client.component, server.component)
            if key in seen and len([link for link in links if (link.client.component, link.server.component) == key]) >= 5:
                continue
            seen.add(key)
            links.append(HttpLink(client=client, server=server, confidence=confidence))
    return links
