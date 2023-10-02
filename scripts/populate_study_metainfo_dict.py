'''
This script contains the funcitons to fill the required fields of metadata for a study

It is not directly called by the user but functions are used in csv_to_fixtures.py
'''

import pandas as pd
import numpy as np
import requests
from get_study_metainformation import get_metainformation, xmlData_to_dict, download_GSE_metadata_files


def get_pubmed_abstract(pmid: str) -> str:
    '''
    Return the abstract for a given paper on pubmed

    Inputs:
        pmid: string

    Returns:
        abstract: string
    '''
    url = f'https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi?db=pubmed&id={pmid}&retmode=xml'
    response = requests.get(url)
    xml = response.text
    if '<Abstract>' in xml:
        abstract = xml.split('<Abstract>')[1].split('</Abstract>')[0]
        abstract = abstract.replace('<', '>')
        abstract_list = abstract.split('>')
        abstract = ' '.join([i for idx, i in enumerate(abstract_list) if idx % 2 == 0])
    else:
        abstract = ''
    return abstract

def get_geo_metainformation(record: dict) -> dict:
    '''
    Get metainformation from GEO

    Inputs:
        record: dictionary

    Returns:
        record: dictionary
    '''
    information_dict = download_GSE_metadata_files(record['GSE'])
    record['Title'] = information_dict['Title']
    record['Study_abstract'] = information_dict['Study_abstract']
    record['Description'] = f"Overall-Design: {information_dict['Overall-Design']}\n Treatment-Protocol: {information_dict['Treatment-Protocol']}\n Growth-Protocol: {information_dict['Growth-Protocol']}\n Extract-Protocol: {information_dict['Extract-Protocol']}\n Data-Processing: {information_dict['Data-Processing']}"
    record['Email'] = information_dict['Email']

    return record

def parse_bioproject_results(results: str, record: dict) -> dict:
    '''
    Parse entrez results from bioproject database

    Inputs:
        results: string
        record: dictionary

    Returns:
        record: dictionary
    '''
    if len(results['DocumentSummarySet']['DocumentSummary']) != 1:
        record['Title'] = ''
        record['Organism'] = ''
        record['Release_Date'] = ''
        return record

    results = results['DocumentSummarySet']['DocumentSummary'][0]

    record['Title'] = results['Project_Title']
    record['Organism'] = results['Organism_Name']
    record['Release_Date'] = results['Registration_Date']
    return record


def parse_sra_results(results: str, record: dict) -> dict:
    '''
    Parse entrez results from sra database

    Inputs:
        results: string
        record: dictionary

    Returns:
        record: dictionary
    '''
    ExpXML = xmlData_to_dict(results[0]['ExpXml'])
    results[0].pop('ExpXml')
    record['Title'] = ExpXML['Title']
    return record


def parse_pubmed_results(results: str, record: dict) -> dict:
    '''
    Parse entrez results from pubmed database

    Inputs:
        results: string
        record: dictionary

    Returns:
        record: dictionary
    '''
    results = results[0]
    record['Authors'] = ','.join(results['AuthorList'])
    record['Publication_title'] = results['Title']
    record['doi'] = results['ArticleIds']['doi']
    record['Date_published'] = results['PubDate']
    if 'pmc' in results['ArticleIds']:
        record['PMC'] = results['ArticleIds']['pmc']
    record['Journal'] = results['FullJournalName']
    return record


