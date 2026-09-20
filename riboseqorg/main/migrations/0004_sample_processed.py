from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("main", "0003_study_authorship_provenance"),
    ]

    operations = [
        migrations.AddField(
            model_name="sample",
            name="processed",
            field=models.BooleanField(db_index=True, default=False),
        ),
    ]
