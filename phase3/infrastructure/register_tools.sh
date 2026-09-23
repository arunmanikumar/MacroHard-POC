#!/bin/bash
# infrastructure/register_tools.sh

set -e
source ~/.agentcore_config 2>/dev/null || true

ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION="${AWS_REGION:-us-east-2}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AGENT_ROLE="arn:aws:iam::${ACCOUNT_ID}:role/bedrock-agentcore-role"
BUCKET="travel-agent-schemas-${ACCOUNT_ID}"

echo "Account : $ACCOUNT_ID"
echo "Region  : $REGION"
echo ""

# ── Create S3 bucket for schemas ──────────────────────────────────────────────
echo "Creating S3 bucket for schemas..."
aws s3 mb "s3://${BUCKET}" --region "$REGION" 2>/dev/null || echo "  Bucket already exists"

# Upload all schemas to S3
echo "Uploading schemas to S3..."
for schema in "$REPO_ROOT"/schemas/*.json; do
  filename=$(basename "$schema")
  aws s3 cp "$schema" "s3://${BUCKET}/schemas/${filename}" --region "$REGION" > /dev/null
  echo "  ✅ Uploaded $filename"
done

# ── Use existing agent or create new ─────────────────────────────────────────
if [ -n "$AGENT_ID" ]; then
  echo ""
  echo "✅ Using existing agent: $AGENT_ID"
else
  echo "Creating AgentCore agent..."
  AGENT_ID=$(aws bedrock-agent create-agent \
    --agent-name "travel-planner-agentcore" \
    --agent-resource-role-arn "$AGENT_ROLE" \
    --foundation-model "anthropic.claude-haiku-4-5-sonnet-20241022" \
    --instruction "You are an expert corporate travel planning assistant for Macrohard. Help employees plan business trips using these tools: GetWeather, SearchFlights, GetCountryInfo, ConvertCurrency, FindHotels, CheckTravelPolicy. Always check travel policy for flights and hotels. Policy caps: domestic hotels \$175/night, international hotels \$250/night. Mandatory travel insurance for international trips per Section 9.1." \
    --region "$REGION" \
    --query 'agent.agentId' \
    --output text)
  echo "export AGENT_ID=\"$AGENT_ID\"" >> ~/.agentcore_config
  echo "✅ Agent created: $AGENT_ID"
fi

echo ""

# ── Register tools via S3 ─────────────────────────────────────────────────────
register_tool() {
  GROUP_NAME=$1
  SCHEMA_FILE=$2
  LAMBDA_NAME=$3

  LAMBDA_ARN="arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:${LAMBDA_NAME}"
  S3_URI="s3://${BUCKET}/schemas/${SCHEMA_FILE}"

  echo "Registering $GROUP_NAME..."

  aws bedrock-agent create-agent-action-group \
    --agent-id "$AGENT_ID" \
    --agent-version "DRAFT" \
    --action-group-name "$GROUP_NAME" \
    --action-group-executor lambda="$LAMBDA_ARN" \
    --api-schema "s3={s3BucketName=${BUCKET},s3ObjectKey=schemas/${SCHEMA_FILE}}" \
    --region "$REGION" > /dev/null

  echo "  ✅ $GROUP_NAME"
}

register_tool "WeatherResearch"    "weather_schema.json"  "travel-agent-get-weather"
register_tool "FlightSearch"       "flight_schema.json"   "travel-agent-search-flights"
register_tool "CountryInfo"        "country_schema.json"  "travel-agent-get-country-info"
register_tool "CurrencyConversion" "currency_schema.json" "travel-agent-convert-currency"
register_tool "HotelSearch"        "hotel_schema.json"    "travel-agent-find-hotels"
register_tool "PolicyValidation"   "policy_schema.json"   "travel-agent-check-travel-policy"

# ── Prepare Agent ─────────────────────────────────────────────────────────────
echo ""
echo "Preparing agent..."
aws bedrock-agent prepare-agent \
  --agent-id "$AGENT_ID" \
  --region "$REGION" > /dev/null

echo "Waiting for PREPARED status..."
for i in {1..20}; do
  STATUS=$(aws bedrock-agent get-agent \
    --agent-id "$AGENT_ID" \
    --region "$REGION" \
    --query 'agent.agentStatus' \
    --output text)
  echo "  Status: $STATUS"
  [ "$STATUS" = "PREPARED" ] && break
  sleep 3
done

echo ""
echo "✅ Agent PREPARED — AGENT_ID=$AGENT_ID"