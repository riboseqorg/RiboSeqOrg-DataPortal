from django.urls import path, re_path
from . import views

urlpatterns = [
    path('', views.recode, name='recode'),
    path('home', views.index, name='home'),
    path('samples', views.samples, name='samples'),
    path('studies', views.studies, name='studies'),
    path('studies/', views.StudyListView.as_view(), name='study-list'),
    path('samples/', views.SampleListView.as_view(), name='sample-list'),
    path('about', views.about, name='about'),
    path('Study/<str:query>/', views.study_detail, name='study'),
    path('Sample/<str:query>/', views.sample_detail, name='sample'),
    path('search/', views.search, name='search'),
    path('links/', views.links, name='links'),
    path('sample_select_form/', views.sample_select_form, name='sample_select_form'),
    path("generate-csv/", views.generate_samples_csv, name="generate_samples_csv"),
    path('download/recode-db/', views.download_recode_db, name='download_recode_db'),
    path('downlaod_selected/', views.download_selected, name='download_selected'),
]
