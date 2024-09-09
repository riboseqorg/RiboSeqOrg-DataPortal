from django.test import TestCase

# Create your tests here.

# from views import *


class TestViews(TestCase):
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