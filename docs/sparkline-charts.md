# Sparkline Charts

Sparkline charts provide a compact visual summary of event activity over time. They appear in issue lists and project views so you can spot trends and regressions at a glance without navigating to a dedicated analytics page.

## Where They Appear

- **Cross-project dashboard** (`/dashboard/`) -- Each issue row shows a sparkline in the "Evolution" column, between the issue title and the "Last Seen" timestamp.
- **Per-project issue list** (`/issues/<project_id>/`) -- Same layout as the dashboard.
- **Project list** (`/projects/`) -- Each project row shows a sparkline in the "Evolution" column, between the event counts and the actions menu.
- **Issue detail sidebar** -- The "Issue Key Info" panel on the right-hand side includes an "Evolution" section with a sparkline for that issue.

## What the Chart Shows

Each sparkline combines two time scales into a single chart:

- **13 daily buckets** covering days -14 through -2 (relative to the start of the hourly window). This gives a two-week trend overview.
- **25 hourly buckets** covering the last 24 hours. This gives recent detail.

The two regions are non-overlapping and stitched together seamlessly, so the left side of the chart shows the longer trend and the right side zooms into recent activity.

## Interactivity

- **Hover tooltips** -- Hovering over any point in the chart shows a native browser tooltip with the time bucket and event count (e.g., "Feb 14, 15:00: 3 events").
- **Peak highlight** -- The highest point in the chart is marked with a dot on the line. The peak event count is displayed as a label above the chart.

## Technical Details

### Data Aggregation (`events/sparkline.py`)

Two public functions share a common implementation:

- `get_issue_sparkline_data(issue_ids)` -- Aggregates events by `issue_id`.
- `get_project_sparkline_data(project_ids)` -- Aggregates events by `project_id`.

Both return a dictionary mapping entity IDs to a list of 38 integers (13 daily + 25 hourly counts). The queries use `TruncDate` and `TruncHour` on the `digested_at` field and hit existing composite indexes on the `Event` model:

- `(issue, digested_at)` for per-issue queries
- `(project, digested_at)` for per-project queries

Data is fetched in two bulk queries (one for daily, one for hourly) per view, keeping database overhead minimal.

### SVG Rendering (`theme/templatetags/sparkline.py`)

The sparkline is rendered as an inline SVG area chart wrapped in a `<div>`:

- **Area fill** with `opacity="0.25"` and **line stroke** with `opacity="0.6"`, both using `currentColor` so the chart adapts to light/dark mode automatically.
- **`preserveAspectRatio="none"`** on the SVG ensures the chart fills its container width.
- **Peak label** rendered as an HTML `<span>` overlay (not SVG text) to avoid distortion from the non-uniform SVG scaling.
- **Tooltip zones** are transparent `<rect>` elements with `<title>` children for native browser tooltips.

Two entry points:

- `sparkline_svg` -- A template filter (`{{ values|sparkline_svg }}`) used in list views where sparkline data is pre-attached to each object by the view.
- `issue_sparkline` -- A template tag (`{% issue_sparkline issue.id %}`) used in the issue detail sidebar. It fetches sparkline data for a single issue directly, avoiding the need to modify multiple issue detail views.

### Responsive Behavior

Sparkline columns use Tailwind responsive breakpoints to hide on smaller screens:

- Dashboard and issue list: `hidden md:block` (visible from 768px).
- Project list: `hidden lg:block` (visible from 1024px).
- Issue detail sidebar: always visible (the sidebar itself is `hidden xl:flex`).
