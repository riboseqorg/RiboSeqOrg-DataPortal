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
    fixture = []

    for i, row in df.iterrows():
        if not last_pk:
            last_pk = 1
        else:
            last_pk += 1
        fixture.append("{\n")
        fixture.append('    "model": "main.sample",\n')
        fixture.append(f'    "pk": {last_pk},\n')
        fixture.append('    "fields": {\n')
        for col in df.columns:
            if col in ["spots", "bases", "avgLength", "size_MB"]:
                try:
                    fixture.append(f'        "{col}": {int(row[col])},\n')
                except:
                    pass
            else:
                if type(row[col]) == str:
                    entry = row[col].replace('""""', "'").replace('\n', ' ').replace('"', "'")
                    fixture.append(f'        "{col}": "{entry}",\n')
                else: 
                    fixture.append(f'        "{col}": "{row[col]}",\n')

        fixture[-1] = fixture[-1][:-2]  # removes trailing comma
        fixture.append("    }\n")
        fixture.append("},\n")

    fixture = " ".join(fixture)
    return fixture


def write_study_fixture(information_dict: dict) -> str:
    """
    Give the accession of the study, return the study fixture
    
    inputs:
        information_dict: dictionary
        pk: int

    returns:
        fixture: string
    """
    fixture = []

    fixture.append("{\n")
    fixture.append('    "model": "main.study",\n')
    fixture.append(f'    "pk":"{information_dict["BioProject"]}",\n')
    fixture.append('    "fields": {\n')

    for field in information_dict:
        if type(information_dict[field]) == str:
            entry = information_dict[field].replace('\n', ' ').replace('"', "'")
            fixture.append(f'        "{field}": "{entry}",\n')
        else:
            fixture.append(f'        "{field}": "{information_dict[field]}",\n')
    fixture[-1] = fixture[-1][:-2]
    fixture.append("    }\n")
    fixture.append("},\n")

    fixture = " ".join(fixture)

    return fixture


def write_OpenColumns_fixture(column: str, bioproject: str, pk: int) -> str:
    '''
    Write the OpenColumns fixture string

    Inputs:
        column: string
        bioProject: string
        last_pk: int

    Returns:
        fixture: string
    '''
    fixture = []
    fixture.append("{\n")
    fixture.append('    "model": "main.opencolumns",\n')
    fixture.append(f'    "pk":{pk},\n')
    fixture.append('    "fields": {\n')
    fixture.append(f'        "column_name": "{column}",\n')
    fixture.append(f'        "bioproject": "{bioproject}",\n')
    fixture[-1] = fixture[-1][:-2]
    fixture.append("    }\n")
    fixture.append("},\n")

    fixture = " ".join(fixture)

    return fixture



def add_study_fixtures(df: pd.DataFrame, db: str, core_columns: list) -> pd.DataFrame:
    """
    Add study fixtures to the dataframe
    
    Inputs:
        df: pandas dataframe
        db: string
        core_columns: list of strings
    
    Returns:
        df: pandas dataframe
    """
    study_fixtures = ""
    study_accessions = []
    # last_pk_study = get_last_pk("main_study", db)
    last_pk_OpenColumns = get_last_pk("main_opencolumns", db)
    for idx, row in df.iterrows():
        if row["BioProject"] not in study_accessions:
            study_accessions.append(row["BioProject"])
            subset_df = df[df["BioProject"] == row["BioProject"]]
            core_df = subset_df[core_columns]
            study_info_dict = get_metainformation_dict(core_df)
            # if last_pk_study:
            #     last_pk_study += 1
            # else:
            #     last_pk_study = 1
            study_fixture = write_study_fixture(study_info_dict)
            
            open_df = subset_df.drop(
                [i for i in core_columns if i != 'BioProject']
                 , axis=1)
            open_df = open_df.dropna(axis=1, how="all")
            bioproject = open_df["BioProject"].iloc[0]
            open_fixtures = ""
            for col in open_df.columns:
                if last_pk_OpenColumns:
                    last_pk_OpenColumns += 1
                else:
                    last_pk_OpenColumns = 1
                open_fixtures += write_OpenColumns_fixture(col, bioproject, last_pk_OpenColumns)

        study_fixtures += study_fixture
        study_fixtures += open_fixtures
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


def generate_open_column_sqlites(df: pd.DataFrame, sqlite_dir_path: str):
    '''
    For all studies (unique BioProject) in the dataframe, generate a sqlite database
    that contains a open columns table named after the BioProject. This is to contain 
    all the columns that are not in the core columns list 

    Inputs:
        df: pandas dataframe no core columns except BioProject
        sqlite_dir_path: string
    
    '''

    grouped = df.groupby("BioProject")
    for group, group_df in grouped:
        group_df = group_df.dropna(axis=1, how="all")
        conn = sqlite3.connect(f"{sqlite_dir_path}/{group}.sqlite")

        group_df.to_sql(group, conn, if_exists="replace")



def main(args):

    df = pd.read_csv(args.input)

    df["Study_Pubmed_id"] = df["Study_Pubmed_id"].astype("Int64").astype(str)
    df['Study_Pubmed_id'] = df['Study_Pubmed_id'].replace("1", '')
    df['YEAR'] = df['YEAR'].astype("Int64").astype(str)

    core_columns = ["BioProject", "Run","spots", "bases", "avgLength", "size_MB", "Experiment", "LibraryName", "LibraryStrategy", "LibrarySelection", "LibrarySource", "LibraryLayout", "InsertSize", "InsertDev", "Platform", "Model", "SRAStudy", "Study_Pubmed_id", "Sample", "BioSample", "SampleType", "TaxID", "ScientificName", "SampleName", "CenterName", "Submission", "MONTH", "YEAR", "AUTHOR", "sample_source", "sample_title", "LIBRARYTYPE", "REPLICATE", "CONDITION", "INHIBITOR", "TIMEPOINT", "TISSUE", "CELL_LINE", "FRACTION"]

    # df = df.drop(["CHECKED", "name", "not_unique", "KEEP", "UNIQUE", "GENE"], axis=1)

    last_pk_sample = get_last_pk("main_sample", args.db)
    print(last_pk_sample)

    print("generating sample fixtures")
    print("generating study fixtures")
    fixtures = "[\n"
    fixtures += add_study_fixtures(df, args.db, core_columns)
    fixtures += df_to_sample_fixture(df[core_columns], last_pk_sample)

    print("Done!")

    fixtures = fixtures[:-2]
    fixtures += "\n]"
    print("writing fixtures to file")
    fixtures_to_file(fixtures, args.output)
    open_df = df.drop(
        [i for i in core_columns if i != 'BioProject']
            , axis=1)
    generate_open_column_sqlites(open_df, "/home/jack/projects/RiboSeqOrg-DataPortal/sqlites")
    print("Done!")



if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Convert csv file to fixture file")
    parser.add_argument("-i", "--input", help="Input csv file", required=True)
    parser.add_argument("--db", help="Sqlite database", required=True)
    parser.add_argument("-o", "--output", help="Output fixture file", required=True)
    args = parser.parse_args()

    main(args)
