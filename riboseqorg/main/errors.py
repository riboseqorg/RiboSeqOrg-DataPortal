"""Custom error pages (wired up as handler404/handler500 in riboseqorg/urls.py)."""
import re

from django.shortcuts import render

from .forms import SearchForm

# Archive accessions people are likely to have in a broken link
ACCESSION = re.compile(
    r'(?<![A-Za-z0-9])((?:SRR|ERR|DRR|SRX|ERX|DRX|SRP|ERP|DRP|SRS|GSE|GSM|'
    r'PRJ[EDN][A-Z]?|SAMN|SAMEA|SAMD)\d+)', re.IGNORECASE)


def page_not_found(request, exception=None):
    match = ACCESSION.search(request.path)
    accession = match.group(1).upper() if match else ''
    form = SearchForm(initial={'query': accession})
    return render(request, '404.html', {
        'accession': accession,
        'search_form': form,
    }, status=404)
