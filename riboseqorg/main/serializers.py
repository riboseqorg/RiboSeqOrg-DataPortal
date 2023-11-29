
from rest_framework import serializers
from .models import Sample, Study


class SampleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Sample
        fields = '__all__'  # This is a default, it might not be needed if you dynamically set the fields in the view

    def __init__(self, *args, **kwargs):
        # Dynamically set the fields based on the Meta.fields attribute
        fields = kwargs.pop('fields', None)
        super().__init__(*args, **kwargs)
        if fields:
            self.fields = {field: self.fields[field] for field in fields}


class StudySerializer(serializers.ModelSerializer):
    class Meta:
        model = Study
        fields = '__all__'
