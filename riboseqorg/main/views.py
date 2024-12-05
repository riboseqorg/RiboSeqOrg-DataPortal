import csv
import mimetypes
import os
import random
import re
import uuid
from datetime import datetime
from functools import reduce
from operator import or_
from typing import List, Type, Union

from urllib.parse import urlparse, parse_qs

import pandas as pd
from django.core.cache import cache
from django.core.paginator import Paginator
from django.db.models import CharField, Count, F, Q, Value
from django.db.models.functions import Concat, Length
from django.db.models.query import QuerySet
from django.http import HttpRequest, HttpResponse, HttpResponseNotFound
from django.shortcuts import get_object_or_404, loader, render
from django.views import View
from django_filters.views import FilterView
from rest_framework import filters, generics
from rest_framework.response import Response
from rest_framework.views import APIView

from .filters import StudyFilter
from .forms import SearchForm
from .models import GWIPS, Sample, Study, Trips
from .serializers import SampleSerializer
from .utilities import (build_bioproject_query, build_query, build_run_query,
                        get_clean_names, get_fastp_report_link,
                        get_fastqc_report_link, get_original_name,
                        get_ribometric_report_link, handle_filter,
                        handle_gwips_urls, handle_ribocrypt_urls,
                        handle_trips_urls, handle_urls_for_query,
                        select_all_query)

CharField.register_lookup(Length, 'length')


class SampleListView(generics.ListCreateAPIView):
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
        fields = self.request.query_params.get('fields')
        limit = self.request.query_params.get('limit', self.default_limit)

        # Start with an empty query
        query = Q()
        query = self.build_query(self.request.query_params)
        queryset = Sample.objects.filter(query)
        # Subset fields to just take selected
        if fields:
            requested_fields = set(fields.split(','))

            valid_fields = [
                field for field in requested_fields
                if field in [f.name for f in Sample._meta.get_fields()] or
                field in self.added_fields
            ]
            if valid_fields:
                self.serializer_class.Meta.fields = valid_fields
        else:
            self.serializer_class.Meta.fields = self.default_fields

        return queryset[:int(limit)]


class SampleFieldsView(APIView):
    def get(self, request):
        # Get all field names from the Sample model
        fields = [field.name for field in Sample._meta.get_fields()]
        return Response(fields)


