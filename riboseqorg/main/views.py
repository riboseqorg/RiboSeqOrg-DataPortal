from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse

from django.db.models import Count


from django.db.models import Q
from .models import Sample, Study, OpenColumns


import pandas as pd
from .forms import SearchForm

from django_filters.views import FilterView
from .filters import StudyFilter, SampleFilter

from django.db.models import Count

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
        # Q(BioProject__icontains=query) |
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
        Q(FRACTION__icontains=query)
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



def samples(request: HttpRequest) -> render:
    """
    Render a page of Sample objects.

    Arguments:
    - request (HttpRequest): the HTTP request for the page
    
    Returns:
    - (render): the rendered HTTP response for the page
    """
    appropriate_fields = ['CELL_LINE', 'INHIBITOR', 'TISSUE', 'LIBRARYTYPE', "ScientificName"]
    clean_names = {'CELL_LINE': 'Cell-Line', 'CONDITION': 'Condition', 'INHIBITOR': 'Inhibitor', 'ScientificName': 'Organism','REPLICATE': 'Replicate', 'TIMEPOINT': 'Timepoint', 'TISSUE': 'Tissue', 'KO': 'KO', 'KD': 'KD', 'KI': 'KI', 'FRACTION': 'Fraction', 'BATCH': 'Batch', 'LIBRARYTYPE': 'Library-Type', 'sample_source': 'Sample-Source', 'count':'count'}
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

    # Paginate the studies
    paginator = Paginator(samples, 50)
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
    appropriate_fields = ['Organism', 'Journal']
    clean_names = {'Organism': 'Organism', 'Journal': 'Journal', 'count':'count'}
    # Get all the query parameters from the request
    query_params = request.GET.lists()

    filtered_columns = [get_original_name(name, clean_names) for name, values in request.GET.lists()]

    # Get the unique values and counts for each parameter within the filtered queryset
    param_options = {}
    for field in Study._meta.fields:
        if field.get_internal_type() == 'CharField':
            if field.name in filtered_columns:
                # update query_params to remove the current field to ensure this field is not filtered by itself
                query_params = [i for i in request.GET.lists() if get_original_name(i[0], clean_names) != field.name]
                query = build_query(request, query_params, clean_names)
                studies = Study.objects.filter(query)

                filtered_studies = studies.values(field.name).annotate(count=Count(field.name)).order_by('-count')
                param_options[field.name] = filtered_studies
            else:
                query = build_query(request, query_params, clean_names)
                studies = Study.objects.filter(query)

                values = studies.values(field.name).annotate(count=Count(field.name)).order_by('-count')
                param_options[field.name] = values


    clean_results_dict = handle_filter(param_options, appropriate_fields, clean_names)
    clean_results_dict.pop('count', None)
    
    # Paginate the studies
    paginator = Paginator(studies, 50)
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
    print(open_columns)
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
    print(query)
    sample_model = get_object_or_404(Sample, Run=query)

    # return all results from Study where Accession=query
    ls = Sample.objects.filter(Run=query)
    context = {'Sample': sample_model, 'ls': ls}
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