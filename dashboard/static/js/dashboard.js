"use strict";

function applyFilters() {
    var team = document.getElementById("teamFilter").value;
    var project = document.getElementById("projectFilter").value;
    var dateRange = document.getElementById("dateRangeFilter").value;

    var params = new URLSearchParams(window.location.search);
    params.delete("page");

    if (team) { params.set("team", team); } else { params.delete("team"); }
    if (project) { params.set("project", project); } else { params.delete("project"); }
    if (dateRange) { params.set("date_range", dateRange); } else { params.delete("date_range"); }

    var q = params.get("q");
    if (!q) { params.delete("q"); }

    var qs = params.toString();
    window.location.href = window.location.pathname + (qs ? "?" + qs : "");
}
