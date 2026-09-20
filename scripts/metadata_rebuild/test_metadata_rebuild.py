"""
Tests for the metadata rebuild. Run from scripts/:
    python -m unittest metadata_rebuild.test_metadata_rebuild
"""
import unittest
import xml.etree.ElementTree as ET

from . import assay
from .authorship import (Resolver, Web, best_institution,
                         shared_author_strings, short_institution,
                         study_name, surname, verify_candidate)
from .build import authorship_queue, organism_name_cleanup, selection
from .core import CoreResolver, normalise_replicate, repair
from .fetch import parse_package
from .merge import Merger, Standardiser, clean_value, combine
from .studies import build_study, valid_pmid


class CombineTests(unittest.TestCase):
    """The old paste(sep = "_") + regex step, and what replaces it."""

    def test_missing_values_are_dropped_not_written_as_na(self):
        # R: paste(NA, NA, "Cycloheximide") -> NA_NA_Cycloheximide -> the
        # regex left NA_Cycloheximide
        self.assertEqual(combine([None, 'NA', 'Cycloheximide']),
                         'Cycloheximide')

    def test_repeated_value_is_kept_once(self):
        # R: sty1delta_sty1delta
        self.assertEqual(combine(['sty1delta', 'sty1delta']), 'sty1delta')
        self.assertEqual(combine(['Mock', 'mock']), 'Mock')

    def test_distinct_values_stay_separated(self):
        # R: 'U-2OS_NA_epithelial' -> the regex glued it to 'U-2OSepithelial'
        self.assertEqual(combine(['U-2OS', None, 'epithelial']),
                         'U-2OS; epithelial')

    def test_numbers_are_not_suffixed(self):
        # R: '2_NA_NA' -> '2NA'
        self.assertEqual(combine(['2', 'NA', 'NA']), '2')

    def test_missing_markers(self):
        for v in ('0.0', 'NANA', 'not applicable', ' N/A ', 'none', '<NA>'):
            self.assertEqual(clean_value(v), '', v)
        self.assertEqual(clean_value('  HeLa   S3 '), 'HeLa S3')
        self.assertEqual(clean_value('0'), '0')


class MergerTests(unittest.TestCase):

    def setUp(self):
        self.merger = Merger()

    def test_synonym_columns_merge_into_one_field(self):
        merged, _ = self.merger.merge([('cell line', 'HeLa'),
                                       ('cell_line', 'HeLa')])
        self.assertEqual(merged['CELL_LINE'], 'HeLa')

    def test_mis_mapped_timepoint_sources_are_not_used(self):
        merged, unmapped = self.merger.merge([('passages', '5-8')])
        self.assertEqual(merged['TIMEPOINT'], '')
        self.assertEqual(unmapped, {'passages': '5-8'})

    def test_unmapped_attributes_are_returned(self):
        _, unmapped = self.merger.merge([('my odd column', 'x'),
                                         ('ENA first public', '2020')])
        self.assertEqual(unmapped, {'my odd column': 'x'})


class StandardiserTests(unittest.TestCase):
    """Port of ORFik findFromPath: exactly one vocabulary term must match."""

    def setUp(self):
        self.s = Standardiser()

    def test_single_match(self):
        self.assertEqual(
            self.s.standardise('INHIBITOR', {'INHIBITOR': 'cycloheximide'}),
            'chx')

    def test_falls_back_to_sample_title(self):
        self.assertEqual(self.s.standardise(
            'LIBRARYTYPE', {'sample_title': 'Ribo-seq_WT_rep1'}), 'RFP')

    def test_chloramphenicol_has_a_real_name(self):
        self.assertEqual(self.s.standardise(
            'INHIBITOR', {'INHIBITOR': 'chloramphenicol'}), 'chloram')


