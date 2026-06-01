"""Analyst sidebar chat widget — call render() from every page."""
import uuid
from datetime import datetime, timezone

import streamlit as st

from swing_lab.config import ANALYST_SNAPSHOT_TTL_SECONDS


def _init_state() -> None:
    defaults = {
        "analyst_history": [],
        "analyst_last_telemetry": {},
        "analyst_snapshot": None,
        "analyst_snapshot_built_at": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def _get_or_build_snapshot(visible_df=None) -> dict:
    from swing_lab.dashboard.snapshot import build_snapshot
    now = datetime.now(timezone.utc)
    built_at = st.session_state.get("analyst_snapshot_built_at")
    if (
        built_at is not None
        and (now - built_at).total_seconds() < ANALYST_SNAPSHOT_TTL_SECONDS
        and st.session_state.get("analyst_snapshot") is not None
    ):
        return st.session_state["analyst_snapshot"]
    snapshot = build_snapshot(
        current_page=st.session_state.get("current_page", "home"),
        visible_df=visible_df,
    )
    st.session_state["analyst_snapshot"] = snapshot
    st.session_state["analyst_snapshot_built_at"] = now
    return snapshot


def _text_from_content(content) -> str:
    """Extract display text from a message content value."""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                parts.append(block["text"])
            elif hasattr(block, "text"):
                parts.append(block.text)
        return "\n\n".join(parts)
    return str(content)


def _render_history() -> None:
    history = st.session_state.get("analyst_history", [])
    if not history:
        st.caption("Ask a question below to start chatting.")
        return

    parts = []
    for msg in history:
        role = msg.get("role")
        content = msg.get("content", "")

        # Skip tool-result messages (user messages with list content containing tool_result)
        if role == "user" and isinstance(content, list):
            if content and isinstance(content[0], dict) and content[0].get("type") == "tool_result":
                continue

        text = _text_from_content(content)
        if not text.strip():
            continue

        if role == "user":
            parts.append(
                f'<div class="sl-chat-bubble sl-chat-bubble-user">'
                f'<div class="sl-chat-msg">{text}</div>'
                f'</div>'
                f'<div class="sl-chat-meta">You</div>'
            )
        elif role == "assistant":
            parts.append(
                f'<div class="sl-chat-bubble">'
                f'<div class="sl-chat-msg">{text}</div>'
                f'</div>'
                f'<div class="sl-chat-meta">Analyst</div>'
            )

    if parts:
        st.markdown("\n".join(parts), unsafe_allow_html=True)


def _run_turn(user_msg: str, visible_df=None) -> None:
    """Call analyst.run_turn and update session state."""
    from swing_lab.analyst import run_turn
    snapshot = _get_or_build_snapshot(visible_df)
    try:
        _text, updated_history, telemetry = run_turn(
            st.session_state["analyst_history"],
            user_msg,
            snapshot,
        )
        st.session_state["analyst_history"] = updated_history
        st.session_state["analyst_last_telemetry"] = telemetry
    except Exception as exc:
        st.error(f"Analyst error: {exc}")


def _save_chat() -> None:
    history = st.session_state.get("analyst_history", [])
    if not history:
        return
    first_user = next(
        (m["content"] for m in history
         if m.get("role") == "user" and isinstance(m.get("content"), str)),
        "Chat",
    )
    title = str(first_user)[:40] + ("…" if len(str(first_user)) > 40 else "")
    session_id = str(uuid.uuid4())
    from swing_lab.db import init_db, save_analyst_session
    conn = init_db()
    try:
        save_analyst_session(conn, session_id, title, history)
        st.toast("Chat saved!")
    finally:
        conn.close()


@st.dialog("Analyst Chat", width="large")
def _chat_dialog(visible_df=None) -> None:
    """Analyst chat rendered inside st.dialog."""
    _init_state()

    # ── Saved sessions ─────────────────────────────────────────────────────────
    from swing_lab.dashboard.lib import load_analyst_session_list, load_analyst_session_messages
    sessions = load_analyst_session_list()
    if sessions:
        session_titles = [s["title"] for s in sessions]
        session_ids = [s["session_id"] for s in sessions]
        c_sel, c_load, c_del = st.columns([3, 1, 1])
        sel_idx = c_sel.selectbox(
            "Saved",
            range(len(session_titles)),
            format_func=lambda i: session_titles[i],
            label_visibility="collapsed",
            key="analyst_session_select",
        )
        if c_load.button("Load", key="analyst_load_btn", use_container_width=True):
            msgs = load_analyst_session_messages(session_ids[sel_idx])
            st.session_state["analyst_history"] = msgs
            st.rerun()
        if c_del.button("Del", key="analyst_del_btn", use_container_width=True):
            from swing_lab.db import init_db, delete_analyst_session
            conn = init_db()
            try:
                delete_analyst_session(conn, session_ids[sel_idx])
            finally:
                conn.close()
            st.rerun()
        st.divider()

    # ── Chat history ───────────────────────────────────────────────────────────
    _render_history()

    # ── Chat input ─────────────────────────────────────────────────────────────
    user_input = st.chat_input("Ask the analyst…", key="analyst_chat_input")
    if user_input:
        with st.spinner("Thinking…"):
            _run_turn(user_input, visible_df)
        st.rerun()

    st.divider()

    # ── Deep dive ──────────────────────────────────────────────────────────────
    snapshot = st.session_state.get("analyst_snapshot") or {}
    scan_info = snapshot.get("scan") or {}
    symbols = [p["symbol"] for p in scan_info.get("top_10", []) if p.get("symbol")]

    if symbols:
        c_sym, c_go = st.columns([3, 1])
        dd_sym = c_sym.selectbox(
            "Deep dive",
            symbols,
            label_visibility="collapsed",
            key="analyst_dd_sym",
        )
        if c_go.button("Go", key="analyst_dd_btn", use_container_width=True):
            with st.spinner(f"Deep diving {dd_sym}…"):
                _run_turn(f"Please do a deep dive on {dd_sym}.", visible_df)
            st.rerun()

    # ── Save / Clear ───────────────────────────────────────────────────────────
    c_save, c_clear = st.columns(2)
    if c_save.button("Save chat", key="analyst_save_btn", use_container_width=True):
        _save_chat()
    if c_clear.button("Clear", key="analyst_clear_btn", use_container_width=True):
        st.session_state["analyst_history"] = []
        st.session_state["analyst_last_telemetry"] = {}
        st.rerun()

    # ── Telemetry caption ──────────────────────────────────────────────────────
    telemetry = st.session_state.get("analyst_last_telemetry") or {}
    if telemetry:
        cache_str = "cache hit" if telemetry.get("cache_hit") else "cache miss"
        tokens = telemetry.get("tokens_saved", 0)
        tools = telemetry.get("tool_calls") or []
        parts = [cache_str]
        if tokens > 0:
            parts.append(f"{tokens:,} tokens saved")
        if tools:
            parts.append(f"tools: {', '.join(tools)}")
        st.caption(" · ".join(parts))


def render_floating_button(visible_df=None) -> None:
    """Inject the floating chat button (bottom-right). Call from every page."""
    _init_state()
    if st.button("💬", key="analyst_float_btn", help="Open Analyst Chat"):
        _chat_dialog(visible_df)


def render(visible_df=None) -> None:
    """Kept for backward compat — redirects to floating button."""
    render_floating_button(visible_df)
