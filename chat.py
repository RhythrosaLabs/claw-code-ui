"""
Claw Code — Chat UI

A natural-language chat interface to the Claw Code agent harness.
Supports slash commands (/status, /help, /tools, /commands, /route, etc.)
and natural-language requests that auto-route to the right commands & tools.

Run:  streamlit run chat.py
"""

from __future__ import annotations

import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from uuid import uuid4

import streamlit as st

# ---------------------------------------------------------------------------
# Importable project root
# ---------------------------------------------------------------------------
_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from src.commands import (
    PORTED_COMMANDS,
    execute_command,
    find_commands,
    get_commands,
)
from src.tools import (
    PORTED_TOOLS,
    execute_tool,
    find_tools,
    get_tools,
)
from src.permissions import ToolPermissionContext
from src.port_manifest import build_port_manifest
from src.query_engine import QueryEngineConfig, QueryEnginePort
from src.runtime import PortRuntime, RoutedMatch
from src.parity_audit import run_parity_audit
from src.setup import run_setup
from src.bootstrap_graph import build_bootstrap_graph
from src.command_graph import build_command_graph
from src.tool_pool import assemble_tool_pool
from src.context import build_port_context, render_context
from src.cost_tracker import CostTracker
from src.history import HistoryLog
from src.llm_client import LLMConfig, ALL_ANTHROPIC_MODELS, ALL_OPENAI_MODELS

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Claw Code",
    page_icon="🦀",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ---------------------------------------------------------------------------