class CoreTests(unittest.TestCase):

    def setUp(self):
        self.core = CoreResolver()

    def test_repairs(self):
        cases = {
            'NA2hr': '2hr', 'CT00NANANA': 'CT00', 'stationary_NA':
            'stationary', 'NA_yeast cells': 'yeast cells', 'tumor_tumor':
            'tumor', '1.0_1NA': '1.0', 'NANA': '',
            # real values that end or start with NA are left alone
            'mRNA': 'mRNA', 'tRNA': 'tRNA', 'NAT10-/-': 'NAT10-/-',
        }
        for raw, want in cases.items():
            self.assertEqual(repair(raw), want, raw)

    def test_replicate(self):
        for raw, want in {'1.0': '1', 'Rep 2': '2', 'biological 3': '3',
                          '2biological replicate': '2', 'P1-2': '',
                          'H1': ''}.items():
            self.assertEqual(normalise_replicate(raw), want, raw)

    def test_display_names(self):
        self.assertEqual(self.core.validate('LIBRARYTYPE', 'RFP'), 'Ribo-Seq')
        self.assertEqual(self.core.validate('INHIBITOR', 'chx'),
                         'Cycloheximide')
        self.assertEqual(self.core.validate('CONDITION', 'WT'), 'Wild Type')

    def test_placeholders_and_strains_are_rejected(self):
        self.assertEqual(self.core.validate('CONDITION', 'Test'), '')
        self.assertEqual(self.core.validate('CELL_LINE', 'C57BL/6'), '')
        self.assertEqual(self.core.validate('CELL_LINE', 'NONE'), '')

    def test_strict_columns(self):
        self.assertEqual(self.core.validate('FRACTION', 'cyto'),
                         'Cytoplasmic')
        self.assertEqual(self.core.validate(
            'FRACTION', 'ribosome-protected mRNA fragments'), '')
        self.assertEqual(self.core.validate('LIBRARYTYPE', 'free RNA'), '')

    def test_first_valid_source_wins(self):
        value, source, rejected = self.core.resolve(
            'CONDITION', {'manual': '', 'baseline': 'Test', 'st': 'KO'})
        self.assertEqual((value, source), ('KO', 'st'))
        self.assertEqual(rejected, [('baseline', 'Test')])

    def test_replicate_prefers_baseline_over_manual(self):
        value, source, _ = self.core.resolve(
            'REPLICATE', {'manual': '2', 'baseline': '1.0'})
        self.assertEqual((value, source), ('1', 'baseline'))

    def test_sra_ribo_seq_strategy_is_the_last_resort(self):
        self.assertEqual(self.core.resolve(
            'LIBRARYTYPE', {'strategy': 'Ribo-Seq'})[:2],
            ('Ribo-Seq', 'strategy'))
        self.assertEqual(self.core.resolve(
            'LIBRARYTYPE', {'auto': 'RNA', 'strategy': 'Ribo-Seq'})[:2],
            ('RNA-Seq', 'auto'))

    def test_misaligned_projects_prefer_fresh_values(self):
        value, source, _ = self.core.resolve(
            'TISSUE', {'baseline': 'liver', 'auto': 'brain'},
            misaligned=True)
        self.assertEqual((value, source), ('Brain', 'auto'))


PACKAGE = """
<EXPERIMENT_PACKAGE>
 <EXPERIMENT accession="SRX1"><IDENTIFIERS><PRIMARY_ID>SRX1</PRIMARY_ID>
  </IDENTIFIERS>
  <DESIGN><LIBRARY_DESCRIPTOR><LIBRARY_NAME>lib</LIBRARY_NAME>
   <LIBRARY_STRATEGY>OTHER</LIBRARY_STRATEGY>
   <LIBRARY_SOURCE>TRANSCRIPTOMIC</LIBRARY_SOURCE>
   <LIBRARY_SELECTION>other</LIBRARY_SELECTION>
   <LIBRARY_LAYOUT><PAIRED/></LIBRARY_LAYOUT></LIBRARY_DESCRIPTOR></DESIGN>
  <PLATFORM><ILLUMINA><INSTRUMENT_MODEL>NovaSeq 6000</INSTRUMENT_MODEL>
  </ILLUMINA></PLATFORM></EXPERIMENT>
 <SUBMISSION accession="SRA1" center_name="GEO"/>
 <STUDY><IDENTIFIERS><PRIMARY_ID>SRP1</PRIMARY_ID>
  <EXTERNAL_ID namespace="BioProject">PRJNA1</EXTERNAL_ID>
  <EXTERNAL_ID namespace="GEO">GSE1</EXTERNAL_ID></IDENTIFIERS></STUDY>
 <SAMPLE alias="GSM1"><IDENTIFIERS><PRIMARY_ID>SRS1</PRIMARY_ID>
  <EXTERNAL_ID namespace="BioSample">SAMN1</EXTERNAL_ID></IDENTIFIERS>
  <TITLE>WT_rep1_RFP</TITLE>
  <SAMPLE_NAME><TAXON_ID>9606</TAXON_ID>
   <SCIENTIFIC_NAME>Homo sapiens</SCIENTIFIC_NAME></SAMPLE_NAME>
  <SAMPLE_ATTRIBUTES>
   <SAMPLE_ATTRIBUTE><TAG>source_name</TAG><VALUE>HeLa</VALUE>
   </SAMPLE_ATTRIBUTE>
   <SAMPLE_ATTRIBUTE><TAG>cell line</TAG><VALUE>HeLa</VALUE>
   </SAMPLE_ATTRIBUTE></SAMPLE_ATTRIBUTES></SAMPLE>
 <RUN_SET>
  <RUN accession="SRR1" total_spots="100" total_bases="5000" size="2097152"
       published="2024-03-05 10:00:00"/>
  <RUN accession="SRR2" total_spots="0" total_bases="0" size="0"
       published="2024-03-05 10:00:00"/>
 </RUN_SET>
</EXPERIMENT_PACKAGE>
"""


