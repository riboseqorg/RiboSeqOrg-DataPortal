from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse

from django.db.models import Count


from django.db.models import Q
from .models import Sample, Study, OpenColumns, Trips, GWIPS


import pandas as pd
from .forms import SearchForm

from django_filters.views import FilterView
from .filters import StudyFilter, SampleFilter

from django.db.models import Count


from django import template

register = template.Library()

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


def column_selction(request: HttpRequest) -> render:
    return False



def index(request: HttpRequest) -> render:
    """
    Render the homepage.

    Arguments:
    - request (HttpRequest): the HTTP request for the page

    Returns:
    - (render): the rendered HTTP response for the page
    """
    search_form = SearchForm()

    context = {
        'search_form': search_form,
    }
    return render(request, "main/home.html", context)


def search_results(request: HttpRequest) -> render:
    """
    Render the search results page based on the query parameters.

    Arguments:
    - request (HttpRequest): the HTTP request for the page

    Returns:
    - (render): the rendered HTTP response for the page
    """
    query = request.GET.get('query', '')
    search_form = SearchForm(request.GET or None)

    # Search across all fields in Study model
    study_results = Study.objects.filter(
        Q(BioProject__icontains=query) |
        Q(Name__icontains=query) |
        Q(Title__icontains=query) |
        Q(Organism__icontains=query) |
        Q(Samples__icontains=query) |
        Q(SRA__icontains=query) |
        Q(Release_Date__icontains=query) |
        Q(Description__icontains=query) |
        Q(seq_types__icontains=query) |
        Q(GSE__icontains=query) |
        Q(PMID__icontains=query) |
        Q(Authors__icontains=query) |
        Q(Study_abstract__icontains=query) |
        Q(Publication_title__icontains=query) |
        Q(doi__icontains=query) |
        Q(Date_published__icontains=query) |
        Q(PMC__icontains=query) |
        Q(Journal__icontains=query) |
        Q(Paper_abstract__icontains=query) |
        Q(Email__icontains=query)
    )


    sample_results = Sample.objects.filter(
        Q(verified__icontains=query) |
        Q(trips_id__icontains=query) |
        Q(gwips_id__icontains=query) |
        Q(ribocrypt_id__icontains=query) |
        Q(readfile__icontains=query) |
        Q(BioProject__icontains=query) |
        Q(Run__icontains=query) |
        Q(spots__icontains=query) |
        Q(bases__icontains=query) |
        Q(avgLength__icontains=query) |
        Q(size_MB__icontains=query) |
        Q(Experiment__icontains=query) |
        Q(LibraryName__icontains=query) |
        Q(LibraryStrategy__icontains=query) |
        Q(LibrarySelection__icontains=query) |
        Q(LibrarySource__icontains=query) |
        Q(LibraryLayout__icontains=query) |
        Q(InsertSize__icontains=query) |
        Q(InsertDev__icontains=query) |
        Q(Platform__icontains=query) |
        Q(Model__icontains=query) |
        Q(SRAStudy__icontains=query) |
        Q(Study_Pubmed_id__icontains=query) |
        Q(Sample__icontains=query) |
        Q(BioSample__icontains=query) |
        Q(SampleType__icontains=query) |
        Q(TaxID__icontains=query) |
        Q(ScientificName__icontains=query) |
        Q(SampleName__icontains=query) |
        Q(CenterName__icontains=query) |
        Q(Submission__icontains=query) |
        Q(MONTH__icontains=query) |
        Q(YEAR__icontains=query) |
        Q(AUTHOR__icontains=query) |
        Q(sample_source__icontains=query) |
        Q(sample_title__icontains=query) |
        Q(LIBRARYTYPE__icontains=query) |
        Q(REPLICATE__icontains=query) |
        Q(CONDITION__icontains=query) |
        Q(INHIBITOR__icontains=query) |
        Q(BATCH__icontains=query) |
        Q(TIMEPOINT__icontains=query) |
        Q(TISSUE__icontains=query) |
        Q(CELL_LINE__icontains=query) |
        Q(FRACTION__icontains=query) |
        Q(ENA_first_public__icontains=query) |
        Q(ENA_last_update__icontains=query) |
        Q(INSDC_center_alias__icontains=query) |
        Q(INSDC_center_name__icontains=query) |
        Q(INSDC_first_public__icontains=query) |
        Q(INSDC_last_update__icontains=query) |
        Q(INSDC_status__icontains=query) |
        Q(ENA_checklist__icontains=query) |
        Q(GEO_Accession__icontains=query) |
        Q(Experiment_Date__icontains=query) |
        Q(date_sequenced__icontains=query) |
        Q(submission_date__icontains=query) |
        Q(date__icontains=query) |
        Q(STAGE__icontains=query) |
        Q(GENE__icontains=query) |
        Q(Sex__icontains=query) |
        Q(Strain__icontains=query) |
        Q(Age__icontains=query) |
        Q(Infected__icontains=query) |
        Q(Disease__icontains=query) |
        Q(Genotype__icontains=query) |
        Q(Feeding__icontains=query) |
        Q(Temperature__icontains=query) |
        Q(SiRNA__icontains=query) |
        Q(SgRNA__icontains=query) |
        Q(ShRNA__icontains=query) |
        Q(Plasmid__icontains=query) |
        Q(Growth_Condition__icontains=query) |
        Q(Stress__icontains=query) |
        Q(Cancer__icontains=query) |
        Q(microRNA__icontains=query) |
        Q(Individual__icontains=query) |
        Q(Antibody__icontains=query) |
        Q(Ethnicity__icontains=query) |
        Q(Dose__icontains=query) |
        Q(Stimulation__icontains=query) |
        Q(Host__icontains=query) |
        Q(UMI__icontains=query) |
        Q(Adapter__icontains=query) |
        Q(Separation__icontains=query) |
        Q(rRNA_depletion__icontains=query) |
        Q(Barcode__icontains=query) |
        Q(Monomosome_purification__icontains=query) |
        Q(Nuclease__icontains=query) |
        Q(Kit__icontains=query) |
        Q(Info__icontains=query)
    )


    context = {
        'search_form': search_form,
        'sample_results': list(sample_results),
        'study_results': list(study_results),
        'query': query,
    }

    return render(request, 'main/search_results.html', context)


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
        options = request.GET.getlist(field)
        q_options = Q()
        for option in options:
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


