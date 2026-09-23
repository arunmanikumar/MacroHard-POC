"""
tools/convert_currency.py
Phase 2 signature: convert_currency(amount, from_currency, to_currency)
"""
import json, sys
sys.path.insert(0, '/opt/python')
from api_calls import convert_currency

def lambda_handler(event, context):
    try:
        props = event["requestBody"]["content"]["application/json"]["properties"]
        result = convert_currency(
            amount=float(props["amount"]),
            from_currency=props["from_currency"],
            to_currency=props["to_currency"]
        )
        return {"statusCode": 200, "body": json.dumps(result)}
    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"status": "failed", "message": str(e)})}
