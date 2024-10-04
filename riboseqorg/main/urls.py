from django.urls import path

from . import views

urlpatterns = [
    path(
        '', views.index, name='home'
        ),
    path(
        'home', views.index, name='home'
        ),
    path(
        'samples', views.samples, name='samples'
        ),
    path(
        'studies', views.studies, name='studies'
        ),
    path(
        'about', views.about, name='about'
        ),
    path(
        'Study/<str:query>/', views.study_detail, name='study'
        ),
    path(
        'Sample/<str:query>/', views.sample_detail, name='sample'
        ),
    path(
        'search/', views.SearchView.as_view(), name='search'
        ),
    path(
        'links/', views.links, name='links'
        ),
    path(
        'pivot/', views.pivot, name='pivot'
        ),
    path(
        'sample_select_form/',
        views.sample_select_form,
        name='sample_select_form',
        ),
    path(
        "generate-csv/",
        views.generate_samples_csv,
        name="generate_samples_csv"
        ),
    path(
        'download_all/', views.download_all, name='download_all'
        ),
    path(
        'reports/<str:query>', views.reports, name='reports'
        ),
    path(
        'Sample/<str:query>/custom', views.custom_track, name='custom_track'
        ),
    # API views
    path(
        'api/samples/',
        views.SampleListView.as_view(),
        name='api-sample-list'
        ),
    path(
        'api/samples/fields/',
        views.SampleFieldsView.as_view(),
        name='api-sample-fields'
         ),
    path(
        'vocabularies/',
        views.vocabularies,
        name='vocabularies'
        ),
    ]