def get_sample_filter_options(studies: list,
                              sample_fields: list=[
                                'CELL_LINE',
                                'INHIBITOR',
                                'TISSUE',
                                'LIBRARYTYPE',
                              ]) -> dict:
    '''
    For a given filtered study queryset, return the filter options for the sample parameters.

    Arguments:
    - studies (list): the filtered study queryset
    - sample_fields (list): the list of sample parameters to filter

    Returns:
    - (dict): the filter options for each sample parameter
    '''
    sample_filter_options = {}
    bioprojects = studies.values_list('BioProject', flat=True)
    clean_names = get_clean_names()
    samples = Sample.objects.filter(BioProject_id__in=bioprojects)

    
    for field in sample_fields:
        values = samples.values(field).annotate(count=Count(field)).order_by('-count')
        for obj in values:
            for field_name in obj.keys():
                if obj[field_name] == '' or obj[field_name] == 'nan':
                    obj[field_name] = 'None'

                if clean_names[field_name] not in sample_filter_options:
                    sample_filter_options[clean_names[field_name]] = [{'value': obj[field_name], 'count': obj['count']}]
                else:
                    sample_filter_options[clean_names[field_name]].append({'value': obj[field_name], 'count': obj['count']})
    return sample_filter_options


def samples(request: HttpRequest) -> render:
    """
    Render a page of Sample objects.

    Arguments:
    - request (HttpRequest): the HTTP request for the page
    
    Returns:
    - (render): the rendered HTTP response for the page
    """

    #fields to show in Filter Panel 
    appropriate_fields = [
        'CELL_LINE',
        'INHIBITOR', 
        'TISSUE', 
        'LIBRARYTYPE', 
        "ScientificName", 
        "FRACTION", 
        "Infected", 
        "Disease", 
        "Sex",
        "Cancer",
        # "Growth_Condition",
        # "Stress",
        # "Genotype",
        # "Feeding",
        # "Temperature",
        ]
    clean_names = get_clean_names()
    # Get all the query parameters from the request
    query_params = request.GET.lists()

    filtered_columns = [get_original_name(name, clean_names) for name, values in request.GET.lists()]

    # Get the unique values and counts for each parameter within the filtered queryset
    param_options = {}
    for field in Sample._meta.fields:
        if field.get_internal_type() == 'CharField':
            if field.name in filtered_columns:
                # update query_params to remove the current field to ensure this field is not filtered by itself
                query_params = [i for i in request.GET.lists() if get_original_name(i[0], clean_names) != field.name]
                query = build_query(request, query_params, clean_names)
                samples = Sample.objects.filter(query)

                filtered_samples = samples.values(field.name).annotate(count=Count(field.name)).order_by('-count')
                param_options[field.name] = filtered_samples
            else:
                query = build_query(request, query_params, clean_names)
                samples = Sample.objects.filter(query)

                values = samples.values(field.name).annotate(count=Count(field.name)).order_by('-count')
                param_options[field.name] = values


    clean_results_dict = handle_filter(param_options, appropriate_fields, clean_names)
    clean_results_dict.pop('count', None)
    query_params = [(name, values) for name, values in request.GET.lists() if get_original_name(name, clean_names) in appropriate_fields]
    query = build_query(request, query_params, clean_names)
    samples = Sample.objects.filter(query)

    # Paginate the studies
    paginator = Paginator(samples, len(samples))
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Render the studies template with the filtered and paginated studies and the filter options
    return render(request, 'main/samples.html', {'page_obj': page_obj, 'param_options': clean_results_dict})


