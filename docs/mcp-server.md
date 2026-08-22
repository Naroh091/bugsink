# MCP Server

The MCP (Model Context Protocol) server lets LLM clients — such as Claude Code or any MCP-compatible agent — connect to Bugsink and autonomously investigate issues. It exposes the same data as the REST API using the same serializers and ORM queries.

## Architecture

The MCP server runs as a **separate process** alongside the main Django app:

```
Django (WSGI, port 8000)  ←→  Shared DB  ←→  MCP Server (ASGI, port 8100)
```

It is built with the [`mcp`](https://pypi.org/project/mcp/) Python SDK's streamable HTTP transport, served by [uvicorn](https://www.uvicorn.org/). This keeps Django's WSGI stack untouched.

## Starting the Server

```bash
python manage.py run_mcp_server
```

Options:

| Flag | Default | Description |
|------|---------|-------------|
| `--host` | `127.0.0.1` | Bind address |
| `--port` | `8100` | Bind port |
| `--path` | `/mcp` | Endpoint path |

Example — listen on all interfaces, port 9000:

```bash
python manage.py run_mcp_server --host 0.0.0.0 --port 9000
```

## Authentication

Every request must include a valid Bugsink API token in the `Authorization` header:

```
Authorization: Bearer <40-hex-char token>
```

Tokens are the same ones used by the REST API and can be created via the admin UI or:

```bash
python manage.py create_auth_token
```

Requests without a valid token receive a `401 Unauthorized` JSON response before they reach any tool, carrying a
`WWW-Authenticate: Bearer` challenge as required by RFC 6750.

Note that a token grants access to the whole instance: there is no per-user scoping and no read-only mode, so any
valid token can read every team and project and can also create and update them.

## Running Behind a Reverse Proxy

The MCP SDK enables DNS-rebinding protection by default, and it only accepts `Host` headers pointing at localhost.
Behind a reverse proxy that serves a public hostname, **every request is rejected with `421 Misdirected Request`**
before it reaches authentication — the most common reason a remote client cannot connect.

The allowlist is derived from `BASE_URL`, so the fix is configuration, not code: set `BASE_URL` to the public URL of
your Bugsink instance. Both `example.com` and `example.com:<any port>` are then accepted, alongside localhost.

The proxy must pass the original `Host` header through (Traefik and nginx do by default), must not strip the path
prefix (the server serves `/mcp` itself), and must not buffer responses — the transport is server-sent events. Give
the proxy a generous idle timeout for the same reason; MCP streams stay open without traffic.

Because the MCP server listens on its own port, the connect page cannot know the public URL. Set `MCP_URL` to what
clients should configure, e.g. `https://bugsink.example.com/mcp`. Left empty, the page assumes a direct connection
and points at `MCP_PORT` on `BASE_URL`'s host.

## Connecting from Claude Code

Add a remote MCP server entry in your Claude Code config (`.claude/settings.json` or the global settings):

```json
{
  "mcpServers": {
    "bugsink": {
      "type": "http",
      "url": "http://localhost:8100/mcp",
      "headers": {
        "Authorization": "Bearer <your-token>"
      }
    }
  }
}
```

Once connected, all 29 tools appear automatically in Claude Code.

## Available Tools

### Teams

| Tool | Parameters | Description |
|------|-----------|-------------|
| `list_teams` | `limit=50`, `order="asc"`, `page?`, `per_page?` | List all teams |
| `get_team` | `team_id` (UUID) | Get a team by ID |
| `create_team` | `name`, `visibility?` | Create a new team |
| `update_team` | `team_id`, `name?`, `visibility?` | Update a team's fields |

### Projects

| Tool | Parameters | Description |
|------|-----------|-------------|
| `list_projects` | `team_id?`, `limit=50`, `order="asc"`, `page?`, `per_page?` | List projects, optionally filtered by team |
| `get_project` | `project_id` (int) | Get a project by ID |
| `create_project` | `team_id`, `name` | Create a project under a team |
| `update_project` | `project_id`, optional fields | Update a project's settings |

`update_project` accepts: `name`, `visibility`, `alert_on_new_issue`, `alert_on_regression`, `alert_on_unmute`, `retention_max_event_count`.

### Issues

| Tool | Parameters | Description |
|------|-----------|-------------|
| `list_issues` | `project_id` (required), `sort`, `order`, `state`, `limit`, `page?`, `per_page?` | List issues with optional state filter |
| `get_issue` | `issue_id` (UUID) | Get an issue by ID |
| `search_issues` | `query?`, `project_id?`, `state`, `sort`, `order`, `limit`, `page?`, `per_page?` | Search issues across projects |
| `resolve_issue` | `issue_id` | Mark an issue as resolved |
| `reopen_issue` | `issue_id` | Reopen a resolved issue |
| `resolve_issue_next_release` | `issue_id` | Resolve until next release |
| `mute_issue` | `issue_id`, `period_name?`, `nr_of_periods?`, `gte_threshold?` | Mute an issue (optionally for a period or threshold) |
| `unmute_issue` | `issue_id` | Unmute an issue |
| `get_issue_stats` | `project_id?` | Get issue statistics (counts by status, recent activity) |
| `get_project_issue_summary` | `project_id` | Get project issue summary with top 10 by event count |
| `list_issue_history` | `issue_id`, `limit?` | Get issue change history (resolved, muted, etc.) |
| `add_issue_comment` | `issue_id`, `comment` | Add a comment to an issue |
| `list_issue_comments` | `issue_id`, `limit?` | List comments on an issue |
| `bulk_resolve_issues` | `issue_ids` (list), `dry_run?` | Bulk resolve issues with preview mode |
| `bulk_mute_issues` | `issue_ids` (list), `period_name?`, `nr_of_periods?`, `gte_threshold?`, `dry_run?` | Bulk mute issues with preview mode |

Valid `sort` values: `last_seen`, `digest_order`, `digested_event_count`.

Valid `state` values: `open` (default, unresolved+unmuted), `unresolved`, `resolved`, `muted`, `all`.

### Events (read-only)

| Tool | Parameters | Description |
|------|-----------|-------------|
| `list_events` | `issue_id` (required), `order="desc"`, `limit=50`, `page?`, `per_page?` | List events for an issue |
| `get_event` | `event_id` (UUID) | Get full event data including parsed JSON and stacktrace markdown |
| `get_event_stacktrace` | `event_id` (UUID) | Get stacktrace as markdown (frames, source context, locals) |

`get_event_stacktrace` is the most useful tool for debugging: it renders the full stacktrace with source lines and local variable values in a format optimised for LLMs.

### Releases

| Tool | Parameters | Description |
|------|-----------|-------------|
| `list_releases` | `project_id` (required), `order="desc"`, `limit=50`, `page?`, `per_page?` | List releases for a project |
| `get_release` | `release_id` (UUID) | Get a release by ID |
| `create_release` | `project_id`, `version` | Create a new release |

### Pagination

All list tools accept a `limit` parameter (default 50, max 250). For explicit pagination, use `page` (1-based) and `per_page`. When paginated, the response includes:

```json
{
  "items": [...],
  "total": 150,
  "page": 1,
  "per_page": 50,
  "has_more": true
}
```

## Implementation Details

**Files:**

| File | Purpose |
|------|---------|
| `bugsink/mcp_server.py` | Core server: auth middleware, tool definitions, sync ORM helpers |
| `bsmain/management/commands/run_mcp_server.py` | Django management command |

**Pattern — sync helper + async tool:**

```python
def _sync_list_issues(project_id, sort, order, state, limit):
    from issues.models import Issue
    from issues.serializers import IssueSerializer
    ordering = _build_ordering(sort, order)
    qs = Issue.objects.filter(project_id=project_id, is_deleted=False)
    if state and state != "all":
        qs = _apply_state_filter(qs, state)
    qs = qs.order_by(*ordering)[:limit]
    return IssueSerializer(qs, many=True).data

@mcp.tool(description="List issues for a project.")
async def list_issues(project_id: int, sort: str = "last_seen", order: str = "desc", state: str = "open", limit: int = 50) -> str:
    result = await asyncio.to_thread(_sync_list_issues, project_id, sort, order, state, _clamp_limit(limit))
    return json.dumps(result, default=str)
```

The async/sync boundary (`asyncio.to_thread`) is necessary because Django ORM is synchronous while the MCP server runs in an async ASGI event loop.

**Auth middleware** (`BearerAuthMiddleware`) validates the `Authorization: Bearer` header against the `AuthToken` model before any request reaches the MCP tools, reusing the same 40-hex-char token format as the REST API.

**Serializers:** All tools reuse existing DRF serializers from the REST API layer (`teams/serializers.py`, `projects/serializers.py`, `issues/serializers.py`, `events/serializers.py`, `releases/serializers.py`), so the MCP and REST responses are identical.