class FetchTests(unittest.TestCase):

    def test_every_run_gets_its_own_experiments_attributes(self):
        rows, _ = parse_package(ET.fromstring(PACKAGE))
        self.assertEqual([r['Run'] for r, _ in rows], ['SRR1', 'SRR2'])
        for row, attrs in rows:
            self.assertIn(('cell line', 'HeLa'), attrs)
        first = rows[0][0]
        self.assertEqual(first['avgLength'], '50')
        self.assertEqual(first['size_MB'], '2')
        self.assertEqual((first['YEAR'], first['MONTH']), ('2024', '03'))
        self.assertEqual(first['LibraryLayout'], 'PAIRED')
        self.assertEqual(first['GEO'], 'GSE1')
        self.assertEqual(first['AUTHOR'], '')
        self.assertEqual(first['sample_source'], 'HeLa')


class AssayTests(unittest.TestCase):
    """Broader data-type rules for runs the ORFik vocabulary leaves blank."""

    def test_run_titles(self):
        cases = {
            'RIBOseq Ba/F3 Rpl22 +/- #13': 'Ribo-Seq',
            'RF 293T4A DOX-3 [ribo_DOX_3]': 'Ribo-Seq',
            '6-Ribo-tRNA-seq, dtrm1 rep1': 'Ribo-tRNA-Seq',
            '8-tRNA-seq, dabp140 rep1': 'tRNA-Seq',
            'RPF_Liver_tRNA_IV_replicate2': 'Ribo-Seq',
            'MitoIP-Ribo_laminin_retapamulin_30s_2': 'Mito-Ribo-Seq',
            'FVB_DDC_Heavy_Polysome_2': 'Polysome-Seq',
            'Ribotag IP sample 3': 'RiboTag',
            'WT input mRNA for Ribosome Profiling': 'RNA-Seq',
            'HepG2 shSETD2 input rep2 (Ribo-seq)': 'RNA-Seq',
            'ribosome-protected mRNA fragments': 'Ribo-Seq',
            'frac_26-34nt': 'Ribo-Seq',
            'GRP3__SC_D03_VEH_404_rFP': 'Ribo-Seq',
        }
        for title, want in cases.items():
            self.assertEqual(assay.run_label([title]), want, title)

    def test_source_name_is_only_a_fallback(self):
        # GEO 'source' describes the starting material of every library
        self.assertEqual(assay.classify(
            ['WT_AL_ZT00_A_RFP'], '', context_texts=['Liver Total RNA']),
            ('Ribo-Seq', 'run'))

    def test_selective_profiling_total_and_ip(self):
        study = 'Co-translational assembly counteracts promiscuous interactions'
        self.assertEqual(assay.classify(['Sec31_IP_No3'], study),
                         ('Selective Ribo-Seq', 'serp'))
        self.assertEqual(assay.classify(['Sec31_total_No3'], study),
                         ('Ribo-Seq', 'serp'))

    def test_study_level_inference(self):
        self.assertEqual(assay.classify(
            ['Translatome BCAA 5+3 AML cells biol rep7'],
            'Ribo-lite, paired transcriptome (RNA-seq) and translatome '
            '(Ribo-seq)'), ('Ribo-Seq', 'study'))
        self.assertEqual(assay.classify(['Index6'], 'Ribosome profiling of X'),
                         ('Ribo-Seq', 'study'))
        self.assertEqual(assay.classify(['D3'], 'Ribo-seq and RNA-seq of X'),
                         ('', ''))

    def test_chromatin_mnase_is_not_rna(self):
        self.assertEqual(assay.classify(['MNase-Seq NF-YA KD'], '',
                                        'MNase-Seq', 'GENOMIC'),
                         ('Not RNA', 'not rna'))


