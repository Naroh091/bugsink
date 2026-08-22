"""
MCP (Model Context Protocol) server for Bugsink.

Exposes Teams, Projects, Issues, Events, and Releases as MCP tools so that
LLMs can autonomously investigate issues.  Runs as a standalone ASGI process
(default port 8100) via ``python manage.py run_mcp_server``.
"""

import asyncio
import json
import logging
from urllib.parse import urlparse

from starlette.responses import JSONResponse

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from bugsink.version import __version__

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
                await self._unauthorized(scope, receive, send, "Authentication required")
                return

            raw = auth[7:].strip()
            if len(raw) != 40 or any(c not in "0123456789abcdef" for c in raw):
                await self._unauthorized(scope, receive, send, "Malformed Bearer token")
                return

            token_obj = await asyncio.to_thread(self._lookup_token, raw)
            if token_obj is None:
                await self._unauthorized(scope, receive, send, "Invalid Bearer token")
                return

        await self.app(scope, receive, send)

    @staticmethod
    async def _unauthorized(scope, receive, send, description):
        # RFC 6750: a 401 must carry a WWW-Authenticate challenge, or clients have no way to learn how to
        # authenticate. Shape matches the MCP SDK's own BearerAuthMiddleware; the resource_metadata parameter is
        # omitted because we do not serve OAuth protected-resource metadata (tokens are provisioned out of band).
        response = JSONResponse(
            {"error": "invalid_token", "error_description": description},
            status_code=401,
            headers={"WWW-Authenticate": f'Bearer error="invalid_token", error_description="{description}"'},
        )
        await response(scope, receive, send)

    @staticmethod
    def _lookup_token(raw):
        from bsmain.models import AuthToken
        return AuthToken.objects.filter(token=raw).first()


# ---------------------------------------------------------------------------
# Sync ORM helpers
# ---------------------------------------------------------------------------

def _clamp_limit(limit):
    return max(1, min(int(limit), MAX_LIMIT))


def _paginate(items, page, per_page):
    """Wrap a list of items in a pagination envelope."""
    total = len(items)
    start = (page - 1) * per_page
    end = start + per_page
    page_items = items[start:end]
    return {
        "items": page_items,
        "total": total,
        "page": page,
        "per_page": per_page,
        "has_more": end < total,
    }


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

def _sync_list_issues(project_id, sort, order, state, limit):
    from issues.models import Issue
    from issues.serializers import IssueSerializer
    ordering = _build_ordering(sort, order)
    if sort == "last_seen":
        ordering.append("-id" if order == "desc" else "id")
    qs = Issue.objects.filter(project_id=project_id, is_deleted=False)
    if state and state != "all":
        qs = _apply_state_filter(qs, state)
    qs = qs.order_by(*ordering)[:limit]
    return IssueSerializer(qs, many=True).data


def _apply_state_filter(qs, state):
    filters = {
        "open": {"is_resolved": False, "is_muted": False},
        "unresolved": {"is_resolved": False},
        "resolved": {"is_resolved": True, "is_muted": False},
        "muted": {"is_resolved": False, "is_muted": True},
    }
    if state in filters:
        return qs.filter(**filters[state])
    return qs


def _sync_search_issues(project_id, query, state, sort, order, limit):
    from django.db.models import Q
    from issues.models import Issue
    from issues.serializers import IssueSerializer
    ordering = _build_ordering(sort, order)
    if sort == "last_seen":
        ordering.append("-id" if order == "desc" else "id")
    qs = Issue.objects.filter(is_deleted=False)
    if project_id is not None:
        qs = qs.filter(project_id=project_id)
    if query:
        qs = qs.filter(Q(calculated_type__icontains=query) | Q(calculated_value__icontains=query))
    if state and state != "all":
        qs = _apply_state_filter(qs, state)
    qs = qs.order_by(*ordering)[:limit]
    return IssueSerializer(qs, many=True).data


