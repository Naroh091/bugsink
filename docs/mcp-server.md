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

Requests without a valid token receive a `401 Unauthorized` JSON response before they reach any tool.

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

Once connected, all 16 tools appear automatically in Claude Code.

## Available Tools

### Teams

| Tool | Parameters | Description |
|------|-----------|-------------|
| `list_teams` | `limit=50`, `order="asc"` | List all teams |
| `get_team` | `team_id` (UUID) | Get a team by ID |
| `create_team` | `name`, `visibility?` | Create a new team |
| `update_team` | `team_id`, `name?`, `visibility?` | Update a team's fields |

### Projects

| Tool | Parameters | Description |
|------|-----------|-------------|
| `list_projects` | `team_id?`, `limit=50`, `order="asc"` | List projects, optionally filtered by team |
| `get_project` | `project_id` (int) | Get a project by ID |
| `create_project` | `team_id`, `name` | Create a project under a team |
| `update_project` | `project_id`, optional fields | Update a project's settings |

`update_project` accepts: `name`, `visibility`, `alert_on_new_issue`, `alert_on_regression`, `alert_on_unmute`, `retention_max_event_count`.

### Issues (read-only)

| Tool | Parameters | Description |
|------|-----------|-------------|
| `list_issues` | `project_id` (required), `sort="last_seen"`, `order="desc"`, `limit=50` | List issues for a project |
| `get_issue` | `issue_id` (UUID) | Get an issue by ID |

Valid `sort` values: `last_seen`, `digest_order`.

### Events (read-only)

| Tool | Parameters | Description |
|------|-----------|-------------|
| `list_events` | `issue_id` (required), `order="desc"`, `limit=50` | List events for an issue |
| `get_event` | `event_id` (UUID) | Get full event data including parsed JSON and stacktrace markdown |
| `get_event_stacktrace` | `event_id` (UUID) | Get stacktrace as markdown (frames, source context, locals) |

`get_event_stacktrace` is the most useful tool for debugging: it renders the full stacktrace with source lines and local variable values in a format optimised for LLMs.

### Releases

| Tool | Parameters | Description |
|------|-----------|-------------|
| `list_releases` | `project_id` (required), `order="desc"`, `limit=50` | List releases for a project |
| `get_release` | `release_id` (UUID) | Get a release by ID |
| `create_release` | `project_id`, `version` | Create a new release |

### Pagination

All list tools accept a `limit` parameter (default 50, max 250). This is intentionally simple — LLMs typically need the first N results rather than cursor-based pagination.

## Implementation Details

**Files:**

| File | Purpose |
|------|---------|
| `bugsink/mcp_server.py` | Core server: auth middleware, tool definitions, sync ORM helpers |
| `bsmain/management/commands/run_mcp_server.py` | Django management command |

**Pattern — sync helper + async tool:**

```python
def _sync_list_issues(project_id, sort, order, limit):
    from issues.models import Issue
    from issues.serializers import IssueSerializer
    ordering = _build_ordering(sort, order)
    qs = Issue.objects.filter(project_id=project_id, is_deleted=False).order_by(*ordering)[:limit]
    return IssueSerializer(qs, many=True).data

@mcp.tool(description="List issues for a project.")
async def list_issues(project_id: int, sort: str = "last_seen", order: str = "desc", limit: int = 50) -> str:
    result = await asyncio.to_thread(_sync_list_issues, project_id, sort, order, _clamp_limit(limit))
    return json.dumps(result, default=str)
```

The async/sync boundary (`asyncio.to_thread`) is necessary because Django ORM is synchronous while the MCP server runs in an async ASGI event loop.

**Auth middleware** (`BearerAuthMiddleware`) validates the `Authorization: Bearer` header against the `AuthToken` model before any request reaches the MCP tools, reusing the same 40-hex-char token format as the REST API.

**Serializers:** All tools reuse existing DRF serializers from the REST API layer (`teams/serializers.py`, `projects/serializers.py`, `issues/serializers.py`, `events/serializers.py`, `releases/serializers.py`), so the MCP and REST responses are identical.
