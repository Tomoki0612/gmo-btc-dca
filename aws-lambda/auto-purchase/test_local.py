import os
os.environ["DRY_RUN"] = "true"
os.environ["SNS_TOPIC_ARN"] = ""

from btc_auto_purchase import lambda_handler

result = lambda_handler({}, None)
print(result)
