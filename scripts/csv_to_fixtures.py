'''
THis script is used to convert csv files to fixtures
It is used to populate the Trips and GWIPS models in the database
These need to be updated in line updates to these resources

CSV columns must match the model fields

'''

import argparse
import pandas as pd

def df_to_sample_fixture(df: pd.DataFrame, last_pk: int, model: str) -> str:
    """
    Convert cleaned df to fixture string 
    
    Inputs:
        df: pandas dataframe
        last_pk: int
        model: string
    
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
        fixture.append(f'    "model": "main.{model}",\n')
        fixture.append(f'    "pk": {last_pk},\n')
        fixture.append('    "fields": {\n')
        for col in df.columns:
            if type(row[col]) == str:
                # entry = row[col].replace('""""', "'").replace('\n', ' ').replace('"', "'")
                fixture.append(f'        "{col}": "{row[col]}",\n')
            else: 
                fixture.append(f'        "{col}": "{row[col]}",\n')

        fixture[-1] = fixture[-1][:-2]  # removes trailing comma
        fixture.append("    }\n")
        fixture.append("},\n")

    fixture = " ".join(fixture)
    return fixture


def main(args):
    df = pd.read_csv(args.input)
    fixture = df_to_sample_fixture(df, 0, args.model)
    with open(args.output, "w") as f:
        f.write(fixture)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-i", "--input", help="csv file to convert to fixture")
    parser.add_argument("-m", "--model", help="model to convert to fixture (trips or gwips)")
    parser.add_argument("-o", "--output", help="output file name")
    args = parser.parse_args()

    main(args)
