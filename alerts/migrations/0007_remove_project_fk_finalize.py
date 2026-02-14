from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("alerts", "0006_populate_team_and_projects"),
    ]

    operations = [
        # Remove the old project FK
        migrations.RemoveField(
            model_name="messagingserviceconfig",
            name="project",
        ),
        # Make team non-nullable and set final related_name
        migrations.AlterField(
            model_name="messagingserviceconfig",
            name="team",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="service_configs",
                to="teams.team",
            ),
        ),
        # Set final related_name on M2M
        migrations.AlterField(
            model_name="messagingserviceconfig",
            name="projects",
            field=models.ManyToManyField(
                blank=True,
                related_name="service_configs",
                to="projects.project",
            ),
        ),
    ]
