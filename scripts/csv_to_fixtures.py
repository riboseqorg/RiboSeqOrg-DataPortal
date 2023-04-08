"""
Python script to convert data from a csv file to a fixture file for a django app
This script assumes that the csv file has a header row and that every other row is to be made into a fixture
Each column in the csv file will be a field in the fixture file and the column name will be the field name

Usage:
    python csv_to_sample_fixture.py -i <csv_file> --db <sqlite database> -o <fixture_file>

"""
from populate_study_metainfo_dict import get_metainformation_dict
import argparse
import pandas as pd
import sqlite3


def get_last_pk(model: str, db: str) -> int:
    """
    Get the last primary key of the model in the database
    
    Inputs:
        model: string
        db: string
    Returns:
        last_pk: int
    """
    conn = sqlite3.connect(db)
    c = conn.cursor()
    c.execute(f"SELECT MAX(id) FROM {model}")
    last_pk = c.fetchone()[0]
    conn.close()

    return last_pk


def df_to_sample_fixture(df: pd.DataFrame, last_pk: int) -> str:
    """
    Convert cleaned df to fixture string 
    
    Inputs:
        df: pandas dataframe
        last_pk: int
    
    Returns:
        fixture string
    """
    fixture = ["[\n"]

    for i, row in df.iterrows():
        if last_pk:
            i += last_pk + 1
        fixture.append("{\n")
        fixture.append('    "model": "main.sample",\n')
        fixture.append(f'    "pk": {i},\n')
        fixture.append('    "fields": {\n')
        for col in df.columns:
            if col in ["spots", "bases", "avgLength", "size_MB"]:
                try:
                    fixture.append(f'        "{col}": {int(row[col])},\n')
                except:
                    pass
            else:
                fixture.append(f'        "{col}": "{row[col]}",\n')
        fixture[-1] = fixture[-1][:-2]  # removes trailing comma
        fixture.append("    }\n")
        fixture.append("},\n")

    fixture = " ".join(fixture)

    return fixture


def write_study_fixture(information_dict: str, pk) -> str:
    """
    Give the accession of the study, return the study fixture
    
    inputs:
        accession: string
    returns:
        fixture: string
    """
    fixture = []
    fixture.append("{\n")
    fixture.append('    "model": "main.study",\n')
    fixture.append(f'    "pk":{pk},\n')
    fixture.append('    "fields": {\n')
    for field in information_dict:    
        fixture.append(f'        "{field}": "{information_dict[field]}",\n')
    fixture[-1] = fixture[-1][:-2]
    fixture.append("    }\n")
    fixture.append("},\n")

    fixture = " ".join(fixture)

    return fixture



def add_study_fixtures(df: pd.DataFrame, db: str) -> pd.DataFrame:
    """
    Add study fixtures to the dataframe
    
    Inputs:
        df: pandas dataframe
        db: string
    
    Returns:
        df: pandas dataframe
    """
    study_fixtures = ""
    study_accessions = []
    last_pk_study = get_last_pk("main_study", db)
    for idx, row in df.iterrows():
        if row["Study_Accession"] not in study_accessions:
            study_accessions.append(row["Study_Accession"])
            subset_df = df[df["Study_Accession"] == row["Study_Accession"]]
            study_info_dict = get_metainformation_dict(subset_df)        
            if last_pk_study:
                last_pk_study += 1
            else:
                last_pk_study = 1
            study_fixture = write_study_fixture(study_info_dict, last_pk_study)
            
        study_fixtures += study_fixture
    return study_fixtures


def fixtures_to_file(fixtures: str, output_file: str):
    """
    Write the fixture string to a file
    
    Inputs:
        fixtures: string
        output_file: string
    """
    with open(output_file, "w") as f:
        f.write(fixtures)


def main():
    parser = argparse.ArgumentParser(description="Convert csv file to fixture file")
    parser.add_argument("-i", "--input", help="Input csv file", required=True)
    parser.add_argument("--db", help="Sqlite database", required=True)
    parser.add_argument("-o", "--output", help="Output fixture file", required=True)
    args = parser.parse_args()

    df = pd.read_csv(args.input)

    ### MESSY: USED FOR TESTING
    # df = df[df['Study_Accession'].str.startswith('PRJ')]
    top_10_accessions = df['Study_Accession'].unique()[:10]
    df = df[df['Study_Accession'].isin(top_10_accessions)]
    ###

    df["Study_Pubmed_id"] = df["Study_Pubmed_id"].astype(str)

    df = df.drop(["CHECKED", "name", "not_unique", "KEEP", "UNIQUE", "GENE"], axis=1)

    last_pk_sample = get_last_pk("main_sample", args.db)

    fixtures = df_to_sample_fixture(df, last_pk_sample)
    fixtures += add_study_fixtures(df, args.db)

    fixtures = fixtures[:-2]
    fixtures += "\n]"
    fixtures_to_file(fixtures, args.output)


if __name__ == "__main__":
    main()
