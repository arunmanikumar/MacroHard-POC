# app.py
import streamlit as st
import sys
import json
from agent import run_agent
import streamlit as st
import os

def check_password():
    if "authenticated" not in st.session_state:
        st.session_state.authenticated = False

    if not st.session_state.authenticated:
        st.title("Macrohard Travel Agent")
        st.markdown("---")
        password = st.text_input(
            "Enter demo password:",
            type="password",
            placeholder="Enter password to access"
        )
        if st.button("Login"):
            if password == os.getenv("APP_ID_TEST"):
                st.session_state.authenticated = True
                st.rerun()
            else:
                st.error("Incorrect password. Please try again.")
        st.stop()

check_password()

# rest of your app code below this line

# Load secrets for cloud deployment
if hasattr(st, 'secrets'):
    for key, value in st.secrets.items():
        os.environ[key] = str(value)
        
# Page config
st.set_page_config(
    page_title="Corporate Travel Planning Agent",
    page_icon="✈️",
    layout="wide"
)

# Header
st.title("✈️ Corporate Travel Planning Agent")
st.caption(
    "Powered by Claude on AWS Bedrock  |  "
    "Policy-compliant corporate travel planning"
)

st.divider()

# Two column layout
col1, col2 = st.columns([2, 1])

with col1:
    user_input = st.text_area(
        "Describe your trip:",
        height=120,
        placeholder=(
            "Example: Book a business trip for 2 people "
            "on November 15th for 5 days from Chicago "
            "to Chennai India with a budget of $6000 USD"
        )
    )

with col2:
    st.markdown("**Quick Test Inputs:**")
    if st.button("Chennai 5 days"):
        st.session_state.quick_input = (
            "Book a business trip for 2 people on "
            "November 15th for 5 days from Chicago "
            "to Chennai India with a budget of $6000 USD"
        )
    if st.button("LA 3 days"):
        st.session_state.quick_input = (
            "Book a business trip from Illinois to "
            "California for 3 days on September 2026 "
            "for budget 1500 USD for 1 person"
        )
    if st.button("London 1 week"):
        st.session_state.quick_input = (
            "Book a trip from India to UK with budget "
            "4000 dollars for a week in August for 2 people"
        )
    if st.button("Policy conflict test"):
        st.session_state.quick_input = (
            "Book a business trip for 3 people for 10 days "
            "from Chicago to Chennai India in November "
            "budget $15000 staying at Taj Coromandel"
        )

# Apply quick input if button was clicked
if "quick_input" in st.session_state:
    user_input = st.session_state.quick_input
    del st.session_state.quick_input

st.divider()

# Run button
run_clicked = st.button(
    "🚀 Plan My Trip",
    type="primary",
    use_container_width=True
)

if run_clicked and user_input.strip():
    # Show progress
    with st.status(
        "Agent is working...",
        expanded=True
    ) as status:
        st.write("Starting orchestrator...")

        try:
            # Capture tool calls as they happen
            result = run_agent(user_input, verbose=False)

            if result["status"] == "success":
                st.write(
                    f"Completed in {result['steps']} steps "
                    f"with {len(result['tool_log'])} tool calls"
                )
                status.update(
                    label="Travel plan ready",
                    state="complete"
                )
            else:
                status.update(
                    label="Agent encountered an error",
                    state="error"
                )

        except Exception as e:
            status.update(
                label="Something went wrong",
                state="error"
            )
            st.error(
                "The agent encountered an unexpected error. "
                "Please try again."
            )
            st.stop()

    # Show results
    if result["status"] == "success":
        st.divider()

        # Main result
        st.markdown("## 📋 Your Travel Plan")
        st.markdown(result["result"])

        st.divider()

        # Tool call trace
        with st.expander(
            f"🔧 Agent Reasoning — "
            f"{len(result['tool_log'])} tool calls across "
            f"{result['steps']} steps"
        ):
            for i, log in enumerate(result["tool_log"]):

                # Color code by tool type
                tool_name = log["tool"]
                if "policy" in tool_name:
                    icon = "🔍"
                elif "flight" in tool_name:
                    icon = "✈️"
                elif "hotel" in tool_name:
                    icon = "🏨"
                elif "weather" in tool_name:
                    icon = "🌤️"
                elif "currency" in tool_name:
                    icon = "💱"
                elif "country" in tool_name:
                    icon = "🌍"
                else:
                    icon = "⚙️"

                # Policy results get special display
                if "policy" in tool_name:
                    output = log["output"]
                    policy_status = output.get("status", "")
                    if policy_status == "PASS":
                        status_icon = "✅"
                    elif policy_status == "FAIL":
                        status_icon = "❌"
                    else:
                        status_icon = "⚠️"

                    st.markdown(
                        f"{icon} **Step {i+1}: {tool_name}** "
                        f"{status_icon} {policy_status}"
                    )
                    st.caption(
                        f"Checked: {log['input'].get('item_type', '')} "
                        f"${log['input'].get('amount_usd', '')} "
                        f"in {log['input'].get('city', '')}"
                    )
                    if policy_status == "FAIL":
                        st.warning(output.get("message", ""))
                else:
                    st.markdown(
                        f"{icon} **Step {i+1}: {tool_name}**"
                    )

                with st.container():
                    tab1, tab2 = st.tabs(["Input", "Output"])
                    with tab1:
                        st.json(log["input"])
                    with tab2:
                        st.json(log["output"])

                st.divider()

elif run_clicked and not user_input.strip():
    st.warning(
        "Please describe your trip before clicking Plan My Trip."
    )

# Footer
st.markdown("---")
st.caption(
    "This is a POC demonstration. "
    "All flight data is representative. "
    "Policy validation uses company travel policy document. "
    "Always confirm bookings with your travel desk."
)