def index(request: HttpRequest) -> str:
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
        paginator: Paginator = Paginator(results, self.paginate_by)
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
    # get entries to populate table
    sample_entries = Sample.objects.filter(query)
    sample_entries = list(
        reversed(sample_entries.order_by('INHIBITOR', 'LIBRARYTYPE')))

    # Paginate the studies
    paginator = Paginator(sample_entries, 10)
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
                studies = Study.objects.filter(query)

                filtered_studies = studies.values(field.name).annotate(
                    count=Count(field.name)).order_by('-count')
                param_options[field.name] = filtered_studies
            else:
                query = build_query(request, query_params, clean_names)
                studies = Study.objects.filter(query)

                values = studies.values(field.name).annotate(
                    count=Count(field.name)).order_by('-count')
                param_options[field.name] = values

        if field.name in boolean_fields:
            query = build_query(request, query_params, clean_names)
            studies = Study.objects.filter(query)
            values = studies.values(field.name).annotate(
                count=Count(field.name)).order_by('-count')

            available = [
                i for i in values if i[field.name] not in ['', 'nan', None]
            ]
            available_count = sum([i['count'] for i in available])

            not_available = [
                i for i in values if i[field.name] in ['', 'nan', None]
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
    study_entries = Study.objects.filter(query)
    for i, obj in enumerate(study_entries):
        date_string = obj.Release_Date
        try:
            date_obj = datetime.strptime(date_string,
                                         "%Y/%m/%d %H:%M").strftime("%m/%d/%Y")
            # Update the object in the database with the date object if needed
        except ValueError:
            print(obj.BioProject, date_string)
            # NOTE: For error associated dates
            date_obj = "01/01/2001"
        study_entries[i].Release_Date = date_obj


# study_entries.save()
# Handle invalid date strings if necessary

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

    # Paginate the studies
    paginator = Paginator(study_entries, 10)
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
    ls = Sample.objects.filter(BioProject=query)

    query = Q(BioProject=query)
    urls = handle_urls_for_query(request, query)

    for entry in ls:
        query = Q(Run=entry.Run)
        urls = handle_urls_for_query(request, query)
        entry.trips_link = urls['trips_link']
        entry.trips_name = urls['trips_name']
        entry.gwips_link = urls['gwips_link']
        entry.gwips_name = urls['gwips_name']
        entry.ribocrypt_link = urls['ribocrypt_link']
        entry.ribocrypt_name = urls['ribocrypt_name']

    # Return all results from Sample and query the sqlite too and add this to
    # the table
    context = {
        'Study': study_model,
        'ls': ls,
        'bioproject_trips_link': urls['trips_link'],
        'bioproject_trips_name': urls['trips_name'],
        'bioproject_gwips_link': urls['gwips_link'],
        'bioproject_gwips_name': urls['gwips_name'],
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
    sample_query = Q(Run=query)

    # check if custom track exists
    if ls[0].bigwig_forward_link or ls[0].bigwig_reverse_link:
        custom_track = "View Custom Track"
    else:
        custom_track = ""
    # generate GWIPS and Trips URLs
    urls = handle_urls_for_query(request, sample_query)

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
    print(selected)
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

    run = str(run)
    if os.path.exists(
            os.path.join(server_base, path_dirs[file_type], run[:6],
                         run + path_suffixes[file_type])):
        return f"/static2/{path_dirs[file_type]}/{run[:6]}/{run + path_suffixes[file_type]}"

    elif os.path.exists(
            os.path.join(server_base, path_dirs[file_type], run[:6],
                         run + "_1" + path_suffixes[file_type])):
        return f"/static2/{path_dirs[file_type]}/{run[:6]}/{run}_1{path_suffixes[file_type]}"

    return None


def check_path_exists(
        path, server_base="/home/DATA/RiboSeqOrg-DataPortal-Files/RiboSeqOrg"):
    """
    Check if a given path exists

    Arguments:
    - path (str): the path to check

    Returns:
    - (bool): True if the path exists, False otherwise
    """
    return os.path.exists(server_base + "/" + path)


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
        print(selected)
        if selected['query'][0]:
            sample_query = select_all_query(selected['query'][0])
            sample_entries = sample_entries.filter(sample_query)
            if "PubMed" in selected['query'][0] and "Available" in selected[
                    'query'][0]:
                sample_entries = sample_entries.filter(
                    BioProject__PMID__length__gt=0)
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
        sample_page_obj = None
        sample_query = None
    
    return sample_entries, bioproject_query


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


        trips = []
        if trips_sql:
            trips_sql = pd.DataFrame(list(trips_sql.values()))
            trips_sql["Trips_id"] = trips_sql["Trips_id"].apply(lambda x:x[:-2])
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
            
        
        # print(trips,"Anmol")
        gwips_sql = GWIPS.objects.filter(BioProject__in=bioproject_query)
        gwips = [] 
        if gwips_sql:
            inhibited = pd.DataFrame(list(sample_entries.values())).drop_duplicates(
                subset=['INHIBITOR', 'BioProject_id'], keep='first')
            noninhibited = inhibited[~inhibited['INHIBITOR'].str.contains(
                 'LTM|LAC|HARR', flags=re.IGNORECASE
            )]
            inhibited = inhibited[inhibited['INHIBITOR'].str.contains(
                 'LTM|LAC|HARR', flags=re.IGNORECASE
            )]

            gwips_sql = pd.DataFrame(list(gwips_sql.values()))
            gwips_sql_a = gwips_sql[gwips_sql["BioProject"].isin(

                inhibited["BioProject_id"].values)]
            gwips_sql_a["files"] = gwips_sql_a["GWIPS_Init_Suffix"].apply(
                lambda x: f"{x}=full"
            )

            gwips_sql_b = gwips_sql[gwips_sql["BioProject"].isin(
                noninhibited["BioProject_id"].values)]

            gwips_sql_b["files"] = gwips_sql_b["GWIPS_Elong_Suffix"].apply(
                lambda x: f"{x}=full"
            )

            gwips_sql = pd.concat([gwips_sql_a, gwips_sql_b]).groupby(["Organism","gwips_db","BioProject"])["files"].apply(list).reset_index()
            gwips_sql["files"] = gwips_sql["files"].apply(
                lambda x: "&".join(x)
            )
        
            for _, gwip in gwips_sql.iterrows():
                gwips.append({
                'clean_organism': gwip['Organism'],
                'bioproject': gwip['BioProject'],
                'gwipsDB': gwip['gwips_db'],
                'files': gwip['files']
            })
        if not gwips: 
            gwips = [
                {
                    'clean_organism': 'None of the Selected Runs are available on GWIPS-Viz',
                    'organism': 'None of the Selected Runs are available on GWIPS-Viz',
                    'gwips_db':"",
                    'files':""
                }
            ]

    else:
        trips = [{
            'clean_organism':
            'None of the Selected Runs are available on Trips-Viz',
            'organism':
            'None of the Selected Runs are available on Trips-Viz',
        }]
        gwips = [{
            'clean_organism':
            'None of the Selected Runs are available on GWIPS-Viz',
            'organism':
            'None of the Selected Runs are available on GWIPS-Viz',
        }]
    # sample_entries = Sample.objects.filter(sample_query)

    # Retrieve entries

    # Paginate
    paginator = Paginator(sample_entries, 10)
    page_number = request.GET.get('page')
    sample_page_obj = paginator.get_page(page_number)

    # get links for entries on page
    for entry in sample_page_obj:
        query = Q(Run=entry.Run)
        urls = handle_urls_for_query(request, query)
        entry.trips_link = urls['trips_link']
        entry.trips_name = urls['trips_name']
        entry.gwips_link = urls['gwips_link']
        entry.gwips_name = urls['gwips_name']
        entry.ribocrypt_link = urls['ribocrypt_link']
        entry.ribocrypt_name = urls['ribocrypt_name']

    return render(
        request, 'main/links.html', {
            'sample_results': sample_page_obj,
            'trips': trips,
            'gwips': gwips,
            #            'ribocrypt': ribocrypt,
            'current_url': request.GET.urlencode(),
        })


def generate_samples_csv(request) -> HttpResponse:
    '''
    Generate and return a csv file containing the metadata for the samples in
    the database based on the request, using chunked processing for large queries
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
            
        return None

    sample_query = get_initial_query()
    
    if sample_query is not None:
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
    else:
        return HttpResponseNotFound("No Samples Selected")

def build_run_query(runs):
    """
    Build a simplified query for runs
    """
    from django.db.models import Q
    
    # Convert to list if it's a queryset
    runs = list(runs)
    
    if not runs:
        return None
        
    # Build a single Q object instead of combining multiple
    query = Q(Run__in=runs)
    return query

def build_bioproject_query(bioprojects):
    """
    Build a simplified query for bioprojects
    """
    from django.db.models import Q
    
    # Convert to list if it's a queryset
    bioprojects = list(bioprojects)
    
    if not bioprojects:
        return None
        
    # Build a single Q object instead of combining multiple
    query = Q(Bioproject__in=bioprojects)
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

    sample_entries, _ = get_links_sample_entries(selected, request)

    if sample_entries is None:
        return HttpResponseNotFound("No Samples Selected")

    run_accessions = sample_entries.values_list('Run', flat=True)
    filename = str(uuid.uuid4())
    static_base_path = "/home/DATA/RiboSeqOrg-DataPortal-Files/RiboSeqOrg/download_files"
    filepath = f"{static_base_path}/RiboSeqOrg_Download_{filename}.sh"

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

    with open(filepath, 'w') as f:
        f.writelines(bash_content)

    with open(filepath, "rb") as f:
        mime_type, _ = mimetypes.guess_type(filepath)
        response = HttpResponse(f, content_type=mime_type)
        response["Content-Disposition"] = f"attachment; filename=RiboSeqOrg_Download_{filename}.sh"

    return response


def custom_track(request, query) -> str:
    '''
    Generate custom track page

    Arguments:
    - request (HttpRequest): the HTTP request for the page

    Returns:
    - (render): the rendered HTTP response for the page
    '''
    sample = Sample.objects.get(Run=query)

    context = {
        'Run': sample.Run,
        'BioProject': sample.BioProject,
        'description': sample.Info,
        'forward_url': sample.bigwig_forward_link,
        'reverse_url': sample.bigwig_reverse_link

    }   
    return render(request, 'main/custom_track.txt', context, content_type='text/plain')


def pivot(request):
    random.seed(42)
    samples = Sample.objects.all().order_by('?')# [:1000]
    samples = pd.DataFrame.from_records(samples.values()).fillna("Missing")
    columns2drop = ["id",'verified','Experiment','InsertDev', 'trips_id', 
                    'gwips_id', 'ribocrypt_id', 'FASTA_file','sample_title',
                    'MONTH', 'YEAR', 'ENA_last_update','sample_title',
                    'ENA_checklist','ENA_first_public', 'ENA_last_update',
                    'INSDC_center_alias', 'INSDC_center_name',
                    'INSDC_first_public', 'INSDC_last_update', 
                    'INSDC_status','spots','SampleName', 'CenterName',
                    'Submission', 'BioProject_id', 'Run','SRAStudy', 
                    'Study_Pubmed_id', 'Sample', 'BioSample','TaxID','AUTHOR',
                    'GEO_Accession', 'Experiment_Date','date_sequenced', 
                    'submission_date', 'date','Info']
    samples = samples.drop(columns2drop, axis=1)
    print(samples.columns)

    samples= samples.to_csv(encoding='utf8')
    if hasattr(samples, 'decode'):
        samples = samples.decode('utf8')

    template = loader.get_template('main/pivot.html')

    context = {
        'data': samples
    }

    return HttpResponse(template.render(context, request))


def vocabularies(request):
    return render(request, 'main/vocabularies.html')


def get_reference_data():
    references_dir = '/home/DATA/RiboSeqOrg-DataPortal-Files/RiboSeqOrg/references'
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