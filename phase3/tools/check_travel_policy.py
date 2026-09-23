"""
tools/check_travel_policy.py
Phase 2 signature: check_travel_policy(item_type, amount_usd, city, is_international, details)
"""
import json, sys
sys.path.insert(0, '/opt/python')
from api_calls import check_travel_policy

def lambda_handler(event, context):
    try:
        props = event["requestBody"]["content"]["application/json"]["properties"]
        result = check_travel_policy(
            item_type=props["item_type"],
            amount_usd=float(props["amount_usd"]),
            city=props["city"],
            is_international=props.get("is_international", False),
            details=props.get("details", "")
        )
        return {"statusCode": 200, "body": json.dumps(result)}
    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"status": "failed", "message": str(e)})}
