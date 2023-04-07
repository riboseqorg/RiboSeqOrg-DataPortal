'''
Python script to convert data from a csv file to a fixture file for a django app
This script assumes that the csv file has a header row and that every other row is to be made into a fixture
Each column in the csv file will be a field in the fixture file and the column name will be the field name

Usage:
    python csv_to_sample_fixture.py -i <csv_file> --db <sqlite database> -o <fixture_file>

'''

import argparse
import pandas as pd 
import sqlite3

def get_last_pk(model: str, db: str) -> int:
    '''
    Get the last primary key of the model in the database
    
    Inputs:
        model: string
        db: string
    Returns:
        last_pk: int
    '''
    conn = sqlite3.connect(db)
    c = conn.cursor()
    c.execute('SELECT MAX(id) FROM %s' % model)
    last_pk = c.fetchone()[0]
    conn.close()

    return last_pk


def df_to_sample_fixture(df: pd.DataFrame, last_pk: int) -> str:
    '''
    Convert cleaned df to fixture string 
    
    Inputs:
        df: pandas dataframe
        last_pk: int
    
    Returns:
        fixture string
    '''
    fixture = ['[\n']

    for i, row in df.iterrows():
        if last_pk:
            i += last_pk + 1
        fixture.append('{\n')
        fixture.append('    "model": "main.sample",\n')
        fixture.append('    "pk": %d,\n' % i)
        fixture.append('    "fields": {\n')
        for col in df.columns:
            if col in ['spots', 'bases', 'avgLength', 'size_MB']:
                try:
                    fixture.append('        "%s": %s,\n' % (col, int(row[col])))
                except:
                    pass
            else:
                fixture.append('        "%s": "%s",\n' % (col, row[col]))
        fixture[-1] = fixture[-1][:-2] # removes trailing comma
        fixture.append('    }\n')
        fixture.append('},\n')

    fixture = ' '.join(fixture)

    return fixture

def df_to_study_fixture(accession: str, pk) -> str:
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
    fixture.append(f'    "pk":{pk},\n')
    fixture.append('    "fields": {\n')
    fixture.append(f'        "Acession": "{accession}",\n')
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
    parser.add_argument('--db', help='Sqlite database', required=True)
    parser.add_argument('-o', '--output', help='Output fixture file', required=True)
    args = parser.parse_args()

    df = pd.read_csv(args.input)

    df['Study_Pubmed_id'] = df['Study_Pubmed_id'].astype(str)

    df = df.drop(['CHECKED', 'name', 'not_unique', 'KEEP', 'UNIQUE', 'GENE'], axis=1)

    study_accessions = df['Study_Accession'].unique()

    last_pk_sample = get_last_pk('main_sample', args.db)
    last_pk_study = get_last_pk('main_study', args.db)

    fixtures = df_to_sample_fixture(df, last_pk_sample)
    for idx, study in enumerate(study_accessions):
        if not last_pk_study:
            pk = 1
            last_pk_study = 1
        else:
            pk = last_pk_study + idx + 1
        fixtures += df_to_study_fixture(study, pk)
    fixtures = fixtures[:-2]
    fixtures += '\n]'
    fixtures_to_file(fixtures, args.output)


if __name__ == '__main__':
    main()