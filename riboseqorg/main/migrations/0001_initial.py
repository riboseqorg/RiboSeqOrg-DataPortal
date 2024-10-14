# Generated by Django 4.2 on 2024-10-14 14:51

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="GWIPS",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("BioProject", models.CharField(max_length=100)),
                ("Organism", models.CharField(max_length=100)),
                ("gwips_db", models.CharField(max_length=100)),
                ("GWIPS_Elong_Suffix", models.CharField(max_length=100)),
                ("GWIPS_Init_Suffix", models.CharField(max_length=100)),
            ],
        ),
        migrations.CreateModel(
            name="OpenColumns",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("column_name", models.CharField(blank=True, max_length=200)),
                ("bioproject", models.CharField(blank=True, max_length=200)),
                ("values", models.CharField(blank=True, max_length=2000)),
            ],
        ),
        migrations.CreateModel(
            name="RiboCrypt",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("BioProject", models.CharField(max_length=100)),
                ("Organism", models.CharField(max_length=100)),
                ("ribocrypt_id", models.CharField(max_length=100)),
                ("Run", models.CharField(max_length=100)),
            ],
        ),
        migrations.CreateModel(
            name="Study",
            fields=[
                (
                    "BioProject",
                    models.CharField(
                        max_length=200, primary_key=True, serialize=False, unique=True
                    ),
                ),
                ("Name", models.CharField(blank=True, max_length=200)),
                ("Title", models.CharField(blank=True, max_length=200)),
                ("ScientificName", models.CharField(blank=True, max_length=200)),
                ("Samples", models.CharField(blank=True, max_length=200)),
                ("SRA", models.CharField(blank=True, max_length=200)),
                ("Release_Date", models.CharField(blank=True, max_length=200)),
                ("Description", models.CharField(blank=True, max_length=1500)),
                ("seq_types", models.CharField(blank=True, max_length=200)),
                ("GSE", models.CharField(blank=True, max_length=200)),
                ("PMID", models.CharField(blank=True, max_length=200)),
                ("Authors", models.CharField(blank=True, max_length=200)),
                ("Study_abstract", models.CharField(blank=True, max_length=1500)),
                ("Publication_title", models.CharField(blank=True, max_length=200)),
                ("doi", models.CharField(blank=True, max_length=200)),
                ("Date_published", models.CharField(blank=True, max_length=200)),
                ("PMC", models.CharField(blank=True, max_length=200)),
                ("Journal", models.CharField(blank=True, max_length=200)),
                ("Paper_abstract", models.CharField(blank=True, max_length=1500)),
                ("Email", models.CharField(blank=True, max_length=200)),
            ],
        ),
        migrations.CreateModel(
            name="Trips",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("BioProject", models.CharField(max_length=100)),
                ("Run", models.CharField(max_length=100)),
                ("Trips_id", models.CharField(max_length=100)),
                ("file_name", models.CharField(max_length=100)),
                ("study_name", models.CharField(max_length=100)),
                ("study_srp", models.CharField(max_length=100)),
                ("study_gse", models.CharField(max_length=100)),
                ("PMID", models.CharField(max_length=100)),
                ("organism", models.CharField(max_length=100)),
                ("transcriptome", models.CharField(max_length=100)),
            ],
        ),
        migrations.CreateModel(
            name="Sample",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("verified", models.BooleanField(blank=True, default=False)),
                ("trips_id", models.BooleanField(default=False)),
                ("gwips_id", models.BooleanField(default=False)),
                ("ribocrypt_id", models.BooleanField(default=False)),
                ("process_status", models.CharField(blank=True, max_length=200)),
                ("FASTA_file", models.BooleanField(default=False)),
                ("GEO", models.CharField(blank=True, max_length=200)),
                ("Run", models.CharField(blank=True, max_length=200)),
                ("spots", models.IntegerField(blank=True, null=True)),
                ("bases", models.IntegerField(blank=True, null=True)),
                ("avgLength", models.IntegerField(blank=True, null=True)),
                ("size_MB", models.IntegerField(blank=True, null=True)),
                ("Experiment", models.CharField(blank=True, max_length=200)),
                ("LibraryName", models.CharField(blank=True, max_length=200)),
                ("LibraryStrategy", models.CharField(blank=True, max_length=200)),
                ("LibrarySelection", models.CharField(blank=True, max_length=200)),
                ("LibrarySource", models.CharField(blank=True, max_length=200)),
                ("LibraryLayout", models.CharField(blank=True, max_length=200)),
                ("InsertSize", models.CharField(blank=True, max_length=200)),
                ("InsertDev", models.CharField(blank=True, max_length=200)),
                ("Platform", models.CharField(blank=True, max_length=200)),
                ("Model", models.CharField(blank=True, max_length=200)),
                ("SRAStudy", models.CharField(blank=True, max_length=200)),
                ("Study_Pubmed_id", models.CharField(blank=True, max_length=200)),
                ("Sample", models.CharField(blank=True, max_length=200)),
                ("BioSample", models.CharField(blank=True, max_length=200)),
                ("SampleType", models.CharField(blank=True, max_length=200)),
                ("TaxID", models.CharField(blank=True, max_length=200)),
                ("ScientificName", models.CharField(blank=True, max_length=200)),
                ("SampleName", models.CharField(blank=True, max_length=200)),
                ("CenterName", models.CharField(blank=True, max_length=200)),
                ("Submission", models.CharField(blank=True, max_length=200)),
                ("MONTH", models.CharField(blank=True, max_length=200)),
                ("YEAR", models.CharField(blank=True, max_length=200)),
                ("AUTHOR", models.CharField(blank=True, max_length=200)),
                ("sample_source", models.CharField(blank=True, max_length=200)),
                ("sample_title", models.CharField(blank=True, max_length=200)),
                ("LIBRARYTYPE", models.CharField(blank=True, max_length=200)),
                ("REPLICATE", models.CharField(blank=True, max_length=200)),
                ("CONDITION", models.CharField(blank=True, max_length=200)),
                ("INHIBITOR", models.CharField(blank=True, max_length=200)),
                ("BATCH", models.CharField(blank=True, max_length=200)),
                ("TIMEPOINT", models.CharField(blank=True, max_length=200)),
                ("TISSUE", models.CharField(blank=True, max_length=200)),
                ("CELL_LINE", models.CharField(blank=True, max_length=200)),
                ("FRACTION", models.CharField(blank=True, max_length=200)),
                ("ENA_first_public", models.CharField(blank=True, max_length=200)),
                ("ENA_last_update", models.CharField(blank=True, max_length=200)),
                ("INSDC_center_alias", models.CharField(blank=True, max_length=200)),
                ("INSDC_center_name", models.CharField(blank=True, max_length=200)),
                ("INSDC_first_public", models.CharField(blank=True, max_length=200)),
                ("INSDC_last_update", models.CharField(blank=True, max_length=200)),
                ("INSDC_status", models.CharField(blank=True, max_length=200)),
                ("ENA_checklist", models.CharField(blank=True, max_length=200)),
                ("GEO_Accession", models.CharField(blank=True, max_length=200)),
                ("Experiment_Date", models.CharField(blank=True, max_length=200)),
                ("date_sequenced", models.CharField(blank=True, max_length=200)),
                ("submission_date", models.CharField(blank=True, max_length=200)),
                ("date", models.CharField(blank=True, max_length=200)),
                ("STAGE", models.CharField(blank=True, max_length=200)),
                ("GENE", models.CharField(blank=True, max_length=200)),
                ("Sex", models.CharField(blank=True, max_length=200)),
                ("Strain", models.CharField(blank=True, max_length=200)),
                ("Age", models.CharField(blank=True, max_length=200)),
                ("Infected", models.CharField(blank=True, max_length=200)),
                ("Disease", models.CharField(blank=True, max_length=200)),
                ("Genotype", models.CharField(blank=True, max_length=200)),
                ("Feeding", models.CharField(blank=True, max_length=200)),
                ("Temperature", models.CharField(blank=True, max_length=200)),
                ("SiRNA", models.CharField(blank=True, max_length=200)),
                ("SgRNA", models.CharField(blank=True, max_length=200)),
                ("ShRNA", models.CharField(blank=True, max_length=200)),
                ("Plasmid", models.CharField(blank=True, max_length=200)),
                ("Growth_Condition", models.CharField(blank=True, max_length=200)),
                ("Stress", models.CharField(blank=True, max_length=200)),
                ("Cancer", models.CharField(blank=True, max_length=200)),
                ("microRNA", models.CharField(blank=True, max_length=200)),
                ("Individual", models.CharField(blank=True, max_length=200)),
                ("Antibody", models.CharField(blank=True, max_length=200)),
                ("Ethnicity", models.CharField(blank=True, max_length=200)),
                ("Dose", models.CharField(blank=True, max_length=200)),
                ("Stimulation", models.CharField(blank=True, max_length=200)),
                ("Host", models.CharField(blank=True, max_length=200)),
                ("UMI", models.CharField(blank=True, max_length=200)),
                ("Adapter", models.CharField(blank=True, max_length=200)),
                ("Separation", models.CharField(blank=True, max_length=200)),
                ("rRNA_depletion", models.CharField(blank=True, max_length=200)),
                ("Barcode", models.CharField(blank=True, max_length=200)),
                ("Monosome_purification", models.CharField(blank=True, max_length=200)),
                ("Nuclease", models.CharField(blank=True, max_length=200)),
                ("Kit", models.CharField(blank=True, max_length=200)),
                ("Info", models.TextField(blank=True)),
                (
                    "BioProject",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sample",
                        to="main.study",
                    ),
                ),
            ],
        ),
    ]
