from datetime import timedelta

from django import template
from django.utils import timezone
from django.utils.safestring import mark_safe

register = template.Library()


def _generate_labels(n):
    """Generate time labels for the combined 13-daily + 25-hourly sparkline."""
    now = timezone.localtime(timezone.now())
    hourly_cutoff = now - timedelta(hours=24)
    hourly_start = hourly_cutoff.replace(minute=0, second=0, microsecond=0)
    daily_end = hourly_cutoff.replace(hour=0, minute=0, second=0, microsecond=0)
    daily_start = daily_end - timedelta(days=13)

    labels = []
    for i in range(13):
        day = daily_start + timedelta(days=i)
        labels.append(day.strftime("%b %d"))
    for i in range(25):
        hour = hourly_start + timedelta(hours=i)
        labels.append(hour.strftime("%b %d, %H:%M"))

    return labels[:n]


def _render_sparkline(values):
    if not values:
        return mark_safe('')  # nosec B308 B703 — static empty string

    n = len(values)
    width = n * 5
    height = 32
    peak = max(values)
    labels = _generate_labels(n)
    seg_w = width / n

    if peak == 0:
        parts = [f'<svg viewBox="0 0 {width} {height}" preserveAspectRatio="none" class="w-full h-8">']
        for i in range(n):
            rx = round(i * seg_w, 2)
            label = labels[i] if i < len(labels) else ""
            parts.append(
                f'<rect x="{rx}" y="0" width="{round(seg_w, 2)}" height="{height}" '
                f'fill="transparent"><title>{label}: 0 events</title></rect>'
            )
        parts.append('</svg>')
        return mark_safe(''.join(parts))  # nosec B308 B703 — values are numeric, labels from strftime

    # Build points
    points = []
    peak_idx = 0
    for i, v in enumerate(values):
        x = round(i * width / (n - 1), 2) if n > 1 else 0
        y = round(height - (v / peak) * (height - 4), 2)
        points.append((x, y))
        if v == peak:
            peak_idx = i

    peak_x, peak_y = points[peak_idx]
    peak_pct_x = round(peak_x / width * 100, 1)

    line_points = ' '.join(f'{x},{y}' for x, y in points)
    area_points = f'0,{height} ' + line_points + f' {points[-1][0]},{height}'

    parts = ['<div class="relative pt-3">']

    # SVG chart
    parts.append(f'<svg viewBox="0 0 {width} {height}" preserveAspectRatio="none" class="w-full h-8">')
    parts.append(f'<polygon points="{area_points}" fill="currentColor" opacity="0.25"/>')
    parts.append(f'<polyline points="{line_points}" fill="none" stroke="currentColor" opacity="0.6" stroke-width="1.5"/>')
    parts.append(f'<circle cx="{peak_x}" cy="{peak_y}" r="2" fill="currentColor" opacity="0.8"/>')

    # Hover zones with tooltips
    for i, v in enumerate(values):
        rx = round(i * seg_w, 2)
        label = labels[i] if i < len(labels) else ""
        evt = "event" if v == 1 else "events"
        parts.append(
            f'<rect x="{rx}" y="0" width="{round(seg_w, 2)}" height="{height}" '
            f'fill="transparent"><title>{label}: {v} {evt}</title></rect>'
        )

    parts.append('</svg>')

    # Peak label as HTML overlay (avoids SVG preserveAspectRatio distortion)
    parts.append(
        f'<span class="absolute top-0 text-[10px] font-semibold opacity-60 -translate-x-1/2 pointer-events-none" '
        f'style="left:{peak_pct_x}%">{peak}</span>'
    )

    parts.append('</div>')
    return mark_safe(''.join(parts))  # nosec B308 B703 — values are numeric, labels from strftime


@register.simple_tag
def issue_sparkline(issue_id):
    from events.sparkline import get_issue_sparkline_data
    data = get_issue_sparkline_data([issue_id])
    values = data.get(issue_id, [0] * 38)
    return _render_sparkline(values)


@register.filter
def sparkline_svg(values):
    return _render_sparkline(values)