def _sync_get_issue_stats(project_id):
    from datetime import timedelta
    from django.db.models import Count, Q
    from django.utils import timezone
    from issues.models import Issue

    qs = Issue.objects.filter(is_deleted=False)
    if project_id is not None:
        qs = qs.filter(project_id=project_id)

    now = timezone.now()
    seven_days_ago = now - timedelta(days=7)

    counts = qs.aggregate(
        unresolved=Count("id", filter=Q(is_resolved=False, is_muted=False)),
        resolved=Count("id", filter=Q(is_resolved=True, is_muted=False)),
        muted=Count("id", filter=Q(is_resolved=False, is_muted=True)),
        total=Count("id"),
    )

    new_issues_7d = qs.filter(first_seen__gte=seven_days_ago).count()
    recent_events_7d = qs.filter(last_seen__gte=seven_days_ago).aggregate(
        total=Count("digested_event_count")
    )["total"]

    return {
        **counts,
        "new_issues_7d": new_issues_7d,
        "recent_events_7d": recent_events_7d,
    }


def _sync_get_project_issue_summary(project_id):
    from issues.models import Issue
    from issues.serializers import IssueSerializer

    qs = Issue.objects.filter(project_id=project_id, is_deleted=False)

    stats = _sync_get_issue_stats(project_id)

    top_issues = qs.order_by("-digested_event_count", "-last_seen")[:10]

    return {
        "stats": stats,
        "top_issues": IssueSerializer(top_issues, many=True).data,
    }


def _sync_get_issue_history(issue_id, limit):
    from issues.models import Issue, TurningPoint

    issue = Issue.objects.get(pk=issue_id, is_deleted=False)

    turning_points = TurningPoint.objects.filter(issue=issue).order_by("-timestamp", "-id")[:limit]

    return {
        "issue_id": str(issue.id),
        "friendly_id": issue.friendly_id,
        "history": [
            {
                "id": tp.id,
                "kind": tp.get_kind_display(),
                "timestamp": tp.timestamp,
                "user": tp.user_id,
                "comment": tp.comment,
            }
            for tp in turning_points
        ],
    }


def _sync_add_issue_comment(issue_id, comment):
    from issues.models import Issue
    from issues.serializers import IssueCommentSerializer

    issue = Issue.objects.get(pk=issue_id, is_deleted=False)

    serializer = IssueCommentSerializer(data={"issue": str(issue.id), "comment": comment})
    serializer.is_valid(raise_exception=True)
    turning_point = serializer.save()

    return {
        "id": turning_point.id,
        "issue": str(turning_point.issue_id),
        "project": turning_point.project_id,
        "timestamp": turning_point.timestamp,
        "comment": turning_point.comment,
        "user": turning_point.user_id,
    }


def _sync_list_issue_comments(issue_id, limit):
    from issues.models import Issue, TurningPoint, TurningPointKind

    issue = Issue.objects.get(pk=issue_id, is_deleted=False)

    turning_points = TurningPoint.objects.filter(
        issue=issue,
        kind=TurningPointKind.MANUAL_ANNOTATION,
    ).order_by("-timestamp", "-id")[:limit]

    return [
        {
            "id": tp.id,
            "timestamp": tp.timestamp,
            "comment": tp.comment,
            "user": tp.user_id,
        }
        for tp in turning_points
    ]


def _sync_bulk_resolve_issues(issue_ids, dry_run):
    from issues.models import Issue, IssueStateManager, apply_issue_action
    from issues.serializers import IssueSerializer

    results = []
    for issue_id in issue_ids:
        try:
            issue = Issue.objects.get(pk=issue_id, is_deleted=False)
            if issue.is_resolved:
                results.append({"issue_id": issue_id, "status": "skipped", "reason": "already resolved"})
                continue
            if dry_run:
                results.append({"issue_id": issue_id, "status": "would_resolve", "issue": IssueSerializer(issue).data})
            else:
                apply_issue_action(IssueStateManager, issue, "resolve", user=None)
                issue.save()
                results.append({"issue_id": issue_id, "status": "resolved", "issue": IssueSerializer(issue).data})
        except Issue.DoesNotExist:
            results.append({"issue_id": issue_id, "status": "error", "reason": "not found"})

    return results


