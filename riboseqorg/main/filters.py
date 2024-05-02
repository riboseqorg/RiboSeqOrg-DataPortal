import django_filters
from .models import Study, Sample


class StudyFilter(django_filters.FilterSet):
    class Meta:
        model = Study
        fields = ['BioProject', 'Name', 'Title', 'Organism', 'Samples', 'SRA', 'Release_Date', 'seq_types', 'GSE', 'PMID', 'Authors', 'Study_abstract', 'Publication_title', 'doi', 'Date_published', 'PMC', 'Journal', 'Paper_abstract', 'Email']


class SampleFilter(django_filters.FilterSet):
    class Meta:
        model = Sample
        fields = [
            'verified',
            'BioProject',
            'Run',
            'spots',
            'bases',
            'avgLength',
            'size_MB',
            'Experiment',
            'LibraryName',
            'LibraryStrategy',
            'LibrarySelection',
            'LibrarySource',
            'LibraryLayout',
            'InsertSize',
            'InsertDev',
            'Platform',
            'Model',
            'SRAStudy',
            'Study_Pubmed_id',
            'Sample',
            'BioSample',
            'SampleType',
            'TaxID',
            'ScientificName',
            'SampleName',
            'CenterName',
            'Submission',
            'MONTH',
            'YEAR',
            'AUTHOR',
            'sample_source',
            'sample_title',
            'LIBRARYTYPE',
            'REPLICATE',
            'CONDITION',
            'INHIBITOR',
            'BATCH',
            'TIMEPOINT',
            'TISSUE',
            'CELL_LINE',
            'FRACTION',
            ]
