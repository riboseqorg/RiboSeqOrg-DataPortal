from django import forms



class addNewSample(forms.Form):
    auto_id = True
    sample_name = forms.CharField(max_length=200)
    sample_description = forms.CharField(widget=forms.Textarea)
    cell_line = forms.CharField(max_length=200, required=False)
    library_type = forms.CharField(max_length=200, required=False)
    treatment = forms.CharField(max_length=200, required=False)

