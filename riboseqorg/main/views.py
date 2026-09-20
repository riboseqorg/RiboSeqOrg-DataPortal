import csv
import os
import uuid
from functools import reduce
from operator import or_
from typing import List, Type, Union

from urllib.parse import urlparse, parse_qs

import pandas as pd
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.paginator import Paginator
from django.db.models import CharField, Count, F, IntegerField, Q, Value
from django.db.models.functions import Cast, Concat, Length
from django.db.models.query import QuerySet
from django.http import (HttpRequest, HttpResponse, HttpResponseBadRequest,
                         HttpResponseNotFound)
from django.shortcuts import get_object_or_404, loader, render
from django.views import View
from django_filters.views import FilterView
from rest_framework import filters, generics
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from . import genome_tracks
from .datafiles import find_run_file
from .filters import StudyFilter
from .forms import SearchForm
from .models import GWIPS, Sample, Study, Trips
from .serializers import SampleSerializer
from .viewer_links import (attach_links, gwips_native_link, sample_links,
                           trips_file_id)
from .utilities import (build_query, get_clean_names, get_fastp_report_link,
                        get_fastqc_report_link, get_original_name,
                        get_ribometric_report_link, handle_filter,
                        PMID_MISSING, pubmed_query, select_all_query)

CharField.register_lookup(Length, 'length')


class SampleListView(generics.ListAPIView):
    serializer_class = SampleSerializer
    filterset_fields = ['Run']
    filter_backends = [filters.OrderingFilter, filters.SearchFilter]
    ordering_fields = ['Run']
    search_fields = ['Run']
    default_limit = 100  # Set a default limit if not provided

    default_fields = [
        'Run',
        'BioProject',
        'CELL_LINE',
        'INHIBITOR',
        'TISSUE',
        'LIBRARYTYPE',
    ]
    added_fields = [
        'fastqc_link',
        'fastp_link',
        'adapter_report_link',
        'ribometric_link',
        'reads_link',
        'counts_link',
        'bam_link',
        'bigwig_forward_link',
        'bigwig_reverse_link',
    ]

    def build_query(self, query_params):
        '''
        Dynamically parse remaining entries and apply filters
        if the key matches a field
        '''
        query = Q()
        for key, values in query_params.lists():
            key_query = Q()
            if key not in ['fields', 'limit']:
                # Check if the key is a valid field in the model
                if key in [field.name for field in Sample._meta.get_fields()]:
                    for value in values:
                        key_query |= Q(**{key: value})
                    query &= key_query
        return query

    def get_queryset(self):
        # Get query parameters
        limit = self.request.query_params.get('limit', self.default_limit)

        try:
            limit = int(limit)
        except (TypeError, ValueError):
            raise ValidationError({'limit': 'Must be an integer.'})
        if limit < 0:
            raise ValidationError({'limit': 'Must not be negative.'})

        query = self.build_query(self.request.query_params)
        try:
            queryset = Sample.objects.filter(query)
        except (ValueError, DjangoValidationError) as e:
            raise ValidationError({'detail': str(e)})
        return queryset[:limit]

    def get_serializer_class(self):
        '''
        A serializer for just the requested fields. Built per request so
        concurrent requests don't share (and overwrite) one field list.
        '''
        fields = self.request.query_params.get('fields')
        selected = self.default_fields
        if fields:
            model_fields = {f.name for f in Sample._meta.get_fields()}
            valid_fields = [
                field for field in dict.fromkeys(fields.split(','))
                if field in model_fields or field in self.added_fields
            ]
            if valid_fields:
                selected = valid_fields

        class Meta(SampleSerializer.Meta):
            pass
        Meta.fields = selected
        return type('RequestSampleSerializer', (SampleSerializer,),
                    {'Meta': Meta})


class SampleFieldsView(APIView):
    def get(self, request):
        # Get all field names from the Sample model
        fields = [field.name for field in Sample._meta.get_fields()]
        return Response(fields)


# Rows-per-page choices offered on the list pages
PAGE_SIZES = (25, 50, 100)
DEFAULT_PAGE_SIZE = 25

# Sortable columns: ?sort=<key> (or -<key> for descending) -> model field
SAMPLE_SORTS = {
    'run': 'Run',
    'study': 'BioProject_id',
    'organism': 'ScientificName',
    'library': 'LIBRARYTYPE',
    'inhibitor': 'INHIBITOR',
}
STUDY_SORTS = {
    'name': 'Name',
    'bioproject': 'BioProject',
    'organism': 'ScientificName',
    'samples': Cast('Samples', IntegerField()),
    'released': 'Release_Date',
    'sra': 'SRA',
}


