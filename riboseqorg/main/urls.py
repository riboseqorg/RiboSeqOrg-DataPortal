from django.urls import path, re_path
from . import views

urlpatterns = [
    path('', views.index, name='home'),
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

]