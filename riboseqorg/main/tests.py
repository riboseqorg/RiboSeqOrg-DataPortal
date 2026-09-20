import os

from django.test import TestCase
from django.urls import reverse

from .models import GWIPS, RiboCrypt, Sample, Study, Trips
from .utilities import select_all_query


class TestViews(TestCase):
    def test_index(self):
        response = self.client.get(reverse('home'))
        self.assertEqual(response.status_code, 200)

    def test_about(self):
        response = self.client.get(reverse('about'))
        self.assertEqual(response.status_code, 200)

    def test_samples(self):
        response = self.client.get(reverse('samples'))
        self.assertEqual(response.status_code, 200)

    def test_studies(self):
        response = self.client.get(reverse('studies'))
        self.assertEqual(response.status_code, 200)


class TestAuditFixes(TestCase):
    @classmethod
    def setUpTestData(cls):
        with_pmid = Study.objects.create(BioProject='PRJ1', PMID='123')
        without_pmid = Study.objects.create(BioProject='PRJ2', PMID='')
        na_pmid = Study.objects.create(BioProject='PRJ3', PMID='<NA>')
        Sample.objects.create(Run='SRR1', BioProject=with_pmid,
                              CELL_LINE='C6/36NA')
        Sample.objects.create(Run='SRR2', BioProject=without_pmid,
                              CELL_LINE='HeLa')
        Sample.objects.create(Run='SRR3', BioProject=na_pmid)

    def test_api_is_read_only(self):
        response = self.client.post(reverse('api-sample-list'), {'Run': 'X'})
        self.assertEqual(response.status_code, 405)
        self.assertEqual(Sample.objects.count(), 3)

    def test_api_bad_params_are_400(self):
        for params in ['limit=abc', 'limit=-5', 'spots=abc']:
            response = self.client.get(reverse('api-sample-list') + '?' + params)
            self.assertEqual(response.status_code, 400, params)

    def test_samples_unknown_param(self):
        response = self.client.get(reverse('samples') + '?bogus=1')
        self.assertEqual(response.status_code, 200)

    def test_links_without_params(self):
        response = self.client.get(reverse('links'))
        self.assertEqual(response.status_code, 200)

    def test_download_all(self):
        url = reverse('download_all')
        self.assertEqual(self.client.get(url).status_code, 404)
        self.assertEqual(
            self.client.get(url + '?bioproject=PRJ1&file_type=zzz').status_code,
            400)
        response = self.client.get(url + '?bioproject=PRJ1')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.content.startswith(b'#!/bin/bash'))

    def test_custom_track_unknown_run(self):
        response = self.client.get(reverse('custom_track', args=['NOPE']))
        self.assertEqual(response.status_code, 404)

    def test_generate_csv_by_bioproject(self):
        response = self.client.get(reverse('generate_samples_csv')
                                   + '?bioproject=PRJ1')
        self.assertEqual(response.status_code, 200)
        self.assertIn(b'SRR1', response.content)
        self.assertNotIn(b'SRR2', response.content)

    def test_select_all_query_decodes_values(self):
        query = select_all_query('Cell-Line=C6%2F36NA&bogus=1')
        self.assertEqual(
            list(Sample.objects.filter(query).values_list('Run', flat=True)),
            ['SRR1'])

    def test_select_all_query_pubmed(self):
        for value, expected in [('Available', ['SRR1']),
                                ('Not+Available', ['SRR2', 'SRR3'])]:
            query = select_all_query(f'PubMed={value}')
            runs = list(Sample.objects.filter(query).order_by('Run')
                        .values_list('Run', flat=True))
            self.assertEqual(runs, expected, value)

    def test_studies_pubmed_filter(self):
        for value, expected in [('Available', 1), ('Not Available', 2)]:
            response = self.client.get(reverse('studies'), {'PubMed': value})
            self.assertEqual(
                response.context['page_obj'].paginator.count, expected, value)


