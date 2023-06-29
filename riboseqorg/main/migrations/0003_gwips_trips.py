# Generated by Django 4.2 on 2023-06-28 16:26

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0002_rename_microrna_sample_microrna'),
    ]

    operations = [
        migrations.CreateModel(
            name='GWIPS',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('BioProject', models.CharField(max_length=100)),
                ('Organism', models.CharField(max_length=100)),
                ('gwips_db', models.CharField(max_length=100)),
                ('GWIPS_Elong_Suffix', models.CharField(max_length=100)),
                ('GWIPS_Init_Suffix', models.CharField(max_length=100)),
            ],
        ),
        migrations.CreateModel(
            name='Trips',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('BioProject', models.CharField(max_length=100)),
                ('Run', models.CharField(max_length=100)),
                ('Trips_id', models.FloatField()),
                ('file_name', models.CharField(max_length=100)),
                ('study_name', models.CharField(max_length=100)),
                ('study_srp', models.CharField(max_length=100)),
                ('study_gse', models.CharField(max_length=100)),
                ('PMID', models.CharField(max_length=100)),
                ('organism', models.CharField(max_length=100)),
                ('transcriptome', models.CharField(max_length=100)),
            ],
        ),
    ]
