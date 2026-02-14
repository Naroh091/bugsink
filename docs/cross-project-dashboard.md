# Cross-Project Dashboard

The cross-project dashboard gives you a unified view of issues across all your teams and projects, so you can triage and act on problems without switching between individual project views.

## Accessing the Dashboard

Navigate to `/dashboard/` from the main navigation. The dashboard is available to all authenticated users and automatically scopes visibility based on your team and project memberships. Superusers see everything.

## Filtering

The dashboard provides several ways to narrow down the issue list:

- **State** -- Filter by Open (default), Unresolved, Muted, Resolved, or All.
- **Date range** -- Restrict to issues seen in the last hour, 24 hours, 7 days, or 30 days.
- **Team** -- Show only issues belonging to projects in a specific team.
- **Project** -- Drill down to a single project's issues.
- **Search** -- Free-text search across issue type and value fields.

Filters are applied via URL parameters, so filtered views can be bookmarked and shared.

## Bulk Actions

Select one or more issues using the checkboxes and apply batch operations:

- **Resolve** -- Mark selected issues as resolved.
- **Mute** -- Mute issues for a specific duration or until a threshold is reached.
- **Unmute** -- Remove the muted status from selected issues.
- **Delete** -- Permanently delete selected issues (with confirmation).

Action buttons adapt to the current filter state. For example, the Resolve button is disabled when you are already viewing resolved issues.

## Issue Details

Each row in the dashboard shows:

- Issue title (type and value)
- Source location (filename and function from the last frame)
- Parent project name
- Last seen timestamp
- Age (time since first seen)
- Event count
- Status indicators for resolved or muted issues
