import os
import json
from base64 import b64encode
from typing import Any, Dict, List

import requests
import streamlit as st

API_BASE_DEFAULT = os.getenv("GCOP_API_BASE", "http://127.0.0.1:8000")
UI_PASSWORD = os.getenv("DEMO_ACCESS_PASSWORD", "").strip()
PASSWORD_HELP = (
    "Use the same shared DEMO_ACCESS_PASSWORD as the API. "
    "If the password rotates, update your env or sidebar value and reload."
)

st.set_page_config(page_title="CommerceOps Copilot — Demo UI", layout="wide")


def _compose_demo_access_headers(password: str | None) -> Dict[str, str]:
    if not password:
        return {}
    token = b64encode(f"demo:{password}".encode("utf-8")).decode("ascii")
    return {
        "Authorization": f"Basic {token}",
        "X-Demo-Password": password,
    }


def _render_access_gate() -> None:
    st.title("Governed Commerce Operations Copilot — Demo UI")
    st.info("This demo UI is password-protected.")
    st.caption(PASSWORD_HELP)
    password = st.text_input("Demo access password", type="password")
    if st.button("Unlock Demo"):
        if password == UI_PASSWORD:
            st.session_state["demo_access_password"] = password
            st.rerun()
        st.error("That password did not match the current shared demo password.")
    st.stop()


if UI_PASSWORD and st.session_state.get("demo_access_password") != UI_PASSWORD:
    _render_access_gate()

# Sidebar configuration
st.sidebar.header("Settings")
api_base = st.sidebar.text_input("API base URL", value=API_BASE_DEFAULT)
demo_access_password = st.sidebar.text_input(
    "Demo access password",
    value=st.session_state.get("demo_access_password", ""),
    type="password",
    help=PASSWORD_HELP,
)
if demo_access_password:
    st.session_state["demo_access_password"] = demo_access_password
role = st.sidebar.selectbox(
    "Demo role",
    options=["support_analyst", "engineering_support", "ops_manager", "admin"],
    index=0,
)
user_id = st.sidebar.text_input("User ID", value="demo-support-001")
st.sidebar.caption("Headers are sent as X-User-Id / X-User-Role when provided.")

st.title("Governed Commerce Operations Copilot — Demo UI")
st.caption("Recommended deployment shape: host the API, keep Streamlit local-only for reviewer demos.")

# Helper functions

def _post(path: str, payload: Dict[str, Any], headers: Dict[str, str] | None = None) -> requests.Response:
    url = f"{api_base.rstrip('/')}{path}"
    return requests.post(url, json=payload, headers=headers or {}, timeout=30)


def _get(path: str, headers: Dict[str, str] | None = None) -> requests.Response:
    url = f"{api_base.rstrip('/')}{path}"
    return requests.get(url, headers=headers or {}, timeout=30)


def _auth_headers() -> Dict[str, str]:
    return {
        "X-User-Id": user_id.strip() if user_id else "",
        "X-User-Role": role,
        **_compose_demo_access_headers(st.session_state.get("demo_access_password")),
    }


def _render_response(title: str, resp_json: Dict[str, Any]) -> None:
    st.subheader(title)
    cols = st.columns([2, 1])
    with cols[0]:
        st.write(resp_json.get("data", {}).get("answer", ""))
        links = resp_json.get("data", {}).get("links", [])
        if links:
            st.markdown("**Links**")
            for link in links:
                st.write(f"- [{link.get('rel')}]({link.get('href')}) — {link.get('description','')}")
        product = resp_json.get("data", {}).get("product")
        if product:
            st.markdown("**Product**")
            st.json(product)
        inventory = resp_json.get("data", {}).get("inventory_results", [])
        if inventory:
            st.markdown("**Inventory Results**")
            st.json(inventory)
        approval = resp_json.get("data", {}).get("approval")
        if approval:
            st.markdown("**Approval**")
            st.json(approval)
        approvals = resp_json.get("data", {}).get("approvals", [])
        if approvals:
            st.markdown("**Approvals**")
            st.json(approvals)
        incident = resp_json.get("data", {}).get("incident")
        if incident:
            st.markdown("**Incident**")
            st.json(incident)
    with cols[1]:
        citations = resp_json.get("data", {}).get("citations", [])
        if citations:
            st.markdown("**Citations**")
            for c in citations:
                st.write(f"- {c.get('title')} ({c.get('doc_key')})")
        st.markdown("**Meta**")
        st.json(resp_json.get("meta", {}))
        st.markdown("**Request**")
        st.code(json.dumps({k: resp_json.get(k) for k in ("request_id", "route_type", "status")}, indent=2))


# Tabs
query_tab, approvals_tab, traces_tab = st.tabs(["Query", "Approvals", "Traces"])

