from django.core.paginator import Paginator
from django.db.models import CharField, Q, Count
from django.db.models.functions import Length
from django.db.models.query import QuerySet
from django_filters.views import FilterView
from django.views import View
from django.http import HttpRequest, HttpResponse, HttpResponseNotFound
from django.shortcuts import render, get_object_or_404

import csv
from datetime import datetime
import mimetypes
import os
import uuid

from .filters import StudyFilter, SampleFilter
from .forms import SearchForm
from .models import Sample, Study

from .utilities import get_clean_names, get_original_name, \
    build_query, handle_filter, handle_gwips_urls, \
    handle_trips_urls, handle_ribocrypt_urls, \
    build_run_query, build_bioproject_query, \
    select_all_query, handle_urls_for_query, \
    get_fastp_report_link, get_fastqc_report_link

from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView
from .serializers import SampleSerializer


CharField.register_lookup(Length, 'length')


class SampleListView(generics.ListCreateAPIView):
    queryset = Sample.objects.all()
    serializer_class = SampleSerializer
    filterset_fields = ['Run']  # This allows filtering by the 'name' field


class SampleFileDownloadView(APIView):
    permission_classes = [
        permissions.IsAuthenticated
                          ]  # Optional: Set the required permissions

    def get(self, request, pk):
        try:
            instance = Sample.objects.get(pk=pk)
        except Sample.DoesNotExist:
            return Response(status=404)

        file_path = instance.file.path  # Assuming 'file' is a FileField
        with open(file_path, 'rb') as file:
            response = Response(file.read())
            response[
                'Content-Disposition'
                ] = f'attachment; filename="{instance.file.name}"'
            return response


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
    template_name = 'main/search.html'
    paginate_by = 10

    def get(self, request, *args, **kwargs):
        query = request.GET.get('query', '')
        search_form = SearchForm(request.GET or None)

        if query == '':
            study_results = Study.objects.all()
            sample_results = Sample.objects.all()
        else:
            study_results = self.get_study_results(Study, query)
            sample_results = self.get_sample_results(Sample, query)

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

    def get_sample_results(self, model, query):
        sample_results = model.objects.filter(
            # Q(verified__icontains=query) |
            # Q(trips_id__icontains=query) |
            # Q(gwips_id__icontains=query) |
            # Q(ribocrypt_id__icontains=query) |
            # Q(readfile__icontains=query) |
            # Q(BioProject__icontains=query) |
            Q(Run__icontains=query) | Q(spots__icontains=query)
            | Q(bases__icontains=query) | Q(avgLength__icontains=query)
            | Q(size_MB__icontains=query) | Q(Experiment__icontains=query)
            | Q(LibraryName__icontains=query) | Q(LibraryStrategy__icontains=query)
            | Q(LibrarySelection__icontains=query)
            | Q(LibrarySource__icontains=query) | Q(LibraryLayout__icontains=query)
            | Q(InsertSize__icontains=query) | Q(InsertDev__icontains=query)
            | Q(Platform__icontains=query) | Q(Model__icontains=query)
            | Q(SRAStudy__icontains=query) | Q(Study_Pubmed_id__icontains=query)
            | Q(Sample__icontains=query) | Q(BioSample__icontains=query)
            | Q(SampleType__icontains=query) | Q(TaxID__icontains=query)
            | Q(ScientificName__icontains=query) | Q(SampleName__icontains=query)
            | Q(CenterName__icontains=query) | Q(Submission__icontains=query)
            | Q(MONTH__icontains=query) | Q(YEAR__icontains=query)
            | Q(AUTHOR__icontains=query) | Q(sample_source__icontains=query)
            | Q(sample_title__icontains=query) | Q(LIBRARYTYPE__icontains=query)
            | Q(REPLICATE__icontains=query) | Q(CONDITION__icontains=query)
            | Q(INHIBITOR__icontains=query) | Q(BATCH__icontains=query)
            | Q(TIMEPOINT__icontains=query) | Q(TISSUE__icontains=query)
            | Q(CELL_LINE__icontains=query) | Q(FRACTION__icontains=query)
            | Q(ENA_first_public__icontains=query)
            | Q(ENA_last_update__icontains=query)
            | Q(INSDC_center_alias__icontains=query)
            | Q(INSDC_center_name__icontains=query)
            | Q(INSDC_first_public__icontains=query)
            | Q(INSDC_last_update__icontains=query)
            | Q(INSDC_status__icontains=query) | Q(ENA_checklist__icontains=query)
            | Q(GEO_Accession__icontains=query)
            | Q(Experiment_Date__icontains=query)
            | Q(date_sequenced__icontains=query)
            | Q(submission_date__icontains=query) | Q(date__icontains=query)
            | Q(STAGE__icontains=query) | Q(GENE__icontains=query)
            | Q(Sex__icontains=query) | Q(Strain__icontains=query)
            | Q(Age__icontains=query) | Q(Infected__icontains=query)
            | Q(Disease__icontains=query) | Q(Genotype__icontains=query)
            | Q(Feeding__icontains=query) | Q(Temperature__icontains=query)
            | Q(SiRNA__icontains=query) | Q(SgRNA__icontains=query)
            | Q(ShRNA__icontains=query) | Q(Plasmid__icontains=query)
            | Q(Growth_Condition__icontains=query) | Q(Stress__icontains=query)
            | Q(Cancer__icontains=query) | Q(microRNA__icontains=query)
            | Q(Individual__icontains=query) | Q(Antibody__icontains=query)
            | Q(Ethnicity__icontains=query) | Q(Dose__icontains=query)
            | Q(Stimulation__icontains=query) | Q(Host__icontains=query)
            | Q(UMI__icontains=query) | Q(Adapter__icontains=query)
            | Q(Separation__icontains=query) | Q(rRNA_depletion__icontains=query)
            | Q(Barcode__icontains=query)
            | Q(Monosome_purification__icontains=query)
            | Q(Nuclease__icontains=query) | Q(Kit__icontains=query)
            | Q(Info__icontains=query))
        return sample_results

    def get_study_results(self, model, query):
        study_results = model.objects.filter(
            Q(BioProject__icontains=query) | Q(Name__icontains=query)
            | Q(Title__icontains=query) | Q(Organism__icontains=query)
            | Q(Samples__icontains=query) | Q(SRA__icontains=query)
            | Q(Release_Date__icontains=query) | Q(Description__icontains=query)
            | Q(seq_types__icontains=query) | Q(GSE__icontains=query)
            | Q(PMID__icontains=query) | Q(Authors__icontains=query)
            | Q(Study_abstract__icontains=query)
            | Q(Publication_title__icontains=query) | Q(doi__icontains=query)
            | Q(Date_published__icontains=query) | Q(PMC__icontains=query)
            | Q(Journal__icontains=query) | Q(Paper_abstract__icontains=query)
            | Q(Email__icontains=query))
        return study_results

    def paginate_results(self, results, page_key, request):
        paginator = Paginator(results, self.paginate_by)
        page_number = request.GET.get(page_key)
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
    toggle_fields = [
        'trips_id',
        'gwips_id',
        'ribocrypt_id',
        'FASTA_file',
        'verified',
    ]
    clean_names = get_clean_names()

    # Get all the query parameters from the request
    query_params = request.GET.lists()
    filtered_columns = [
        get_original_name(name, clean_names)
        for name, values in request.GET.lists()
    ]

    # Get the unique values and counts for each parameter
    # within the filtered queryset
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
    query_params = [
        (name, values) for name, values in request.GET.lists()
        if get_original_name(name, clean_names) in appropriate_fields
        or name in toggle_fields
    ]
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
    return render(request, 'main/samples.html', context)


