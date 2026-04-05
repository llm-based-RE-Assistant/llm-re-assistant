"""
app.py
=======
RE Assistant — Iteration 2 | University of Hildesheim
Minimal Streamlit UI for evaluation sessions.

Purpose
-------
Replaces the CLI for team evaluation runs (Scenarios S1–S5).
No Python/venv knowledge required from evaluators — just:
    streamlit run src/app.py

Features (exactly three — no scope creep)
------------------------------------------
1. Chat interface  — conversation loop with the RE Assistant
2. Coverage panel  — live IEEE-830 coverage tracker, always visible
3. Generate SRS    — one-click download of the .md SRS document

Provider support
----------------
Configure via the sidebar:
  - Ollama (local, no API key needed — recommended for evaluation)
  - OpenAI GPT-4o (requires OPENAI_API_KEY env var)
  - Stub  (scripted responses, for UI testing without an LLM)

Run
---
    pip install streamlit
    streamlit run app.py
    # or with a specific model:
    streamlit run app.py -- --provider ollama --model gemma3:latest
"""

from __future__ import annotations
import sys
from pathlib import Path
import streamlit as st

# ---------------------------------------------------------------------------
# Path setup — make src/ importable regardless of working directory
# ---------------------------------------------------------------------------
_SRC = Path(__file__).parent
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from src.components.conversation_manager import (
    ConversationManager,
    SessionLogger,
    create_provider,
)
from src.components.conversation_state import ConversationState
from src.components.prompt_architect import IEEE830_CATEGORIES, MANDATORY_NFR_CATEGORIES
from src.components.srs_template import SRSTemplate

# ---------------------------------------------------------------------------
# Page config — must be the first Streamlit call
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="RE Assistant",
    page_icon="📋",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_OUTPUT_DIR = _SRC / "output"
_LOG_DIR    = _SRC / "logs"

_OPENING_MESSAGE = (
    "Hello! I'm your Requirements Engineering assistant. "
    "I'll help you create a complete, structured Software Requirements Specification (SRS) "
    "for your software project.\n\n"
    "To get started, please describe the software system you want to build — "
    "its main purpose, who will use it, and any key features you have in mind."
)

_PROVIDER_HELP = {
    "ollama": "Local Ollama model — no API key needed. Run `ollama serve` first.",
    "openai": "OpenAI GPT-4o — requires OPENAI_API_KEY environment variable.",
    "stub":   "Scripted responses — for testing the UI without a real LLM.",
}

