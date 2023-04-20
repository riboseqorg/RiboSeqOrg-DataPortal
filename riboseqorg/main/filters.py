import django_filters
from .models import Study, Sample

class StudyFilter(django_filters.FilterSet):
    class Meta:
        model = Study
        fields = ['Accession', 'Name', 'Title', 'Organism', 'Samples', 'SRA', 'Release_Date', 'seq_types', 'GSE', 'BioProject', 'PMID', 'Authors', 'Study_abstract', 'Publication_title', 'doi', 'Date_published', 'PMC', 'Journal', 'Paper_abstract', 'Email']

class SampleFilter(django_filters.FilterSet):
    class Meta:
        model = Sample
        fields = ['verified', 'trips', 'gwips', 'ribocrypt', 'ftp', 'Study_Accession', 'Run', 'spots', 'bases', 'avgLength', 'size_MB', 'Experiment', 'LibraryName', 'LibraryStrategy', 'LibrarySelection', 'LibrarySource', 'LibraryLayout', 'InsertSize', 'InsertDev', 'Platform', 'Model', 'SRAStudy', 'BioProject', 'Study_Pubmed_id', 'ProjectID', 'Sample', 'BioSample', 'SampleType', 'TaxID', 'ScientificName', 'SampleName', 'CenterName', 'Submission', 'MONTH', 'YEAR', 'AUTHOR', 'sample_source', 'sample_title', 'LIBRARYTYPE', 'REPLICATE', 'CONDITION', 'INHIBITOR', 'BATCH', 'TIMEPOINT', 'TISSUE', 'CELL_LINE', 'KO', 'KD', 'KI', 'FRACTION']