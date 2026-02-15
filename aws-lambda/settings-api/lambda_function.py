import json
import boto3
from decimal import Decimal

dynamodb = boto3.resource("dynamodb")
table = dynamodb.Table("btc-dca-settings")

HEADERS = {
    "Access-Control-Allow-Origin": "*",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Access-Control-Allow-Headers": "Content-Type",
}


def decimal_to_num(obj):
    if isinstance(obj, Decimal):
        return int(obj) if obj == int(obj) else float(obj)
    raise TypeError


def lambda_handler(event, context):
    method = event["httpMethod"]

    if method == "GET":
        response = table.get_item(Key={"userId": "user1"})
        item = response.get("Item", {})
        return {
            "statusCode": 200,
            "headers": HEADERS,
            "body": json.dumps(item, default=decimal_to_num),
        }

    if method == "POST":
        body = json.loads(event["body"])
        table.put_item(
            Item={
                "userId": "user1",
                "amount": body["amount"],
                "schedule": body["schedule"],
                "apiKey": body["apiKey"],
                "apiSecret": body["apiSecret"],
            }
        )
        return {
            "statusCode": 200,
            "headers": HEADERS,
            "body": json.dumps({"message": "saved"}),
        }

    return {
        "statusCode": 405,
        "headers": HEADERS,
        "body": json.dumps({"message": "Method Not Allowed"}),
    }