def studies(request: HttpRequest) -> str:
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

    # Render the studies template with the filtered and paginated studies
    # and the filter options
    return render(request, 'main/studies.html', {
        'page_obj': page_obj,
        'param_options': clean_results_dict
    })


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
        # get download link
        link = generate_link(entry.BioProject, entry.Run)
        if isinstance(link, str):
            entry.link = f"/file-download/{link}"
            entry.link_type = "FASTA"
        else:
            entry.link = ""
            entry.link_type = "Not Available"

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

    # generate GWIPS and Trips URLs
    urls = handle_urls_for_query(request, sample_query)

    for entry in ls:
        link = generate_link(entry.BioProject, entry.Run)
        if isinstance(link, str):
            entry.link = f"{link}"
            entry.link_type = "FASTA"
        else:
            entry.link = ""

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


def generate_link(project, run, type="reads"):
    """
    Generate Link for a specific run of a given type (default is reads)
    Ensure path is valid before returning link

    Arguments:
    - project (str): the project accession number
    - run (str): the run accession number
    - type (str): the type of link to generate (default is reads)

    Returns:
    - (str): the link to the file
    OR
    - (None): if the link is not valid
    """
    server_base = "/home/DATA/RiboSeqOrg-DataPortal-Files/RiboSeqOrg"
    path_suffixes = {
        "reads": "_clipped_collapsed.fastq.gz",
        "counts": "_counts.txt",
    }
    path_dirs = {
        "reads": "collapsed_fastq",
        "counts": "counts",
    }
    project = str(project)
    run = str(run)
    if os.path.exists(
            os.path.join(server_base, path_dirs[type],
                         run + path_suffixes[type])):
        return f"/static2/{path_dirs[type]}/{run + path_suffixes[type]}"

    elif os.path.exists(
            os.path.join(server_base, path_dirs[type],
                         run + "_1" + path_suffixes[type])):
        return f"/static2/{path_dirs[type]}/{run}_1{path_suffixes[type]}"

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


