'''
This script is used to generate a GEO MINiML file from a GEO submission and parse it into a dictionary

'''
import requests
import BytesIO
import gzip

def parse_MINiML(miniml: str) -> dict:
    '''
    Parse MINiML file

    Inputs:
        miniml: string

    Returns:
        information_dict: dictionary
    '''
    fields = ['Title', 
              'Summary', 
              'Overall-Design', 
              'Treatment-Protocol', 
              'Growth-Protocol', 
              'Extract-Protocol', 
              'Label-Protocol', 
              'Hyb-Protocol', 
              'Scan-Protocol', 
              'Data-Processing',
              'Email',
              ]
    information_dict = {}
    replace = False
    minimal = ' '.join(miniml.split('\n')[1:-1])
    for line in minimal.split('<'):
        if line.startswith('/'):
            continue
        else:
            if line.startswith('Series'):
                replace = True

            for field in fields:
                if line.startswith(field):
                    if not replace:
                        if field not in information_dict:
                            information_dict[field] = line.split('>')[1].split('<')[0]
                    else:
                        information_dict[field] = line.split('>')[1].split('<')[0]
    return information_dict

def download_GSE_metadata_files(accession: str) -> dict:
    '''
    Download the metadata files from GEO for a given accession

    Inputs:
        accession: string

    Returns:
        metadata_files: dictionary
    '''
    Miniml_url = f'https://ftp.ncbi.nlm.nih.gov/geo/series/{accession[0:-3]}nnn/{accession}/miniml/{accession}_family.xml.tgz'


    minimal = requests.get(Miniml_url)
    minimal = BytesIO(gzip.decompress(minimal.content)).read().decode('utf-8')
    information_dict = parse_MINiML(minimal)