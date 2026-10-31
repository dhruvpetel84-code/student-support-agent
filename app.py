
"""Authenticated Streamlit chat UI.
Run with: python -m streamlit run app.py
"""

import os
import uuid
import streamlit as st

from database.seed import seed
from database.db import connect

from config.settings import get_chat_model
from agent.graph import build_graph, run_agent

from rag.retrieval import PolicyRetriever

from memory.store import (
    list_memories,
    save_memory,
    delete_memory
)

from memory.policies import classify_memory

from observability.tracing import write_trace
from observability.audit import list_audit

from security.auth import authenticate
from security.redaction import redact_sensitive
from security.authorization import authenticated_as
from security.approvals import (
    request_email_change,
    pending_actions,
    decide_action
)


# --------------------------------------------------
# PAGE CONFIGURATION
# --------------------------------------------------

st.set_page_config(
    page_title="Student Support Agent",
    page_icon="🎓",
    layout="wide"
)

st.title("🎓 Intelligent Student Support Agent")
st.caption(
    "Assignment 2 local demo. All student data is fictional."
)


# --------------------------------------------------
# DATABASE INITIALIZATION
# --------------------------------------------------

try:
    seed()
except Exception as e:
    st.error(f"Database initialization failed: {e}")
    st.exception(e)
    st.stop()


# --------------------------------------------------
# SESSION STATE INITIALIZATION
# --------------------------------------------------

if "principal" not in st.session_state:
    st.session_state.principal = None

if "chat" not in st.session_state:
    st.session_state.chat = []

if "session_id" not in st.session_state:
    st.session_state.session_id = str(uuid.uuid4())


# --------------------------------------------------
# AUTHENTICATION
# --------------------------------------------------

if st.session_state.principal is None:

    st.subheader("Sign in")

    with st.form("login_form"):

        username = st.text_input("Username")

        password = st.text_input(
            "Password",
            type="password"
        )

        submit = st.form_submit_button("Sign in")

    if submit:

        if not username or not password:
            st.warning("Please enter username and password.")

        else:
            try:
                principal = authenticate(
                    username.strip(),
                    password
                )

                if principal is not None:

                    st.session_state.principal = principal
                    st.session_state.chat = []
                    st.session_state.session_id = str(uuid.uuid4())

                    st.success("Login successful!")

                    st.rerun()

                else:
                    st.error(
                        "Sign-in failed. Check your username and password."
                    )

            except Exception as e:
                st.error("Authentication error occurred.")
                st.exception(e)

    st.info(
        """
        **Demo Accounts**

        - asha / Asha-Demo-2026!
        - kabir / Kabir-Demo-2026!
        - mira / Mira-Demo-2026!
        - approver / Approve-Demo-2026!
        """
    )

    st.stop()


# --------------------------------------------------
# GET AUTHENTICATED PRINCIPAL
# --------------------------------------------------

principal = st.session_state.principal

if principal is None:

    st.session_state.principal = None
    st.error("Your session has expired. Please sign in again.")
    st.stop()


# --------------------------------------------------
# SIDEBAR
# --------------------------------------------------

with st.sidebar:

    st.success(
        f"Signed in: {principal.username} ({principal.role})"
    )

    if st.button("Sign out"):

        st.session_state.principal = None
        st.session_state.chat = []
        st.session_state.session_id = str(uuid.uuid4())

        st.rerun()

    st.divider()

    st.caption(
        "Conversation session: "
        + st.session_state.session_id[:8]
    )

    if st.button("New conversation session"):

        st.session_state.session_id = str(uuid.uuid4())
        st.session_state.chat = []

        st.rerun()

    # ----------------------------------------------
    # STUDENT LONG-TERM MEMORY
    # ----------------------------------------------

    if principal.role == "student":

        st.subheader("Long-term memory")

        try:

            memories = list_memories(principal.student_id)

            for m in memories:

                c1, c2 = st.columns([4, 1])

                c1.write(m["fact"])

                if c2.button(
                    "Delete",
                    key=f"del-{m['memory_id']}"
                ):

                    delete_memory(
                        principal.student_id,
                        m["memory_id"]
                    )

                    st.rerun()

        except Exception as e:
            st.error(f"Memory loading failed: {e}")

        with st.expander(
            "Save a stable preference or study fact"
        ):

            fact = st.text_input("Fact")

            if st.button("Save memory") and fact:

                try:

                    safe, _ = redact_sensitive(fact)

                    result = save_memory(
                        principal.student_id,
                        safe
                    )

                    st.info(result["reason"])
                    st.rerun()

                except Exception as e:
                    st.error(f"Memory saving failed: {e}")


