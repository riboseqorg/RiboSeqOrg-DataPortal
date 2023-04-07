from django.shortcuts import render
from django.core.paginator import Paginator

from django.http import HttpResponseRedirect
from .models import Data, Sample
from .forms import addNewSample

from django_datatables_view.base_datatable_view import BaseDatatableView
from django.utils.html import escape

import pandas as pd


class OrderListJson(BaseDatatableView):
    # The model we're going to show
    model = Data

    # define the columns that will be returned
    columns = ['sample_name', 'sample_description', 'cell_line', 'treatment', 'library_type']

    # define column names that will be used in sorting
    # order is important and should be same as order of columns
    # displayed by datatables. For non-sortable columns use empty
    # value like ''
    order_columns = ['sample_name', 'sample_description', 'cell_line', 'treatment', 'library_type']

    # set max limit of records returned, this is used to protect our site if someone tries to attack our site
    # and make it return huge amount of data
    max_display_length = 500

    def render_column(self, row, column):
        # We want to render user as a custom column
        if column == 'user':
            # escape HTML for security reasons
            return escape('{0} {1}'.format(row.customer_firstname, row.customer_lastname))
        else:
            return super(OrderListJson, self).render_column(row, column)

    def filter_queryset(self, qs):
        # use parameters passed in GET request to filter queryset

        # simple example:
        search = self.request.GET.get('search[value]', None)
        if search:
            qs = qs.filter(name__istartswith=search)

        # more advanced example using extra parameters
        filter_customer = self.request.GET.get('customer', None)

        if filter_customer:
            customer_parts = filter_customer.split(' ')
            qs_params = None
            for part in customer_parts:
                q = Q(customer_firstname__istartswith=part) | Q(customer_lastname__istartswith=part)
                qs_params = qs_params | q if qs_params else q
            qs = qs.filter(qs_params)
        return qs


# Create your views here.
def index(response):
    return render(response, "main/home.html", {})


def db(request):
    ls = Data.objects.get(id=1)
    print(ls.sample_set.all())
    paginator = Paginator(ls.sample_set.all(), 5) 
    
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    for i in page_obj:
        print(i)
    return render(request, 'main/database.html', {'ls': page_obj })


def add(response):
    if response.method == "POST":
        form = addNewSample(response.POST)

        if form.is_valid():
            new = Sample(
                riboseq=Data.objects.get(id=1),
                sample_name=form.cleaned_data["sample_name"],
                sample_description=form.cleaned_data["sample_description"],
                cell_line=form.cleaned_data["cell_line"],
                library_type=form.cleaned_data["library_type"],
                treatment=form.cleaned_data["treatment"],
            )
            new.save()
        return HttpResponseRedirect("/db")

    form = addNewSample()
    return render(response, "main/add.html", {'form': form})
