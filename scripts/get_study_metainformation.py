'''
Script to obtain study metainformation from public repositories given an accession 

Usage:
    get_study_metainformation.py -a <accession> 

'''

import argparse
import sys
from Bio import Entrez
import requests
import gzip
from io import BytesIO


def xmlData_to_dict(xmlData):
    '''
    Convert xmlData to dictionary

    Inputs:
        xmlData: string

    Returns:
        information_dict: dictionary
    '''
    information_dict = {}
    xml_list = xmlData.split('>')
    key = None
    for i in xml_list:
        if i.startswith('<'):
            key = i[1:]
        else:
            if key:
                information_dict[key] = i.split('<')[0].strip().replace('\xa0', ' ')
    
    return information_dict


def parse_soft_metadata(soft: str) -> dict:
    '''
    Extract desired metadata from soft string 

    Inputs:
        soft: string

    Returns:
        information_dict: dictionary
    '''
    fields = {
        'Title': '!Series_title',
        'Study_abstract': '!Series_summary',
        'Overall-Design': '!Series_overall_design',
        'Treatment-Protocol': '!Sample_treatment_protocol',
        'Growth-Protocol': '!Sample_growth_protocol',
        'Extract-Protocol': '!Sample_extract_protocol',
        'Data-Processing': '!Sample_data_processing',
        'Email': '!Series_contact_email',
        'Date': '!Series_submission_date',
    }
    information_dict = {}
    for line in soft.split('\n'):
        for field in fields:
            if line.startswith(fields[field]):
                if field not in information_dict:
                    information_dict[field] = [line.split('=')[1].strip()]
                else:
                    if line.split('=')[1].strip() not in information_dict[field]:
                        information_dict[field].append(line.split('=')[1].strip())
    for field in fields:
        if field not in information_dict:
            information_dict[field] = ['']

    return {i:'; '.join(information_dict[i]) for i in information_dict}


def download_GSE_metadata_files(accession: str) -> dict:
    '''
    Download the metadata files from GEO for a given accession

    Inputs:
        accession: string

    Returns:
        metadata_files: dictionary
    '''
    base_url = f'https://ftp.ncbi.nlm.nih.gov/geo/series/{accession[0:-3]}nnn/{accession}'

    metadata_files = {
                    'soft':f'{base_url}/soft/{accession}_family.soft.gz',
                    'miniml':f'{base_url}/miniml/{accession}_family.xml.tgz',
                    'supp':f'{base_url}/suppl/{accession}_raw.tar',
                }
    print(metadata_files['soft'])
    soft = requests.get(metadata_files['soft'])
    soft_content = BytesIO(gzip.decompress(soft.content)).read().decode('utf-8')
    information_dict = parse_soft_metadata(soft_content)
    return information_dict


def get_metainformation(accession: str, database) -> dict:
    '''
    Get study metainformation from public repositories given an accession 

    Inputs:
        accession: string

    Returns:
        record: dictionary
    '''

    Entrez.email = 'riboseq@gmail.com'
    handle = Entrez.esearch(db=database, term=accession)
    record = Entrez.read(handle)

    if record['Count'] == '0':
        raise ValueError(f'No study found with accession {accession}')
    
    study_id = record['IdList'][0]
    handle = Entrez.esummary(db=database, id=study_id)
    record = Entrez.read(handle, validate=False)

    return record if type(record) == dict or type(record) == Entrez.Parser.DictionaryElement else record


def main(args):

    if args.accession.startswith('SRP'):
        print('Accession is from SRA. Running search...')
        d = get_metainformation(args.accession, 'sra')
        d = xmlData_to_dict(d['ExpXml'])

    elif args.accession.startswith('PRJ'):
        print('Accession is from BioProject. Running search...')
        d = get_metainformation(args.accession, 'bioproject')

    elif args.accession.startswith('ERP'):
        print('Accession is from ArrayExpress. Running search...')
        d = get_metainformation(args.accession, 'sra')
        d = xmlData_to_dict(d['ExpXml'])

    elif args.accession.startswith('GSE'):
        print('Accession is from GEO. Running search...')
        d = get_metainformation(args.accession, 'gds')
        d = get_metainformation(200116523, 'geoprofiles')
    else:
        raise ValueError(f'Accession {args.accession} not recognized')

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Script to obtain study metainformation from public repositories given an accession')
    parser.add_argument('-a', '--accession', help='Study accession', required=True)
    args = parser.parse_args()
    main(args)
