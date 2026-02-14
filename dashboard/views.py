from django.db.models import Q
from django.utils import timezone
from django.shortcuts import render
from django.urls import reverse

from bugsink.transaction import durable_atomic, immediate_atomic
from bugsink.period_utils import sub_periods_from_datetime

from issues.models import Issue, IssueQuerysetStateManager
from issues.views import UncountablePaginator, GLOBAL_MUTE_OPTIONS, _apply_action, _q_for_invalid_for_action
from projects.models import Project
from teams.models import Team


STATE_FILTER_CHOICES = [
    ("open", "Open"),
    ("unresolved", "Unresolved"),
    ("muted", "Muted"),
    ("resolved", "Resolved"),
    ("all", "All"),
]

STATE_FILTER_URLS = {
    "open": "dashboard",
    "unresolved": "dashboard_unresolved",
    "muted": "dashboard_muted",
    "resolved": "dashboard_resolved",
    "all": "dashboard_all",
}

DATE_RANGE_CHOICES = [
    ("", "All time"),
    ("1h", "Last hour"),
    ("24h", "Last 24 hours"),
    ("7d", "Last 7 days"),
    ("30d", "Last 30 days"),
]

DATE_RANGE_MAP = {
    "1h": ("hour", 1),
    "24h": ("hour", 24),
    "7d": ("day", 7),
    "30d": ("day", 30),
}


def _get_user_teams(user):
    if user.is_superuser:
        return Team.objects.all()
    return Team.objects.filter(teammembership__user=user, teammembership__accepted=True).distinct()


def _get_user_projects(user):
    if user.is_superuser:
        return Project.objects.filter(is_deleted=False)
    return Project.objects.filter(
        projectmembership__user=user, projectmembership__accepted=True, is_deleted=False
    ).distinct()


def dashboard(request, state_filter="open"):
    unapplied_issue_ids = _dashboard_pt_1(request)
    with durable_atomic():
        return _dashboard_pt_2(request, state_filter, unapplied_issue_ids)


def _dashboard_pt_1(request):
    if request.method == "POST":
        with immediate_atomic():
            issue_ids = request.POST.getlist('issue_ids[]')
            user_project_ids = _get_user_projects(request.user).values_list("id", flat=True)
            issue_qs = Issue.objects.filter(pk__in=issue_ids, project_id__in=user_project_ids)
            illegal_conditions = _q_for_invalid_for_action(request.POST["action"])
            unapplied_issue_ids = list(issue_qs.filter(illegal_conditions).values_list("id", flat=True))
            _apply_action(
                IssueQuerysetStateManager, issue_qs.exclude(illegal_conditions), request.POST["action"], request.user)
            return unapplied_issue_ids
    return None


def _dashboard_pt_2(request, state_filter, unapplied_issue_ids):
    user = request.user
    teams = _get_user_teams(user)
    projects = _get_user_projects(user)

    d_state_filter = {
        "open": lambda qs: qs.filter(is_resolved=False, is_muted=False),
        "unresolved": lambda qs: qs.filter(is_resolved=False),
        "resolved": lambda qs: qs.filter(is_resolved=True),
        "muted": lambda qs: qs.filter(is_muted=True),
        "all": lambda qs: qs,
    }

    issue_list = Issue.objects.filter(
        project__in=projects, is_deleted=False
    ).select_related('project').order_by("-last_seen")

    selected_team = request.GET.get("team", "")
    if selected_team:
        issue_list = issue_list.filter(project__team_id=selected_team)

    selected_project = request.GET.get("project", "")
    if selected_project:
        issue_list = issue_list.filter(project_id=selected_project)

    selected_date_range = request.GET.get("date_range", "")
    if selected_date_range and selected_date_range in DATE_RANGE_MAP:
        period_name, nr_of_periods = DATE_RANGE_MAP[selected_date_range]
        cutoff = sub_periods_from_datetime(timezone.now(), nr_of_periods, period_name)
        issue_list = issue_list.filter(last_seen__gte=cutoff)

    issue_list = d_state_filter[state_filter](issue_list)

    q = request.GET.get("q", "")
    if q:
        issue_list = issue_list.filter(
            Q(calculated_type__icontains=q) | Q(calculated_value__icontains=q)
        )

    paginator = UncountablePaginator(issue_list, 250)
    page_number = request.GET.get("page")
    page_obj = paginator.get_page(page_number)

    from events.sparkline import get_issue_sparkline_data
    page_issue_ids = [issue.id for issue in page_obj.object_list]
    sparkline_data = get_issue_sparkline_data(page_issue_ids)
    for issue in page_obj.object_list:
        issue.sparkline_data = sparkline_data.get(issue.id, [0] * 38)

    state_url_map = {key: reverse(url_name) for key, url_name in STATE_FILTER_URLS.items()}

    return render(request, "dashboard/dashboard.html", {
        "state_filter": state_filter,
        "mute_options": GLOBAL_MUTE_OPTIONS,
        "unapplied_issue_ids": unapplied_issue_ids,
        "disable_resolve_buttons": state_filter == "resolved",
        "disable_mute_buttons": state_filter in ("resolved", "muted"),
        "disable_unmute_buttons": state_filter in ("resolved", "open"),
        "q": q,
        "page_obj": page_obj,
        "teams": teams,
        "projects": projects,
        "selected_team": selected_team,
        "selected_project": selected_project,
        "selected_date_range": selected_date_range,
        "date_range_choices": DATE_RANGE_CHOICES,
        "state_filter_choices": STATE_FILTER_CHOICES,
        "state_url_map": state_url_map,
    })