# ---------------------------------------------------------------------------
# Minimal CSS — clean academic tool aesthetic, not a consumer app
# ---------------------------------------------------------------------------
st.markdown("""
<style>
/* ── Base ──────────────────────────────────────────── */
@import url('https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;500&family=IBM+Plex+Sans:wght@300;400;500;600&display=swap');

:root {
    --bg-dark: #0e0e17;
    --bg-panel: #151528;
    --bg-soft: #f7f7fa;

    --text-primary: #e6e8ef;
    --text-secondary: #9aa0b3;

    --accent-blue: #5b8cff;
    --accent-green: #22c55e;

    --border-subtle: #26263d;
    --border-strong: #2f3150;
}

/* Global */
html, body, [class*="css"] {
    font-family: 'IBM Plex Sans', sans-serif;
    background: var(--bg-dark);
    color: var(--text-primary);
}

/* ── Chat messages ──────────────────────────────────── */
.msg-user {
    background: linear-gradient(145deg, #1b1b32, #141427);
    color: var(--text-primary);
    border-radius: 10px 10px 4px 10px;
    padding: 14px 18px;
    margin: 8px 0 8px 52px;
    font-size: 0.94rem;
    line-height: 1.65;
    border: 1px solid var(--border-subtle);
    border-left: 3px solid var(--accent-blue);
}

.msg-assistant {
    background: var(--bg-soft);
    color: #1a1a2e;
    border-radius: 4px 10px 10px 10px;
    padding: 14px 18px;
    margin: 8px 52px 8px 0;
    font-size: 0.94rem;
    line-height: 1.65;
    border: 1px solid #e4e6ef;
    border-left: 3px solid var(--accent-green);
    white-space: pre-wrap;
}

/* Labels */
.msg-label {
    font-size: 0.68rem;
    font-weight: 600;
    letter-spacing: 0.1em;
    text-transform: uppercase;
    color: var(--text-secondary);
    margin-bottom: 4px;
}

/* ── Coverage badges ─────────────────────────────────── */
.cov-badge {
    display: inline-block;
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.70rem;
    padding: 3px 8px;
    border-radius: 6px;
    margin: 3px 0;
    width: 100%;
    box-sizing: border-box;
    border: 1px solid transparent;
}

.cov-covered {
    background: #d1fae5;
    color: #065f46;
    border-color: #a7f3d0;
}

.cov-missing {
    background: #2a1414;
    color: #fca5a5;
    border-color: #3f1f1f;
}

.cov-mandatory {
    font-weight: 600;
}

/* ── Progress bar ────────────────────────────────────── */
.prog-bar-outer {
    background: #1c1c30;
    border-radius: 999px;
    height: 6px;
    margin: 6px 0 14px 0;
    overflow: hidden;
    border: 1px solid var(--border-subtle);
}

.prog-bar-inner {
    height: 100%;
    border-radius: 999px;
    background: linear-gradient(90deg, var(--accent-blue), var(--accent-green));
    transition: width 0.35s ease;
}

/* ── Sidebar ─────────────────────────────────────────── */
section[data-testid="stSidebar"] {
    background: var(--bg-panel);
    border-right: 1px solid var(--border-subtle);
}

section[data-testid="stSidebar"] * {
    color: var(--text-primary) !important;
}

section[data-testid="stSidebar"] .stSelectbox label,
section[data-testid="stSidebar"] .stTextInput label {
    color: var(--text-secondary) !important;
    font-size: 0.78rem;
}

/* ── Metric boxes ────────────────────────────────────── */
.metric-box {
    background: linear-gradient(145deg, #1a1a2e, #141427);
    border: 1px solid var(--border-strong);
    border-radius: 10px;
    padding: 12px 14px;
    margin-bottom: 10px;
    text-align: center;
    transition: transform 0.15s ease, border 0.15s ease;
}

.metric-box:hover {
    transform: translateY(-1px);
    border-color: var(--accent-blue);
}

.metric-val {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 1.5rem;
    font-weight: 500;
    color: var(--accent-blue);
    line-height: 1.1;
}

.metric-lbl {
    font-size: 0.70rem;
    color: var(--text-secondary);
    text-transform: uppercase;
    letter-spacing: 0.08em;
}

/* ── Title ───────────────────────────────────────────── */
.app-title {
    font-family: 'IBM Plex Mono', monospace;
    font-size: 0.80rem;
    color: var(--accent-blue);
    letter-spacing: 0.14em;
    text-transform: uppercase;
}

.app-subtitle {
    font-size: 0.72rem;
    color: var(--text-secondary);
    margin-top: 3px;
}

/* ── Thinking indicator ──────────────────────────────── */
.thinking {
    color: var(--text-secondary);
    font-size: 0.82rem;
    font-style: italic;
    padding: 10px 0;
}

/* ── Scrollbar (subtle upgrade) ─────────────────────── */
::-webkit-scrollbar {
    width: 6px;
}
::-webkit-scrollbar-thumb {
    background: #2a2a44;
    border-radius: 10px;
}
::-webkit-scrollbar-thumb:hover {
    background: #3a3a5a;
}

/* ── Hide Streamlit chrome ───────────────────────────── */
#MainMenu, footer, header { visibility: hidden; }
.block-container { padding-top: 1.2rem; }

</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Session state initialisation
# ---------------------------------------------------------------------------
 
def _init_session() -> None:
    """Initialise all st.session_state keys on first load."""
    if "initialised" not in st.session_state:
        st.session_state.initialised      = False
        st.session_state.messages         = []   # list of {"role", "content"}
        st.session_state.manager          = None
        st.session_state.conv_state       = None
        st.session_state.logger           = None
        st.session_state.template         = None
        st.session_state.session_id       = None
        st.session_state.srs_ready        = False
        st.session_state.srs_content      = None  # str of generated markdown
        st.session_state.srs_filename     = None
        st.session_state.provider_name    = "openai"
        st.session_state.model_name       = "gpt-4o"
        st.session_state.error            = None
        st.session_state.thinking         = False
 
 
def _start_new_session(provider_name: str, model_name: str) -> None:
    """Create a fresh ConversationManager and start a session."""
    try:
        provider = create_provider(provider_name, model=model_name)
    except Exception as e:
        st.session_state.error = str(e)
        return
 
    manager = ConversationManager(
        provider=provider,
        log_dir=_LOG_DIR,
        output_dir=_OUTPUT_DIR,
    )
    session_id, conv_state, logger, template = manager.start_session()
 
    st.session_state.manager     = manager
    st.session_state.conv_state  = conv_state
    st.session_state.logger      = logger
    st.session_state.template    = template
    st.session_state.session_id  = session_id
    st.session_state.initialised = True
    st.session_state.srs_ready   = False
    st.session_state.srs_content = None
    st.session_state.messages    = [
        {"role": "assistant", "content": _OPENING_MESSAGE}
    ]
    st.session_state.error       = None
 
 
# ---------------------------------------------------------------------------
# Coverage sidebar rendering
# ---------------------------------------------------------------------------
 
def _render_coverage_sidebar() -> None:
    state: ConversationState = st.session_state.conv_state
    template: SRSTemplate    = st.session_state.template
 
    if state is None:
        st.sidebar.markdown("*Start a session to see coverage.*")
        return
 
    report = state.get_coverage_report()
    pct    = report["coverage_percentage"]
 
    # Session header
    st.sidebar.markdown(f"""
<div class="app-title">RE Assistant</div>
<div class="app-subtitle">Session: <code>{st.session_state.session_id}</code></div>
""", unsafe_allow_html=True)
    st.sidebar.markdown("---")
 
    # Metrics row
    col1, col2, col3 = st.sidebar.columns(3)
    with col1:
        st.markdown(f"""
<div class="metric-box">
  <div class="metric-val">{report['turn_count']}</div>
  <div class="metric-lbl">Turns</div>
</div>""", unsafe_allow_html=True)
    with col2:
        st.markdown(f"""
<div class="metric-box">
  <div class="metric-val">{report['functional_count']}</div>
  <div class="metric-lbl">FRs</div>
</div>""", unsafe_allow_html=True)
    with col3:
        st.markdown(f"""
<div class="metric-box">
  <div class="metric-val">{report['nonfunctional_count']}</div>
  <div class="metric-lbl">NFRs</div>
</div>""", unsafe_allow_html=True)
 
    # Coverage progress bar
    st.sidebar.markdown(f"""
<div style="font-size:0.75rem;color:#888;text-transform:uppercase;letter-spacing:0.08em;margin-bottom:4px;">
  IEEE-830 Coverage — {pct:.0f}%
</div>
<div class="prog-bar-outer">
  <div class="prog-bar-inner" style="width:{pct}%"></div>
</div>
""", unsafe_allow_html=True)
 
    # Per-category badges
    covered = state.covered_categories
    badges_html = ""
    for cat_key, cat_label in IEEE830_CATEGORIES.items():
        is_covered   = cat_key in covered
        is_mandatory = cat_key in MANDATORY_NFR_CATEGORIES
        tick    = "✓" if is_covered else "✗"
        cls     = "cov-covered" if is_covered else "cov-missing"
        mand    = " cov-mandatory" if is_mandatory else ""
        mand_dot = " ●" if is_mandatory else ""
        badges_html += (
            f'<div class="cov-badge {cls}{mand}">'
            f'{tick} {cat_label}{mand_dot}'
            f'</div>\n'
        )
    st.sidebar.markdown(badges_html, unsafe_allow_html=True)
    st.sidebar.markdown(
        '<div style="font-size:0.68rem;color:#2b2b2b;margin-top:4px;">'
        '● = mandatory NFR</div>',
        unsafe_allow_html=True,
    )
 
    # SMART quality if any reqs exist
    if template and template.total_requirements > 0:
        st.sidebar.markdown("---")
        st.sidebar.markdown(
            '<div style="font-size:0.75rem;color:#888;text-transform:uppercase;'
            'letter-spacing:0.08em;margin-bottom:6px;">Quality</div>',
            unsafe_allow_html=True,
        )
        avg = template.avg_smart_score
        hi  = template.high_quality_count
        lo  = template.needs_improvement_count
        tot = template.total_requirements
        st.sidebar.markdown(f"""
<div style="font-size:0.82rem;line-height:1.8;">
  Avg SMART score: <b>{avg}/5</b><br>
  ✅ High quality: <b>{hi}</b> / {tot}<br>
  ❌ Needs work: <b>{lo}</b> / {tot}
</div>
""", unsafe_allow_html=True)
 
    # Mandatory NFR status
    missing_mandatory = report.get("missing_mandatory_nfrs", [])
    if missing_mandatory:
        st.sidebar.markdown("---")
        st.sidebar.warning(
            f"⚠️ **{len(missing_mandatory)} mandatory NFR(s) not yet covered:**\n"
            + "\n".join(f"- {c}" for c in missing_mandatory)
        )
 
 
# ---------------------------------------------------------------------------
# Settings sidebar (provider / model / new session)
# ---------------------------------------------------------------------------
 
def _render_settings_sidebar() -> None:
    st.sidebar.markdown("---")
    st.sidebar.markdown(
        '<div style="font-size:0.75rem;color:#888;text-transform:uppercase;'
        'letter-spacing:0.08em;margin-bottom:8px;">Settings</div>',
        unsafe_allow_html=True,
    )
 
    provider = st.sidebar.selectbox(
        "LLM Provider",
        options=["ollama", "openai", "stub"],
        index=["ollama", "openai", "stub"].index(
            st.session_state.get("provider_name", "openai")
        ),
        help=_PROVIDER_HELP.get(st.session_state.get("provider_name", "openai"), ""),
    )
    st.session_state.provider_name = provider
 
    model_defaults = {
        "ollama": "llama3.2",
        "openai": "gpt-4o",
        "stub":   "stub-v1",
    }
    model = st.sidebar.text_input(
        "Model",
        value=st.session_state.get("model_name", model_defaults.get(provider, "gpt-4o")),
    )
    st.session_state.model_name = model
 
    if st.sidebar.button("🔄 New Session", use_container_width=True):
        _start_new_session(provider, model)
        st.rerun()
 
 
# ---------------------------------------------------------------------------
# Chat rendering
# ---------------------------------------------------------------------------
 
def _render_chat() -> None:
    messages = st.session_state.messages
    for msg in messages:
        role    = msg["role"]
        content = msg["content"]
        if role == "user":
            st.markdown(
                f'<div class="msg-label" style="text-align:right;">You</div>'
                f'<div class="msg-user">{content}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="msg-label">RE Assistant</div>'
                f'<div class="msg-assistant">{content}</div>',
                unsafe_allow_html=True,
            )
 
    if st.session_state.thinking:
        st.markdown('<div class="thinking">▌ RE Assistant is thinking…</div>',
                    unsafe_allow_html=True)
 
 
# ---------------------------------------------------------------------------
# SRS generation and download
# ---------------------------------------------------------------------------
 
def _generate_srs() -> None:
    """Generate the SRS document via finalize_session (includes LLM extraction)."""
    manager: ConversationManager = st.session_state.manager
    state: ConversationState     = st.session_state.conv_state
    logger: SessionLogger        = st.session_state.logger
 
    if state is None or manager is None:
        return
 
    try:
        srs_path = manager.finalize_session(state, logger)
    except Exception as e:
        st.session_state.error = f"SRS generation failed: {e}"
        return
 
    st.session_state.srs_ready    = True
    st.session_state.srs_content  = srs_path.read_text(encoding="utf-8")
    st.session_state.srs_filename = srs_path.name
 
 
# ---------------------------------------------------------------------------
# Main layout
# ---------------------------------------------------------------------------
 
def main() -> None:
    _init_session()
 
    # ── Sidebar ─────────────────────────────────────────────────────────────
    with st.sidebar:
        if not st.session_state.initialised:
            # First load — show header + settings only
            st.markdown("""
<div class="app-title">RE Assistant</div>
<div class="app-subtitle">University of Hildesheim · Iteration 2</div>
""", unsafe_allow_html=True)
            st.markdown("---")
        else:
            _render_coverage_sidebar()
 
        _render_settings_sidebar()
 
    # ── Main area ────────────────────────────────────────────────────────────
    if not st.session_state.initialised:
        # ── Landing / start screen ──
        st.markdown("""
<div style="max-width:520px;margin:80px auto;text-align:center;">
  <div style="font-family:'IBM Plex Mono',monospace;font-size:2rem;
              font-weight:500;color:#1a1a2e;letter-spacing:-0.02em;margin-bottom:8px;">
    RE Assistant
  </div>
  <div style="color:#666;font-size:1rem;margin-bottom:32px;">
    IEEE-830 Requirements Elicitation · Iteration 2 Prototype<br>
    University of Hildesheim · DSR Project
  </div>
</div>
""", unsafe_allow_html=True)
 
        col_l, col_c, col_r = st.columns([1, 2, 1])
        with col_c:
            provider = st.selectbox(
                "LLM Provider",
                ["ollama", "openai", "stub"],
                help="Choose the LLM backend for this session.",
            )
            model_default = {"ollama": "llama3.2", "openai": "gpt-4o", "stub": "stub-v1"}
            model = st.text_input("Model", value=model_default.get(provider, "llama3.2"))
 
            if provider == "ollama":
                st.caption("💡 Make sure `ollama serve` is running and the model is pulled.")
            elif provider == "openai":
                st.caption("💡 Set the `OPENAI_API_KEY` environment variable before starting.")
 
            if st.button("▶ Start Session", use_container_width=True, type="primary"):
                st.session_state.provider_name = provider
                st.session_state.model_name    = model
                _start_new_session(provider, model)
                if st.session_state.error:
                    st.error(f"Could not start session: {st.session_state.error}")
                else:
                    st.rerun()
        return
 
    # ── Active session ──────────────────────────────────────────────────────
 
    # Show any error from the last turn
    if st.session_state.error:
        st.error(st.session_state.error)
        st.session_state.error = None
 
    # Chat history
    _render_chat()
 
    # ── SRS download / generate buttons ─────────────────────────────────────
    st.markdown("<br>", unsafe_allow_html=True)
 
    if st.session_state.srs_ready and st.session_state.srs_content:
        st.success("✅ SRS generated successfully.")
        st.download_button(
            label="⬇ Download SRS (.md)",
            data=st.session_state.srs_content,
            file_name=st.session_state.srs_filename,
            mime="text/markdown",
            use_container_width=True,
        )
        col_a, col_b = st.columns(2)
        with col_a:
            if st.button("📋 View SRS in chat", use_container_width=True):
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": f"```markdown\n{st.session_state.srs_content[:3000]}\n```\n"
                               f"*(showing first 3000 chars — download for full document)*",
                })
                st.rerun()
        with col_b:
            if st.button("🔄 Start new session", use_container_width=True):
                _start_new_session(
                    st.session_state.provider_name,
                    st.session_state.model_name,
                )
                st.rerun()
 
    elif not st.session_state.srs_ready:
        col_input, col_btn = st.columns([5, 1])
        with col_input:
            user_input = st.chat_input(
                "Describe your system, answer questions, or type 'generate srs' to finish…"
            )
        # Explicit generate-SRS button always visible
        with col_btn:
            generate_clicked = st.button(
                "📄 Generate SRS",
                use_container_width=True,
                help="End the session and generate the SRS document.",
            )
 
        # ── Handle user input ────────────────────────────────────────────────
        if user_input or generate_clicked:
            msg_text = user_input if user_input else "generate srs"
 
            # Add user message to display
            st.session_state.messages.append({"role": "user", "content": msg_text})
            st.session_state.thinking = True
            st.rerun()
 
    # Processing happens on rerun when thinking=True
    if st.session_state.thinking:
        st.session_state.thinking = False
        msg_text = st.session_state.messages[-1]["content"]
 
        manager: ConversationManager = st.session_state.manager
        state: ConversationState     = st.session_state.conv_state
        logger: SessionLogger        = st.session_state.logger
 
        # Check for explicit SRS trigger
        if manager._should_generate_srs(msg_text, state) or msg_text.strip().lower() in (
            "generate srs", "generate the srs"
        ):
            _generate_srs()
            # Add assistant confirmation
            report = state.get_coverage_report()
            missing = report.get("missing_mandatory_nfrs", [])
            warn = ""
            if missing:
                warn = (
                    f"\n\n⚠️ **Note:** The following mandatory NFR categories were not fully "
                    f"elicited: {', '.join(missing)}. The SRS has been generated with "
                    f"'NOT ELICITED' placeholders for these sections."
                )
            st.session_state.messages.append({
                "role": "assistant",
                "content": (
                    f"The SRS document has been generated for **{state.project_name}**. "
                    f"It covers {report['coverage_percentage']:.0f}% of IEEE-830 categories "
                    f"and contains {report['total_requirements']} structured requirements "
                    f"({report['functional_count']} FR, {report['nonfunctional_count']} NFR).{warn}"
                ),
            })
        else:
            # Normal conversation turn
            try:
                response = manager.send_turn(msg_text, state, logger)
                st.session_state.messages.append({"role": "assistant", "content": response})
            except RuntimeError as e:
                st.session_state.error = str(e)
 
        st.rerun()
 
 
# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
 
if __name__ == "__main__":
    main()