def _sync_bulk_mute_issues(issue_ids, period_name, nr_of_periods, gte_threshold, dry_run):
    from issues.models import Issue, IssueStateManager, apply_issue_action
    from issues.serializers import IssueSerializer

    results = []
    for issue_id in issue_ids:
        try:
            issue = Issue.objects.get(pk=issue_id, is_deleted=False)
            if issue.is_muted:
                results.append({"issue_id": issue_id, "status": "skipped", "reason": "already muted"})
                continue
            if issue.is_resolved:
                results.append({"issue_id": issue_id, "status": "skipped", "reason": "resolved issues cannot be muted"})
                continue

            if gte_threshold is not None:
                action = f"mute_until:{period_name},{nr_of_periods},{gte_threshold}"
            elif period_name is not None:
                action = f"mute_for:{period_name},{nr_of_periods},"
            else:
                action = "mute"

            if dry_run:
                results.append({"issue_id": issue_id, "status": "would_mute", "issue": IssueSerializer(issue).data})
            else:
                apply_issue_action(IssueStateManager, issue, action, user=None)
                issue.save()
                results.append({"issue_id": issue_id, "status": "muted", "issue": IssueSerializer(issue).data})
        except Issue.DoesNotExist:
            results.append({"issue_id": issue_id, "status": "error", "reason": "not found"})

    return results


def _sync_get_issue(issue_id):
    from issues.models import Issue
    from issues.serializers import IssueSerializer
    issue = Issue.objects.get(pk=issue_id, is_deleted=False)
    return IssueSerializer(issue).data


def _sync_resolve_issue(issue_id):
    from issues.models import Issue, IssueStateManager, apply_issue_action
    from issues.serializers import IssueSerializer
    issue = Issue.objects.get(pk=issue_id, is_deleted=False)
    apply_issue_action(IssueStateManager, issue, "resolve", user=None)
    issue.save()
    return IssueSerializer(issue).data


def _sync_reopen_issue(issue_id):
    from issues.models import Issue, IssueStateManager, apply_issue_action
    from issues.serializers import IssueSerializer
    issue = Issue.objects.get(pk=issue_id, is_deleted=False)
    apply_issue_action(IssueStateManager, issue, "reopen", user=None)
    issue.save()
    return IssueSerializer(issue).data


def _sync_resolve_issue_next_release(issue_id):
    from issues.models import Issue, IssueStateManager, apply_issue_action
    from issues.serializers import IssueSerializer
    issue = Issue.objects.get(pk=issue_id, is_deleted=False)
    apply_issue_action(IssueStateManager, issue, "resolved_next", user=None)
    issue.save()
    return IssueSerializer(issue).data


def _sync_mute_issue(issue_id, period_name, nr_of_periods, gte_threshold):
    from issues.models import Issue, IssueStateManager, apply_issue_action
    from issues.serializers import IssueSerializer
    issue = Issue.objects.get(pk=issue_id, is_deleted=False)
    if gte_threshold is not None:
        action = f"mute_until:{period_name},{nr_of_periods},{gte_threshold}"
    elif period_name is not None:
        action = f"mute_for:{period_name},{nr_of_periods},"
    else:
        action = "mute"
    apply_issue_action(IssueStateManager, issue, action, user=None)
    issue.save()
    return IssueSerializer(issue).data


def _sync_unmute_issue(issue_id):
    from issues.models import Issue, IssueStateManager, apply_issue_action
    from issues.serializers import IssueSerializer
    issue = Issue.objects.get(pk=issue_id, is_deleted=False)
    apply_issue_action(IssueStateManager, issue, "unmute", user=None)
    issue.save()
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


def _deduce_transport_security():
    """Host/Origin allowlist for the SDK's DNS-rebinding protection.

    That protection only accepts localhost by default, so behind a reverse proxy every request is rejected with a 421
    before it reaches any tool. The public hostname comes from BASE_URL; ":*" allows any port.
    """
    from bugsink.app_settings import get_settings

    base_url = get_settings().BASE_URL
    hostname = urlparse(base_url).hostname

    allowed_hosts = ["localhost", "localhost:*", "127.0.0.1", "127.0.0.1:*"]
    if hostname and hostname not in allowed_hosts:
        allowed_hosts += [hostname, f"{hostname}:*"]

    # Origin is only sent by browser-based clients; absent Origin is allowed by the SDK, so server-to-server
    # clients (Claude Code, the Claude connectors) are unaffected by this list.
    return TransportSecuritySettings(allowed_hosts=allowed_hosts, allowed_origins=[base_url])