# CSS — dark chat UI inspired by Claude Code / OpenClaw WebChat
# ---------------------------------------------------------------------------
st.markdown("""
<style>
:root {
    --bg: #0d1117; --surface: #161b22; --surface2: #1c2333;
    --border: #30363d; --text: #e6edf3; --muted: #8b949e;
    --accent: #58a6ff; --green: #3fb950; --orange: #d29922;
    --red: #f85149; --purple: #a371f7;
}
/* hide default streamlit chrome */
#MainMenu, header, footer { visibility: hidden; }
.block-container { padding: 0 !important; max-width: 100% !important; }
[data-testid="stSidebar"] { background: var(--bg); border-right: 1px solid var(--border); }

/* Status bar */
.status-bar {
    position: fixed; top: 0; left: 0; right: 0; z-index: 999;
    background: var(--surface); border-bottom: 1px solid var(--border);
    padding: 8px 20px; display: flex; align-items: center; gap: 16px;
    font-size: 13px; color: var(--muted);
}
.status-bar .logo { font-size: 16px; font-weight: 700; color: var(--text); }
.status-bar .logo span { color: var(--accent); }
.status-bar .sep { color: var(--border); }
.status-bar .pill {
    background: var(--surface2); border: 1px solid var(--border);
    border-radius: 12px; padding: 2px 10px; font-size: 11px;
}
.status-bar .pill-green { color: var(--green); border-color: #238636; }
.status-bar .pill-orange { color: var(--orange); border-color: #9e6a03; }

/* Chat area */
.chat-wrap { padding: 56px 0 80px 0; max-width: 780px; margin: 0 auto; }
.msg { padding: 12px 16px; margin: 6px 20px; border-radius: 12px; font-size: 14px; line-height: 1.6; }
.msg-user {
    background: #1f6feb22; border: 1px solid #1f6feb55; margin-left: 80px;
    border-bottom-right-radius: 4px;
}
.msg-assistant {
    background: var(--surface); border: 1px solid var(--border); margin-right: 80px;
    border-bottom-left-radius: 4px;
}
.msg-system {
    background: transparent; border: 1px dashed var(--border); text-align: center;
    color: var(--muted); font-size: 12px; margin: 4px 80px;
}
.msg .role { font-size: 11px; font-weight: 600; text-transform: uppercase; margin-bottom: 4px; }
.msg .role-user { color: var(--accent); }
.msg .role-claw { color: var(--green); }
.msg .role-sys { color: var(--muted); }
.msg pre, .msg code { font-size: 12.5px; }

/* Tool/cmd tags */
.tag { display: inline-block; font-size: 11px; padding: 1px 7px; border-radius: 10px;
       font-weight: 600; margin-right: 4px; vertical-align: middle; }
.t-cmd { background: #1f6feb22; color: var(--accent); border: 1px solid #1f6feb; }
.t-tool { background: #23863522; color: var(--green); border: 1px solid #238635; }
.t-deny { background: #f8514922; color: var(--red); border: 1px solid #f85149; }
.t-info { background: #a371f722; color: var(--purple); border: 1px solid #a371f7; }

/* Routed match cards */
.route-card {
    background: var(--surface2); border: 1px solid var(--border); border-radius: 8px;
    padding: 8px 12px; margin: 4px 0; font-size: 13px;
}
.route-card:hover { border-color: var(--accent); }

/* input override */
[data-testid="stChatInput"] textarea { font-size: 14px !important; }
</style>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Session state init
# ---------------------------------------------------------------------------
if "messages" not in st.session_state:
    st.session_state.messages = []
if "session_id" not in st.session_state:
    st.session_state.session_id = uuid4().hex[:12]
if "cost" not in st.session_state:
    st.session_state.cost = CostTracker()
if "history" not in st.session_state:
    st.session_state.history = HistoryLog()
if "engine" not in st.session_state:
    st.session_state.engine = QueryEnginePort.from_workspace()
if "runtime" not in st.session_state:
    st.session_state.runtime = PortRuntime()
if "turn_count" not in st.session_state:
    st.session_state.turn_count = 0
if "llm_provider" not in st.session_state:
    st.session_state.llm_provider = "anthropic"
if "llm_model" not in st.session_state:
    st.session_state.llm_model = ""


def _add(role: str, content: str, meta: dict | None = None):
    st.session_state.messages.append({"role": role, "content": content, "meta": meta or {}})


def _reset_session():
    # Preserve LLM config across resets
    llm_cfg = st.session_state.engine.llm_config if "engine" in st.session_state else LLMConfig()
    st.session_state.messages = []
    st.session_state.session_id = uuid4().hex[:12]
    st.session_state.cost = CostTracker()
    st.session_state.history = HistoryLog()
    engine = QueryEnginePort.from_workspace()
    engine.set_llm_config(llm_cfg)
    st.session_state.engine = engine
    st.session_state.runtime = PortRuntime()
    st.session_state.turn_count = 0


# Auto-apply LLM config from .env on first load
if not st.session_state.engine.llm_active:
    auto_config = LLMConfig(
        provider=st.session_state.llm_provider,
        model=st.session_state.llm_model,
    )
    if auto_config.is_configured:
        st.session_state.engine.set_llm_config(auto_config)


# ---------------------------------------------------------------------------
# Status bar
# ---------------------------------------------------------------------------
n_cmds = len(PORTED_COMMANDS)
n_tools = len(PORTED_TOOLS)
manifest = build_port_manifest()
n_mods = len(manifest.top_level_modules)
usage = st.session_state.engine.total_usage
llm_on = st.session_state.engine.llm_active
llm_label = "LLM ✓" if llm_on else "shim"
model_label = st.session_state.engine.llm_config.resolved_model if llm_on else "none"
st.markdown(f"""
<div class="status-bar">
    <div class="logo">🦀 <span>Claw Code</span></div>
    <span class="sep">|</span>
    <span class="pill pill-green">● session {st.session_state.session_id}</span>
    <span class="pill">{n_cmds} cmds</span>
    <span class="pill">{n_tools} tools</span>
    <span class="pill">{n_mods} modules</span>
    <span class="pill pill-orange">↓{usage.input_tokens} ↑{usage.output_tokens} tokens</span>
    <span class="pill">turn {st.session_state.turn_count}</span>
    <span class="pill {'pill-green' if llm_on else ''}">{llm_label}: {model_label}</span>
</div>
""", unsafe_allow_html=True)

# ---------------------------------------------------------------------------
# Welcome message
# ---------------------------------------------------------------------------
if not st.session_state.messages:
    _add("system", "Session started. Type a message or use a /slash command. Try `/help` for available commands.")

# ---------------------------------------------------------------------------
# Slash command handlers
# ---------------------------------------------------------------------------

SLASH_HELP = """**Available commands:**

| Command | Description |
|---|---|
| `/help` | Show this help |
| `/status` | Session status (model, tokens, cost) |
| `/new` or `/reset` | Reset the session |
| `/compact` | Compact session context |
| `/commands [query]` | List or search commands |
| `/tools [query]` | List or search tools |
| `/route <prompt>` | Route a prompt to matching commands & tools |
| `/run <prompt>` | Full bootstrap session (route → execute → persist) |
| `/exec-cmd <name> [prompt]` | Execute a specific command shim |
| `/exec-tool <name> [payload]` | Execute a specific tool shim |
| `/parity` | Run parity audit |
| `/architecture` | Show bootstrap graph & architecture |
| `/setup` | Show setup report |
| `/pool` | Show assembled tool pool |
| `/graph` | Show command graph segmentation |
| `/subsystems` | List Python modules |

Or just **type naturally** — your message will be routed to the best matching commands and tools."""


def _render_routed_matches(matches: list[RoutedMatch]) -> str:
    if not matches:
        return "*No matches found.*"
    lines = []
    for m in matches:
        tag = "t-cmd" if m.kind == "command" else "t-tool"
        lines.append(
            f'<span class="tag {tag}">{m.kind}</span> '
            f"**{m.name}** (score: {m.score}) → `{m.source_hint}`"
        )
    return "\n\n".join(lines)


def handle_slash(text: str) -> str | None:
    """Handle /slash commands. Returns response text or None if not a slash command."""
    parts = text.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd == "/help":
        return SLASH_HELP

    if cmd in ("/new", "/reset"):
        _reset_session()
        return None  # special: will be handled by caller

    if cmd == "/status":
        u = st.session_state.engine.total_usage
        return (
            f"**Session:** `{st.session_state.session_id}`\n\n"
            f"**Turns:** {st.session_state.turn_count}\n\n"
            f"**Usage:** {u.input_tokens} input / {u.output_tokens} output tokens\n\n"
            f"**Cost events:** {len(st.session_state.cost.events)} ({st.session_state.cost.total_units} units)\n\n"
            f"**Messages:** {len(st.session_state.engine.mutable_messages)}\n\n"
            f"**Transcript:** {len(st.session_state.engine.transcript_store.entries)} entries "
            f"({'flushed' if st.session_state.engine.transcript_store.flushed else 'active'})"
        )

    if cmd == "/compact":
        before = len(st.session_state.engine.mutable_messages)
        st.session_state.engine.compact_messages_if_needed()
        after = len(st.session_state.engine.mutable_messages)
        return f"Compacted session context. Messages: {before} → {after}"

    if cmd == "/commands":
        if arg:
            matches = find_commands(arg)
            if not matches:
                return f"No commands matching `{arg}`."
            lines = [f"**Commands matching `{arg}`:** ({len(matches)} results)\n"]
            for m in matches[:20]:
                lines.append(f'<span class="tag t-cmd">cmd</span> **`/{m.name}`** → `{m.source_hint}`')
            return "\n\n".join(lines)
        else:
            cmds = get_commands()
            unique = sorted(set(c.name for c in cmds))
            return f"**{len(cmds)} command entries** ({len(unique)} unique names):\n\n" + ", ".join(
                f"`/{n}`" for n in unique[:60]
            ) + ("\n\n…and more" if len(unique) > 60 else "")

    if cmd == "/tools":
        if arg:
            matches = find_tools(arg)
            if not matches:
                return f"No tools matching `{arg}`."
            lines = [f"**Tools matching `{arg}`:** ({len(matches)} results)\n"]
            for m in matches[:20]:
                lines.append(f'<span class="tag t-tool">tool</span> **`{m.name}`** → `{m.source_hint}`')
            return "\n\n".join(lines)
        else:
            tools = get_tools()
            unique = sorted(set(t.name for t in tools))
            return f"**{len(tools)} tool entries** ({len(unique)} unique names):\n\n" + ", ".join(
                f"`{n}`" for n in unique[:60]
            ) + ("\n\n…and more" if len(unique) > 60 else "")

    if cmd == "/route":
        if not arg:
            return "Usage: `/route <your prompt>`"
        matches = st.session_state.runtime.route_prompt(arg, limit=8)
        return f"**Routing:** `{arg}`\n\n" + _render_routed_matches(matches)

    if cmd == "/run":
        if not arg:
            return "Usage: `/run <your prompt>`"
        session = st.session_state.runtime.bootstrap_session(arg, limit=5)
        st.session_state.turn_count += 1
        st.session_state.cost.record("bootstrap", 1)
        st.session_state.history.add("bootstrap", arg)

        parts_out = [f"**Bootstrap session for:** `{arg}`\n"]

        # Routed matches
        parts_out.append("**Routed matches:**\n")
        parts_out.append(_render_routed_matches(session.routed_matches))

        # Command executions
        if session.command_execution_messages and session.command_execution_messages != ("none",):
            parts_out.append("\n**Command executions:**")
            for msg in session.command_execution_messages:
                parts_out.append(f"```\n{msg}\n```")

        # Tool executions
        if session.tool_execution_messages and session.tool_execution_messages != ("none",):
            parts_out.append("\n**Tool executions:**")
            for msg in session.tool_execution_messages:
                parts_out.append(f"```\n{msg}\n```")

        # Turn result
        parts_out.append(f"\n**Turn result** (stop: `{session.turn_result.stop_reason}`):")
        parts_out.append(f"```\n{session.turn_result.output}\n```")

        # Usage
        u = session.turn_result.usage
        parts_out.append(f"\n*Usage: {u.input_tokens} in / {u.output_tokens} out — Session persisted to `{session.persisted_session_path}`*")

        return "\n".join(parts_out)

    if cmd == "/exec-cmd":
        if not arg:
            return "Usage: `/exec-cmd <name> [prompt]`"
        cmd_parts = arg.split(maxsplit=1)
        name = cmd_parts[0]
        prompt = cmd_parts[1] if len(cmd_parts) > 1 else ""
        result = execute_command(name, prompt)
        st.session_state.cost.record("exec-cmd", 1)
        status = "✅" if result.handled else "❌"
        return f"{status} **Command `{name}`:**\n```\n{result.message}\n```"

    if cmd == "/exec-tool":
        if not arg:
            return "Usage: `/exec-tool <name> [payload]`"
        tool_parts = arg.split(maxsplit=1)
        name = tool_parts[0]
        payload = tool_parts[1] if len(tool_parts) > 1 else "{}"
        result = execute_tool(name, payload)
        st.session_state.cost.record("exec-tool", 1)
        status = "✅" if result.handled else "❌"
        return f"{status} **Tool `{name}`:**\n```\n{result.message}\n```"

    if cmd == "/parity":
        audit = run_parity_audit()
        return f"**Parity Audit:**\n```\n{audit.to_markdown()}\n```"

    if cmd == "/architecture":
        graph = build_bootstrap_graph()
        return f"**Bootstrap / Runtime Graph:**\n```\n{graph.as_markdown()}\n```"

    if cmd == "/setup":
        report = run_setup()
        return f"**Setup Report:**\n```\n{report.as_markdown()}\n```"

    if cmd == "/pool":
        pool = assemble_tool_pool()
        return f"**Tool Pool:**\n```\n{pool.as_markdown()}\n```"

    if cmd == "/graph":
        graph = build_command_graph()
        return f"**Command Graph:**\n```\n{graph.as_markdown()}\n```"

    if cmd == "/subsystems":
        mods = manifest.top_level_modules
        lines = [f"**{len(mods)} Python modules:**\n"]
        for m in mods:
            lines.append(f"- `{m.name}` ({m.file_count} files) — {m.notes}")
        return "\n".join(lines)

    return None  # not a known slash command


# ---------------------------------------------------------------------------
# Natural-language handler (auto-route + respond)
# ---------------------------------------------------------------------------

def handle_natural(text: str) -> str:
    """Route a natural-language message through the harness and generate a response."""
    runtime = st.session_state.runtime
    engine = st.session_state.engine

    # Route prompt
    matches = runtime.route_prompt(text, limit=6)
    matched_cmds = tuple(m.name for m in matches if m.kind == "command")
    matched_tools = tuple(m.name for m in matches if m.kind == "tool")

    # Submit through query engine (uses real LLM if configured, shim otherwise)
    result = engine.submit_message(text, matched_cmds, matched_tools)
    st.session_state.turn_count += 1
    st.session_state.cost.record("turn", 1)
    st.session_state.history.add("message", text)

    parts = []

    # Show routing
    if matches:
        parts.append("**Routed to:**\n")
        parts.append(_render_routed_matches(matches))

    # Show any permission denials
    if result.permission_denials:
        parts.append("\n**Permission denials:**")
        for d in result.permission_denials:
            parts.append(f'<span class="tag t-deny">denied</span> `{d.tool_name}` — {d.reason}')

    # Show response — if LLM is active, render output directly as markdown
    if engine.llm_active:
        parts.append(f"\n{result.output}")
    else:
        parts.append(f"\n**Response** (stop: `{result.stop_reason}`):\n")
        parts.append(f"```\n{result.output}\n```")

    # Usage footer
    u = result.usage
    parts.append(f"\n*{u.input_tokens} in / {u.output_tokens} out tokens · turn {st.session_state.turn_count}*")

    return "\n".join(parts)


def handle_natural_streaming(text: str):
    """Stream a natural-language response via generator for st.write_stream."""
    runtime = st.session_state.runtime
    engine = st.session_state.engine

    matches = runtime.route_prompt(text, limit=6)
    matched_cmds = tuple(m.name for m in matches if m.kind == "command")
    matched_tools = tuple(m.name for m in matches if m.kind == "tool")

    st.session_state.turn_count += 1
    st.session_state.cost.record("turn", 1)
    st.session_state.history.add("message", text)

    # Yield routing info first
    if matches:
        yield "**Routed to:**\n\n"
        yield _render_routed_matches(matches) + "\n\n"

    # Stream from the query engine
    for event in engine.stream_submit_message(text, matched_cmds, matched_tools):
        if event["type"] == "message_delta":
            yield event["text"]
        elif event["type"] == "message_stop":
            u = event["usage"]
            yield f"\n\n*{u['input_tokens']} in / {u['output_tokens']} out tokens · turn {st.session_state.turn_count}*"


# ---------------------------------------------------------------------------
# Sidebar — session history & quick actions
# ---------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### 🦀 Claw Code")
    st.caption(f"Session `{st.session_state.session_id}`")

    if st.button("🔄 New Session", use_container_width=True):
        _reset_session()
        st.rerun()

    st.divider()

    st.markdown("**Quick actions**")
    col1, col2 = st.columns(2)
    with col1:
        if st.button("📊 Status", use_container_width=True, key="sb_status"):
            _add("user", "/status")
            _add("assistant", handle_slash("/status"))
            st.rerun()
        if st.button("🔧 Tools", use_container_width=True, key="sb_tools"):
            _add("user", "/tools")
            _add("assistant", handle_slash("/tools"))
            st.rerun()
        if st.button("📋 Parity", use_container_width=True, key="sb_parity"):
            _add("user", "/parity")
            _add("assistant", handle_slash("/parity"))
            st.rerun()
    with col2:
        if st.button("⚡ Commands", use_container_width=True, key="sb_cmds"):
            _add("user", "/commands")
            _add("assistant", handle_slash("/commands"))
            st.rerun()
        if st.button("📦 Modules", use_container_width=True, key="sb_subs"):
            _add("user", "/subsystems")
            _add("assistant", handle_slash("/subsystems"))
            st.rerun()
        if st.button("🏗️ Arch", use_container_width=True, key="sb_arch"):
            _add("user", "/architecture")
            _add("assistant", handle_slash("/architecture"))
            st.rerun()

    st.divider()

    st.markdown("**Session history**")
    for event in reversed(st.session_state.history.events[-10:]):
        st.caption(f"• {event.title}: {event.detail[:50]}")

    if not st.session_state.history.events:
        st.caption("No events yet.")

    st.divider()

    # ── LLM Configuration ──────────────────────────────────────────
    st.markdown("**🤖 AI Provider**")

    provider = st.selectbox(
        "Provider",
        ["anthropic", "openai"],
        index=0 if st.session_state.llm_provider == "anthropic" else 1,
        key="sb_provider",
    )

    model_options = ALL_ANTHROPIC_MODELS if provider == "anthropic" else ALL_OPENAI_MODELS
    current_model = st.session_state.llm_model
    if current_model in model_options:
        model_index = model_options.index(current_model)
    else:
        model_index = 0  # default to first (best balance) model

    model = st.selectbox(
        "Model",
        model_options,
        index=model_index,
        key="sb_model",
    )

    if st.button("💾 Apply", use_container_width=True, key="sb_apply_llm"):
        st.session_state.llm_provider = provider
        st.session_state.llm_model = model
        new_config = LLMConfig(provider=provider, model=model)
        st.session_state.engine.set_llm_config(new_config)
        if new_config.is_configured:
            st.success(f"✓ Connected: {new_config.resolved_model}")
        else:
            env_var = "ANTHROPIC_API_KEY" if provider == "anthropic" else "OPENAI_API_KEY"
            st.warning(f"No key — set {env_var} in .env")
        st.rerun()

    if st.session_state.engine.llm_active:
        st.caption(f"✓ Active: {st.session_state.engine.llm_config.resolved_model}")
    else:
        st.caption("⚠ Shim mode — set API key in .env file")


# ---------------------------------------------------------------------------
# Render chat messages
# ---------------------------------------------------------------------------
for msg in st.session_state.messages:
    role = msg["role"]
    if role == "user":
        with st.chat_message("user", avatar="👤"):
            st.markdown(msg["content"])
    elif role == "assistant":
        with st.chat_message("assistant", avatar="🦀"):
            st.markdown(msg["content"], unsafe_allow_html=True)
    elif role == "system":
        with st.chat_message("assistant", avatar="⚙️"):
            st.caption(msg["content"])

# ---------------------------------------------------------------------------
# Chat input
# ---------------------------------------------------------------------------
if prompt := st.chat_input("Message Claw Code… (or /help for commands)"):
    # Show user message
    _add("user", prompt)
    with st.chat_message("user", avatar="👤"):
        st.markdown(prompt)

    # Process
    stripped = prompt.strip()

    if stripped.startswith("/"):
        # Check for /new or /reset
        cmd_word = stripped.split()[0].lower()
        if cmd_word in ("/new", "/reset"):
            _reset_session()
            st.rerun()

        response = handle_slash(stripped)
        if response is None:
            # Unknown slash command → try natural language
            if st.session_state.engine.llm_active:
                with st.chat_message("assistant", avatar="🦀"):
                    response = st.write_stream(handle_natural_streaming(stripped))
                _add("assistant", response)
            else:
                response = handle_natural(stripped)
                _add("assistant", response)
                with st.chat_message("assistant", avatar="🦀"):
                    st.markdown(response, unsafe_allow_html=True)
        else:
            _add("assistant", response)
            with st.chat_message("assistant", avatar="🦀"):
                st.markdown(response, unsafe_allow_html=True)
    else:
        # Natural language — stream if LLM is active
        if st.session_state.engine.llm_active:
            with st.chat_message("assistant", avatar="🦀"):
                try:
                    response = st.write_stream(handle_natural_streaming(stripped))
                except Exception as e:
                    response = f"**Error:** {e}"
                    st.error(response)
            _add("assistant", response)
        else:
            response = handle_natural(stripped)
            _add("assistant", response)
            with st.chat_message("assistant", avatar="🦀"):
                st.markdown(response, unsafe_allow_html=True)
