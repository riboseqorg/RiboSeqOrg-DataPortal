from django.shortcuts import render, get_object_or_404
from django.core.paginator import Paginator
from django.views.generic.detail import DetailView

from .models import Sample, Study

from django_datatables_view.base_datatable_view import BaseDatatableView
from django.utils.html import escape

import pandas as pd


# Create your views here.
def index(response):
    return render(response, "main/home.html", {})


def samples(request):
    ls = Sample.objects.all()
    paginator = Paginator(ls, 100) 
    
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    for i in page_obj:
        print(i)
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

