"""Authentication contract for read-only Grile endpoints."""

from __future__ import annotations

from fastapi.routing import APIRoute

from auth import require_auth
from routers.grile import router


def test_grile_read_routes_require_authentication() -> None:
    routes = {
        route.path: route
        for route in router.routes
        if isinstance(route, APIRoute)
    }

    for path in ("/api/grile/overview", "/api/grile/run-status"):
        dependency_calls = {
            dependency.call for dependency in routes[path].dependant.dependencies
        }
        assert require_auth in dependency_calls