def get_metainformation_dict(df: pd.DataFrame) -> dict:
    '''
    Get study metainformation from public repositories given an accession 

    Inputs:
        df: pandas dataframe

    Returns:
        record: dictionary
    '''
    record = {
        "BioProject":"",
        "Name":"",
        "Title":"",
        "Organism":"",
        "Samples":"",
        "SRA":"",
        "Release_Date":"",
        "Description" :"",
        "seq_types":"",
        "GSE":"",
        "PMID":"",
        "Authors":"",
        "Study_abstract" :"",
        "Publication_title":"",
        "doi":"",
        "Date_published":"",
        "PMC":"",
        "Journal":"",
        "Paper_abstract" :"",
        "Email":"",
    }
    # Accession is the unique value by which this dataframe has been subsetted. [0] is used to get the value from the series
    record['BioProject'] = df['BioProject'].unique()[0]

    # Samples is the number of samples that share this study accession i.e the number of rows in this df
    record['Samples'] = df.shape[0]

    # Organism is a ; separated list of all organisms in this study
    record['Organism'] = '; '.join(list(df['ScientificName'].astype(str).unique()))
    if len(record['Organism']) < 2:
        print(df['ScientificName'])
        print(record['Organism'])

    # SRA is a ; separated list of all SRA studies (SRPs) in this study
    record['SRA'] = ';'.join(list(df['SRAStudy'].unique()))

    # Release date is the date of the first publication of this data. It is a combination of the month and year. But date can be overwritten from GSE/BioProject
    # 00 is used to make sure that the date is in the correct format as the date is not known only month and year
    record['Release_Date'] = '/'.join([str(df['YEAR'].unique()[0]), str(df['MONTH'].unique()[0]), '00', '00:00'])

    # Seq_types is a ; separated list of all sequencing types in this study (Ribo-Seq, RNA-Seq, etc.)
    if list(df['LIBRARYTYPE'].unique()) == ['nan']:
        record['seq_types'] = ';'.join(list(df['LIBRARYTYPE'].unique())).replace('RFP', 'Ribo-Seq').replace('RNA', 'RNA-Seq')

    # GSE is the GEO accession number. Can only be assigned here if the study accession is a GSE
    record['GSE'] = record['BioProject'] if record['BioProject'].startswith('GSE') else ''

    # BioProject is the BioProject accession number. If study_accession is GSE then this may be a list of BioProjects
    if list(df['BioProject'].unique()) == ['nan']:
        record['BioProject'] = ';'.join(list(df['BioProject'].unique()))

    # PMID is the Pubmed ID. If there are multiple PMIDs then they are separated by ;
    if df['Study_Pubmed_id'].unique()[0] != np.nan:
        for i in df['Study_Pubmed_id'].unique():
            if record['PMID'] == '':
                record['PMID'] = i.split('.')[0]
            else:
                record['PMID'] += f";{i.split('.')[0]}"

    # Authors is a ; separated list of all authors in this study this will be overwritten from pubmed if possible
    if list(df['AUTHOR'].unique()) != ['nan'] or list(df['AUTHOR'].unique()) != ['Makar']:
        if len(list(df['AUTHOR'].unique())) == 1:
            record['Authors'] = list(df['AUTHOR'].unique())[0]
        else:
            record['Authors'] = ';'.join(str(list(df['AUTHOR'].unique())))
    else:
        record['Authors'] = 'Unknown Author'

    # Name assigned to the study. It is a combination of the author and the year. But Author and year can be overwritten from pubmed
    if df['AUTHOR'].unique()[0] in ['nan', '']:
        record['Name'] = f"Unknown Author {df['YEAR'].unique()[0]}"
    else:
        record['Name'] = f"{df['AUTHOR'].unique()[0]} et al. {df['YEAR'].unique()[0]}" 

    if record['BioProject'].startswith('PRJ'):
        print(f'Accession {record["BioProject"]} is from BioProject. Running search...')
        d = get_metainformation(record['BioProject'], 'bioproject')
        record = parse_bioproject_results(d, record)

    elif record['BioProject'].startswith('GSE'):
        print('Accession is from GEO. Running search...')
        record = get_geo_metainformation(record)

    else:
        raise ValueError(f"Accession {record['BioProject']} not recognized")

    if record['PMID'] != '':
        print('Found PMID. Running search...')
        d = get_metainformation(record['PMID'], 'pubmed')
        record = parse_pubmed_results(d, record)
        record['Paper_abstract'] = get_pubmed_abstract(record['PMID'])

    return record
