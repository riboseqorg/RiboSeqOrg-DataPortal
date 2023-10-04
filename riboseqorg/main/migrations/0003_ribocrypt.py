# Generated by Django 4.2 on 2023-10-04 11:53

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('main', '0002_rename_readfile_sample_fasta_file'),
    ]

    operations = [
        migrations.CreateModel(
            name='RiboCrypt',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('BioProject', models.CharField(max_length=100)),
                ('Organism', models.CharField(max_length=100)),
                ('ribocrypt_id', models.CharField(max_length=100)),
                ('run', models.CharField(max_length=100)),
            ],
        ),
    ]