class TestDataFiles(TestCase):
    def setUp(self):
        import tempfile
        from django.test import override_settings
        from .datafiles import clear_cache
        self.tmp = tempfile.TemporaryDirectory()
        os.makedirs(os.path.join(self.tmp.name, 'bams', 'SRR123'))
        open(os.path.join(self.tmp.name, 'bams', 'SRR123', 'SRR1234_1.bam'), 'w').close()
        self.settings_override = override_settings(RIBOSEQORG_DATA_DIR=self.tmp.name)
        self.settings_override.enable()
        clear_cache()

    def tearDown(self):
        self.settings_override.disable()
        self.tmp.cleanup()

    def test_find_run_file(self):
        from .datafiles import find_run_file
        self.assertEqual(find_run_file('bams', 'SRR1234', ['.bam', '_1.bam']),
                         'bams/SRR123/SRR1234_1.bam')
        self.assertIsNone(find_run_file('bams', 'SRR9999', ['.bam']))
        self.assertIsNone(find_run_file('counts', 'SRR1234', ['_counts.txt']))

    def test_sample_link_property(self):
        study = Study.objects.create(BioProject='PRJ1')
        sample = Sample.objects.create(Run='SRR1234', BioProject=study)
        with self.assertNumQueries(0):
            self.assertEqual(sample.bam_link,
                             'https://rdp.ucc.ie/static2/bams/SRR123/SRR1234_1.bam')
            self.assertEqual(sample.reads_link, '')


