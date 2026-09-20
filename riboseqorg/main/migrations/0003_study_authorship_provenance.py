from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0002_link_lookup_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="study",
            name="Submitters",
            field=models.CharField(blank=True, max_length=1000),
        ),
        migrations.AddField(
            model_name="study",
            name="Institution",
            field=models.CharField(blank=True, max_length=500),
        ),
        migrations.AddField(
            model_name="study",
            name="Authorship_source",
            field=models.CharField(blank=True, max_length=20),
        ),
        migrations.AddField(
            model_name="study",
            name="PMID_source",
            field=models.CharField(blank=True, max_length=20),
        ),
    ]