def page_size(request: HttpRequest) -> int:
    """The ?per_page value if it is one of PAGE_SIZES, else the default."""
    try:
        size = int(request.GET.get('per_page', DEFAULT_PAGE_SIZE))
    except ValueError:
        return DEFAULT_PAGE_SIZE
    return size if size in PAGE_SIZES else DEFAULT_PAGE_SIZE


def sort_order(request: HttpRequest, columns: dict, default: list) -> list:
    """
    order_by() arguments for the ?sort parameter, falling back to default.
    'pk' is always last so pages are stable.
    """
    sort = request.GET.get('sort', '')
    field = columns.get(sort.lstrip('-'))
    if field is None:
        return default
    descending = sort.startswith('-')
    if isinstance(field, str):
        field = F(field)
    field = field.desc(nulls_last=True) if descending else field.asc(nulls_last=True)
    return [field, 'pk']


def index(request: HttpRequest) -> str:
    """
    Render the homepage.

    Arguments:
    - request (HttpRequest): the HTTP request for the page

    Returns:
    - (render): the rendered HTTP response for the page
    """
    search_form = SearchForm()

    # Headline numbers for the home page; they only change on a DB reload
    stats = cache.get('home_stats')
    if stats is None:
        stats = {
            'samples': Sample.objects.count(),
            'studies': Study.objects.count(),
            'organisms': Sample.objects.exclude(
                ScientificName__in=['', 'nan', '0.0', '<NA>']
            ).values('ScientificName').distinct().count(),
        }
        cache.set('home_stats', stats, 60 * 60)

    context = {
        'search_form': search_form,
        'stats': stats,
    }
    return render(request, "main/home.html", context)


class SearchView(View):
    template_name: str = 'main/search.html'
    paginate_by: int = 10
    sample_exclude_fields: List = [
        "verified",
        "trips_id",
        "gwips_id",
        "ribocrypt_id",
        "readfile",
        "BioProject",
    ]
    study_exclude_fields: List = ["sample"]

    def get(self, request: HttpRequest, *args, **kwargs) -> render:
        """
        Handle GET requests for the search view.

        Arguments:
        - request (HttpRequest): The HTTP request for the page.

        Returns:
        - (render): The rendered HTTP response for the page.
        """
        query: str = request.GET.get('query', '')
        search_form = SearchForm(request.GET or None)

        if query == '':
            study_results = Study.objects.all()
            sample_results = Sample.objects.all()
        else:
            study_results = self.get_search_results(
                Study,
                query,
                self.study_exclude_fields,
                )
            sample_results = self.get_search_results(
                Sample,
                query,
                self.sample_exclude_fields,
                )

        study_page_obj = self.paginate_results(
            study_results, 'study_page', request
            )
        sample_page_obj = self.paginate_results(
            sample_results, 'sample_page', request
            )

        context = {
            'search_form': search_form,
            'sample_results': sample_page_obj,
            'study_results': study_page_obj,
            'query': query,
        }

        return render(request, self.template_name, context)

    def get_search_results(
            self, model: Type, query: str, exclude: List
            ) -> QuerySet:
        """
        Get search results based on the query and excluded fields.

        Arguments:
        - model (Type): The model type.
        - query (str): The search query.
        - exclude (List): The list of fields to exclude.

        Returns:
        - (QuerySet): QuerySet of search results.
        """
        field_names: List = [
            f.name for f in model._meta.get_fields() if f.name not in exclude
            ]
        conditions: Q = reduce(
            or_, [Q(**{f'{field}__icontains': query}) for field in field_names]
            )
        results: QuerySet = model.objects.filter(conditions)
        return results

    def paginate_results(
            self, results: QuerySet, page_key: str, request: HttpRequest):
        """
        Paginate the search results.

        Arguments:
        - results (QuerySet): The results to paginate.
        - page_key (str): The key for the page number in the request.
        - request (HttpRequest): The HTTP request.

        Returns:
        - Union[Paginator, render]: Paginator if pagination is successful,
            otherwise render response.
        """
        paginator: Paginator = Paginator(
            results.order_by('pk'), page_size(request))
        page_number: str = request.GET.get(page_key)
        return paginator.get_page(page_number)


