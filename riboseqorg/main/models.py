from django.db import models

# Create your models here.
class Study(models.Model):
    name = models.CharField(max_length=200)

    def __str__(self):
        return self.name

class Dataset(models.Model):
    riboseq = models.ForeignKey(Study, on_delete=models.CASCADE)
    sample_name = models.CharField(max_length=200)
    sample_description = models.TextField()
    cell_line = models.CharField(max_length=200, blank=True)
    library_type = models.CharField(max_length=200, blank=True)
    treatment = models.CharField(max_length=200, blank=True)
    verified = models.BooleanField(default=False)
    # trips = models.CharField(max_length=200, blank=True)
    # gwips = models.CharField(max_length=200, blank=True)
    # ribocrypt = models.CharField(max_length=200, blank=True)

    def __str__(self):
        return self.sample_name