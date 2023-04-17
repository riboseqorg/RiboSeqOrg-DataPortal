from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator
from django.views.generic.detail import DetailView

from django.db.models import Q
from .models import Sample, Study

from django_datatables_view.base_datatable_view import BaseDatatableView
from django.utils.html import escape

import pandas as pd
from .forms import SearchForm



# Create your views here.
def index(response):
    search_form = SearchForm()

    context = {
        'search_form': search_form,
    }
    return render(response, "main/home.html", context)

def search_results(request):
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

def samples(request):
    ls = Sample.objects.all()
    paginator = Paginator(ls, 100) 
    
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'main/samples.html', {'ls': page_obj })

def studies(request):
    ls = Study.objects.all()
    paginator = Paginator(ls, 5) 
    
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'main/studies.html', {'ls': ls })

def about(response):
    return render(response, "main/about.html", {})


def study_detail(request, query):
    study_model = get_object_or_404(Study, Accession=query)

    # return all results from Study where Accession=query
    ls = Sample.objects.filter(Study_Accession=query)
    context = {'Study': study_model, 'ls': ls}
    return render(request, 'main/study.html', context)

