"""Template helpers shared by the portal's list and detail pages."""
import os
from datetime import datetime

from django import template
from django.contrib.staticfiles import finders
from django.templatetags.static import static
from django.utils.html import format_html

register = template.Library()

# Values that mean "no data" in the metadata tables
BLANK_VALUES = {'', 'nan', 'NaN', 'None', '<NA>', 'NA', '0.0'}

# Query parameters that belong to a paginator rather than a filter
PAGE_KEYS = ('page', 'study_page', 'sample_page')


@register.filter
def present(value) -> bool:
    """True when a metadata value holds real data."""
    if value is None:
        return False
    return str(value).strip() not in BLANK_VALUES


@register.simple_tag(takes_context=True)
def query_set(context, key, value) -> str:
    """Current query string with one key replaced, e.g. for paging."""
    params = context['request'].GET.copy()
    params[key] = value
    return '?' + params.urlencode()


@register.simple_tag(takes_context=True)
def query_toggle(context, key, value) -> str:
    """
    Current query string with one filter value added, or removed if it is
    already applied, back on page one.
    """
    params = context['request'].GET.copy()
    for page_key in PAGE_KEYS:
        params.pop(page_key, None)
    values = params.getlist(key)
    if value in values:
        params.setlist(key, [v for v in values if v != value])
    else:
        params.appendlist(key, value)
    return '?' + params.urlencode()


@register.simple_tag(takes_context=True)
def active_nav(context, *url_names) -> str:
    """'active' when the current page is one of the named URLs."""
    match = getattr(context.get('request'), 'resolver_match', None)
    return 'active' if match and match.url_name in url_names else ''


@register.filter
def label(name) -> str:
    """Human label for a field name, e.g. 'Library-Type' -> 'Library Type'."""
    return str(name).replace('_', ' ').replace('-', ' ').strip()


@register.filter
def short_date(value) -> str:
    """'2012/07/25 00:00' -> '2012-07-25'; '' for anything unparseable."""
    try:
        return datetime.strptime(str(value).strip(), '%Y/%m/%d %H:%M').strftime('%Y-%m-%d')
    except ValueError:
        return ''


@register.simple_tag(takes_context=True)
def sort_header(context, key, text, css=''):
    """
    A sortable <th>. The first click sorts ascending, the next descending.
    Changing the sort goes back to page one.
    """
    params = context['request'].GET.copy()
    current = params.get('sort', '')
    params.pop('page', None)
    if current == key:
        params['sort'] = '-' + key
        state, icon = 'ascending', 'fa-sort-up'
    elif current == '-' + key:
        params['sort'] = key
        state, icon = 'descending', 'fa-sort-down'
    else:
        params['sort'] = key
        state, icon = 'none', 'fa-sort'
    return format_html(
        '<th scope="col" class="sortable {}" aria-sort="{}">'
        '<a href="?{}">{}<i class="fa {} sort-icon" aria-hidden="true"></i></a></th>',
        css, state, params.urlencode(), text, icon)


@register.filter
def thousands(value) -> str:
    """14004 -> '14,004'."""
    try:
        return f'{int(value):,}'
    except (TypeError, ValueError):
        return value


@register.simple_tag
def asset(path) -> str:
    """
    Static URL with the file's modification time as a version, so browsers
    fetch a fresh copy whenever the file changes instead of a cached one.
    """
    url = static(path)
    found = finders.find(path)
    if found:
        url += f'?v={int(os.path.getmtime(found))}'
    return url
