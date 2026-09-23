#!/bin/bash
# infrastructure/iam_roles.sh

set -e
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION="${AWS_REGION:-us-east-2}"
BUCKET="travel-agent-schemas-${ACCOUNT_ID}"

echo "Account : $ACCOUNT_ID"
echo "Region  : $REGION"
echo ""

# ── AgentCore Role ────────────────────────────────────────────────────────────
echo "Creating bedrock-agentcore-role..."

aws iam create-role \
  --role-name bedrock-agentcore-role \
  --assume-role-policy-document '{
    "Version":"2012-10-17",
    "Statement":[{
      "Effect":"Allow",
      "Principal":{"Service":"bedrock.amazonaws.com"},
      "Action":"sts:AssumeRole"
    }]
  }' 2>/dev/null || echo "  Role already exists"

aws iam put-role-policy \
  --role-name bedrock-agentcore-role \
  --policy-name agentcore-permissions \
  --policy-document "{
    \"Version\":\"2012-10-17\",
    \"Statement\":[
      {
        \"Effect\":\"Allow\",
        \"Action\":\"bedrock:InvokeModel\",
        \"Resource\":\"arn:aws:bedrock:${REGION}::foundation-model/anthropic.claude-haiku-4-5-sonnet-20241022\"
      },
      {
        \"Effect\":\"Allow\",
        \"Action\":\"lambda:InvokeFunction\",
        \"Resource\":\"arn:aws:lambda:${REGION}:${ACCOUNT_ID}:function:travel-agent-*\"
      },
      {
        \"Effect\":\"Allow\",
        \"Action\":[\"bedrock:Retrieve\",\"bedrock:RetrieveAndGenerate\"],
        \"Resource\":\"arn:aws:bedrock:${REGION}:${ACCOUNT_ID}:knowledge-base/*\"
      },
      {
        \"Effect\":\"Allow\",
        \"Action\":[\"s3:GetObject\",\"s3:ListBucket\"],
        \"Resource\":[
          \"arn:aws:s3:::${BUCKET}\",
          \"arn:aws:s3:::${BUCKET}/*\"
        ]
      }
    ]
  }"

echo "✅ bedrock-agentcore-role ready"

# ── Lambda Role ───────────────────────────────────────────────────────────────
echo "Creating travel-agent-lambda-role..."

aws iam create-role \
  --role-name travel-agent-lambda-role \
  --assume-role-policy-document '{
    "Version":"2012-10-17",
    "Statement":[{
      "Effect":"Allow",
      "Principal":{"Service":"lambda.amazonaws.com"},
      "Action":"sts:AssumeRole"
    }]
  }' 2>/dev/null || echo "  Role already exists"

aws iam put-role-policy \
  --role-name travel-agent-lambda-role \
  --policy-name lambda-permissions \
  --policy-document "{
    \"Version\":\"2012-10-17\",
    \"Statement\":[
      {
        \"Effect\":\"Allow\",
        \"Action\":[\"logs:CreateLogGroup\",\"logs:CreateLogStream\",\"logs:PutLogEvents\"],
        \"Resource\":\"arn:aws:logs:${REGION}:${ACCOUNT_ID}:*\"
      },
      {
        \"Effect\":\"Allow\",
        \"Action\":[\"bedrock:Retrieve\",\"bedrock:RetrieveAndGenerate\"],
        \"Resource\":\"arn:aws:bedrock:${REGION}:${ACCOUNT_ID}:knowledge-base/*\"
      }
    ]
  }"

echo "✅ travel-agent-lambda-role ready"
echo ""
echo "✅ All IAM roles ready"