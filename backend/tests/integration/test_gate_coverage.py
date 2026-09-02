"""Meta-test: every mutating route is classified as ingress vs non-ingress,
and every ingress route actually depends on ``require_legal_accepted``.

Adding a new POST/PUT/PATCH/DELETE without an entry in
``app.legal.gate_registry`` fails this test. Wiring the gate but forgetting
the registry (or vice-versa) also fails this test. Rationale: the gate
existed before this test but there was no signal when a new endpoint
appeared without it — this closes that hole.
"""
from __future__ import annotations

from fastapi.routing import APIRoute

from app.legal.gate import require_legal_accepted
from app.legal.gate_registry import INGRESS_ROUTES, NON_INGRESS_ROUTES


def _walk_routes(routes):
    """FastAPI includes routers as ``_IncludedRouter`` wrappers whose
    original ``APIRouter`` is on ``.original_router``. Recurse through
    both to yield every ``APIRoute``."""
    for r in routes:
        if isinstance(r, APIRoute):
            yield r
        elif hasattr(r, "original_router"):
            yield from _walk_routes(r.original_router.routes)
        elif hasattr(r, "routes"):
            yield from _walk_routes(r.routes)


def _mutating_routes(app):
    for r in _walk_routes(app.routes):
        methods = r.methods - {"GET", "HEAD", "OPTIONS"}
        for m in methods:
            yield (m, r.path)


def _collect_dep_callables(dependant) -> set:
    """Recursively collect every dependency ``call`` in the tree."""
    out = set()
    for d in dependant.dependencies:
        if d.call is not None:
            out.add(d.call)
        out |= _collect_dep_callables(d)
    return out


def _find_route(app, method: str, path: str):
    for r in _walk_routes(app.routes):
        if r.path == path and method in r.methods:
            return r
    return None


def test_every_mutating_route_is_classified(fastapi_app) -> None:
    actual = set(_mutating_routes(fastapi_app))
    classified = INGRESS_ROUTES | NON_INGRESS_ROUTES

    unclassified = actual - classified
    stale = classified - actual
    overlap = INGRESS_ROUTES & NON_INGRESS_ROUTES

    assert not overlap, (
        "A route appears in BOTH INGRESS_ROUTES and NON_INGRESS_ROUTES — "
        f"pick one: {sorted(overlap)}"
    )
    assert not unclassified, (
        "New mutating routes have no gate-registry entry. Add each to "
        "app/legal/gate_registry.py in either INGRESS_ROUTES (and wire "
        "require_legal_accepted) or NON_INGRESS_ROUTES (with reviewer "
        f"justification):\n  {sorted(unclassified)}"
    )
    assert not stale, (
        "Registry references routes that no longer exist. Remove from "
        f"app/legal/gate_registry.py:\n  {sorted(stale)}"
    )


def test_every_ingress_route_depends_on_gate(fastapi_app) -> None:
    """Prove the wire-up: each INGRESS_ROUTE actually has
    ``require_legal_accepted`` somewhere in its dependency tree."""
    missing: list[tuple[str, str]] = []
    for method, path in sorted(INGRESS_ROUTES):
        route = _find_route(fastapi_app, method, path)
        assert route is not None, f"registry claims {method} {path} but app has no such route"
        deps = _collect_dep_callables(route.dependant)
        if require_legal_accepted not in deps:
            missing.append((method, path))
    assert not missing, (
        "INGRESS_ROUTES entries missing require_legal_accepted dependency:\n"
        f"  {missing}\n"
        "Add ``_legal: None = Depends(require_legal_accepted)`` to each handler."
    )


def test_no_non_ingress_route_has_the_gate(fastapi_app) -> None:
    """The inverse of the above. A non-ingress route with the gate wired
    is likely a copy-paste bug — it will 403 firms whose acceptance is
    pending on internal state transitions they legitimately need to make."""
    accidental: list[tuple[str, str]] = []
    for method, path in sorted(NON_INGRESS_ROUTES):
        route = _find_route(fastapi_app, method, path)
        if route is None:
            # Route was removed but still in registry — caught by the
            # 'stale' assertion in the first test. Skip here.
            continue
        deps = _collect_dep_callables(route.dependant)
        if require_legal_accepted in deps:
            accidental.append((method, path))
    assert not accidental, (
        "NON_INGRESS_ROUTES entries unexpectedly depend on "
        "require_legal_accepted. If the classification is wrong, move "
        "the entry to INGRESS_ROUTES; if the wire-up is wrong, drop the "
        f"Depends():\n  {accidental}"
    )
