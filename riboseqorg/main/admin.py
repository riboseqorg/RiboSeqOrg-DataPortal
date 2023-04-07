from django.contrib import admin

from .models import Dataset, Study
# Register your models here.

admin.site.register(Dataset)
admin.site.register(Study)