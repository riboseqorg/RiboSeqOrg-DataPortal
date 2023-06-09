from django.http import HttpRequest
from django.db.models import Q
from .models import Sample, Study, OpenColumns, Trips, GWIPS
import pandas as pd



def get_clean_names() -> dict:
    '''
    Return a dictionary of clean names to original names as in database
    
    Returns:
        clean_names: dictionary
    '''
    clean_names = {
    'Run':'Run Accession', 
    'spots':'Total Number of Spots (Original file))', 
    'bases':'Total Number of Bases (Original file)', 
    'avgLength':'Average Read Length', 
    'size_MB':'Original File Size (MB)', 
    'LibraryName':'Library Name', 
    'LibraryStrategy':'Library Strategy', 
    'LibrarySelection':'Library Selection', 
    'LibrarySource':'Library Source', 
    'LibraryLayout':'Library Layout', 
    'InsertSize':'Insert Size', 
    'InsertDev':'Insert Deviation', 
    'Platform':'Platform',	
    'Model':'Model',	
    'SRAStudy': 'SRA Project Accession (SRP)',	
    'BioProject':'BioProject',
    'Study_Pubmed_id':'PubMed ID',
    'Sample':'Sample',
    'BioSample':'BioSample',
    'SampleType':'Sample Type',
    'TaxID':'Organism TaxID',
    'ScientificName':'Organism',
    'SampleName':'Sample Name',
    'CenterName':'Center Name',	
    'Submission':'Submission',
    'MONTH':'Month',
    'YEAR':'Year',
    'AUTHOR':'Author',
    'sample_source':'Sample Source',
    'sample_title':'Sample Title',
    'ENA_first_public':'ENA First Public',
    'ENA_last_update':'ENA Last Update',
    'INSDC_center_alias':'INSDC Center Alias',	
    'INSDC_center_name':'INSDC Center Name',
    'INSDC_first_public':'INSDC First Public',
    'INSDC_last_update':'INSDC Last Update',
    'GEO_Accession'	:'GEO Accession',
    'Experiment_Date':'Date of Experiment',
    'date_sequenced':'Date of Sequencing',
    'submission_date':'Submission Date',
    'date':'Date',
    'Experiment':'Experiment ID',
    'CELL_LINE':'Cell-Line',
    'TISSUE':'Tissue',
    'INHIBITOR':'Inhibitor',
    'TIMEPOINT':'Timepoint',
    'FRACTION':'Cellular-Compartment',
    'REPLICATE':'Replicate-Number',
    'CONDITION':'Condition',
    'LIBRARYTYPE':'Library-Type',
    'STAGE':'Stage',
    'GENE':'Gene',
    'Sex':'Sex',
    'Strain':'Strain',
    'Age':'Age',
    'Infected':'Infected',
    'Disease':'Disease',
    'Genotype'	:'Genotype',
    'Feeding':'Feeding',
    'Temperature':'Temperature',
    'SiRNA':'SiRNA',
    'SgRNA':'SgRNA',
    'ShRNA':'ShRNA',
    'Plasmid':'Plasmid',
    'Growth_Condition':'Growth-Condition',
    'Stress':'Stress',
    'Cancer':'Cancer',
    'microRNA':'MicroRNA',
    'Individual':'Individual',
    'Antibody':'Antibody Used',
    'Ethnicity':'Ethnicity',
    'Dose':'Dose',
    'Stimulation':'Stimulation',
    'Host':'Host Organism',
    'UMI':'Unique Molecular Identifier (UMI)',
    'Adapter':'Adapter Sequence',
    'Separation':'Mode of Separation',
    'rRNA_depletion':'Mode of rRNA depletion',
    'Barcode':'Barcode Information',
    'Monosome_purification':'Mode of Purification',
    'Nuclease':'Nucelase Used',
    'Kit':'Kit Used',
    'Organism': 'Organism',
    'PMID': 'PubMed',
    'count':'count',
    'verified':'verified',
    'trips_id':'trips_id',
    'gwips_id':'gwips_id',
    'ribocrypt_id':'ribocrypt_id',
    'readfile':'readfile',
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


def build_query(request: HttpRequest, query_params: dict, clean_names: dict) -> Q:
    """
    Build a query based on the query parameters.

    Arguments:
    - query_params dict_itemiterator

    Returns:
    - (Q): the query
    """
    # Build the query for the studies based on the query parameters
    query = Q()
    #loop over unique keys in query_params
    for field, values in query_params:
        if field in ['page']:
            continue
        options = request.GET.getlist(field)
        q_options = Q()
        for option in options:
            if field in ['trips_id', 'gwips_id', 'ribocrypt_id', 'readfile', 'verified']:
                if option == 'on':
                    option = True
                else:
                    option = False
            q_options |= Q(**{ get_original_name(field, clean_names): option})
        query &= q_options
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
    clean_results_dict = {}
    result_dict = {}

    # Convert the values to a list of dictionaries for each parameter as I couldn't get the template to iterate over the values in the queryset
    for name, queryset in param_options.items():
        if name in appropriate_fields:
            for obj in queryset:
                for field_name in obj.keys():
                    if field_name not in result_dict:
                        result_dict[field_name] = []
                        clean_results_dict[clean_names[field_name]] = []
                    if obj[field_name] == '' or obj[field_name] == 'nan':
                        obj[field_name] = 'None'
                    result_dict[field_name].append({'value': obj[field_name], 'count': obj['count']})
                    clean_results_dict[clean_names[field_name]].append({'value': obj[field_name], 'count': obj['count']})
    return clean_results_dict


def build_run_query(run_list: list) -> Q:
    '''
    For a given run list return a query to filter the Sample model.

    Arguments:
    - run_list (list): the list of runs to filter  

    Returns:
    - (Q): the query
    '''
    query = Q()
    for run in run_list:
        query |= Q(Run=run)

    return query


def build_bioproject_query(run_list: list) -> Q:
    '''
    For a given run list return a query to filter the Sample model.

    Arguments:
    - run_list (list): the list of runs to filter  

    Returns:
    - (Q): the query
    '''
    query = Q()
    for run in run_list:
        query |= Q(BioProject=run)

    return query


def handle_trips_urls(query: Q) -> list:
    '''
    For a given query return the required information to link those sample in trips.

    Arguments:
    - query (Q): the query

    Returns:
    - (list): the required information to link those samples in trips (list of dicts)
    '''
    trips = []
    trips_entries = Trips.objects.filter(query)

    trips_df = pd.DataFrame(list(trips_entries.values()))
    if trips_df.empty:
        trips.append(
            {
                'clean_organism': 'None of the Selected Runs are available on Trips-Viz',
                'organism': 'None of the Selected Runs are available on Trips-Viz',
            }
        )
    else:
        for transcriptome in trips_df['transcriptome'].unique():
            organism_df = trips_df[trips_df['transcriptome'] == transcriptome]
            file_ids = [str(int(i)) for i in organism_df['Trips_id'].unique().tolist()]
            trips_dict = {
                'clean_organism': organism_df['organism'].unique()[0].replace('_', ' ').capitalize(),
                'organism': organism_df['organism'].unique()[0],
                'transcriptome': transcriptome,
                'files': f"files={','.join(file_ids)}",
            }
            trips.append(trips_dict)

    return trips


def handle_gwips_urls(request: HttpRequest, query=None) -> list:
    '''
    For a given query return the required information to link those sample in GWIPS-viz.

    Arguments:
    - request (HttpRequest): the HTTP request for the page
 

    Returns:
    - (list): the required information to link those samples in GWIPS-viz (list of dicts)
    '''
    gwips = []

    requested = dict(request.GET.lists())
    if str(query) != '<Q: (AND: )>' and query is not None:
        samples = Sample.objects.filter(query)
    elif 'run' in requested:
        runs = requested['run']
        samples = Sample.objects.filter(build_run_query(runs))
    elif 'bioproject' in requested:
        bioprojects = requested['bioproject']
        samples = Sample.objects.filter(BioProject__in=bioprojects)

    samples_df = pd.DataFrame(list(samples.values()))
    organisms = samples_df['ScientificName'].unique()

    if 'run' in requested:
        for organism in organisms:
            organism_df = samples_df[samples_df['ScientificName'] == organism]
            gwips_dict = {
                'clean_organism': organism.replace('_', ' ').capitalize(),
                'bioprojects': '',
                'files': '',
                'gwipsDB': '',
            }
            for idx, row in organism_df.iterrows():
                gwips_entry = GWIPS.objects.filter(BioProject=row['BioProject_id'])
                if gwips_entry:
                    gwips_df = pd.DataFrame(list(gwips_entry.values()))
                    if row['BioProject_id'] not in gwips_dict['bioprojects']:
                        gwips_dict['bioprojects'] += f"{row['BioProject_id']}, "
                    gwips_dict['gwipsDB'] = gwips_df['gwips_db'].unique()[0]

                    if any(map(row['INHIBITOR'].__contains__, ['ltm', 'LTM', 'Lac', 'LAC', 'harr', 'Harr', 'HARR'])):
                        suffix = gwips_df['GWIPS_Init_Suffix'].unique()[0]
                    else:
                        suffix = gwips_df['GWIPS_Elong_Suffix'].unique()[0]

                    if gwips_dict['files'] != '' and f"{suffix}=full" not in gwips_dict['files']:
                        gwips_dict['files'].append(f"{suffix}=full")
                    elif f"{suffix}=full" not in gwips_dict['files']:
                        gwips_dict['files'] = [f"{suffix}=full"]
            gwips_dict['files'] = '&'.join(gwips_dict['files'])
            gwips.append(gwips_dict)

    elif 'bioproject' in requested or str(query) != '<Q: (AND: )>':
        for organism in organisms:
            organism_df = samples_df[samples_df['ScientificName'] == organism]
            organism_df = organism_df[organism_df['gwips_id'] == True]
            if organism_df.empty:
                continue
            gwips_dict = None
            for bioproject in organism_df['BioProject_id'].unique():
                gwips_entry = GWIPS.objects.filter(BioProject=bioproject)
                if gwips_entry:
                    gwips_df = pd.DataFrame(list(gwips_entry.values()))
                    if gwips_df['Organism'].unique()[0] != organism:
                        continue
                    if not gwips_dict:
                        gwips_dict = {
                            'bioproject': bioproject,
                            'clean_organism': organism.replace('_', ' ').capitalize(),
                            'gwipsDB': gwips_df['gwips_db'].unique()[0],
                            'files': [],
                        }
                    for col in ['GWIPS_Elong_Suffix', 'GWIPS_Init_Suffix']:
                        if gwips_df[col].unique()[0] != '':
                            if f"{gwips_df[col].unique()[0]}=full" not in gwips_dict['files']:
                                gwips_dict['files'].append(f"{gwips_df[col].unique()[0]}=full")

            if gwips_dict:
                gwips_dict['files'] = '&'.join(gwips_dict['files'])
                gwips.append(gwips_dict)

    return gwips


def select_all_query(query_string):
    '''
    Generate a query string to select all the samples in the database that were shown in the table

    Arguments:
    - query_string (str): the query string

    Returns:
    - (str): the query string to select all the samples in the database that were shown in the table
    '''
    query_string = query_string.replace('+', ' ')
    query_list = [i.split("=") for i in query_string.split('&')]

    query = Q()  # Initialize an empty query
    if len(query_list[0]) != 1:
        query_list = [[i[0], i[1].replace('on', 'True')] if i[1] == 'on' else i for i in query_list]
        query_mappings = {
            i[0]: get_original_name(i[0], get_clean_names()) for i in query_list
        }

        for model_key, value in query_list:
            query &= Q(**{query_mappings[model_key]: value})
    return query
