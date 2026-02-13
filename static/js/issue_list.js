"use strict";

function toggleContainedCheckbox(circleDiv) {
    const checkbox = circleDiv.querySelector("[type=\"checkbox\"]");
    checkbox.checked = !checkbox.checked;
}

function matchIssueCheckboxesStateToMain(elementContainingMainCheckbox) {
    const mainCheckbox = elementContainingMainCheckbox.querySelector("[type=\"checkbox\"]");
    const checkboxes = document.querySelectorAll(".js-issue-checkbox");
    for (let i = 0; i < checkboxes.length; i++) {
        checkboxes[i].checked = mainCheckbox.checked;
    }
    updateActionBar();
}

function matchMainCheckboxStateToIssueCheckboxes() {
    const checkboxes = document.querySelectorAll(".js-issue-checkbox");
    let allChecked = true;
    let allUnchecked = true;

    for (let i = 0; i < checkboxes.length; i++) {
        if (checkboxes[i].checked) {
            allUnchecked = false;
        }
        if (!checkboxes[i].checked) {
            allChecked = false;
        }
        if (!allChecked && !allUnchecked) {
            break;
        }
    }

    const mainCheckbox = document.querySelector(".js-main-checkbox");
    if (allChecked) {
        mainCheckbox.checked = true;
    }
    if (allUnchecked) {
        mainCheckbox.checked = false;
    }
    updateActionBar();
}

function updateActionBar() {
    const checkboxes = document.querySelectorAll(".js-issue-checkbox");
    let anyChecked = false;
    for (let i = 0; i < checkboxes.length; i++) {
        if (checkboxes[i].checked) {
            anyChecked = true;
            break;
        }
    }
    const bar = document.getElementById("js-action-bar");
    if (!bar) return;
    if (anyChecked) {
        bar.classList.remove("opacity-0", "pointer-events-none");
        bar.classList.add("opacity-100");
    } else {
        bar.classList.add("opacity-0", "pointer-events-none");
        bar.classList.remove("opacity-100");
    }
}

function applySearch(event) {
    if (event.key === "Enter") {
        event.preventDefault();
        var params = new URLSearchParams(window.location.search);
        params.delete("page");
        var q = event.target.value;
        if (q) { params.set("q", q); } else { params.delete("q"); }
        var qs = params.toString();
        window.location.href = window.location.pathname + (qs ? "?" + qs : "");
    }
}

function followContainedLink(circleDiv) {
    const link = circleDiv.querySelector("a");
    window.location.href = link.href;
}
