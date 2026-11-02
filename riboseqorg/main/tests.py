from django.test import TestCase

from .utilities import build_gwips_url, get_gwips_assembly
from .views import format_organism_name

# Create your tests here.

# from views import *


class TestViews(TestCase):
    def test_gwips_assembly_allowlist(self):
        self.assertEqual(get_gwips_assembly('Homo sapiens'), 'hg38')
        self.assertEqual(get_gwips_assembly('Mus_musculus'), 'mm39')
        self.assertEqual(get_gwips_assembly('Salmonella enterica'), '')

    def test_gwips_url_is_only_built_for_supported_organisms(self):
        self.assertEqual(
            build_gwips_url('human', 'track=full'),
            'https://gwips.ucc.ie/cgi-bin/hgTracks?db=hg38&track=full',
        )
        self.assertEqual(
            build_gwips_url('mouse', 'track=full'),
            'https://gwips.ucc.ie/cgi-bin/hgTracks?db=mm39&track=full',
        )
        self.assertEqual(build_gwips_url('unknown organism', 'track=full'), '')
        self.assertEqual(build_gwips_url('human', ''), '')

    def test_format_organism_name(self):
        self.assertEqual(format_organism_name('Homo_sapiens'), 'Homo sapiens')
        self.assertEqual(format_organism_name('Mus_Musculus'), 'Mus musculus')

    def test_index(self):
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)

    def test_about(self):
        response = self.client.get('/about/')
        self.assertEqual(response.status_code, 200)

    def test_samples(self):
        response = self.client.get('/samples/')
        self.assertEqual(response.status_code, 200)

    def test_studies(self):
        response = self.client.get('/studies/')
        self.assertEqual(response.status_code, 200)
