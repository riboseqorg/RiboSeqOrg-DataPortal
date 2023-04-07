'''
Python script to convert data from a csv file to a fixture file for a django app
This script assumes that the csv file has a header row and that every other row is to be made into a fixture
Each column in the csv file will be a field in the fixture file and the column name will be the field name

Usage:
    python csv_to_sample_fixture.py -i <csv_file> -o <fixture_file>

'''

import argparse
import pandas as pd 


def df_to_sample_fixture(df: pd.DataFrame) -> str:
    '''
    Convert cleaned df to fixture string 
    
    Inputs:
        df: pandas dataframe
    
    Returns:
        fixture string
    '''
    fixture = ['[\n']

    for i, row in df.iterrows():
        fixture.append('{\n')
        fixture.append('    "model": "main.sample",\n')
        fixture.append('    "pk": %d,\n' % i)
        fixture.append('    "fields": {\n')
        for col in df.columns:
            fixture.append('        "%s": "%s",\n' % (col, row[col]))
        fixture[-1] = fixture[-1][:-2] # removes trailing comma
        fixture.append('    }\n')
        fixture.append('},\n')

    fixture = ' '.join(fixture)

    return fixture

def df_to_study_fixture(accession: str) -> str:
    '''
    Give the accession of the study, return the study fixture
    
    inputs:
        accession: string
    returns:
        fixture: string
    '''
    fixture = []
    fixture.append('{\n')
    fixture.append('    "model": "main.study",\n')
    fixture.append('    "pk": 1,\n')
    fixture.append('    "fields": {\n')
    fixture.append('        "Acession": "%s",\n' % accession)
    fixture[-1] = fixture[-1][:-2]
    fixture.append('    }\n')
    fixture.append('},\n')

    fixture = ' '.join(fixture)

    return fixture


def fixtures_to_file(fixtures: str, output_file: str):
    '''
    Write the fixture string to a file
    
    Inputs:
        fixtures: string
        output_file: string
    '''
    with open(output_file, 'w') as f:
        f.write(fixtures)

def main():
    parser = argparse.ArgumentParser(description='Convert csv file to fixture file')
    parser.add_argument('-i', '--input', help='Input csv file', required=True)
    parser.add_argument('-o', '--output', help='Output fixture file', required=True)
    args = parser.parse_args()

    df = pd.read_csv(args.input)
    df = df.drop(['CHECKED', 'name', 'not_unique', 'KEEP', 'UNIQUE', 'GENE'], axis=1)

    study_accessions = df['Study_Accession'].unique()

    print(len(df.columns), study_accessions)
    fixtures = df_to_sample_fixture(df)
    for study in study_accessions:
        fixtures += df_to_study_fixture(study)
    fixtures = fixtures[:-2]
    fixtures += '\n]'
    fixtures_to_file(fixtures, args.output)


if __name__ == '__main__':
    main()