from datetime import timedelta
from collections import defaultdict

from django.db.models import Count
from django.db.models.functions import TruncHour, TruncDate
from django.utils import timezone

from events.models import Event


def _get_sparkline_data(filter_field, entity_ids):
    """Returns {entity_id: [13 daily counts] + [25 hourly counts]} combining 14-day trend with 24h detail.

    The daily portion covers the 13 days before the hourly window (no overlap).
    The hourly portion covers the last 24 hours.
    """
    if not entity_ids:
        return {}

    now = timezone.now()

    # Hourly: last 24 hours
    hourly_cutoff = now - timedelta(hours=24)
    hourly_start = hourly_cutoff.replace(minute=0, second=0, microsecond=0)
    hourly_keys = [hourly_start + timedelta(hours=i) for i in range(25)]

    # Daily: 13 days ending at the hourly boundary (no overlap)
    daily_end = hourly_cutoff.replace(hour=0, minute=0, second=0, microsecond=0)
    daily_start = daily_end - timedelta(days=13)
    daily_keys = [(daily_start + timedelta(days=i)).date() for i in range(13)]

    # Query 1: daily buckets
    daily_rows = (
        Event.objects
        .filter(**{f'{filter_field}__in': entity_ids, 'digested_at__gte': daily_start, 'digested_at__lt': hourly_cutoff})
        .annotate(bucket=TruncDate('digested_at'))
        .values(filter_field, 'bucket')
        .annotate(count=Count('id'))
    )

    # Query 2: hourly buckets
    hourly_rows = (
        Event.objects
        .filter(**{f'{filter_field}__in': entity_ids, 'digested_at__gte': hourly_cutoff})
        .annotate(bucket=TruncHour('digested_at'))
        .values(filter_field, 'bucket')
        .annotate(count=Count('id'))
    )

    daily_data = defaultdict(lambda: {d: 0 for d in daily_keys})
    for row in daily_rows:
        bucket_date = row['bucket']
        eid = row[filter_field]
        if bucket_date in daily_data[eid]:
            daily_data[eid][bucket_date] = row['count']

    hourly_data = defaultdict(lambda: {h: 0 for h in hourly_keys})
    for row in hourly_rows:
        eid = row[filter_field]
        if row['bucket'] in hourly_data[eid]:
            hourly_data[eid][row['bucket']] = row['count']

    result = {}
    for eid in entity_ids:
        daily_counts = [daily_data[eid][d] for d in daily_keys]
        hourly_counts = [hourly_data[eid][h] for h in hourly_keys]
        result[eid] = daily_counts + hourly_counts
    return result


def get_issue_sparkline_data(issue_ids):
    return _get_sparkline_data('issue_id', issue_ids)


def get_project_sparkline_data(project_ids):
    return _get_sparkline_data('project_id', project_ids)
