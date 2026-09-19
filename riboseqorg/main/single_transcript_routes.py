import logging
import os
from tqdm import tqdm
import json



#@single_transcript_query_blueprint.route('/query', methods=['POST'])
def query_plot():  #TODO: add return type
    """
    jquery route for single transcript plot.

    Parameters:
    - request

    Returns:
    """
    data = ""
    with open("/home/DATA/www/RiboSeqOrg-DataPortal/riboseqorg/main/NARS.json") as fin:
        data = fin.read()
    print(data)
    return json.loads(data)








    # get user_id

    #return riboflask.generate_plot(data, settings)
if __name__=='__main__':
    query_plot()