class TestViewerLinks(TestCase):
    @classmethod
    def setUpTestData(cls):
        study = Study.objects.create(BioProject='PRJ1')
        for i, (run, org) in enumerate([('SRR1', 'Homo sapiens'),
                                        ('SRR2', 'Homo sapiens'),
                                        ('SRR3', 'Mus musculus')]):
            Sample.objects.create(Run=run, BioProject=study, ScientificName=org,
                                  LIBRARYTYPE='Ribo-Seq', CELL_LINE='HeLa',
                                  INHIBITOR='0.0', trips_id=True, ribocrypt_id=True)
            Trips.objects.create(BioProject='PRJ1', Run=run, Trips_id=f'{10 + i}.0',
                                 organism=org.lower().replace(' ', '_'),
                                 transcriptome=f"{org.split()[0].lower()}_tx")
            RiboCrypt.objects.create(BioProject='PRJ1', Run=run, Organism=org,
                                     ribocrypt_id='all_samples-PRJ1')

    def setUp(self):
        import tempfile
        from django.test import override_settings
        from .datafiles import clear_cache
        self.tmp = tempfile.TemporaryDirectory()
        bigwig = os.path.join(self.tmp.name, 'bigwig')
        # SRR1: both strands; SRR2: forward only; SRR3: none
        for name in ['SRR1.forward.bw', 'SRR1.reverse.bw', 'SRR2.forward.bw']:
            os.makedirs(os.path.join(bigwig, name[:4]), exist_ok=True)
            open(os.path.join(bigwig, name[:4], name), 'w').close()
        self.settings_override = override_settings(
            RIBOSEQORG_DATA_DIR=self.tmp.name, PUBLIC_BASE_URL='https://portal.test')
        self.settings_override.enable()
        clear_cache()

    def tearDown(self):
        self.settings_override.disable()
        self.tmp.cleanup()

    def test_per_run_and_study_links(self):
        from .viewer_links import sample_links
        samples = list(Sample.objects.order_by('pk'))
        # One bulk query per link table: Trips, RiboCrypt, GWIPS
        with self.assertNumQueries(3):
            per_run, combined = sample_links(samples, {'bioproject': ['PRJ1']})
        self.assertEqual(per_run['SRR1']['trips_link'],
                         'https://trips.ucc.ie/homo_sapiens/homo_tx/interactive_plot/?files=10')
        self.assertEqual(
            per_run['SRR3']['ribocrypt_link'],
            'https://ribocrypt.org/?dff=all_samples-PRJ1-mus_musculus'
            '&library=SRR3&go=TRUE&go=TRUE')
        # Study-level links cover every run, not just the last one
        self.assertEqual(combined['trips_link'],
                         'https://trips.ucc.ie/homo_sapiens/homo_tx/interactive_plot/?files=10,11')
        self.assertEqual(
            combined['ribocrypt_link'],
            'https://ribocrypt.org/?dff=all_samples-PRJ1-homo_sapiens'
            '&library=SRR1,SRR2&go=TRUE&go=TRUE')

    def test_genome_browser_links(self):
        from urllib.parse import parse_qs, urlparse
        from .viewer_links import sample_links
        per_run, combined = sample_links(list(Sample.objects.order_by('pk')),
                                         {'bioproject': ['PRJ1']})
        # One run: both strands inline, with metadata in the description
        url = urlparse(per_run['SRR1']['gwips_link'])
        self.assertEqual(url.netloc, 'gwips.ucc.ie')
        query = parse_qs(url.query)
        self.assertEqual(query['db'], ['hg38'])
        tracks = query['hgct_customText'][0].split('\n')
        self.assertEqual(tracks, [
            'track type=bigWig name="SRR1 fwd" description="SRR1 Ribo-Seq, HeLa '
            '(PRJ1), forward strand" visibility=full color=0,100,200 '
            'bigDataUrl=https://rdp.ucc.ie/static2/bigwig/SRR1/SRR1.forward.bw',
            'track type=bigWig name="SRR1 rev" description="SRR1 Ribo-Seq, HeLa '
            '(PRJ1), reverse strand" visibility=full color=200,60,60 '
            'bigDataUrl=https://rdp.ucc.ie/static2/bigwig/SRR1/SRR1.reverse.bw',
        ])
        self.assertEqual(per_run['SRR2']['gwips_name'], 'Visit GWIPS-viz')
        # No bigWigs, no link
        self.assertEqual(per_run['SRR3']['gwips_name'], '')
        # Study: the browser fetches the track lines from the tracks view
        query = parse_qs(urlparse(combined['gwips_link']).query)
        self.assertEqual(
            query['hgct_customText'],
            ['https://portal.test/tracks/ucsc.txt?bioproject=PRJ1&organism=Homo+sapiens'])

    def test_tracks_view(self):
        response = self.client.get(reverse('genome_track_lines'),
                                   {'bioproject': 'PRJ1', 'organism': 'Homo sapiens'})
        self.assertEqual(response.status_code, 200)
        lines = response.content.decode().splitlines()
        self.assertEqual([l.split('"')[1] for l in lines if l.startswith('track')],
                         ['SRR1 fwd', 'SRR1 rev', 'SRR2 fwd'])
        self.assertEqual(self.client.get(reverse('genome_track_lines')).status_code, 400)

    def test_custom_track(self):
        response = self.client.get(reverse('custom_track', args=['SRR2']))
        self.assertEqual(response.status_code, 200)
        self.assertIn('name="SRR2 fwd"', response.content.decode())
        response = self.client.get(reverse('custom_track', args=['SRR3']))
        self.assertEqual(response.status_code, 404)

    def test_sync_bigwig_flags(self):
        from io import StringIO
        from django.core.management import call_command
        Sample.objects.filter(Run='SRR3').update(gwips_id=True)
        call_command('sync_bigwig_flags', stdout=StringIO())
        self.assertEqual(Sample.objects.filter(gwips_id=True).count(), 1)  # dry run
        call_command('sync_bigwig_flags', '--apply', stdout=StringIO())
        self.assertEqual(
            sorted(Sample.objects.filter(gwips_id=True).values_list('Run', flat=True)),
            ['SRR1', 'SRR2'])

    def test_native_gwips_links(self):
        from .viewer_links import sample_links
        # No GWIPS rows yet: only the custom-track link, and the native side
        # falls back to the home page with no name
        per_run, combined = sample_links(list(Sample.objects.order_by('pk')),
                                         {'bioproject': ['PRJ1']})
        self.assertEqual(per_run['SRR1']['gwips_native_name'], '')
        self.assertEqual(per_run['SRR1']['gwips_native_link'],
                         'https://gwips.ucc.ie/')

        GWIPS.objects.create(BioProject='PRJ1', Organism='Homo sapiens',
                             gwips_db='hg38',
                             GWIPS_Elong_Suffix='Study15_All_RiboProElong_track',
                             GWIPS_Init_Suffix='Study15_All_RiboProInit_track')
        per_run, combined = sample_links(list(Sample.objects.order_by('pk')),
                                         {'bioproject': ['PRJ1']})
        expected = ('https://gwips.ucc.ie/cgi-bin/hgTracks?db=hg38'
                    '&Study15_All_RiboProElong_track=full'
                    '&Study15_All_RiboProInit_track=full')
        # Native tracks are per study, so every run of it gets the same link
        self.assertEqual(per_run['SRR1']['gwips_native_link'], expected)
        self.assertEqual(per_run['SRR3']['gwips_native_link'], expected)
        self.assertEqual(combined['gwips_native_link'], expected)
        self.assertEqual(combined['gwips_native_name'], 'Visit GWIPS-viz')
        # The custom-track link is unaffected: the two are shown side by side
        self.assertIn('hgct_customText', per_run['SRR1']['gwips_link'])

    def test_native_gwips_link_without_initiating_tracks(self):
        from .viewer_links import gwips_native_link
        row = GWIPS(BioProject='PRJ1', Organism='Homo sapiens', gwips_db='hg38',
                    GWIPS_Elong_Suffix='Study15_All_RiboProElong_track',
                    GWIPS_Init_Suffix='')
        self.assertEqual(
            gwips_native_link([row])[0],
            'https://gwips.ucc.ie/cgi-bin/hgTracks?db=hg38'
            '&Study15_All_RiboProElong_track=full')
        # A row with an assembly but no tracks at all is not a link
        self.assertEqual(gwips_native_link([GWIPS(gwips_db='hg38')]),
                         ('https://gwips.ucc.ie/', ''))

    def test_study_page_query_count_is_constant(self):
        # Study, samples, then one query per link table
        with self.assertNumQueries(5):
            response = self.client.get(reverse('study', args=['PRJ1']))
        self.assertEqual(response.status_code, 200)
        self.assertIn('tracks%2Fucsc.txt', response.context['bioproject_gwips_link'])