def studies(request: HttpRequest) -> render:
    """
    Render a page of studies filtered by query parameters.
    
    Arguments:
    - request (HttpRequest): the HTTP request for the page
    
    Returns:
    - (render): the rendered HTTP response for the page
    """    
    appropriate_fields = [
        'Organism',
        ]
    boolean_fields = [
        'PMID',
    ]
    clean_names = get_clean_names()
    del clean_names['ScientificName']
    
    # Get all the query parameters from the request
    # used for filter panel
    query_params = [(name, values) for name, values in request.GET.lists() if name in appropriate_fields or name in boolean_fields]
    filtered_columns = [get_original_name(name, clean_names) for name, values in request.GET.lists()]

    boolenan_param_options = {}
    # Get the unique values and counts for each parameter within the filtered queryset
    param_options = {}
    for field in Study._meta.fields:
        if field.get_internal_type() == 'CharField':
            if field.name in filtered_columns:
                # update query_params to remove the current field to ensure this field is not filtered by itself
                query_params = [i for i in request.GET.lists() if get_original_name(i[0], clean_names) != field.name]
                query_params = [(name, values) for name, values in request.GET.lists() if (name in appropriate_fields or name in boolean_fields) and get_original_name(name, clean_names) != field.name]

                query = build_query(request, query_params, clean_names)
                studies = Study.objects.filter(query)

                filtered_studies = studies.values(field.name).annotate(count=Count(field.name)).order_by('-count')
                param_options[field.name] = filtered_studies
            else:
                query = build_query(request, query_params, clean_names)
                studies = Study.objects.filter(query)

                values = studies.values(field.name).annotate(count=Count(field.name)).order_by('-count')
                param_options[field.name] = values

        if field.name in boolean_fields:
            query = build_query(request, query_params, clean_names)
            studies = Study.objects.filter(query)
            values = studies.values(field.name).annotate(count=Count(field.name)).order_by('-count')

            available = [i for i in values if i[field.name] not in ['', 'nan', None]]
            available_count = sum([i['count'] for i in available])

            not_available = [i for i in values if i[field.name] in ['', 'nan', None]]
            not_available_count = sum([i['count'] for i in not_available])

            clean_name = clean_names[field.name]
            boolenan_param_options[clean_name] = [{'count': available_count, 'value': 'Available'}, {'count': not_available_count, 'value': 'Not Available'}]


    # rebuild query to populate table
    query_params = [(name, values) for name, values in request.GET.lists() if name in appropriate_fields or name in boolean_fields]
    query = build_query(request, query_params, clean_names)
    studies = Study.objects.filter(query)
    sample_filter_options = get_sample_filter_options(studies)
    clean_results_dict = handle_filter(param_options, appropriate_fields, clean_names)
    clean_results_dict = {**clean_results_dict, **boolenan_param_options}#, **sample_filter_options}
    clean_results_dict.pop('count', None)
    
    # Paginate the studies
    paginator = Paginator(studies, len(studies))
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Render the studies template with the filtered and paginated studies and the filter options
    return render(request, 'main/studies.html', {'page_obj': page_obj, 'param_options': clean_results_dict})


def about(request: HttpRequest) -> render:
    """
    Render the about page.
    
    Arguments:
    - request (HttpRequest): the HTTP request for the page
    
    Returns:
    - (render): the rendered HTTP response for the page
    """ 
    return render(request, "main/about.html", {})


def study_detail(request: HttpRequest, query: str) -> render:
    """
    Render a page for a specific study.
    
    Arguments:
    - request (HttpRequest): the HTTP request for the page
    - query (str): the study accession number
    
    Returns:
    - (render): the rendered HTTP response for the page
    """ 
    study_model = get_object_or_404(Study, BioProject=query)

    # return all results from Study where Accession=query
    ls = Sample.objects.filter(BioProject=query)
    open_columns = OpenColumns.objects.filter(bioproject=query)

    # Return all results from Sample and query the sqlite too and add this to the table
    context = {'Study': study_model, 'ls': ls}
    return render(request, 'main/study.html', context)


