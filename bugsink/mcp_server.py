"""
MCP (Model Context Protocol) server for Bugsink.

Exposes Teams, Projects, Issues, Events, and Releases as MCP tools so that
LLMs can autonomously investigate issues.  Runs as a standalone ASGI process
(default port 8100) via ``python manage.py run_mcp_server``.
"""

import asyncio
import json
import logging

from starlette.responses import JSONResponse

from mcp.server.fastmcp import FastMCP

logger = logging.getLogger("bugsink.mcp")

MAX_LIMIT = 250
DEFAULT_LIMIT = 50


# ---------------------------------------------------------------------------
# Authentication middleware
# ---------------------------------------------------------------------------

class BearerAuthMiddleware:
    """ASGI middleware that validates Bearer tokens against the AuthToken model."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            auth = headers.get(b"authorization", b"").decode()

            if not auth.startswith("Bearer "):
                response = JSONResponse({"error": "Missing or invalid Authorization header"}, status_code=401)
                await response(scope, receive, send)
                return

            raw = auth[7:].strip()
            if len(raw) != 40 or any(c not in "0123456789abcdef" for c in raw):
                response = JSONResponse({"error": "Malformed Bearer token"}, status_code=401)
                await response(scope, receive, send)
                return

            token_obj = await asyncio.to_thread(self._lookup_token, raw)
            if token_obj is None:
                response = JSONResponse({"error": "Invalid Bearer token"}, status_code=401)
                await response(scope, receive, send)
                return

        await self.app(scope, receive, send)

    @staticmethod
    def _lookup_token(raw):
        from bsmain.models import AuthToken
        return AuthToken.objects.filter(token=raw).first()


# ---------------------------------------------------------------------------
# Sync ORM helpers
# ---------------------------------------------------------------------------

def _clamp_limit(limit):
    return max(1, min(int(limit), MAX_LIMIT))


def _build_ordering(field, order):
    prefix = "-" if order == "desc" else ""
    return [f"{prefix}{field}"]


# -- Teams --

def _sync_list_teams(limit, order):
    from teams.models import Team
    from teams.serializers import TeamListSerializer
    qs = Team.objects.order_by(*_build_ordering("name", order))[:limit]
    return TeamListSerializer(qs, many=True).data


def _sync_get_team(team_id):
    from teams.models import Team
    from teams.serializers import TeamDetailSerializer
    team = Team.objects.get(pk=team_id)
    return TeamDetailSerializer(team).data


def _sync_create_team(name, visibility):
    from teams.serializers import TeamCreateUpdateSerializer
    from teams.serializers import TeamDetailSerializer
    data = {"name": name}
    if visibility is not None:
        data["visibility"] = visibility
    serializer = TeamCreateUpdateSerializer(data=data)
    serializer.is_valid(raise_exception=True)
    team = serializer.save()
    return TeamDetailSerializer(team).data


def _sync_update_team(team_id, name, visibility):
    from teams.models import Team
    from teams.serializers import TeamCreateUpdateSerializer
    from teams.serializers import TeamDetailSerializer
    team = Team.objects.get(pk=team_id)
    data = {}
    if name is not None:
        data["name"] = name
    if visibility is not None:
        data["visibility"] = visibility
    serializer = TeamCreateUpdateSerializer(team, data=data, partial=True)
    serializer.is_valid(raise_exception=True)
    team = serializer.save()
    return TeamDetailSerializer(team).data


# -- Projects --

def _sync_list_projects(team_id, limit, order):
    from projects.models import Project
    from projects.serializers import ProjectListSerializer
    qs = Project.objects.filter(is_deleted=False)
    if team_id is not None:
        qs = qs.filter(team_id=team_id)
    qs = qs.order_by(*_build_ordering("name", order))[:limit]
    return ProjectListSerializer(qs, many=True).data


def _sync_get_project(project_id):
    from projects.models import Project
    from projects.serializers import ProjectDetailSerializer
    project = Project.objects.get(pk=project_id)
    return ProjectDetailSerializer(project).data


def _sync_create_project(team_id, name):
    from projects.serializers import ProjectCreateUpdateSerializer
    from projects.serializers import ProjectDetailSerializer
    from teams.models import Team
    team = Team.objects.get(pk=team_id)
    serializer = ProjectCreateUpdateSerializer(data={"team": team.pk, "name": name})
    serializer.is_valid(raise_exception=True)
    project = serializer.save()
    return ProjectDetailSerializer(project).data


def _sync_update_project(project_id, **fields):
    from projects.models import Project
    from projects.serializers import ProjectCreateUpdateSerializer
    from projects.serializers import ProjectDetailSerializer
    project = Project.objects.get(pk=project_id)
    data = {k: v for k, v in fields.items() if v is not None}
    serializer = ProjectCreateUpdateSerializer(project, data=data, partial=True)
    serializer.is_valid(raise_exception=True)
    project = serializer.save()
    return ProjectDetailSerializer(project).data


# -- Issues --

def _sync_list_issues(project_id, sort, order, limit):
    from issues.models import Issue
    from issues.serializers import IssueSerializer
    ordering = _build_ordering(sort, order)
    if sort == "last_seen":
        ordering.append("-id" if order == "desc" else "id")
    qs = Issue.objects.filter(project_id=project_id, is_deleted=False).order_by(*ordering)[:limit]
    return IssueSerializer(qs, many=True).data


def _sync_get_issue(issue_id):
    from issues.models import Issue
    from issues.serializers import IssueSerializer
    issue = Issue.objects.get(pk=issue_id, is_deleted=False)
    return IssueSerializer(issue).data


# -- Events --

def _sync_list_events(issue_id, order, limit):
    from events.models import Event
    from events.serializers import EventListSerializer
    qs = Event.objects.filter(issue_id=issue_id).order_by(*_build_ordering("digest_order", order))[:limit]
    return EventListSerializer(qs, many=True).data


def _sync_get_event(event_id):
    from events.models import Event
    from events.serializers import EventDetailSerializer
    event = Event.objects.get(pk=event_id)
    return EventDetailSerializer(event).data


def _sync_get_event_stacktrace(event_id):
    from events.models import Event
    from events.markdown_stacktrace import render_stacktrace_md
    event = Event.objects.get(pk=event_id)
    return render_stacktrace_md(event, in_app_only=False, include_locals=True)


# -- Releases --

def _sync_list_releases(project_id, order, limit):
    from releases.models import Release
    from releases.serializers import ReleaseListSerializer
    qs = Release.objects.filter(project_id=project_id).order_by(*_build_ordering("date_released", order))[:limit]
    return ReleaseListSerializer(qs, many=True).data


def _sync_get_release(release_id):
    from releases.models import Release
    from releases.serializers import ReleaseDetailSerializer
    release = Release.objects.get(pk=release_id)
    return ReleaseDetailSerializer(release).data


def _sync_create_release(project_id, version):
    from releases.serializers import ReleaseCreateSerializer
    from releases.serializers import ReleaseDetailSerializer
    from projects.models import Project
    project = Project.objects.get(pk=project_id)
    serializer = ReleaseCreateSerializer(data={"project": project.pk, "version": version})
    serializer.is_valid(raise_exception=True)
    release = serializer.save()
    return ReleaseDetailSerializer(release).data


# ---------------------------------------------------------------------------
# MCP server factory
# ---------------------------------------------------------------------------

def _json_result(data):
    """Serialize ORM/serializer output to a JSON string for MCP text content."""
    return json.dumps(data, default=str)


def create_mcp_server():
    """Create and return a FastMCP instance with all Bugsink tools registered."""
    mcp = FastMCP("Bugsink", instructions=(
        "Bugsink MCP server. Use these tools to investigate issues, inspect stacktraces, "
        "and manage teams/projects/releases."
    ))

    # -- Teams --

    @mcp.tool(description="List teams. Returns team id, name, and visibility.")
    async def list_teams(limit: int = DEFAULT_LIMIT, order: str = "asc") -> str:
        result = await asyncio.to_thread(_sync_list_teams, _clamp_limit(limit), order)
        return _json_result(result)

    @mcp.tool(description="Get a single team by UUID.")
    async def get_team(team_id: str) -> str:
        result = await asyncio.to_thread(_sync_get_team, team_id)
        return _json_result(result)

    @mcp.tool(description="Create a new team.")
    async def create_team(name: str, visibility: str | None = None) -> str:
        result = await asyncio.to_thread(_sync_create_team, name, visibility)
        return _json_result(result)

    @mcp.tool(description="Update an existing team. Only provided fields are changed.")
    async def update_team(team_id: str, name: str | None = None, visibility: str | None = None) -> str:
        result = await asyncio.to_thread(_sync_update_team, team_id, name, visibility)
        return _json_result(result)

    # -- Projects --

    @mcp.tool(description="List projects. Optionally filter by team UUID. Hides soft-deleted projects.")
    async def list_projects(team_id: str | None = None, limit: int = DEFAULT_LIMIT, order: str = "asc") -> str:
        result = await asyncio.to_thread(_sync_list_projects, team_id, _clamp_limit(limit), order)
        return _json_result(result)

    @mcp.tool(description="Get a single project by integer ID.")
    async def get_project(project_id: int) -> str:
        result = await asyncio.to_thread(_sync_get_project, project_id)
        return _json_result(result)

    @mcp.tool(description="Create a new project under a team.")
    async def create_project(team_id: str, name: str) -> str:
        result = await asyncio.to_thread(_sync_create_project, team_id, name)
        return _json_result(result)

    @mcp.tool(description="Update an existing project. Only provided fields are changed.")
    async def update_project(
        project_id: int,
        name: str | None = None,
        visibility: str | None = None,
        alert_on_new_issue: bool | None = None,
        alert_on_regression: bool | None = None,
        alert_on_unmute: bool | None = None,
        retention_max_event_count: int | None = None,
    ) -> str:
        result = await asyncio.to_thread(
            _sync_update_project, project_id,
            name=name, visibility=visibility,
            alert_on_new_issue=alert_on_new_issue,
            alert_on_regression=alert_on_regression,
            alert_on_unmute=alert_on_unmute,
            retention_max_event_count=retention_max_event_count,
        )
        return _json_result(result)

    # -- Issues --

    @mcp.tool(description="List issues for a project. Defaults to most recently seen first.")
    async def list_issues(
        project_id: int,
        sort: str = "last_seen",
        order: str = "desc",
        limit: int = DEFAULT_LIMIT,
    ) -> str:
        result = await asyncio.to_thread(_sync_list_issues, project_id, sort, order, _clamp_limit(limit))
        return _json_result(result)

    @mcp.tool(description="Get a single issue by UUID.")
    async def get_issue(issue_id: str) -> str:
        result = await asyncio.to_thread(_sync_get_issue, issue_id)
        return _json_result(result)

    # -- Events --

    @mcp.tool(description="List events for an issue. Defaults to newest first.")
    async def list_events(issue_id: str, order: str = "desc", limit: int = DEFAULT_LIMIT) -> str:
        result = await asyncio.to_thread(_sync_list_events, issue_id, order, _clamp_limit(limit))
        return _json_result(result)

    @mcp.tool(description="Get a single event by UUID. Includes full event data and stacktrace markdown.")
    async def get_event(event_id: str) -> str:
        result = await asyncio.to_thread(_sync_get_event, event_id)
        return _json_result(result)

    @mcp.tool(description=(
        "Get the stacktrace of an event as markdown. "
        "Includes source context and local variables. Best tool for investigating errors."
    ))
    async def get_event_stacktrace(event_id: str) -> str:
        return await asyncio.to_thread(_sync_get_event_stacktrace, event_id)

    # -- Releases --

    @mcp.tool(description="List releases for a project. Defaults to newest first.")
    async def list_releases(project_id: int, order: str = "desc", limit: int = DEFAULT_LIMIT) -> str:
        result = await asyncio.to_thread(_sync_list_releases, project_id, order, _clamp_limit(limit))
        return _json_result(result)

    @mcp.tool(description="Get a single release by UUID.")
    async def get_release(release_id: str) -> str:
        result = await asyncio.to_thread(_sync_get_release, release_id)
        return _json_result(result)

    @mcp.tool(description="Create a new release for a project.")
    async def create_release(project_id: int, version: str) -> str:
        result = await asyncio.to_thread(_sync_create_release, project_id, version)
        return _json_result(result)

    return mcp


# ---------------------------------------------------------------------------
# Server runner
# ---------------------------------------------------------------------------

def run_mcp_server(host="127.0.0.1", port=8100, path="/mcp"):
    """Build the Starlette ASGI app with auth middleware and run with uvicorn."""
    import uvicorn

    mcp = create_mcp_server()

    # streamable_http_app() already registers the route at /mcp internally,
    # so we wrap it directly with the auth middleware instead of double-mounting.
    app = BearerAuthMiddleware(mcp.streamable_http_app())

    logger.info("Starting MCP server on %s:%s%s", host, port, path)
    uvicorn.run(app, host=host, port=port, log_level="info")
