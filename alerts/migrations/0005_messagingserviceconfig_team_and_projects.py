from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("alerts", "0004_alter_messagingserviceconfig_kind"),
        ("teams", "0001_initial"),
        ("projects", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="messagingserviceconfig",
            name="team",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name="service_configs_new",
                to="teams.team",
            ),
        ),
        migrations.AddField(
            model_name="messagingserviceconfig",
            name="projects",
            field=models.ManyToManyField(
                blank=True,
                related_name="service_configs_new",
                to="projects.project",
            ),
        ),
    ]
