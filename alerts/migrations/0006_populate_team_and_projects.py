from django.db import migrations


def populate_team_and_projects(apps, schema_editor):
    MessagingServiceConfig = apps.get_model("alerts", "MessagingServiceConfig")
    for config in MessagingServiceConfig.objects.select_related("project__team").all():
        config.team = config.project.team
        config.save(update_fields=["team"])
        config.projects.add(config.project)


class Migration(migrations.Migration):

    dependencies = [
        ("alerts", "0005_messagingserviceconfig_team_and_projects"),
    ]

    operations = [
        migrations.RunPython(populate_team_and_projects, migrations.RunPython.noop),
    ]
