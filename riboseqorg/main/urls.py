from django.urls import path, re_path
from . import views

urlpatterns = [
    path('', views.index, name='home'),
    path('home', views.index, name='home'),
    path('samples', views.samples, name='samples'),
    path('studies', views.studies, name='studies'),
    path('about', views.about, name='about'),
    path('Study/<str:query>/', views.study_detail, name='study'),

]