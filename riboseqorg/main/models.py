from django.db import models

import os

def generate_link(project, run, type="reads"):
    """
    Generate Link for a specific run of a given type (default is reads)
    Ensure path is valid before returning link

    Arguments:
    - project (str): the project accession number
    - run (str): the run accession number
    - type (str): the type of link to generate (default is reads)

    Returns:
    - (str): the link to the file
    OR
    - (None): if the link is not valid
    """
    server_base = "/home/DATA/RiboSeqOrg-DataPortal-Files/RiboSeqOrg"
    path_suffixes = {
        "reads": ".collapsed.fa.gz",
        "counts": "_counts.txt",
        "bams": ".bam",
        "adapter_report": ".adapter.fa",
        "fastp": ".html",
        "fastqc": "_fastqc.html",
        "ribometric": "bamtrans_RiboMetric.html",
        "bigwig (forward)": "_pshifted_forward.bigWig",
        "bigwig (reverse)": "_pshifted_reverse.bigWig",
    }
    path_dirs = {
        "reads": "collapsed_reads",
        "counts": "counts",
        "bams": "bams",
        "adapter_report": "adapter_reports",
        "fastp": "fastp",
        "fastqc": "fastqc",
        "ribometric": "ribometric",
        "bigwig (forward)": "bigwig",
        "bigwig (reverse)": "bigwig",
    }
    project = str(project)
    run = str(run)
    if os.path.exists(
            os.path.join(server_base, path_dirs[type], run[:6],
                         run + path_suffixes[type])):
        return f"/static2/{path_dirs[type]}/{run[:6]}/{run + path_suffixes[type]}"

    elif os.path.exists(
            os.path.join(server_base, path_dirs[type], run[:6],
                         run + "_1" + path_suffixes[type])):
        return f"/static2/{path_dirs[type]}/{run[:6]}/{run}_1{path_suffixes[type]}"
    return ""

class Study(models.Model):
    BioProject = models.CharField(max_length=200, blank=False, null=False, unique=True, primary_key=True)
    Name = models.CharField(max_length=200, blank=True)
    Title = models.CharField(max_length=200, blank=True)
    Organism = models.CharField(max_length=200, blank=True)
    Samples = models.CharField(max_length=200, blank=True)
    SRA = models.CharField(max_length=200, blank=True)
    Release_Date = models.CharField(max_length=200, blank=True)
    Description = models.CharField(max_length=1500, blank=True)
    seq_types = models.CharField(max_length=200, blank=True)
    GSE = models.CharField(max_length=200, blank=True)
    PMID = models.CharField(max_length=200, blank=True)
    Authors = models.CharField(max_length=200, blank=True)
    Study_abstract = models.CharField(max_length=1500, blank=True)
    Publication_title = models.CharField(max_length=200, blank=True)
    doi = models.CharField(max_length=200, blank=True)
    Date_published = models.CharField(max_length=200, blank=True)
    PMC = models.CharField(max_length=200, blank=True)
    Journal = models.CharField(max_length=200, blank=True)
    Paper_abstract = models.CharField(max_length=1500, blank=True)
    Email = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return self.BioProject