class TestLoadViewerLinks(TestCase):
    def setUp(self):
        import sqlite3
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.trips_db = os.path.join(self.tmp.name, 'trips.sqlite')
        db = sqlite3.connect(self.trips_db)
        db.executescript('''
            CREATE TABLE organisms (organism_id INT, organism_name TEXT,
                transcriptome_list TEXT, private INT);
            CREATE TABLE studies (study_id INT, study_name TEXT, srp_nos TEXT,
                gse_nos TEXT, paper_pmid TEXT, private INT);
            CREATE TABLE files (file_id INT, organism_id INT, study_id INT,
                file_name TEXT, file_type TEXT);
            INSERT INTO organisms VALUES (4, 'homo_sapiens', 'Gencode_v25', 0),
                                         (5, 'secret', 'tx', 1);
            INSERT INTO studies VALUES (1, 'Study', 'SRP1', 'GSE1', '123', 0),
                                       (2, 'Private', '', '', '', 1);
            INSERT INTO files VALUES
                (10, 4, 1, 'SRR1.sqlite', 'riboseq'),
                (11, 4, 1, 'SRR2.sqlite', 'rnaseq'),
                (12, 4, 2, 'SRR3.sqlite', 'riboseq'),
                (13, 5, 1, 'SRR3.sqlite', 'riboseq'),
                (14, 4, 1, 'SRR999.sqlite', 'riboseq'),
                (15, 4, 1, 'sample_a.bam.sqlite', 'riboseq');
        ''')
        db.commit()
        db.close()
        study = Study.objects.create(BioProject='PRJ1')
        for run in ['SRR1', 'SRR2', 'SRR3']:
            Sample.objects.create(Run=run, BioProject=study, trips_id=(run == 'SRR3'))

    def tearDown(self):
        self.tmp.cleanup()

    def run_command(self, *args):
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        call_command('load_viewer_links', '--trips-sqlite', self.trips_db, *args,
                     stdout=out)
        return out.getvalue()

    def test_dry_run_writes_nothing(self):
        output = self.run_command()
        self.assertIn('Trips: 1 rows', output)
        self.assertEqual(Trips.objects.count(), 0)

    def test_apply_loads_public_matching_files_and_syncs_flags(self):
        self.run_command('--trips-types', 'riboseq,rnaseq', '--apply', '--sync-flags')
        self.assertEqual(
            sorted(Trips.objects.values_list('Run', 'Trips_id', 'BioProject',
                                             'organism', 'transcriptome')),
            [('SRR1', '10', 'PRJ1', 'homo_sapiens', 'Gencode_v25'),
             ('SRR2', '11', 'PRJ1', 'homo_sapiens', 'Gencode_v25')])
        self.assertEqual(
            sorted(Sample.objects.filter(trips_id=True).values_list('Run', flat=True)),
            ['SRR1', 'SRR2'])


