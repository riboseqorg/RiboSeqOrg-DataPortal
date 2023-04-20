from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse

from django.db.models import Count


from django.db.models import Q
from .models import Sample, Study


import pandas as pd
from .forms import SearchForm

from django_filters.views import FilterView
from .filters import StudyFilter, SampleFilter

from django.db.models import Count



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
        Q(Accession__icontains=query) |
        Q(Name__icontains=query) |
        Q(Title__icontains=query) |
        Q(Organism__icontains=query) |
        Q(Samples__icontains=query) |
        Q(SRA__icontains=query) |
        Q(Release_Date__icontains=query) |
        Q(All_protocols__icontains=query) |
        Q(seq_types__icontains=query) |
        Q(GSE__icontains=query) |
        Q(BioProject__icontains=query) |
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
        Q(trips__icontains=query) |
        Q(gwips__icontains=query) |
        Q(ribocrypt__icontains=query) |
        Q(ftp__icontains=query) |
        Q(Study_Accession__icontains=query) |
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
        Q(BioProject__icontains=query) |
        Q(Study_Pubmed_id__icontains=query) |
        Q(ProjectID__icontains=query) |
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
        Q(KO__icontains=query) |
        Q(KD__icontains=query) |
        Q(KI__icontains=query) |
        Q(FRACTION__icontains=query)
    )

    context = {
        'search_form': search_form,
        'sample_results': list(sample_results),
        'study_results': list(study_results),
        'query': query,
    }

    return render(request, 'main/search_results.html', context)


def build_query(request: HttpRequest, query_params: dict) -> Q:
    """
    Build a query based on the query parameters.

    Arguments:
    - query_params (dict): the query parameters

    Returns:
    - (Q): the query
    """
    # Build the query for the studies based on the query parameters
    query = Q()
    for key, value in query_params.items():
        options = request.GET.getlist(key)
        q_options = Q()
        for option in options:
            q_options |= Q(**{key: option})
        query &= q_options

    return query

def samples(request: HttpRequest) -> HttpResponse:
    """
    Render a page of Sample objects.

    Arguments:
    - request (HttpRequest): the HTTP request for the page
    
    Returns:
    - (HttpResponse): the HTTP response for the page
    """
    ls = Sample.objects.all()
    paginator = Paginator(ls, 100) 
    
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'main/samples.html', {'ls': page_obj })


def studies(request: HttpRequest) -> render:
    """
    Render a page of studies filtered by query parameters.
    
    Arguments:
    - request (HttpRequest): the HTTP request for the page
    
    Returns:
    - (render): the rendered HTTP response for the page
    """    
    appropriate_fields = ['Organism', 'Journal']
    # Get all the query parameters from the request
    query_params = request.GET.dict()

    query = build_query(request, query_params)

    # Get the studies that match the query
    studies = Study.objects.filter(query)

    # Get the unique values and counts for each parameter within the filtered queryset
    param_options = {}
    for field in Study._meta.fields:
        if field.get_internal_type() == 'CharField':
            values = studies.values(field.name).annotate(count=Count(field.name)).order_by('-count')
            param_options[field.name] = values
    
    result_dict = {}

    # Convert the values to a list of dictionaries for each parameter as I couldn't get the template to iterate over the values in the queryset
    for name, queryset in param_options.items():
        if name in appropriate_fields:
            for obj in queryset:
                for field_name in obj.keys():
                    if field_name not in result_dict:
                        result_dict[field_name] = []
                    if obj[field_name] == '':
                        obj[field_name] = 'None'
                    result_dict[field_name].append({'value': obj[field_name], 'count': obj['count']})

    # Remove the count from the list of values for each parameter
    result_dict.pop('count', None)

    # Paginate the studies
    paginator = Paginator(studies, 5)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    # Render the studies template with the filtered and paginated studies and the filter options
    return render(request, 'main/studies.html', {'page_obj': page_obj, 'param_options': result_dict})


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
    study_model = get_object_or_404(Study, Accession=query)

    # return all results from Study where Accession=query
    ls = Sample.objects.filter(Study_Accession=query)
    context = {'Study': study_model, 'ls': ls}
    return render(request, 'main/study.html', context)


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