def get_sample_filter_options(
    studies: QuerySet,
    sample_fields: list = [
        'CELL_LINE',
        'INHIBITOR',
        'TISSUE',
        'LIBRARYTYPE',
    ]
) -> dict:
    '''
    For a given filtered study queryset, return the filter options f
    or the sample parameters.

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
        values = samples.values(field).annotate(
            count=Count(field)).order_by('-count')
        for obj in values:
            for field_name in obj.keys():
                if obj[field_name] == '' or obj[field_name] == 'nan':
                    obj[field_name] = 'None'

                if clean_names[field_name] not in sample_filter_options:
                    sample_filter_options[clean_names[field_name]] = [{
                        'value':
                        obj[field_name],
                        'count':
                        obj['count']
                    }]
                else:
                    sample_filter_options[clean_names[field_name]].append(
                            {
                                'value': obj[field_name],
                                'count': obj['count']
                            }
                        )
    return sample_filter_options


def samples(request: HttpRequest) -> str:
    """
    Render a page of Sample objects.

    Arguments:
    - request (HttpRequest): the HTTP request for the page

    Returns:
    - (render): the rendered HTTP response for the page
    """

    # fields to show in Filter Panel
    appropriate_fields = [
        'CELL_LINE',
        'INHIBITOR',
        'TISSUE',
        'LIBRARYTYPE',
        "ScientificName",
        # "FRACTION",
        # "Infected",
        # "Disease",
        "Sex",
        # "Cancer",
        # "Growth_Condition",
        # "Stress",
        # "Genotype",
        # "Feeding",
        # "Temperature",
    ]
    toggle_fields = [
        'trips_id',
        'gwips_id',
        'ribocrypt_id',
        'FASTA_file',
        'verified',
    ]
    clean_names = get_clean_names()

    cache_key = f"samples_view_{request.GET.urlencode()}"
    cached_result = cache.get(cache_key)
    if cached_result is not None:
        return cached_result

    # Get all the query parameters from the request
    query_params = request.GET.lists()
    filtered_columns = [
        get_original_name(name, clean_names)
        for name, values in request.GET.lists()
    ]
    param_options = {}
    for field in Sample._meta.fields:
        # if field.get_internal_type() == 'CharField':
        if field.name in filtered_columns:
            # update query_params to remove the current field to ensure this
            # field is not filtered by itself
            query_params = [
                i for i in request.GET.lists()
                if get_original_name(i[0], clean_names) != field.name
            ]
            query = build_query(request, query_params, clean_names)
            sample_entries = Sample.objects.filter(query)

            filtered_samples = sample_entries.values(field.name).annotate(
                count=Count(field.name)).order_by('-count')
            param_options[field.name] = filtered_samples
        else:
            query_params = request.GET.lists()
            query = build_query(request, query_params, clean_names)
            sample_entries = Sample.objects.filter(query)

            values = sample_entries.values(field.name).annotate(
                count=Count(field.name)).order_by('-count')
            param_options[field.name] = values

    clean_results_dict = handle_filter(param_options, appropriate_fields,
                                       clean_names)
    clean_results_dict.pop('count', None)
    query_params = []
    for name, values in request.GET.lists():
        if get_original_name(name, clean_names) in appropriate_fields or name in toggle_fields:
            query_params.append((name, values))

    query = build_query(request, query_params, clean_names)
    # get entries to populate table (only the page shown is fetched)
    sample_entries = Sample.objects.filter(query).order_by(
        *sort_order(request, SAMPLE_SORTS,
                    ['-INHIBITOR', '-LIBRARYTYPE', '-pk']))

    # Paginate the samples
    paginator = Paginator(sample_entries, page_size(request))
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'page_obj': page_obj,
        'param_options': clean_results_dict,
        'trips_toggle_state': request.GET.get('trips_id', False),
        'gwips_toggle_state': request.GET.get('gwips_id', False),
        'ribocrypt_toggle_state': request.GET.get('ribocrypt_id', False),
        'FASTA_file_toggle_state': request.GET.get('FASTA_file', False),
        'verified_toggle_state': request.GET.get('verified', False),
    }
    # Render the studies template with the filtered and paginated studies
    # and the filter options
    response = render(request, 'main/samples.html', context)
    cache.set(cache_key, response, 60 * 15)  # Cache for 15 minutes

    # Render the studies template with the filtered and paginated studies
    # and the filter options
    return response


def studies(request: HttpRequest) -> str:
    """
    Render a page of studies filtered by query parameters.

    Arguments:
    - request (HttpRequest): the HTTP request for the page

    Returns:
    - (render): the rendered HTTP response for the page
    """
    appropriate_fields = [
        'ScientificName',
        'Organism',
    ]
    boolean_fields = [
        'PMID',
    ]
    clean_names = get_clean_names()
    pubmed_filter = pubmed_query(request.GET.getlist('PubMed'))

    cache_key = f"studies_view_{request.GET.urlencode()}"
    cached_result = cache.get(cache_key)
    if cached_result is not None:
        return cached_result

    # Get all the query parameters from the request
    # used for filter panel
    query_params = [(name, values) for name, values in request.GET.lists()
                    if name in appropriate_fields or name in boolean_fields]
    filtered_columns = [
        get_original_name(name, clean_names)
        for name, values in request.GET.lists()
    ]

    boolean_param_options = {}
    # Get the unique values and counts for each parameter within the
    # filtered queryset
    param_options = {}
    for field in Study._meta.fields:
        if field.get_internal_type() == 'CharField':
            if field.name in filtered_columns:
                # update query_params to remove the current field to ensure
                # this field is not filtered by itself
                query_params = [
                    i for i in request.GET.lists()
                    if get_original_name(i[0], clean_names) != field.name
                ]
                query_params = [
                    (name, values) for name, values in request.GET.lists()
                    if (name in appropriate_fields or name in boolean_fields)
                    and get_original_name(name, clean_names) != field.name
                ]

                query = build_query(request, query_params, clean_names)
                studies = Study.objects.filter(query & pubmed_filter)

                filtered_studies = studies.values(field.name).annotate(
                    count=Count(field.name)).order_by('-count')
                param_options[field.name] = filtered_studies
            else:
                query = build_query(request, query_params, clean_names)
                studies = Study.objects.filter(query & pubmed_filter)

                values = studies.values(field.name).annotate(
                    count=Count(field.name)).order_by('-count')
                param_options[field.name] = values

        if field.name in boolean_fields:
            query = build_query(request, query_params, clean_names)
            studies = Study.objects.filter(query)
            values = studies.values(field.name).annotate(
                count=Count(field.name)).order_by('-count')

            available = [
                i for i in values if i[field.name] not in PMID_MISSING + [None]
            ]
            available_count = sum([i['count'] for i in available])

            not_available = [
                i for i in values if i[field.name] in PMID_MISSING + [None]
            ]
            not_available_count = sum([i['count'] for i in not_available])

            clean_name = clean_names[field.name]
            boolean_param_options[clean_name] = [{
                'count': available_count,
                'value': 'Available'
            }, {
                'count': not_available_count,
                'value': 'Not Available'
            }]

    # rebuild query to populate table
    query_params = [(name, values) for name, values in request.GET.lists()
                    if name in appropriate_fields or name in boolean_fields]
    query = build_query(request, query_params, clean_names)
    study_entries = Study.objects.filter(query & pubmed_filter)

    # The idea behind sample filter options is to be able to filter a study
    # based on the metadata of the samples it contains. This is not currently
    # implemented
    # sample_filter_options = get_sample_filter_options(study_entries)
    clean_results_dict = handle_filter(param_options, appropriate_fields,
                                       clean_names)
    clean_results_dict = {
        **clean_results_dict,
        **boolean_param_options
    }  # , **sample_filter_options}
    clean_results_dict.pop('count', None)

    study_entries = study_entries.order_by(
        *sort_order(request, STUDY_SORTS, ['pk']))

    # Paginate the studies
    paginator = Paginator(study_entries, page_size(request))
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    response = render(request, 'main/studies.html', {
        'page_obj': page_obj,
        'param_options': clean_results_dict
    })
    cache.set(cache_key, response, 60 * 15)  # Cache for 15 minutes

    # Render the studies template with the filtered and paginated studies
    # and the filter options
    return response


def about(request: HttpRequest) -> str:
    """
    Render the about page.

    Arguments:
    - request (HttpRequest): the HTTP request for the page

    Returns:
    - (render): the rendered HTTP response for the page
    """
    return render(request, "main/about.html", {})


def study_detail(request: HttpRequest, query: str) -> str:
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
    ls = list(Sample.objects.filter(BioProject=query).order_by('pk'))

    # Per-sample links, plus study-level links covering every sample
    urls = attach_links(ls, selection={'bioproject': [study_model.BioProject]})

    # Return all results from Sample and query the sqlite too and add this to
    # the table
    context = {
        'Study': study_model,
        'ls': ls,
        'bioproject_trips_link': urls['trips_link'],
        'bioproject_trips_name': urls['trips_name'],
        'bioproject_gwips_link': urls['gwips_link'],
        'bioproject_gwips_name': urls['gwips_name'],
        'bioproject_gwips_native_link': urls['gwips_native_link'],
        'bioproject_gwips_native_name': urls['gwips_native_name'],
        'bioproject_ribocrypt_link': urls['ribocrypt_link'],
        'bioproject_ribocrypt_name': urls['ribocrypt_name'],
    }
    return render(request, 'main/study.html', context)


def sample_detail(request: HttpRequest, query: str) -> str:
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
        'Genotype',
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
        'Nuclease',
        'Kit',
    ]

    clean_names = get_clean_names()
    sample_model = get_object_or_404(Sample, Run=query)

    ls = Sample.objects.filter(Run=query)

    ks = []
    for key, value in ls.values()[0].items():
        if value not in ['nan', '']:
            if key in appropriate_fields:
                ks.append((clean_names[key], value))
    # check if custom track exists
    if ls[0].bigwig_forward_link or ls[0].bigwig_reverse_link:
        custom_track = "View Custom Track"
    else:
        custom_track = ""
    # generate GWIPS and Trips URLs
    per_run, _ = sample_links([sample_model])
    urls = per_run[sample_model.Run]

    paginator = Paginator(ls, len(ls))
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    context = {
        'Sample': sample_model,
        'ls': page_obj,
        'ks': ks,
        'trips': urls['trips_link'],
        'trips_name': urls['trips_name'],
        'gwips': urls['gwips_link'],
        'gwips_name': urls['gwips_name'],
        'gwips_native': urls['gwips_native_link'],
        'gwips_native_name': urls['gwips_native_name'],
        'ribocrypt': urls['ribocrypt_link'],
        'ribocrypt_name': urls['ribocrypt_name'],
        'custom_track': custom_track,
        'fastp': get_fastp_report_link(sample_model.Run),
        'fastqc': get_fastqc_report_link(sample_model.Run),
    }
    return render(request, 'main/sample.html', context)


class StudyListView(FilterView):
    """
    View to display a list of studies based on applied filters.
    """
    model = Study
    template_name = 'study_list.html'
    filterset_class = StudyFilter


def sample_select_form(request: HttpRequest) -> str:
    """
    handle the samples selection form and either call links or
    download metadata

    Arguments:
    - request (HttpRequest): the HTTP request for the page

    Returns:
    - (render): the rendered HTTP response for the page
    """
    selected = dict(request.GET.lists())
    if 'download-metadata' in selected:
        return generate_samples_csv(request)
    elif 'link-all' in selected:
        return links(request)
    elif "links" in selected:
        return links(request)
    elif 'metadata' in selected:
        return generate_samples_csv(request)
    else:
        return links(request)


# File suffix for each downloadable file type
DOWNLOAD_FILE_TYPES = {
    "reads": ".collapsed.fa.gz",
    "counts": "_counts.txt",
    "bams": ".bam",
    "adapter_report": ".adapter.fa",
    "fastp": ".html",
    "fastqc": "_fastqc.html",
    "ribometric": "bamtrans_RiboMetric.html",
    "bigwig (forward)": ".forward.bw",
    "bigwig (reverse)": ".reverse.bw",
}


def generate_link(run, file_type="reads"):
    """
    Generate Link for a specific run of a given type (default is reads)
    Ensure path is valid before returning link

    Arguments:
    - run (str): the run accession number
    - type (str): the type of link to generate (default is reads)

    Returns:
    - (str): the link to the file
    OR
    - (None): if the link is not valid
    """
    path_suffixes = DOWNLOAD_FILE_TYPES
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

    suffix = path_suffixes[file_type]
    path = find_run_file(path_dirs[file_type], run, [suffix, "_1" + suffix])
    return f"/static2/{path}" if path else None


def get_links_sample_entries(selected: dict, request: HttpRequest):
    """
    Get the sample entries for a given links request

    Arguments:
    - selected (dict): the params from the query
    - request (HttpRequest): the HTTP request for the page

    Retruns:    
    - sample_entries: The entries matching the links query
    """
    sample_entries = Sample.objects.all()

    # Parse query from request
    if 'query' in selected:
        if selected['query'][0]:
            sample_query = select_all_query(selected['query'][0])
            sample_entries = sample_entries.filter(sample_query)
        bioproject_query = sample_entries.values("BioProject").distinct()
        # trips = Trips.objects.filter(Run__in=sample_entries)
        # print(sample_entries)
        # print(trips)

    elif 'run' in selected:
        sample_query = selected['run']
        sample_entries = Sample.objects.filter(Run__in=sample_query)
        bioproject_query = sample_entries.values("BioProject").distinct()
        # sample_query = build_run_query(selected['run'])

    elif 'bioproject' in selected:
        bioproject_query = selected['bioproject']
        sample_entries = Sample.objects.filter(BioProject__in=bioproject_query)
        # sample_query = build_bioproject_query(selected['bioproject'])

    else:
        sample_entries = Sample.objects.none()
        bioproject_query = []

    return sample_entries, bioproject_query


# Most curated-track links shown on the links page; a wide selection can
# cover hundreds of studies, and the list is a convenience, not a listing
MAX_NATIVE_GWIPS_LINKS = 10


def native_gwips_links(sample_entries) -> list:
    '''
    Curated GWIPS-viz track links for the studies among the selected samples.

    Returns:
    - (list): dicts with bioproject, organism and link, newest first by
      table order, capped at MAX_NATIVE_GWIPS_LINKS
    '''
    projects = sample_entries.values_list('BioProject', flat=True).distinct()
    rows = GWIPS.objects.filter(
        BioProject__in=list(projects)).order_by('pk')[:MAX_NATIVE_GWIPS_LINKS]
    links = []
    for row in rows:
        link, name = gwips_native_link([row])
        if name:
            links.append({'bioproject': row.BioProject,
                          'organism': row.Organism or row.gwips_db,
                          'link': link})
    return links


def links(request: HttpRequest) -> str:
    """
    Render the links page.

    Arguments:
    - request (HttpRequest): the HTTP request for the page

    Returns:
    - (render): the rendered HTTP response for the page
    """
    selected = dict(request.GET.lists())

    sample_entries, bioproject_query = get_links_sample_entries(selected, request)
    # generate GWIPS and Trips URLs
    if sample_entries:
        # print(sample_query,
        #       "Anmol"
        #       )
        # trips = handle_trips_urls(sample_query)
        if 'bioproject' in selected:
            trips_sql = Trips.objects.filter(BioProject__in=bioproject_query)
        else:
            trips_sql = Trips.objects.filter(Run__in=sample_entries.values("Run"))
        trips_sql = trips_sql.order_by('pk')


        trips = []
        if trips_sql:
            trips_sql = pd.DataFrame(list(trips_sql.values()))
            trips_sql["Trips_id"] = trips_sql["Trips_id"].apply(trips_file_id)
            trips_sql = trips_sql.groupby(
                ["organism","transcriptome"]
            )["Trips_id"].apply(list).reset_index()
            for _, trip in trips_sql.iterrows():
                trips.append({
                    'clean_organism': f"{trip['organism'].replace('_', ' ').capitalize()} - {trip['transcriptome']}",
                    'organism': trip['organism'],
                    'transcriptome': trip['transcriptome'],
                    'files': 'files='+','.join(trip['Trips_id'])
                })
        else:
            trips.append(
                {
                    'clean_organism': 'None of the Selected Runs are available on Trips-Viz',
                    'organism': 'None of the Selected Runs are available on Trips-Viz',
                }
            )
            
        
        # Genome browser: one link per organism, built from bigWigs
        gwips = genome_tracks.selection_links(
            sample_entries, genome_tracks.selection_from(request.GET))
        if not gwips:
            gwips = [{
                'clean_organism': 'None of the Selected Runs have genome browser tracks',
            }]
        # The curated tracks GWIPS-viz already hosts, for whichever of the
        # selected studies it has loaded
        gwips_native = native_gwips_links(sample_entries)

    else:
        trips = [{
            'clean_organism':
            'None of the Selected Runs are available on Trips-Viz',
            'organism':
            'None of the Selected Runs are available on Trips-Viz',
        }]
        gwips = [{
            'clean_organism': 'None of the Selected Runs have genome browser tracks',
        }]
        gwips_native = []
    # sample_entries = Sample.objects.filter(sample_query)

    # Retrieve entries

    # Paginate
    paginator = Paginator(sample_entries, page_size(request))
    page_number = request.GET.get('page')
    sample_page_obj = paginator.get_page(page_number)

    # get links for entries on page
    attach_links(sample_page_obj)

    return render(
        request, 'main/links.html', {
            'sample_results': sample_page_obj,
            'trips': trips,
            'gwips': gwips,
            'gwips_native': gwips_native,
            #            'ribocrypt': ribocrypt,
            'current_url': request.GET.urlencode(),
        })


def generate_samples_csv(request) -> HttpResponse:
    '''
    Generate and return a csv file containing the metadata for the samples in
    the database based on the request, using chunked processing for large queries.
    If no specific query is provided, returns all metadata.
    '''
    selected = dict(request.GET.lists())
    
    exclude_fields = [
        "id",
        "verified",
        "trips_id",
        "gwips_id",
        "ribocrypt_id",
        "readfile",
    ]

    CHUNK_SIZE = 500

    def process_queryset_in_chunks(base_query, chunk_size):
        """Process a large queryset in smaller chunks to avoid SQLite limitations"""
        offset = 0
        total_processed = 0
        
        while True:
            chunk = base_query.order_by('id')[offset:offset + chunk_size]
            chunk_data = list(chunk)  # Evaluate the chunk
            
            if not chunk_data:
                break
                
            for item in chunk_data:
                total_processed += 1
                yield item
                
            offset += chunk_size

    def get_initial_query():
        if 'download-metadata' in selected:
            sample_query = select_all_query(selected['download-metadata'][0])
            sample_entries = Sample.objects.filter(sample_query)
            
            runs = sample_entries.values_list('Run', flat=True)
            
            if not str(sample_query) == "(AND: )":
                return build_run_query(runs)
                
        elif 'run' in selected:
            print(f"Using run query: {selected['run']}")  # Debug log
            return build_run_query(selected['run'])
            
        elif 'bioproject' in selected:
            return build_bioproject_query(selected['bioproject'])
            
        # Return empty Q object for all records instead of None
        return Q()

    sample_query = get_initial_query()
    
    # No need to check if sample_query is None since we always return a Q object
    base_queryset = Sample.objects.filter(sample_query)
    
    response = HttpResponse(content_type="text/csv")
    response["Content-Disposition"] = 'attachment; filename="RiboSeqOrg_Metadata.csv"'

    fields = [field.name for field in Sample._meta.get_fields() 
             if field.name not in exclude_fields]

    writer = csv.writer(response)
    writer.writerow(fields)  # Write header row
    
    rows_written = 0  # Debug counter
    
    # Process the queryset in chunks
    for item in process_queryset_in_chunks(base_queryset, CHUNK_SIZE):
        row_data = [getattr(item, field) for field in fields 
                   if field not in exclude_fields]
        writer.writerow(row_data)
        rows_written += 1  # Debug counter
        
    return response

def build_run_query(runs):
    """
    Build a simplified query for runs
    """
    from django.db.models import Q
    
    # Build a single Q object instead of combining multiple
    query = Q(Run__in=list(runs))
    return query

def build_bioproject_query(bioprojects):
    """
    Build a simplified query for bioprojects
    """
    from django.db.models import Q
    
    # Build a single Q object instead of combining multiple
    query = Q(BioProject__in=list(bioprojects))
    return query

def reports(request, query) -> str:
    '''
    Generate reports page

    Arguments:
    - request (HttpRequest): the HTTP request for the page

    Returns:
    - (render): the rendered HTTP response for the page
    '''

    return render(
        request, 'main/reports.html', {
            'fastp': get_fastp_report_link(query),
            'fastqc': get_fastqc_report_link(query),
            'ribometric': get_ribometric_report_link(query)
        })


def download_all(request) -> HttpResponse:
    '''
    Download all corresponding files for the accessions in the request
    '''
    selected = dict(request.GET.lists())
    file_type = selected.get('file_type', ['reads'])[0]
    if file_type != "bigwigs" and file_type not in DOWNLOAD_FILE_TYPES:
        return HttpResponseBadRequest(f"Unknown file_type: {file_type}")

    sample_entries, _ = get_links_sample_entries(selected, request)

    if not sample_entries.exists():
        return HttpResponseNotFound("No Samples Selected")

    run_accessions = sample_entries.values_list('Run', flat=True)
    filename = str(uuid.uuid4())

    bash_content = [
        "#!/bin/bash\n\n",
        "# Base URL\n",
        "BASE_URL=\"https://rdp.ucc.ie\"\n\n",
        "# Array of file paths\n",
        "FILES=(\n"
    ]

    for accession in run_accessions:
        formats = ["bigwig (forward)", "bigwig (reverse)"] if file_type == "bigwigs" else [file_type]
        for file_format in formats:
            link = generate_link(accession, file_format)
            if link:
                bash_content.append(f'  "{link}"\n')

    if len(bash_content) > 5:  # Check if any files were added to the array
        bash_content.extend([
            ")\n\n",
            "# Download function\n",
            "download_file() {\n",
            "  local url=\"$BASE_URL/$1\"\n",
            "  echo \"Downloading: $url\"\n",
            "  wget -c \"$url\"\n",
            "}\n\n",
            "# Main loop\n",
            "for file in \"${FILES[@]}\"; do\n",
            "  download_file \"$file\"\n",
            "done\n\n",
            "echo \"All downloads completed!\"\n"
        ])
    else:
        bash_content = ["#!/bin/bash\n\n", "echo 'No files available for download'\n"]

    response = HttpResponse("".join(bash_content),
                            content_type="application/x-sh")
    response["Content-Disposition"] = f"attachment; filename=RiboSeqOrg_Download_{filename}.sh"

    return response


def custom_track(request, query) -> HttpResponse:
    '''
    UCSC custom track lines for one run's bigWigs, as plain text

    Arguments:
    - request (HttpRequest): the HTTP request for the page
    - query (str): the run accession

    Returns:
    - (HttpResponse): the track lines
    '''
    sample = get_object_or_404(Sample, Run=query)
    lines = genome_tracks.track_lines([sample])
    if not lines:
        return HttpResponseNotFound("No bigWig tracks available for this run",
                                    content_type='text/plain')
    header = ['# Paste into https://gwips.ucc.ie/cgi-bin/hgCustom '
              '(or any UCSC Genome Browser custom tracks page)']
    return HttpResponse('\n'.join(header + lines) + '\n',
                        content_type='text/plain')


def genome_track_lines(request) -> HttpResponse:
    '''
    UCSC custom track lines for a selection of runs of one organism, fetched
    by the genome browser from links built in genome_tracks.selection_link.
    Takes the links-page parameters (run / bioproject / query) plus organism.
    '''
    organism = request.GET.get('organism', '')
    selected = genome_tracks.selection_from(request.GET)
    if not organism or not selected:
        return HttpResponseBadRequest('Give organism and run, bioproject or query',
                                      content_type='text/plain')
    sample_entries, _ = get_links_sample_entries(selected, request)
    samples = sample_entries.filter(ScientificName=organism).order_by('pk')
    return HttpResponse(genome_tracks.tracks_text(samples),
                        content_type='text/plain')


PIVOT_EXCLUDE = frozenset([
    'id', 'verified', 'Experiment', 'InsertDev', 'trips_id', 'gwips_id',
    'ribocrypt_id', 'FASTA_file', 'sample_title', 'MONTH', 'YEAR',
    'ENA_last_update', 'ENA_checklist', 'ENA_first_public',
    'INSDC_center_alias', 'INSDC_center_name', 'INSDC_first_public',
    'INSDC_last_update', 'INSDC_status', 'spots', 'SampleName', 'CenterName',
    'Submission', 'BioProject_id', 'Run', 'SRAStudy', 'Study_Pubmed_id',
    'Sample', 'BioSample', 'TaxID', 'AUTHOR', 'GEO_Accession',
    'Experiment_Date', 'date_sequenced', 'submission_date', 'date', 'Info',
])


def pivot(request):
    # Same for every visitor, so build the CSV once per cache period
    data = cache.get('pivot_csv')
    if data is None:
        columns = [f.attname for f in Sample._meta.concrete_fields
                   if f.attname not in PIVOT_EXCLUDE]
        samples = pd.DataFrame.from_records(
            Sample.objects.order_by('pk').values(*columns),
            columns=columns).fillna("Missing")
        data = samples.to_csv(encoding='utf8')
        cache.set('pivot_csv', data, 60 * 15)

    template = loader.get_template('main/pivot.html')

    context = {
        'data': data
    }

    return HttpResponse(template.render(context, request))


def vocabularies(request):
    return render(request, 'main/vocabularies.html')


def get_reference_data():
    references_dir = os.path.join(settings.RIBOSEQORG_DATA_DIR, 'references')
    reference_data = []

    for organism_dir in os.listdir(references_dir):
        organism_path = os.path.join(references_dir, organism_dir)
        if os.path.isdir(organism_path):
            organism_name = organism_dir.replace('_', ' ').title()
            gtf_file = next((f for f in os.listdir(organism_path) if f.endswith('.gtf')), None)
            fa_file = next((f for f in os.listdir(organism_path) if f.endswith('.fa')), None)

            if gtf_file and fa_file:
                reference_data.append({
                    'name': organism_name,
                    'gtf': os.path.join("static2", "references", organism_dir, gtf_file),
                    'fasta': os.path.join("static2", "references", organism_dir, fa_file)
                })

    return sorted(reference_data, key=lambda x: x['name'])


def references(request):
    reference_data = get_reference_data()
    return render(request, 'main/references.html', {'references': reference_data})