class TestGwipsTrackDb(TestCase):
    '''
    Reading the native GWIPS-viz tracks out of a trackDb dump.
    '''
    COLUMNS = 'db\ttableName\tshortLabel\tlongLabel\ttype\tgrp\tsettings\thtml'

    def setUp(self):
        import tempfile
        self.tmp = tempfile.TemporaryDirectory()
        self.dump = self.tmp.name
        self.write('gwips_dbDb.tsv',
                   'name\torganism\tscientificName\tdescription\ttaxId\tactive',
                   'hg38\tHuman\tHomo sapiens\tDec. 2013\t9606\t1')
        self.write(
            'gwips_trackDb_hg38.tsv', self.COLUMNS,
            # The study-level aggregate, named in the longLabel
            'hg38\tCenik15_All_ribopro_track\tCenik 2015\tRibosome profiles from '
            'Cenik et al. (2015) study,  SRP055009,  added 2015-10-28\tbigWig\t'
            'RP-ElongatingRibos\t\t',
            # A single sample of the same study: never preferred over _All_
            'hg38\tCenik15_SRR1_track\tCenik 2015 rep1\tOne sample of SRP055009'
            '\tbigWig\tRP-ElongatingRibos\t\t',
            'hg38\tCenik15_All_riboinit_track\tCenik 2015 init\tInitiating ribosomes,'
            '  SRP055009\tbigWig\tRP-InitiatingRibos\t\t',
            # Accession only in the html column
            'hg38\tOther16_All_ribopro_track\tOther 2016\tRibosome profiles'
            '\tbigWig\tRP-ElongatingRibos\t\t<p>Data from GSE12345</p>',
            # Not a data track, and a study the portal doesn't have
            'hg38\tknownGene\tGENCODE\tGene models, SRP055009\tgenePred\tgenes\t\t',
            'hg38\tStranger_All_ribopro_track\tStranger\tFrom SRP999999'
            '\tbigWig\tRP-ElongatingRibos\t\t')

    def write(self, name, *lines):
        with open(os.path.join(self.dump, name), 'w') as f:
            f.write('\n'.join(lines) + '\n')

    def tearDown(self):
        self.tmp.cleanup()

    def read(self):
        from .management.commands.load_viewer_links import (
            read_gwips_trackdb, study_accession_index)
        index = study_accession_index([('PRJ1', 'SRP055009', ''),
                                       ('PRJ2', '', 'GSE12345')])
        return read_gwips_trackdb(self.dump, index)

    def test_builds_one_row_per_study_and_assembly(self):
        rows, skipped = self.read()
        self.assertEqual(
            sorted((r.BioProject, r.Organism, r.gwips_db, r.GWIPS_Elong_Suffix,
                    r.GWIPS_Init_Suffix) for r in rows),
            [('PRJ1', 'Homo sapiens', 'hg38', 'Cenik15_All_ribopro_track',
              'Cenik15_All_riboinit_track'),
             ('PRJ2', 'Homo sapiens', 'hg38', 'Other16_All_ribopro_track', '')])
        self.assertEqual(skipped['study not in portal'], 1)
        self.assertEqual(skipped['not a ribosome profiling track'], 1)

    def test_accession_must_belong_to_a_portal_study(self):
        from .management.commands.load_viewer_links import read_gwips_trackdb
        rows, skipped = read_gwips_trackdb(self.dump, {})
        self.assertEqual(rows, [])
        self.assertEqual(skipped['study not in portal'], 5)

    def test_study_accession_index_keeps_the_first_claim(self):
        from .management.commands.load_viewer_links import study_accession_index
        index = study_accession_index([('PRJ1', 'SRP1; SRP2', 'GSE1'),
                                       ('PRJ2', 'SRP1', '')])
        self.assertEqual(index['SRP2'], 'PRJ1')
        self.assertEqual(index['GSE1'], 'PRJ1')
        self.assertEqual(index['SRP1'], 'PRJ1')

    def test_reads_a_tarball_as_well_as_a_directory(self):
        import tarfile
        from .management.commands.load_viewer_links import (
            read_gwips_trackdb, study_accession_index)
        archive = os.path.join(self.tmp.name, 'trackdb.tgz')
        with tarfile.open(archive, 'w:gz') as tar:
            for name in ['gwips_dbDb.tsv', 'gwips_trackDb_hg38.tsv']:
                tar.add(os.path.join(self.dump, name), arcname=name)
        rows, _ = read_gwips_trackdb(
            archive, study_accession_index([('PRJ1', 'SRP055009', '')]))
        self.assertEqual([r.BioProject for r in rows], ['PRJ1'])

    def test_no_track_files_is_an_error(self):
        import tempfile
        from django.core.management.base import CommandError
        from .management.commands.load_viewer_links import read_gwips_trackdb
        with tempfile.TemporaryDirectory() as empty:
            with self.assertRaises(CommandError):
                read_gwips_trackdb(empty, {})