# --------------------------------------------------
# APPROVER DASHBOARD
# --------------------------------------------------

if principal.role == "approver":

    st.subheader("Pending sensitive changes")

    try:

        with authenticated_as(principal):
            actions = pending_actions()

        if not actions:

            st.info("No pending actions.")

        for action in actions:

            st.write(
                f"Action {action['action_id']} · "
                f"{action['requester_id']} proposes contact email "
                f"{action['proposed_value']}"
            )

            col1, col2 = st.columns(2)

            if col1.button(
                "Approve",
                key=f"approve-{action['action_id']}"
            ):

                with authenticated_as(principal):

                    result = decide_action(
                        action["action_id"],
                        True
                    )

                st.success(result["message"])
                st.rerun()

            if col2.button(
                "Reject",
                key=f"reject-{action['action_id']}"
            ):

                with authenticated_as(principal):

                    result = decide_action(
                        action["action_id"],
                        False
                    )

                st.success(result["message"])
                st.rerun()

    except Exception as e:

        st.error("Approver dashboard error.")
        st.exception(e)


# --------------------------------------------------
# STUDENT SENSITIVE ACTION REQUEST
# --------------------------------------------------

else:

    with st.expander(
        "Sensitive action: request contact email change"
    ):

        new_email = st.text_input(
            "New contact email"
        )

        if st.button("Submit for approver review"):

            try:

                with authenticated_as(principal):

                    result = request_email_change(
                        principal.student_id,
                        new_email,
                        correlation_id=st.session_state.session_id
                    )

                st.info(
                    f"Pending approval · Action ID: "
                    f"{result['action_id']}"
                )

            except (ValueError, PermissionError):

                st.error(
                    "This request could not be submitted. "
                    "Check the email and try again."
                )

            except Exception as e:

                st.error("Request submission failed.")
                st.exception(e)


# --------------------------------------------------
# STUDENT SUPPORT CHAT
# --------------------------------------------------

st.subheader("Student support chat")

# Display existing conversation

for item in st.session_state.chat:

    with st.chat_message(item["role"]):

        st.markdown(item["content"])


# Only students can access chat

question = None

if principal.role == "student":

    question = st.chat_input(
        "Ask about fees, scholarships, courses, policy, or support"
    )


# --------------------------------------------------
# AGENT EXECUTION
# --------------------------------------------------

if question:

    safe_question, secret_detected = redact_sensitive(question)

    st.session_state.chat.append(
        {
            "role": "user",
            "content": safe_question
        }
    )

    with st.chat_message("user"):
        st.markdown(safe_question)

    with st.chat_message("assistant"):

        try:

            # MEMORY CLASSIFICATION

            allowed, _ = classify_memory(safe_question)

            if allowed:

                save_memory(
                    principal.student_id,
                    safe_question
                )

            # LOAD CHAT MODEL

            model = get_chat_model()

            # INITIALIZE POLICY RETRIEVER

            retriever = PolicyRetriever(
                os.getenv(
                    "STUDENT_AGENT_POLICY",
                    "rag/sample_handbook.md"
                )
            )

            # BUILD LANGGRAPH AGENT

            graph = build_graph(
                model,
                retriever
            )

            # EXECUTE AGENT

            result = run_agent(
                graph,
                safe_question,
                principal.student_id,
                st.session_state.session_id,
                principal
            )

            # HANDLE SENSITIVE INFORMATION

            answer = result["answer"]

            if (
                secret_detected
                and "excluded from saved history" not in answer
            ):

                answer += (
                    "\n\nFor your safety, sensitive credentials "
                    "were excluded from saved history and memory."
                )

            # DISPLAY ANSWER

            st.markdown(answer)

            st.session_state.chat.append(
                {
                    "role": "assistant",
                    "content": answer
                }
            )

            # SAVE TRACE

            write_trace(
                result["trace"],
                safe_question,
                answer
            )

            # DISPLAY TRACE AND POLICY EVIDENCE

            with st.expander(
                "Run trace and policy evidence"
            ):

                st.json(result["trace"])

                for item in result["policy"]:

                    st.markdown(
                        f"**{item['chunk_id']}** · "
                        f"{item['source']}\n\n"
                        f"{item['text']}"
                    )

        except Exception as e:

            st.error(
                f"Agent Error: {type(e).__name__}: {e}"
            )

            # Detailed traceback for debugging

            st.exception(e)


# --------------------------------------------------
# SECURITY AUDIT
# --------------------------------------------------

with st.expander("Security audit (evaluator)"):

    try:

        st.json(list_audit(100))

    except Exception as e:

        st.error(f"Audit loading failed: {e}")
        st.exception(e)