class BuildTests(unittest.TestCase):

    def test_organism_names(self):
        self.assertEqual(organism_name_cleanup(
            'Escherichia coli str. K-12 substr. MG1655'), 'Escherichia coli')
        self.assertEqual(organism_name_cleanup(
            'Saccharomyces cerevisiae BY4741'), 'Saccharomyces cerevisiae')
        self.assertEqual(organism_name_cleanup('Homo sapiens'),
                         'Homo sapiens')

    def test_selection(self):
        info = {'sample_title': 'WT RPF', 'LibraryStrategy': 'OTHER',
                'LibraryLayout': 'PAIRED', 'Platform': 'BGISEQ'}
        self.assertEqual(selection(info, [], False)[0], True)
        info['LibraryStrategy'] = 'ATAC-seq'
        self.assertEqual(selection(info, [], True)[0], False)
        info.update(LibraryStrategy='RNA-Seq', sample_title='liver')
        self.assertEqual(selection(info, [], False),
                         (False, 'no Ribo-seq term in metadata'))


class StudyTests(unittest.TestCase):

    def test_placeholder_pmids(self):
        for v in ('1', '<NA>', '0.0', 'nan', ''):
            self.assertEqual(valid_pmid(v), '', v)
        self.assertEqual(valid_pmid('26554015.0'), '26554015')

    def test_names(self):
        self.assertEqual(study_name('Atger F, Gobet C', '', '2015'),
                         'Atger et al. 2015')

    def test_broken_study_row_is_repaired(self):
        sample = {'ScientificName': 'Homo sapiens', 'SRAStudy': 'SRP1',
                  'LIBRARYTYPE': 'Ribo-Seq', 'GEO': 'GSE9',
                  'Study_Pubmed_id': '', 'YEAR': '2022', 'MONTH': '05'}
        row, notes = build_study(
            'PRJNA1', [sample], {'Name': '0.0 et al. 2022', 'PMID': '<NA>',
                                 'Authors': 'Makar AB', 'Title': 'T'},
            '', None)
        self.assertEqual(row['PMID'], '')
        self.assertEqual(row['Authors'], '')
        self.assertEqual(row['Name'], 'Unknown 2022')
        self.assertEqual(row['Samples'], '1')
        self.assertEqual(row['GSE'], 'GSE9')
        self.assertTrue(notes)

    def test_a_wrong_author_list_is_not_inherited(self):
        # The 358 contaminated studies: the row carries a stranger's paper
        # and no PMID that anything links to the data. Both must go.
        sample = {'ScientificName': 'Arabidopsis thaliana',
                  'SRAStudy': 'DRP006737', 'LIBRARYTYPE': 'Ribo-Seq',
                  'GEO': '', 'Study_Pubmed_id': '', 'YEAR': '2020',
                  'MONTH': '11'}
        row, _ = build_study(
            'PRJDB10544', [sample],
            {'Name': 'Vogel et al. 2020',
             'Authors': 'Vogel P, Beyer D, Holm C, Palberg T',
             'Publication_title': 'CO2-induced drastic decharging',
             'Journal': 'Soft matter', 'doi': '10.1039/d4sm01000k',
             'PMID': ''},
            '', None, Resolver(web=Web(offline=True)))
        self.assertEqual(row['Authors'], '')
        self.assertEqual(row['Publication_title'], '')
        self.assertEqual(row['Journal'], '')
        self.assertEqual(row['Name'], 'Unknown 2020')