# The inconsistent naming is due to the fact that the data is coming from different sources
# SRA run info data is named as seen in that file 
# Manually curated metadata is in columns that are in all caps
class Sample(models.Model):
    verified = models.BooleanField(blank=True, default=False)
    trips_id = models.BooleanField(default=False)
    gwips_id = models.BooleanField(default=False)
    ribocrypt_id = models.BooleanField(default=False)
    FASTA_file = models.BooleanField(default=False)

    BioProject = models.ForeignKey(Study, on_delete=models.CASCADE, to_field='BioProject', related_name="sample", blank=True, null=True)
    Run = models.CharField(max_length=200, blank=True)
    spots = models.IntegerField(blank=True, null=True)
    bases = models.IntegerField(blank=True, null=True)
    avgLength = models.IntegerField(blank=True, null=True)
    size_MB = models.IntegerField(blank=True, null=True)
    Experiment = models.CharField(max_length=200, blank=True)
    LibraryName = models.CharField(max_length=200, blank=True)
    LibraryStrategy = models.CharField(max_length=200, blank=True)
    LibrarySelection = models.CharField(max_length=200, blank=True)
    LibrarySource = models.CharField(max_length=200, blank=True)
    LibraryLayout = models.CharField(max_length=200, blank=True)
    InsertSize = models.CharField(max_length=200, blank=True)
    InsertDev = models.CharField(max_length=200, blank=True)
    Platform = models.CharField(max_length=200, blank=True)
    Model = models.CharField(max_length=200, blank=True)
    SRAStudy = models.CharField(max_length=200, blank=True)
    Study_Pubmed_id = models.CharField(max_length=200, blank=True)
    Sample = models.CharField(max_length=200, blank=True)
    BioSample = models.CharField(max_length=200, blank=True)
    SampleType = models.CharField(max_length=200, blank=True)
    TaxID = models.CharField(max_length=200, blank=True)
    ScientificName = models.CharField(max_length=200, blank=True)
    SampleName = models.CharField(max_length=200, blank=True)
    CenterName = models.CharField(max_length=200, blank=True)
    Submission = models.CharField(max_length=200, blank=True)
    MONTH = models.CharField(max_length=200, blank=True)
    YEAR = models.CharField(max_length=200, blank=True)
    AUTHOR = models.CharField(max_length=200, blank=True)
    sample_source = models.CharField(max_length=200, blank=True)
    sample_title = models.CharField(max_length=200, blank=True)
    LIBRARYTYPE = models.CharField(max_length=200, blank=True)
    REPLICATE = models.CharField(max_length=200, blank=True)
    CONDITION = models.CharField(max_length=200, blank=True)
    INHIBITOR = models.CharField(max_length=200, blank=True)
    BATCH = models.CharField(max_length=200, blank=True)
    TIMEPOINT = models.CharField(max_length=200, blank=True)
    TISSUE = models.CharField(max_length=200, blank=True)
    CELL_LINE = models.CharField(max_length=200, blank=True)
    FRACTION = models.CharField(max_length=200, blank=True)

    # Additional fields from the list
    ENA_first_public = models.CharField(max_length=200, blank=True)
    ENA_last_update = models.CharField(max_length=200, blank=True)
    INSDC_center_alias = models.CharField(max_length=200, blank=True)
    INSDC_center_name = models.CharField(max_length=200, blank=True)
    INSDC_first_public = models.CharField(max_length=200, blank=True)
    INSDC_last_update = models.CharField(max_length=200, blank=True)
    INSDC_status = models.CharField(max_length=200, blank=True)
    ENA_checklist = models.CharField(max_length=200, blank=True)
    GEO_Accession = models.CharField(max_length=200, blank=True)
    Experiment_Date = models.CharField(max_length=200, blank=True)
    date_sequenced = models.CharField(max_length=200, blank=True)
    submission_date = models.CharField(max_length=200, blank=True)
    date = models.CharField(max_length=200, blank=True)
    STAGE = models.CharField(max_length=200, blank=True)
    GENE = models.CharField(max_length=200, blank=True)
    Sex = models.CharField(max_length=200, blank=True)
    Strain = models.CharField(max_length=200, blank=True)
    Age = models.CharField(max_length=200, blank=True)
    Infected = models.CharField(max_length=200, blank=True)
    Disease = models.CharField(max_length=200, blank=True)
    Genotype = models.CharField(max_length=200, blank=True)
    Feeding = models.CharField(max_length=200, blank=True)
    Temperature = models.CharField(max_length=200, blank=True)
    SiRNA = models.CharField(max_length=200, blank=True)
    SgRNA = models.CharField(max_length=200, blank=True)
    ShRNA = models.CharField(max_length=200, blank=True)
    Plasmid = models.CharField(max_length=200, blank=True)
    Growth_Condition = models.CharField(max_length=200, blank=True)
    Stress = models.CharField(max_length=200, blank=True)
    Cancer = models.CharField(max_length=200, blank=True)
    microRNA = models.CharField(max_length=200, blank=True)
    Individual = models.CharField(max_length=200, blank=True)
    Antibody = models.CharField(max_length=200, blank=True)
    Ethnicity = models.CharField(max_length=200, blank=True)
    Dose = models.CharField(max_length=200, blank=True)
    Stimulation = models.CharField(max_length=200, blank=True)
    Host = models.CharField(max_length=200, blank=True)
    UMI = models.CharField(max_length=200, blank=True)
    Adapter = models.CharField(max_length=200, blank=True)
    Separation = models.CharField(max_length=200, blank=True)
    rRNA_depletion = models.CharField(max_length=200, blank=True)
    Barcode = models.CharField(max_length=200, blank=True)
    Monosome_purification = models.CharField(max_length=200, blank=True)
    Nuclease = models.CharField(max_length=200, blank=True)
    Kit = models.CharField(max_length=200, blank=True)
    Info = models.TextField(blank=True)

    def __str__(self):
        return self.Run
    
    @property
    def fastqc_link(self):
        return generate_link(self.BioProject, self.Run, "fastqc")
    
    @property
    def fastp_link(self):
        return generate_link(self.BioProject, self.Run, "fastp")
    
    @property
    def adapter_report_link(self):
        return generate_link(self.BioProject, self.Run, "adapter_report")
    
    @property
    def ribometric_link(self):
        return generate_link(self.BioProject, self.Run, "ribometric")
    
    @property
    def reads_link(self):
        return generate_link(self.BioProject, self.Run, "reads")
    
    @property
    def counts_link(self):
        return generate_link(self.BioProject, self.Run, "counts")
    
    @property
    def bam_link(self):
        return generate_link(self.BioProject, self.Run, "bams")

    @property
    def bigwig_forward_link(self):
        return generate_link(self.BioProject, self.Run, "bigwig (forward)")
    
    @property
    def bigwig_reverse_link(self):
        return generate_link(self.BioProject, self.Run, "bigwig (reverse)")

