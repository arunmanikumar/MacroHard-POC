"""
tools/get_country_info.py
Phase 2 signature: get_country_info(country_name, is_international)
"""
import json, sys
sys.path.insert(0, '/opt/python')
from api_calls import get_country_info

def lambda_handler(event, context):
    try:
        props = event["requestBody"]["content"]["application/json"]["properties"]
        result = get_country_info(
            country_name=props["country_name"],
            is_international=props.get("is_international", True)
        )
        return {"statusCode": 200, "body": json.dumps(result)}
    except Exception as e:
        return {"statusCode": 500, "body": json.dumps({"status": "failed", "message": str(e)})}