class AuthorshipTests(unittest.TestCase):
    """Ownership is evidence, not a guess."""

    def test_surnames(self):
        self.assertEqual(surname('Ingolia NT'), 'ingolia')
        self.assertEqual(surname('Nicholas,T,Ingolia'), 'ingolia')
        self.assertEqual(surname('Castelo-Szekely V'), 'castelo-szekely')
        self.assertEqual(surname('Jürgen B'), 'jurgen')

    def test_institution_display_names(self):
        cases = {
            'RIKEN Center for Biosystems Dynamics Research': 'RIKEN',
            'Institut de Biologie de Ecole normale superieure (IBENS), '
            'France': 'IBENS',
            'KTH, SCIENCE FOR LIFE LABORATORY': 'KTH',
            'UNIVERSITY COLLEGE CORK': 'University College Cork',
            'Max Delbrück Center for Molecular Medicine, Berlin-Buch, '
            'Germany': 'Max Delbrück Center for Molecular Medicine',
        }
        for value, expected in cases.items():
            self.assertEqual(short_institution(value), expected, value)

    def test_institution_credit_when_no_paper(self):
        self.assertEqual(
            study_name('', 'RIKEN Center for Biosystems Dynamics Research',
                       '2020'), 'RIKEN, 2020')
        self.assertEqual(study_name('', '', '2024'), 'Unknown 2024')

    def test_junk_institutions_are_dropped(self):
        # Submitters type their role into GEO's institute field
        for value in ('Postdoc', 'postdoc', 'PhD student', 'unknown', 'NA'):
            self.assertEqual(short_institution(value), '', value)

    def test_acronym_strings_keep_their_capitals(self):
        self.assertEqual(short_institution('ICBFM SB RAS'), 'ICBFM SB RAS')
        self.assertEqual(short_institution('KAIST'), 'KAIST')

    def test_long_names_are_shortened_without_lying(self):
        cases = {
            'Chinese Academy of Medical Sciences and Peking Union Medical '
            'College': 'Chinese Academy of Medical Sciences',
            'Section on Nutrient Control of Gene Expression, Eunice Kennedy '
            'Shriver National Institute of Child Health and Human '
            'Development': 'Eunice Kennedy Shriver National Institute',
        }
        for value, expected in cases.items():
            self.assertEqual(short_institution(best_institution(value)),
                             expected, value)

    def test_the_organisation_is_picked_out_of_an_address(self):
        cases = {
            # GEO contact institutes, as they really arrive
            'Qian Lab, Cornell University': 'Cornell University',
            # 'State University' alone would be wrong
            'The Ohio State University': 'Ohio State University',
            'the first affiliated hospital of guangxi medical university':
                'First Affiliated Hospital of Guangxi Medical University',
            # The city is written twice, and 'of' leads nowhere
            'Department of Pathology University of Cambridge Cambridge':
                'University of Cambridge',
            'Botanical Institute of': 'Botanical Institute',
            'Graduate School of Science and Technology, Nara Institute of '
            'Science and Technology': 'Nara Institute of Science and '
                                      'Technology',
            'Peking University Health Science Center; Demin Zhou, Chemical '
            'Bilogy, Peking University': 'Peking University',
            'Department of Biochemistry University of Cambridge UK':
                'University of Cambridge',
            'KAIST': 'KAIST',
        }
        for value, expected in cases.items():
            self.assertEqual(short_institution(best_institution(value)),
                             expected, value)

    def test_citing_paper_needs_the_submitters(self):
        submitters = ['ingolia', 'brar', 'rouskin', 'weissman']
        produced = {'surnames': ['ingolia', 'lareau', 'weissman'],
                    'affiliations': ''}
        reused = {'surnames': ['liu', 'song'], 'affiliations': ''}
        self.assertTrue(verify_candidate(produced, submitters, [])[0])
        self.assertFalse(verify_candidate(reused, submitters, [])[0])

    def test_one_submitter_still_verifies(self):
        # GEO often names a single contact; requiring two would reject the
        # study's own paper.
        cand = {'surnames': ['nadimpalli', 'katsioudi', 'gatfield'],
                'affiliations': ''}
        self.assertTrue(verify_candidate(cand, ['nadimpalli'], [])[0])

    def test_a_preprint_is_accepted_with_its_doi(self):
        # PRJNA1032574, PRJNA566006 and PRJNA977618: the author list is
        # verified against the submitters, but the paper is a preprint, so
        # it carries a DOI and no PubMed ID. Dropping it for want of a PMID
        # threw away a correct answer.
        class PreprintWeb(Web):
            def __init__(self):
                super().__init__(offline=True)

            def geo_series(self, gse):
                return {'people': ['Ingolia N'], 'institutes': [],
                        'pmids': []}

            def mentions(self, accessions):
                return [{'pmid': '', 'doi': '10.1101/2023.01.01.000001',
                         'id': 'PPR123456', 'source': 'PPR', 'year': '2023',
                         'title': 'Ribosome profiling without a journal',
                         'authorString': 'Ingolia N, Lareau L',
                         'surnames': ['ingolia', 'lareau'],
                         'affiliations': ''}]

        ev = Resolver(web=PreprintWeb()).resolve(
            'PRJNA977618', [{'CenterName': ''}], {}, ['GSE1'], [])
        self.assertEqual(ev.authors, 'Ingolia N, Lareau L')
        self.assertEqual(ev.source, 'europepmc')
        self.assertEqual(ev.pmid, '')
        row = ev.as_row()
        self.assertEqual(row['doi'], '10.1101/2023.01.01.000001')
        self.assertEqual(row['Publication_title'],
                         'Ribosome profiling without a journal')

    def test_institution_fallback_needs_two_distinctive_words(self):
        institutions = ['RIKEN Center for Biosystems Dynamics Research']
        weak = {'surnames': ['wu'],
                'affiliations': 'Department of Research, University'}
        strong = {'surnames': ['wu'],
                  'affiliations': 'RIKEN Center for Biosystems Dynamics '
                                  'Research, Kobe, Japan'}
        self.assertFalse(verify_candidate(weak, [], institutions)[0])
        self.assertTrue(verify_candidate(strong, [], institutions)[0])

    def test_brokered_submissions_are_not_an_institution(self):
        # Every ENA study is 'owned' by the EBI, which says nothing.
        cand = {'surnames': ['xiao'],
                'affiliations': 'European Bioinformatics Institute'}
        self.assertFalse(verify_candidate(
            cand, [], ['European Bioinformatics Institute'])[0])

    def test_shared_author_strings_catch_contamination(self):
        rows = [{'Authors': 'Vogel P, Beyer D', 'PMID': str(i),
                 'BioProject': f'PRJNA{i}'} for i in range(20)]
        # The Theofanidis string sat on 15 studies but only 4 PubMed IDs,
        # so counting distinct IDs alone would have missed it
        rows += [{'Authors': 'Theofanidis AH', 'PMID': str(i % 4),
                  'BioProject': f'PRJEB{i}'} for i in range(15)]
        rows += [{'Authors': 'Wangen JR, Green R', 'PMID': '31971508',
                  'BioProject': f'PRJNA9{i}'} for i in range(8)]
        rows += [{'Authors': '', 'PMID': '', 'BioProject': 'PRJNA0'}] * 3
        shared = shared_author_strings(rows)
        self.assertIn('Vogel P, Beyer D', shared)
        self.assertIn('Theofanidis AH', shared)
        # One group with several datasets under one paper is not suspicious
        self.assertNotIn('Wangen JR, Green R', shared)

    def test_queue_lists_studies_that_need_a_person(self):
        resolver = Resolver(web=Web(offline=True))
        studies = [
            {'BioProject': 'PRJNA1', 'Authors': 'Ingolia NT', 'PMID': '1234',
             'PMID_source': 'ncbi_link', 'Authorship_source': 'pubmed',
             'Submitters': 'Ingolia N', 'Institution': 'UCB', 'Name': 'n',
             'Release_Date': '2011/01/01', 'GSE': '', 'SRA': '', 'Title': ''},
            {'BioProject': 'PRJNA2', 'Authors': '', 'PMID': '',
             'PMID_source': '', 'Authorship_source': 'submitters',
             'Submitters': 'Tanaka H', 'Institution': 'RIKEN', 'Name': 'n',
             'Release_Date': '2020/01/01', 'GSE': '', 'SRA': '', 'Title': ''},
        ]
        queue = authorship_queue(studies, resolver)
        self.assertEqual([r['BioProject'] for r in queue], ['PRJNA2'])


if __name__ == '__main__':
    unittest.main()
