"""
phase3/app.py

Streamlit UI for Phase 3.
Only change from Phase 2 app_v2.py:
  - Instead of calling graph.invoke() directly
  - Calls AgentCore endpoint via boto3
"""
import os
import json
import streamlit as st
import boto3
from uuid import uuid4
from dotenv import load_dotenv

load_dotenv()

# AgentCore runtime client
bedrock_agentcore = boto3.client(
    "bedrock-agentcore-runtime",
    region_name=os.getenv("AWS_REGION", "us-east-2")
)

AGENT_ARN = os.getenv("AGENTCORE_AGENT_ARN")  # set after deploy

st.set_page_config(
    page_title="Macrohard Travel Planner",
    page_icon="🌍",
    layout="wide"
)

st.title("🌍 Macrohard Corporate Travel Planner")
st.caption("Phase 3 — Powered by Amazon Bedrock AgentCore + LangGraph")

# Session management (AgentCore handles memory per session)
if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []

# Sidebar
with st.sidebar:
    st.header("Session")
    st.code(st.session_state.session_id[:16] + "...")
    if st.button("🔄 New Session"):
        st.session_state.session_id = str(uuid4())
        st.session_state.messages = []
        st.rerun()
    st.divider()
    st.markdown("**Policy Limits (HR-TRAV-001 v4.1)**")
    st.markdown("- 🏨 Domestic: $175/night")
    st.markdown("- 🌐 International: $250/night")
    st.markdown("- ✈️ Insurance mandatory for intl trips")

# Chat history
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# Input
if query := st.chat_input("Plan a trip (e.g. Chicago to London Oct 15-22)"):
    # Show user message
    st.session_state.messages.append({"role": "user", "content": query})
    with st.chat_message("user"):
        st.markdown(query)

    # Call AgentCore
    with st.chat_message("assistant"):
        with st.spinner("Planning your trip..."):
            try:
                response = bedrock_agentcore.invoke_agent_runtime(
                    agentRuntimeArn=AGENT_ARN,
                    sessionId=st.session_state.session_id,
                    payload=json.dumps({
                        "prompt": query,
                        "session_id": st.session_state.session_id
                    })
                )

                # Parse response
                result = json.loads(response["body"].read())
                answer = result.get("response", "No response")

                st.markdown(answer)
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": answer
                })

            except Exception as e:
                st.error(f"Error: {str(e)}")