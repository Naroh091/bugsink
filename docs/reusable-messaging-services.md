# Reusable Messaging Services

Messaging services (Slack, Discord, Mattermost) are defined at the **team level** and can be attached to any number of projects within that team. This means you configure a webhook once and reuse it everywhere, instead of duplicating the same URL across each project.

## Key Concepts

- A **messaging service** belongs to a team and holds the webhook configuration (URL, channel, display name).
- Each service can be **attached to multiple projects**. When an issue fires an alert in a project, all services attached to that project receive notifications.
- **Detaching** a service from a project stops alerts for that project without affecting other projects that use the same service.
- **Deleting** a service at the team level removes it from all projects.

## Managing Team Services

Team admins can manage messaging services from the team list:

1. Open the **Teams** page.
2. Click the three-dot menu on your team and select **Messaging Services**.
3. From here you can:
   - **Add** a new service (Slack, Discord, or Mattermost).
   - **Edit** an existing service's display name or webhook configuration.
   - **Test** a service to verify the webhook is working.
   - **Delete** a service (removes it from all projects).

Each service in the list shows which projects it is currently attached to.

## Attaching Services to Projects

There are three ways to connect a service to a project:

### During Project Creation

When creating a new project, the form shows clickable badges for the selected team's existing messaging services. Click a badge to select it -- the background darkens to indicate selection. Selected services are automatically attached when the project is saved.

### From the Project Alerts Page

Navigate to a project's **Alerts** page (from the project actions menu). Here you can:

- **Attach** any of the team's available services that aren't already connected.
- **Detach** a service to stop receiving alerts for this project.
- **Test** an attached service to send a test message.
- **Add** a brand-new service, which is created at the team level and automatically attached to this project.

### From the Team Messaging Services Page

After creating a service at the team level, go to any project's Alerts page to attach it.

## Supported Backends

| Backend     | Configuration         |
|-------------|-----------------------|
| Slack       | Webhook URL           |
| Discord     | Webhook URL           |
| Mattermost  | Webhook URL, optional channel override |

## Failure Tracking

Each service tracks the result of its most recent message attempt. If a webhook call fails, the service shows:

- Failure timestamp
- HTTP status code (if applicable)
- Error type and message
- Response body (for debugging webhook issues)

Failure details are visible on the service edit page. A successful message automatically clears the failure status.
