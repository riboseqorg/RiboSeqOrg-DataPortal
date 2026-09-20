from django.http import HttpRequest
from django.db.models import Q
from typing import List, Dict

from urllib.parse import parse_qsl

from .datafiles import find_run_file
from .models import Sample


def get_clean_names() -> dict:
    '''
    Return a dictionary of clean names to original names as in database

    Returns:
        clean_names: dictionary
    '''
    clean_names = {
        'Run': 'Run Accession',
        'spots': 'Total Number of Spots (Original file))',
        'bases': 'Total Number of Bases (Original file)',
        'avgLength': 'Average Read Length',
        'size_MB': 'Original File Size (MB)',
        'LibraryName': 'Library Name',
        'LibraryStrategy': 'Library Strategy',
        'LibrarySelection': 'Library Selection',
        'LibrarySource': 'Library Source',
        'LibraryLayout': 'Library Layout',
        'InsertSize': 'Insert Size',
        'InsertDev': 'Insert Deviation',
        'Platform': 'Platform',
        'Model': 'Model',
        'SRAStudy':  'SRA Project Accession (SRP)',
        'BioProject': 'BioProject',
        'Study_Pubmed_id': 'PubMed ID',
        'Sample': 'Sample',
        'BioSample': 'BioSample',
        'SampleType': 'Sample Type',
        'TaxID': 'Organism TaxID',
        'ScientificName': 'Organism',
        'SampleName': 'Sample Name',
        'CenterName': 'Center Name',
        'Submission': 'Submission',
        'MONTH': 'Month',
        'YEAR': 'Year',
        'AUTHOR': 'Author',
        'sample_source': 'Sample Source',
        'sample_title': 'Sample Title',
        'ENA_first_public': 'ENA First Public',
        'ENA_last_update': 'ENA Last Update',
        'INSDC_center_alias': 'INSDC Center Alias',
        'INSDC_center_name': 'INSDC Center Name',
        'INSDC_first_public': 'INSDC First Public',
        'INSDC_last_update': 'INSDC Last Update',
        'INSDC_status': 'INSDC Status',
        'GEO_Accession': 'GEO Accession',
        'Experiment_Date': 'Date of Experiment',
        'date_sequenced': 'Date of Sequencing',
        'submission_date': 'Submission Date',
        'date': 'Date',
        'Experiment': 'Experiment ID',
        'CELL_LINE': 'Cell-Line',
        'TISSUE': 'Tissue',
        'INHIBITOR': 'Inhibitor',
        'TIMEPOINT': 'Timepoint',
        'FRACTION': 'Cellular-Compartment',
        'REPLICATE': 'Replicate-Number',
        'CONDITION': 'Condition',
        'LIBRARYTYPE': 'Library-Type',
        'STAGE': 'Stage',
        'GENE': 'Gene',
        'Sex': 'Sex',
        'Strain': 'Strain',
        'Age': 'Age',
        'Infected': 'Infected',
        'Disease': 'Disease',
        'Genotype': 'Genotype',
        'Feeding': 'Feeding',
        'Temperature': 'Temperature',
        'SiRNA': 'SiRNA',
        'SgRNA': 'SgRNA',
        'ShRNA': 'ShRNA',
        'Plasmid': 'Plasmid',
        'Growth_Condition': 'Growth-Condition',
        'Stress': 'Stress',
        'Cancer': 'Cancer',
        'microRNA': 'MicroRNA',
        'Individual': 'Individual',
        'Antibody': 'Antibody Used',
        'Ethnicity': 'Ethnicity',
        'Dose': 'Dose',
        'Stimulation': 'Stimulation',
        'Host': 'Host Organism',
        'UMI': 'Unique Molecular Identifier (UMI)',
        'Adapter': 'Adapter Sequence',
        'Separation': 'Mode of Separation',
        'rRNA_depletion': 'Mode of rRNA depletion',
        'Barcode': 'Barcode Information',
        'Monosome_purification': 'Mode of Purification',
        'Nuclease': 'Nucelase Used',
        'Kit': 'Kit Used',
        # 'Organism': 'Organism',
        'PMID': 'PubMed',
        'count': 'count',
        'verified': 'verified',
        'trips_id': 'trips_id',
        'gwips_id': 'gwips_id',
        'ribocrypt_id': 'ribocrypt_id',
        'FASTA_file': 'FASTA_file',
        'processed': 'processed',
    }
    return clean_names


def get_original_name(name: str, clean_names: dict) -> str:
    """
    Get the original name of a parameter from the clean name.

    Arguments:
    - name (str): the clean name of the parameter
    - clean_names (dict): the dictionary of clean names to original names

    Returns:
    - (str): the original name of the parameter
    """
    for original_name, clean_name in clean_names.items():
        if clean_name == name:
            return original_name

    return name


