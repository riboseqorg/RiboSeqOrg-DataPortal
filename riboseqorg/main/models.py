from django.db import models

class Study(models.Model):
    Accession = models.CharField(max_length=200, blank=True)
    Name = models.CharField(max_length=200, blank=True)
    Title = models.CharField(max_length=200, blank=True)
    Organism = models.CharField(max_length=200, blank=True)
    Samples = models.CharField(max_length=200, blank=True)
    SRA = models.CharField(max_length=200, blank=True)
    Release_Date = models.CharField(max_length=200, blank=True)
    All_protocols = models.CharField(max_length=1500, blank=True)
    seq_types = models.CharField(max_length=200, blank=True)
    GSE = models.CharField(max_length=200, blank=True)
    BioProject = models.CharField(max_length=200, blank=True)
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
        return self.Accession
    


# The inconsistent naming is due to the fact that the data is coming from different sources
# SRA run info data is named as seen in that file 
# Manually curated metadata is in columns that are in all caps
class Sample(models.Model):
    verified = models.BooleanField(blank=True, default=False)
    trips = models.CharField(max_length=200, blank=True, default=False)
    gwips = models.CharField(max_length=200, blank=True, default=False)
    ribocrypt = models.CharField(max_length=200, blank=True, default=False)
    ftp = models.CharField(max_length=200, blank=True, default=False)

    Study_Accession = models.CharField(max_length=200, blank=True)
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
    BioProject = models.CharField(max_length=200, blank=True)
    Study_Pubmed_id = models.CharField(max_length=200, blank=True)
    ProjectID = models.CharField(max_length=200, blank=True)
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
    KO = models.CharField(max_length=200, blank=True)
    KD = models.CharField(max_length=200, blank=True)
    KI = models.CharField(max_length=200, blank=True)
    FRACTION = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return self.Study_Accession