def create_mcp_server():
    """Create and return an MCPServer instance with all Bugsink tools registered."""
    mcp = MCPServer("Bugsink", version=__version__, instructions=(
        "Bugsink MCP server. Use these tools to investigate issues, inspect stacktraces, "
        "and manage teams/projects/releases."
    ))

    # -- Teams --

    @mcp.tool(description="List teams. Returns team id, name, and visibility.")
    async def list_teams(
        limit: int = DEFAULT_LIMIT,
        order: str = "asc",
        page: int | None = None,
        per_page: int = DEFAULT_LIMIT,
    ) -> str:
        effective_limit = _clamp_limit(per_page) if page else _clamp_limit(limit)
        result = await asyncio.to_thread(_sync_list_teams, effective_limit, order)
        if page is not None:
            result = _paginate(result, page, _clamp_limit(per_page))
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
    async def list_projects(
        team_id: str | None = None,
        limit: int = DEFAULT_LIMIT,
        order: str = "asc",
        page: int | None = None,
        per_page: int = DEFAULT_LIMIT,
    ) -> str:
        effective_limit = _clamp_limit(per_page) if page else _clamp_limit(limit)
        result = await asyncio.to_thread(_sync_list_projects, team_id, effective_limit, order)
        if page is not None:
            result = _paginate(result, page, _clamp_limit(per_page))
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

    @mcp.tool(description=(
        "List issues for a project. Defaults to most recently seen first. "
        "Use state to filter: open (default, unresolved+unmuted), unresolved, resolved, muted, or all. "
        "For pagination, set page (1-based) and per_page; response includes total, has_more."
    ))
    async def list_issues(
        project_id: int,
        sort: str = "last_seen",
        order: str = "desc",
        state: str = "open",
        limit: int = DEFAULT_LIMIT,
        page: int | None = None,
        per_page: int = DEFAULT_LIMIT,
    ) -> str:
        effective_limit = _clamp_limit(per_page) if page else _clamp_limit(limit)
        result = await asyncio.to_thread(_sync_list_issues, project_id, sort, order, state, effective_limit)
        if page is not None:
            result = _paginate(result, page, _clamp_limit(per_page))
        return _json_result(result)

    @mcp.tool(description="Get a single issue by UUID.")
    async def get_issue(issue_id: str) -> str:
        result = await asyncio.to_thread(_sync_get_issue, issue_id)
        return _json_result(result)

    @mcp.tool(description=(
        "Search issues across projects. Optionally filter by project, state, or text query. "
        "Text search matches against issue type and value. "
        "For pagination, set page (1-based) and per_page; response includes total, has_more."
    ))
    async def search_issues(
        query: str | None = None,
        project_id: int | None = None,
        state: str = "open",
        sort: str = "last_seen",
        order: str = "desc",
        limit: int = DEFAULT_LIMIT,
        page: int | None = None,
        per_page: int = DEFAULT_LIMIT,
    ) -> str:
        effective_limit = _clamp_limit(per_page) if page else _clamp_limit(limit)
        result = await asyncio.to_thread(
            _sync_search_issues, project_id, query, state, sort, order, effective_limit
        )
        if page is not None:
            result = _paginate(result, page, _clamp_limit(per_page))
        return _json_result(result)

    @mcp.tool(description="Resolve an issue. Marks it as fixed.")
    async def resolve_issue(issue_id: str) -> str:
        result = await asyncio.to_thread(_sync_resolve_issue, issue_id)
        return _json_result(result)

    @mcp.tool(description="Reopen a resolved issue.")
    async def reopen_issue(issue_id: str) -> str:
        result = await asyncio.to_thread(_sync_reopen_issue, issue_id)
        return _json_result(result)

    @mcp.tool(description="Resolve an issue until the next release. The issue will be checked against future releases.")
    async def resolve_issue_next_release(issue_id: str) -> str:
        result = await asyncio.to_thread(_sync_resolve_issue_next_release, issue_id)
        return _json_result(result)

    @mcp.tool(description=(
        "Mute an issue to suppress alerts. Optionally mute for a period or until a volume threshold is reached. "
        "Examples: mute_issue(issue_id) for permanent mute, mute_issue(issue_id, period_name='day', nr_of_periods=3) "
        "to mute for 3 days, or mute_issue(issue_id, period_name='day', nr_of_periods=1, gte_threshold=10) to mute "
        "until 10 events occur in a day."
    ))
    async def mute_issue(
        issue_id: str,
        period_name: str | None = None,
        nr_of_periods: int | None = None,
        gte_threshold: int | None = None,
    ) -> str:
        result = await asyncio.to_thread(_sync_mute_issue, issue_id, period_name, nr_of_periods, gte_threshold)
        return _json_result(result)

    @mcp.tool(description="Unmute a muted issue to resume alerts.")
    async def unmute_issue(issue_id: str) -> str:
        result = await asyncio.to_thread(_sync_unmute_issue, issue_id)
        return _json_result(result)

    @mcp.tool(description=(
        "Get issue statistics. Without project_id returns global stats; with project_id returns project-level stats. "
        "Includes counts by status and recent activity (last 7 days)."
    ))
    async def get_issue_stats(project_id: int | None = None) -> str:
        result = await asyncio.to_thread(_sync_get_issue_stats, project_id)
        return _json_result(result)

    @mcp.tool(description=(
        "Get a project issue summary with stats and top 10 issues by event count."
    ))
    async def get_project_issue_summary(project_id: int) -> str:
        result = await asyncio.to_thread(_sync_get_project_issue_summary, project_id)
        return _json_result(result)

    @mcp.tool(description=(
        "Get the change history of an issue (resolved, muted, reopened, etc.)."
    ))
    async def list_issue_history(issue_id: str, limit: int = DEFAULT_LIMIT) -> str:
        result = await asyncio.to_thread(_sync_get_issue_history, issue_id, _clamp_limit(limit))
        return _json_result(result)

    @mcp.tool(description="Add a comment to an issue.")
    async def add_issue_comment(issue_id: str, comment: str) -> str:
        result = await asyncio.to_thread(_sync_add_issue_comment, issue_id, comment)
        return _json_result(result)

    @mcp.tool(description="List comments (manual annotations) on an issue.")
    async def list_issue_comments(issue_id: str, limit: int = DEFAULT_LIMIT) -> str:
        result = await asyncio.to_thread(_sync_list_issue_comments, issue_id, _clamp_limit(limit))
        return _json_result(result)

    @mcp.tool(description=(
        "Bulk resolve multiple issues. Set dry_run=true to preview without changes. "
        "Returns per-issue results with status (resolved, skipped, error)."
    ))
    async def bulk_resolve_issues(issue_ids: list[str], dry_run: bool = False) -> str:
        result = await asyncio.to_thread(_sync_bulk_resolve_issues, issue_ids, dry_run)
        return _json_result(result)

    @mcp.tool(description=(
        "Bulk mute multiple issues. Set dry_run=true to preview without changes. "
        "Optionally mute for a period or until a threshold. "
        "Returns per-issue results with status (muted, skipped, error)."
    ))
    async def bulk_mute_issues(
        issue_ids: list[str],
        period_name: str | None = None,
        nr_of_periods: int | None = None,
        gte_threshold: int | None = None,
        dry_run: bool = False,
    ) -> str:
        result = await asyncio.to_thread(
            _sync_bulk_mute_issues, issue_ids, period_name, nr_of_periods, gte_threshold, dry_run
        )
        return _json_result(result)

    # -- Events --

    @mcp.tool(description="List events for an issue. Defaults to newest first.")
    async def list_events(
        issue_id: str,
        order: str = "desc",
        limit: int = DEFAULT_LIMIT,
        page: int | None = None,
        per_page: int = DEFAULT_LIMIT,
    ) -> str:
        effective_limit = _clamp_limit(per_page) if page else _clamp_limit(limit)
        result = await asyncio.to_thread(_sync_list_events, issue_id, order, effective_limit)
        if page is not None:
            result = _paginate(result, page, _clamp_limit(per_page))
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
    async def list_releases(
        project_id: int,
        order: str = "desc",
        limit: int = DEFAULT_LIMIT,
        page: int | None = None,
        per_page: int = DEFAULT_LIMIT,
    ) -> str:
        effective_limit = _clamp_limit(per_page) if page else _clamp_limit(limit)
        result = await asyncio.to_thread(_sync_list_releases, project_id, order, effective_limit)
        if page is not None:
            result = _paginate(result, page, _clamp_limit(per_page))
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

    # streamable_http_app() already registers the route itself, so we wrap it directly with the auth middleware
    # instead of double-mounting.
    app = BearerAuthMiddleware(mcp.streamable_http_app(
        streamable_http_path=path,
        transport_security=_deduce_transport_security(),
    ))

    logger.info("Starting MCP server on %s:%s%s", host, port, path)
    uvicorn.run(app, host=host, port=port, log_level="info")