def build_query(
    request: HttpRequest,
    query_params: List[tuple],
    clean_names: Dict[str, str]
) -> Q:
    """
    Build a query based on the query parameters.

    Arguments:
    - request (HttpRequest): the HTTP request
    - query_params (List[tuple]): list of (field, values) tuples
    - clean_names (Dict[str, str]): mapping of clean names to original names

    Returns:
    - (Q): the query
    """
    query = Q()
    toggle_fields = {'trips_id', 'gwips_id', 'ribocrypt_id', 'FASTA_file', 'processed',
                     'verified'}
    for field, values in query_params:
        if field in ('page', 'csrfmiddlewaretoken'):
            continue

        options = request.GET.getlist(field)
        if not options:
            continue

        cn = {v: k for k, v in clean_names.items()}
        original_field = cn.get(field)
        if original_field is None:
            # Not a filter this page knows about
            continue

        if field in toggle_fields:
            query &= Q(**{original_field: 'on' in options})
        else:
            query &= Q(**{f"{original_field}__in": options})
    return query


def handle_filter(
        param_options: dict,
        appropriate_fields: list,
        clean_names: dict) -> dict:
    '''
    Get the filter options for each parameter in the query parameters.

    Arguments:
    - request (HttpRequest): the HTTP request for the page
    - query_params (dict): the query parameters
    - appropriate_fields (list): the list of fields that should be filtered
    - clean_names (dict): the dictionary of clean names to original names

    Returns:
    - (dict): the filter options for each parameter
    '''
    clean_results_dict: dict = {}
    result_dict: dict = {}

    # Convert the values to a list of dictionaries for each parameter as
    # I couldn't get the template to iterate over the values in the queryset
    for name, queryset in param_options.items():
        if name in appropriate_fields:
            for obj in queryset:
                for field_name in obj.keys():
                    if field_name not in result_dict:
                        result_dict[field_name] = []
                        clean_results_dict[clean_names[field_name]] = []
                    if obj[field_name] == '' or obj[field_name] == 'nan':
                        obj[field_name] = 'None'
                    result_dict[field_name].append(
                        {'value': obj[field_name], 'count': obj['count']}
                        )
                    clean_results_dict[clean_names[field_name]].append(
                        {'value': obj[field_name], 'count': obj['count']}
                        )
    return clean_results_dict


# Values used for "no PMID" in Study.PMID
PMID_MISSING = ['', 'nan', '<NA>']


def pubmed_query(options: list, prefix: str = '') -> Q:
    '''
    Build the query for the PubMed filter, whose options are 'Available'
    and/or 'Not Available'.

    Arguments:
    - options (list): the selected PubMed options
    - prefix (str): lookup prefix to reach Study.PMID, e.g. 'BioProject__'

    Returns:
    - (Q): the query (empty if both or neither option is selected)
    '''
    missing = (Q(**{f'{prefix}PMID__isnull': True})
               | Q(**{f'{prefix}PMID__in': PMID_MISSING}))
    available = 'Available' in options
    not_available = 'Not Available' in options
    if available and not not_available:
        return ~missing
    if not_available and not available:
        return missing
    return Q()


def select_all_query(query_string):
    '''
    Generate a query to select all the samples in the database that were shown in the table

    Arguments:
    - query_string (str): the query string

    Returns:
    - (Q): the Django Q object to select all the samples in the database that were shown in the table
    '''
    ignored_keys = [
        'page',
        'csrfmiddlewaretoken',
        'links',
        'sample_page',
        'study_page',
        'query',
    ]
    sample_fields = {field.name for field in Sample._meta.get_fields()}
    clean_names = get_clean_names()

    main_query = Q()  # Initialize an empty main query for AND between fields
    field_queries = {}  # Dictionary to store OR queries for each field
    pubmed_options = []

    for model_key, value in parse_qsl(query_string):
        if model_key in ignored_keys:
            continue
        if model_key == 'PubMed':
            # PMID lives on Study, not Sample
            pubmed_options.append(value)
            continue
        if value == 'on':
            value = 'True'

        field_name = 'Run' if model_key == 'run' else get_original_name(
            model_key, clean_names)
        if field_name not in sample_fields:
            continue

        # If the field already exists in field_queries, add to its OR query
        if field_name in field_queries:
            field_queries[field_name] |= Q(**{field_name: value})
        else:
            # If it's a new field, create a new OR query
            field_queries[field_name] = Q(**{field_name: value})

    # Combine all field queries with AND
    for field_query in field_queries.values():
        main_query &= field_query

    return main_query & pubmed_query(pubmed_options, prefix='BioProject__')


def get_fastp_report_link(run: str):
    '''
    Return path to fastp report file for given run

    Arguments:
    - run (str): the run to get the report for

    Returns:
    - (str): the path to the report file, relative to RIBOSEQORG_DATA_DIR
    OR
    - (None): if there is no report
    '''
    return find_run_file('fastp', run, ['.html', '_1.html', '_2.html'])


def get_fastqc_report_link(run: str):
    '''
    Return path to FastQC report file for given run (see get_fastp_report_link)
    '''
    return find_run_file('fastqc', run, [
        '_fastqc.html', '_1_fastqc.html', '_2_fastqc.html'])


def get_ribometric_report_link(run: str):
    '''
    Return path to RiboMetric report file for given run (see get_fastp_report_link)
    '''
    return find_run_file('ribometric', run, [
        'bamtrans_RiboMetric.html', '_1bamtrans_RiboMetric.html',
        '_2bamtrans_RiboMetric.html'])
