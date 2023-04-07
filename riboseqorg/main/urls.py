from django.urls import path, re_path
from . import views

from .views import OrderListJson

urlpatterns = [
    path('', views.index, name='home'),
    path('home', views.index, name='home'),
    path('db', views.db, name='db'),
    path('add', views.add, name='add'),
    re_path(r'^my/datatable/data/$', OrderListJson.as_view(), name='order_list_json'),
]