def sample_detail(request: HttpRequest, query: str) -> render:
    """
    Render a page for a specific study.
    
    Arguments:
    - request (HttpRequest): the HTTP request for the page
    - query (str): the study accession number
    
    Returns:
    - (render): the rendered HTTP response for the page
    """ 

    appropriate_fields = [
        'Run', 
        'spots', 
        'bases', 
        'avgLength', 
        'size_MB', 
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
        'BioProject',
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
        'ENA_first_public',
        'ENA_last_update',
        'INSDC_center_alias',	
        'INSDC_center_name',
        'INSDC_first_public',
        'INSDC_last_update',
        'INSDC_status',
        'ENA_checklist',
        'GEO_Accession',
        'Experiment_Date',
        'date_sequenced',
        'submission_date',
        'date',
        'Experiment',
        'CELL_LINE',
        'TISSUE',
        'INHIBITOR',
        'TIMEPOINT',
        'FRACTION',
        'REPLICATE',
        'CONDITION',
        'LIBRARYTYPE',
        'STAGE',
        'GENE',
        'Sex',
        'Strain',
        'Age',
        'Infected',
        'Disease',
        'Genotype'	,
        'Feeding',
        'Temperature',
        'SiRNA',
        'SgRNA',
        'ShRNA',
        'Plasmid',
        'Growth_Condition',
        'Stress',
        'Cancer',
        'microRNA',
        'Individual',
        'Antibody',
        'Ethnicity',
        'Dose',
        'Stimulation',
        'Host',
        'UMI',
        'Adapter',
        'Separation',
        'rRNA_depletion',
        'Barcode',
        'Monosome_purification',
        'Nuclease'
        'Kit',
        ]
    
    clean_names = get_clean_names()
    sample_model = get_object_or_404(Sample, Run=query)

    # return all results from Study where Accession=query
    ls = Sample.objects.filter(Run=query)
    # Return all results from Sample and query the sqlite too and add this to the table

    ks = []
    for key, value in ls.values()[0].items():
        if value not in ['nan', '']:
            if key in appropriate_fields:
                ks.append(
                    (clean_names[key], value)
                )

    paginator = Paginator(ls, len(ls))
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {'Sample': sample_model, 'ls': page_obj, 'ks': ks}
    return render(request, 'main/sample.html', context)

class StudyListView(FilterView):
    """
    View to display a list of studies based on applied filters.
    """
    model = Study
    template_name = 'study_list.html'
    filterset_class = StudyFilter


class SampleListView(FilterView):
    """
    View to display a list of samples based on applied filters.
    """
    model = Sample
    template_name = 'sample_list.html'
    filterset_class = SampleFilter


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


# def handle_gwips_urls(request: HttpRequest) -> list:
#     '''
#     For a given query return the required information to link those sample in GWIPS-viz.

#     Arguments:
#     - request (HttpRequest): the HTTP request for the page
 

#     Returns:
#     - (list): the required information to link those samples in GWIPS-viz (list of dicts)
#     '''
#     gwips = []

#     requested = dict(request.GET.lists())
#     if 'run' in requested:
#         samples = Sample.objects.filter(build_run_query(requested['run']))
#         bioprojects = samples.values_list('BioProject', flat=True)

#         for sample in samples.values():


#     elif 'bioproject' in requested:
#         bioprojects = requested['bioproject']

#     for bioproject in bioprojects:
#         samples = Sample.objects.filter(BioProject=bioproject)
#         samples_df = pd.DataFrame(list(samples.values()))
#         if samples_df['INHIBITOR'].unique().tolist() == [' ']:
#         print(samples_df['INHIBITOR'].value_counts())
#         if samples_df.empty:
#             gwips.append(
#                 {
#                     'clean_organism': 'None of the Selected Runs are available on GWIPS-Viz',

#                 }
#             )
#         # else:
#         #     gwips_dict = {
#         #         'bioproject': bioproject,
#         #         'gwipsDB':
#         #         'files': f"files={bioproject}",
#         #     }
#         print(bioproject)




def links(request: HttpRequest) -> render:
    """
    Render the links page.
    
    Arguments:
    - request (HttpRequest): the HTTP request for the page
    
    Returns:
    - (render): the rendered HTTP response for the page
    """ 


    selected = dict(request.GET.lists())
    if 'run' in selected:
        sample_query = build_run_query(selected['run'])
        print(sample_query)
        sample_entries = Sample.objects.filter(sample_query)
        paginator = Paginator(sample_entries, len(sample_entries))
        page_number = request.GET.get('page')
        sample_page_obj = paginator.get_page(page_number)

    elif 'bioproject' in selected:
        sample_query = build_bioproject_query(selected['bioproject'])
        sample_entries = Sample.objects.filter(sample_query)
        paginator = Paginator(sample_entries, len(sample_entries))
        page_number = request.GET.get('page')
        sample_page_obj = paginator.get_page(page_number)
    
    else:
        sample_page_obj = None
        sample_query = None

    trips = handle_trips_urls(sample_query)
    gwips = handle_gwips_urls(request)
    print(gwips)
    return render(request, 'main/links.html', {
        'sample_results': sample_page_obj,
        'trips': trips
        })

