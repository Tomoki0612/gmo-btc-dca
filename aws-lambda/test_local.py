import os
from dotenv import load_dotenv  
load_dotenv("../.env")  
from btc_auto_purchase import lambda_handler
                                                                                                                  
lambda_handler({}, {})