with query_tab:
    st.subheader("Unified Query")
    examples = [
        "What is the return process for damaged products?",
        "Check inventory for the Phantom X shoes.",
        "Summarize incident INC-1091 and tell me the likely customer impact.",
        "Should INC-1091 be escalated right now?",
        "Show me the approval dashboard.",
    ]
    ex_col1, ex_col2, ex_col3, ex_col4, ex_col5 = st.columns(5)
    ex_cols = [ex_col1, ex_col2, ex_col3, ex_col4, ex_col5]
    for i, (c, txt) in enumerate(zip(ex_cols, examples)):
        if c.button(f"Example {i+1}"):
            st.session_state["query_text"] = txt
    query_text = st.text_area("Message", key="query_text", value=examples[0], height=100)
    if st.button("Send Query"):
        payload = {
            "message": query_text,
            "user_id": user_id.strip() or "demo-support-001",
            "user_role": role,
            "top_k": 5,
        }
        r = _post("/api/v1/query", payload, headers=_auth_headers())
        try:
            resp_json = r.json()
        except Exception:
            st.error(f"Invalid response: {r.status_code}")
        else:
            if 200 <= r.status_code < 300:
                _render_response("Query Response", resp_json)
            else:
                details = resp_json.get("error", {}).get("details", {})
                st.error(f"{r.status_code} — {resp_json.get('error', {}).get('message')}")
                if details.get("how_to_authenticate"):
                    st.caption(details["how_to_authenticate"])
                st.json(resp_json)

with approvals_tab:
    st.subheader("Approval Workflow")
    st.markdown("Create escalation request")
    inc_code = st.text_input("Incident code", value="INC-1091")
    reason = st.text_input("Escalation reason", value="Customer impact remains elevated.")
    priority = st.selectbox("Proposed priority", options=["medium", "high", "critical"], index=2)
    draft = st.text_area("Draft summary", value="Escalate to management due to ongoing checkout failures.")
    if st.button("Create Escalation Request"):
        payload = {
            "incident_code": inc_code.strip(),
            "escalation_reason": reason.strip(),
            "proposed_priority": priority,
            "draft_summary": draft.strip(),
            "requested_by_user_id": user_id.strip() or "demo-support-001",
            "requested_by_role": role,
        }
        r = _post("/api/v1/escalations", payload, headers=_auth_headers())
        try:
            data = r.json()
        except Exception:
            st.error(f"Invalid response: {r.status_code}")
        else:
            if 200 <= r.status_code < 300:
                st.success("Escalation approval created")
                st.json(data.get("data", {}))
                if data.get("data", {}).get("approval"):
                    st.session_state["last_approval_id"] = data["data"]["approval"]["approval_id"]
            else:
                st.error(f"{r.status_code} — {data.get('error', {}).get('message')}")
                if data.get("error", {}).get("details", {}).get("how_to_authenticate"):
                    st.caption(data["error"]["details"]["how_to_authenticate"])
                st.json(data)

    st.markdown("Lookup approval status")
    approval_id = st.text_input("Approval ID", value=st.session_state.get("last_approval_id", ""))
    if st.button("Get Status") and approval_id:
        r = _get(f"/api/v1/approvals/{approval_id}", headers=_auth_headers())
        try:
            data = r.json()
        except Exception:
            st.error(f"Invalid response: {r.status_code}")
        else:
            if 200 <= r.status_code < 300:
                st.json(data.get("data", {}))
            else:
                st.error(f"{r.status_code} — {data.get('error', {}).get('message')}")
                if data.get("error", {}).get("details", {}).get("how_to_authenticate"):
                    st.caption(data["error"]["details"]["how_to_authenticate"])
                st.json(data)

    st.markdown("Submit approval decision (requires ops_manager/admin)")
    decision = st.selectbox("Decision", options=["approved", "rejected"], index=0)
    notes = st.text_input("Decision notes", value="Approved for incident coordination.")
    decider_role = st.selectbox("Decider role", options=["support_analyst", "engineering_support", "ops_manager", "admin"], index=2)
    decider_user = st.text_input("Decider user", value="demo-ops-manager-001")
    if st.button("Submit Decision") and approval_id:
        payload = {
            "decision": decision,
            "decision_notes": notes.strip() or None,
            "decider_user_id": decider_user.strip() or "demo-ops-manager-001",
            "decider_role": decider_role,
        }
        headers = {**_auth_headers(), "X-User-Role": decider_role, "X-User-Id": decider_user}
        r = _post(f"/api/v1/approvals/{approval_id}/decision", payload, headers=headers)
        try:
            data = r.json()
        except Exception:
            st.error(f"Invalid response: {r.status_code}")
        else:
            if 200 <= r.status_code < 300:
                st.success("Decision applied")
                st.json(data.get("data", {}))
            else:
                st.error(f"{r.status_code} — {data.get('error', {}).get('message')}")
                if data.get("error", {}).get("details", {}).get("how_to_authenticate"):
                    st.caption(data["error"]["details"]["how_to_authenticate"])
                st.json(data)

with traces_tab:
    st.subheader("Request Traces")
    st.write("Artifacts are written to artifacts/*.jsonl. Use the inspect script below.")
    st.code(
        "python scripts/inspect_logs.py --tail 50\npython scripts/inspect_logs.py --request-id <req_id>\npython scripts/inspect_logs.py --approval-id <apr_id>",
        language="bash",
    )