class OpenColumns(models.Model):
    column_name = models.CharField(max_length=200, blank=True)
    bioproject = models.CharField(max_length=200, blank=True)
    values = models.CharField(max_length=2000, blank=True)

    def __str__(self):
        return self.column_name


class Trips(models.Model):
    BioProject = models.CharField(max_length=100)
    Run = models.CharField(max_length=100)
    Trips_id = models.FloatField()
    file_name = models.CharField(max_length=100)
    study_name = models.CharField(max_length=100)
    study_srp = models.CharField(max_length=100)
    study_gse = models.CharField(max_length=100)
    PMID = models.CharField(max_length=100)
    organism = models.CharField(max_length=100)
    transcriptome = models.CharField(max_length=100)

    def __str__(self):
        return f"Trips {self.pk}: {self.file_name}"


class GWIPS(models.Model):
    BioProject = models.CharField(max_length=100)
    Organism = models.CharField(max_length=100)
    gwips_db = models.CharField(max_length=100)
    GWIPS_Elong_Suffix = models.CharField(max_length=100)
    GWIPS_Init_Suffix = models.CharField(max_length=100)

    def __str__(self):
        return f"GWIPS {self.pk}: {self.gwips_db}"


class RiboCrypt(models.Model):
    BioProject = models.CharField(max_length=100)
    Organism = models.CharField(max_length=100)
    ribocrypt_id = models.CharField(max_length=100)
    Run = models.CharField(max_length=100)

    def __str__(self):
        return f"RiboCrypt {self.pk}: {self.ribocrypt_id}"