def links(request: HttpRequest) -> str:
    """
    Render the links page.

    Arguments:
    - request (HttpRequest): the HTTP request for the page

    Returns:
    - (render): the rendered HTTP response for the page
    """
    selected = dict(request.GET.lists())

    # Parse query from request
    if 'query' in selected:
        sample_query = select_all_query(selected['query'][0])
        if "PubMed" in selected['query'][0] and "Available" in selected[
                'query'][0]:
            sample_entries = Sample.objects.filter(
                BioProject__PMID__length__gt=0)
        sample_entries = Sample.objects.filter(sample_query)
        runs = sample_entries.values_list('Run', flat=True)
        if not str(sample_query) == "(AND: )":
            sample_query = build_run_query(runs)

    elif 'run' in selected:
        sample_query = build_run_query(selected['run'])

    elif 'bioproject' in selected:
        sample_query = build_bioproject_query(selected['bioproject'])

    else:
        sample_page_obj = None
        sample_query = None

    # generate GWIPS and Trips URLs
    if sample_query is not None:
        trips = handle_trips_urls(sample_query)
        if 'query' in selected:
            gwips = handle_gwips_urls(request, sample_query)
            ribocrypt = handle_ribocrypt_urls(request, sample_query)
        else:
            gwips = handle_gwips_urls(request)
            ribocrypt = handle_ribocrypt_urls(request)

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
    sample_entries = Sample.objects.filter(sample_query)

    # Retrieve entries
    sample_entries = Sample.objects.filter(sample_query)

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

        link = generate_link(entry.BioProject, entry.Run)
        if isinstance(link, str):
            entry.link = f"{link}"
            entry.link_type = "FASTA"
        else:
            entry.link = ""
    return render(
        request, 'main/links.html', {
            'sample_results': sample_page_obj,
            'trips': trips,
            'gwips': gwips,
            'ribocrypt': ribocrypt,
            'current_url': request.get_full_path(),
        })


def generate_samples_csv(request) -> HttpResponse:
    '''
    Generate and return a csv file containing the metadata for the samples in
    the database based on the request
    '''
    selected = dict(request.GET.lists())

    if 'download-metadata' in selected:
        sample_query = select_all_query(selected['download-metadata'][0])
        sample_entries = Sample.objects.filter(sample_query)
        runs = sample_entries.values_list('Run', flat=True)
        if not str(sample_query) == "(AND: )":
            sample_query = build_run_query(runs)
    elif 'run' in selected:
        sample_query = build_run_query(selected['run'])
    elif 'bioproject' in selected:
        sample_query = build_bioproject_query(selected['bioproject'])
    else:
        sample_query = None

    if sample_query is not None:
        queryset = Sample.objects.filter(sample_query)

        response = HttpResponse(content_type="text/csv")
        response[
            "Content-Disposition"
            ] = 'attachment; filename="RiboSeqOrg_Metadata.csv"'

        fields = [field.name for field in Sample._meta.get_fields()]

        writer = csv.writer(response)
        writer.writerow(fields)  # Write header row

        for item in queryset:
            writer.writerow([getattr(item, field)
                             for field in fields])  # Write data rows

        return response
    else:
        return HttpResponseNotFound("No Samples Selected")


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
        })


def download_all(request) -> HttpRequest:
    '''
    Download all corresponding files for the accessions in the request
    '''
    selected = dict(request.GET.lists())
    filename = str(uuid.uuid4())

    static_base_path = "/home/DATA/RiboSeqOrg-DataPortal-Files/RiboSeqOrg/download-files"

    file_content = ["#!/usr/bin/env bash\n", "wget -c "]
    filepath = f"{static_base_path}RiboSeqOrg_Download_{filename}.sh"

    with open(filepath, 'w') as f:
        for accession in selected['run']:
            link = generate_link(accession, accession)
            if link:
                file_content.append(f"https://rdp.ucc.ie/{link} ")

        if file_content == ["#!/usr/bin/env bash\n", "wget -c "]:
            file_content.append("echo 'No files Available for download'")

        f.writelines(file_content)

    path = open(filepath, "r")
    mime_type, _ = mimetypes.guess_type(filepath)
    response = HttpResponse(path, content_type=mime_type)
    response[
        "Content-Disposition"
        ] = f"attachment; filename=RiboSeqOrg_Download_{filename}.sh"
    return response
