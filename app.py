"""
Claw Code — Harness Explorer UI

A streamlined interactive dashboard for exploring the Claw Code
agent harness: commands, tools, subsystems, routing, sessions, and parity.

Run:  streamlit run app.py
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import sys
from pathlib import Path

import streamlit as st

# ---------------------------------------------------------------------------
# Ensure the project root is importable
# ---------------------------------------------------------------------------
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

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
from src.models import PortingModule
from src.permissions import ToolPermissionContext
from src.port_manifest import build_port_manifest
from src.query_engine import QueryEngineConfig, QueryEnginePort
from src.runtime import PortRuntime
from src.parity_audit import run_parity_audit
from src.setup import run_setup
from src.bootstrap_graph import build_bootstrap_graph
from src.command_graph import build_command_graph
from src.tool_pool import assemble_tool_pool
from src.context import build_port_context, render_context

# ---------------------------------------------------------------------------
# Reference data helpers
# ---------------------------------------------------------------------------
REF_DIR = _PROJECT_ROOT / "src" / "reference_data"
SUBSYSTEM_DIR = REF_DIR / "subsystems"


def _load_json(path: Path):
    with open(path) as f:
        return json.load(f)


@st.cache_data
def load_commands_snapshot():
    return _load_json(REF_DIR / "commands_snapshot.json")


@st.cache_data
def load_tools_snapshot():
    return _load_json(REF_DIR / "tools_snapshot.json")


@st.cache_data
def load_subsystems():
    results = []
    if SUBSYSTEM_DIR.is_dir():
        for fp in sorted(SUBSYSTEM_DIR.iterdir()):
            if fp.suffix == ".json":
                results.append(_load_json(fp))
    return results


@st.cache_data
def load_archive_surface():
    p = REF_DIR / "archive_surface_snapshot.json"
    if p.exists():
        return _load_json(p)
    return {}


# ---------------------------------------------------------------------------
# Capture CLI output helper
# ---------------------------------------------------------------------------
def _capture(fn, *args, **kwargs) -> str:
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            fn(*args, **kwargs)
    except SystemExit:
        pass
    except Exception as exc:
        buf.write(f"Error: {exc}")
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Page configuration
# ---------------------------------------------------------------------------
st.set_page_config(
    page_title="Claw Code · Harness Explorer",
    page_icon="🦀",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------------------------------------------------------------------------
# Custom CSS
# ---------------------------------------------------------------------------
st.markdown(
    """
<style>
/* Dark refined look */
[data-testid="stSidebar"] { background-color: #0d1117; }
.block-container { padding-top: 2rem; }
h1, h2, h3 { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; }
.metric-card {
    background: #161b22; border: 1px solid #30363d; border-radius: 10px;
    padding: 1.2rem; text-align: center;
}
.metric-card .num { font-size: 2.2rem; font-weight: 700; color: #58a6ff; }
.metric-card .label { font-size: 0.8rem; color: #8b949e; margin-top: 0.2rem; }
.tag { display: inline-block; font-size: 0.7rem; padding: 2px 8px; border-radius: 12px;
       margin-right: 4px; font-weight: 600; }
.tag-cmd { background: #1f6feb33; color: #58a6ff; border: 1px solid #1f6feb; }
.tag-tool { background: #23863533; color: #3fb950; border: 1px solid #238635; }
.tag-plugin { background: #d2992233; color: #d29922; border: 1px solid #d29922; }
.tag-skill { background: #a371f733; color: #a371f7; border: 1px solid #a371f7; }
div[data-testid="stExpander"] { border: 1px solid #30363d; border-radius: 8px; }
</style>
""",
    unsafe_allow_html=True,
)

# ---------------------------------------------------------------------------
# Sidebar navigation
# ---------------------------------------------------------------------------
st.sidebar.markdown("## 🦀 Claw Code")
st.sidebar.caption("Harness Explorer")
page = st.sidebar.radio(
    "Navigate",
    [
        "🏠 Dashboard",
        "⚡ Commands",
        "🔧 Tools",
        "📦 Subsystems",
        "🔀 Prompt Router",
        "🚀 Session Runner",
        "📊 Parity Audit",
        "🏗️ Architecture",
    ],
    label_visibility="collapsed",
)

# =====================================================================
# 🏠 DASHBOARD
# =====================================================================
if page == "🏠 Dashboard":
    st.title("🦀 Claw Code — Harness Explorer")
    st.caption(
        "A clean-room Python rewrite of an AI agent harness. "
        "Explore the full command, tool, and subsystem inventory mirrored from the original TypeScript architecture."
    )

    # Metrics
    manifest = build_port_manifest()
    n_commands = len(PORTED_COMMANDS)
    n_tools = len(PORTED_TOOLS)
    n_modules = len(manifest.top_level_modules)
    archive = load_archive_surface()
    n_ts_files = archive.get("total_files", "—")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Commands", n_commands)
    c2.metric("Tools", n_tools)
    c3.metric("Python Modules", n_modules)
    c4.metric("TS Archive Files", n_ts_files)

    st.divider()

    # Quick search
    st.subheader("Quick Search")
    query = st.text_input(
        "Search commands and tools by name…",
        placeholder="e.g. bash, review, agent, mcp, plan",
        key="dash_search",
    )
    if query:
        col_a, col_b = st.columns(2)
        with col_a:
            st.markdown("**Matching Commands**")
            matches = find_commands(query)
            if matches:
                for m in matches[:15]:
                    st.markdown(
                        f'<span class="tag tag-cmd">cmd</span> **{m.name}** — `{m.source_hint}`',
                        unsafe_allow_html=True,
                    )
            else:
                st.info("No matching commands.")
        with col_b:
            st.markdown("**Matching Tools**")
            matches = find_tools(query)
            if matches:
                for m in matches[:15]:
                    st.markdown(
                        f'<span class="tag tag-tool">tool</span> **{m.name}** — `{m.source_hint}`',
                        unsafe_allow_html=True,
                    )
            else:
                st.info("No matching tools.")

    st.divider()

    # Recent subsystems
    st.subheader("Top Subsystems (by module count)")
    subsystems = load_subsystems()
    if subsystems:
        sorted_sub = sorted(subsystems, key=lambda s: s.get("module_count", 0), reverse=True)[:10]
        for s in sorted_sub:
            name = s.get("archive_name") or s.get("package_name", "?")
            count = s.get("module_count", 0)
            samples = s.get("sample_files", [])[:3]
            with st.expander(f"**{name}** — {count} modules"):
                st.write(f"Package: `{s.get('package_name', name)}`")
                st.write(f"Module count: **{count}**")
                if samples:
                    st.write("Sample files:")
                    for sf in samples:
                        st.code(sf, language="text")


# =====================================================================
# ⚡ COMMANDS
# =====================================================================
elif page == "⚡ Commands":
    st.title("⚡ Command Inventory")
    st.caption(f"{len(PORTED_COMMANDS)} command entries mirrored from the original TypeScript harness.")

    # Filters
    col1, col2 = st.columns([2, 1])
    with col1:
        search = st.text_input("Filter by name…", key="cmd_search")
    with col2:
        cat_filter = st.selectbox(
            "Category",
            ["All", "Builtins", "Plugin-related", "Skill-related"],
            key="cmd_cat",
        )

    commands = list(PORTED_COMMANDS)
    if search:
        search_lower = search.lower()
        commands = [c for c in commands if search_lower in c.name.lower() or search_lower in c.source_hint.lower()]
    if cat_filter == "Plugin-related":
        commands = [c for c in commands if "plugin" in c.source_hint.lower()]
    elif cat_filter == "Skill-related":
        commands = [c for c in commands if "skill" in c.source_hint.lower()]
    elif cat_filter == "Builtins":
        commands = [
            c for c in commands
            if "plugin" not in c.source_hint.lower() and "skill" not in c.source_hint.lower()
        ]

    st.info(f"Showing {len(commands)} of {len(PORTED_COMMANDS)} entries")

    # Deduplicated unique names for the table view
    for cmd in commands[:50]:
        tag = "tag-cmd"
        if "plugin" in cmd.source_hint.lower():
            tag = "tag-plugin"
        elif "skill" in cmd.source_hint.lower():
            tag = "tag-skill"
        st.markdown(
            f'<span class="tag {tag}">{"plugin" if "plugin" in cmd.source_hint.lower() else "skill" if "skill" in cmd.source_hint.lower() else "builtin"}</span> '
            f"**`/{cmd.name}`** &nbsp;→&nbsp; `{cmd.source_hint}`",
            unsafe_allow_html=True,
        )

    if len(commands) > 50:
        st.warning(f"Showing first 50 of {len(commands)}. Use the filter to narrow down.")

    st.divider()

    # Execute a command
    st.subheader("Execute Command Shim")
    exec_name = st.text_input("Command name", placeholder="e.g. help, status, plan", key="exec_cmd_name")
    exec_prompt = st.text_input("Prompt", placeholder="e.g. show project status", key="exec_cmd_prompt")
    if st.button("Execute", key="exec_cmd_btn") and exec_name:
        result = execute_command(exec_name, exec_prompt or "")
        if result.handled:
            st.success(result.message)
        else:
            st.error(result.message)


# =====================================================================
# 🔧 TOOLS
# =====================================================================
elif page == "🔧 Tools":
    st.title("🔧 Tool Inventory")
    st.caption(f"{len(PORTED_TOOLS)} tool entries mirrored from the original TypeScript harness.")

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        search = st.text_input("Filter by name…", key="tool_search")
    with col2:
        simple_mode = st.checkbox("Simple mode (Bash/Read/Edit only)", key="tool_simple")
    with col3:
        no_mcp = st.checkbox("Exclude MCP tools", key="tool_no_mcp")

    perm_ctx = ToolPermissionContext.from_iterables([], [])
    tools = list(get_tools(simple_mode=simple_mode, include_mcp=not no_mcp, permission_context=perm_ctx))

    if search:
        search_lower = search.lower()
        tools = [t for t in tools if search_lower in t.name.lower() or search_lower in t.source_hint.lower()]

    st.info(f"Showing {len(tools)} tools")

    # Group by tool family (first path component)
    families: dict[str, list[PortingModule]] = {}
    for t in tools:
        family = t.source_hint.split("/")[1] if "/" in t.source_hint else t.name
        families.setdefault(family, []).append(t)

    for family_name in sorted(families.keys()):
        members = families[family_name]
        with st.expander(f"🔧 **{family_name}** ({len(members)} entries)"):
            for m in members:
                st.markdown(f"- **`{m.name}`** — `{m.source_hint}`")

    st.divider()

    # Execute a tool shim
    st.subheader("Execute Tool Shim")
    tool_name = st.text_input("Tool name", placeholder="e.g. BashTool, FileReadTool", key="exec_tool_name")
    tool_payload = st.text_input("Payload", placeholder='e.g. {"command": "ls"}', key="exec_tool_payload")
    if st.button("Execute", key="exec_tool_btn") and tool_name:
        result = execute_tool(tool_name, tool_payload or "{}")
        if result.handled:
            st.success(result.message)
        else:
            st.error(result.message)


# =====================================================================
# 📦 SUBSYSTEMS
# =====================================================================
elif page == "📦 Subsystems":
    st.title("📦 Subsystem Map")
    st.caption("Archive subsystem inventory — the original TypeScript directory structure.")

    subsystems = load_subsystems()
    if not subsystems:
        st.warning("No subsystem data found in reference_data/subsystems/")
    else:
        # Bar chart of module counts
        sorted_sub = sorted(subsystems, key=lambda s: s.get("module_count", 0), reverse=True)
        chart_data = {
            s.get("archive_name") or s.get("package_name", "?"): s.get("module_count", 0)
            for s in sorted_sub
        }
        st.bar_chart(chart_data, horizontal=True)

        st.divider()

        # Searchable list
        q = st.text_input("Filter subsystems…", key="sub_search")
        for s in sorted_sub:
            name = s.get("archive_name") or s.get("package_name", "?")
            if q and q.lower() not in name.lower():
                continue
            count = s.get("module_count", 0)
            samples = s.get("sample_files", [])
            with st.expander(f"**{name}** — {count} modules"):
                st.metric("Module Count", count)
                if samples:
                    st.write(f"**Sample files** ({len(samples)} total):")
                    for sf in samples[:20]:
                        st.text(sf)
                    if len(samples) > 20:
                        st.caption(f"… and {len(samples) - 20} more")


# =====================================================================
# 🔀 PROMPT ROUTER
# =====================================================================
elif page == "🔀 Prompt Router":
    st.title("🔀 Prompt Router")
    st.caption(
        "Enter a natural-language prompt and see which commands and tools the harness would route it to. "
        "Routing scores each entry by keyword overlap."
    )

    prompt = st.text_area(
        "Your prompt",
        placeholder="e.g. search for files matching *.py in the project",
        height=80,
        key="route_prompt",
    )
    limit = st.slider("Max results", 3, 20, 8, key="route_limit")

    if st.button("Route", key="route_btn", type="primary") and prompt:
        runtime = PortRuntime()
        matches = runtime.route_prompt(prompt, limit=limit)
        if not matches:
            st.warning("No matches found for this prompt.")
        else:
            st.success(f"Found {len(matches)} matches")
            for m in matches:
                tag_class = "tag-cmd" if m.kind == "command" else "tag-tool"
                st.markdown(
                    f'<span class="tag {tag_class}">{m.kind}</span> '
                    f"**{m.name}** &nbsp;(score: {m.score}) → `{m.source_hint}`",
                    unsafe_allow_html=True,
                )


# =====================================================================
# 🚀 SESSION RUNNER
# =====================================================================
elif page == "🚀 Session Runner":
    st.title("🚀 Session Runner")
    st.caption(
        "Run a full bootstrap session or multi-turn loop against the mirrored runtime. "
        "This simulates the harness startup, routing, execution, and session persistence flow."
    )

    tab_boot, tab_loop = st.tabs(["Bootstrap Session", "Turn Loop"])

    with tab_boot:
        prompt = st.text_area(
            "Prompt",
            placeholder="e.g. explain the project structure",
            height=80,
            key="boot_prompt",
        )
        limit = st.slider("Match limit", 3, 15, 5, key="boot_limit")
        if st.button("Run Bootstrap", key="boot_btn", type="primary") and prompt:
            with st.spinner("Running bootstrap session…"):
                session = PortRuntime().bootstrap_session(prompt, limit=limit)
            st.success("Session complete!")

            # Context
            with st.expander("📋 Context"):
                st.code(render_context(session.context), language="markdown")

            # Setup
            with st.expander("⚙️ Setup"):
                st.write(f"**Python:** {session.setup.python_version} ({session.setup.implementation})")
                st.write(f"**Platform:** {session.setup.platform_name}")
                st.write(f"**Test command:** `{session.setup.test_command}`")
                st.write("**Startup steps:**")
                for step in session.setup.startup_steps():
                    st.write(f"- {step}")

            # Routed matches
            with st.expander("🔀 Routed Matches"):
                for m in session.routed_matches:
                    tag = "tag-cmd" if m.kind == "command" else "tag-tool"
                    st.markdown(
                        f'<span class="tag {tag}">{m.kind}</span> **{m.name}** (score: {m.score}) → `{m.source_hint}`',
                        unsafe_allow_html=True,
                    )

            # Execution
            with st.expander("▶️ Execution"):
                st.write("**Command executions:**")
                for msg in session.command_execution_messages:
                    st.code(msg, language="text")
                st.write("**Tool executions:**")
                for msg in session.tool_execution_messages:
                    st.code(msg, language="text")

            # Stream events
            with st.expander("📡 Stream Events"):
                for event in session.stream_events:
                    st.json(event)

            # Turn result
            with st.expander("📝 Turn Result"):
                st.code(session.turn_result.output, language="text")
                st.write(f"**Stop reason:** `{session.turn_result.stop_reason}`")
                st.write(
                    f"**Usage:** {session.turn_result.usage.input_tokens} in / "
                    f"{session.turn_result.usage.output_tokens} out"
                )

            st.info(f"Session persisted to: `{session.persisted_session_path}`")

    with tab_loop:
        prompt = st.text_area(
            "Prompt",
            placeholder="e.g. review the codebase for issues",
            height=80,
            key="loop_prompt",
        )
        c1, c2 = st.columns(2)
        with c1:
            max_turns = st.slider("Max turns", 1, 8, 3, key="loop_turns")
        with c2:
            structured = st.checkbox("Structured output", key="loop_structured")
        if st.button("Run Turn Loop", key="loop_btn", type="primary") and prompt:
            with st.spinner(f"Running {max_turns}-turn loop…"):
                results = PortRuntime().run_turn_loop(
                    prompt, limit=5, max_turns=max_turns, structured_output=structured
                )
            st.success(f"Completed {len(results)} turns")
            for idx, result in enumerate(results, 1):
                with st.expander(f"Turn {idx} — stop: {result.stop_reason}"):
                    st.code(result.output, language="text")
                    st.write(
                        f"**Usage:** {result.usage.input_tokens} in / "
                        f"{result.usage.output_tokens} out"
                    )
                    if result.matched_commands:
                        st.write(f"**Commands:** {', '.join(result.matched_commands)}")
                    if result.matched_tools:
                        st.write(f"**Tools:** {', '.join(result.matched_tools)}")
                    if result.permission_denials:
                        st.write(f"**Denials:** {', '.join(d.tool_name for d in result.permission_denials)}")


# =====================================================================
# 📊 PARITY AUDIT
# =====================================================================
elif page == "📊 Parity Audit":
    st.title("📊 Parity Audit")
    st.caption(
        "Compare the current Python workspace against the original TypeScript archive surface. "
        "See how much of the original system has been mirrored."
    )

    with st.spinner("Running parity audit…"):
        audit = run_parity_audit()

    st.code(audit.to_markdown(), language="markdown")

    st.divider()

    # Visual gauges
    archive = load_archive_surface()
    if archive:
        ts_root_files = archive.get("root_file_count", 18)
        ts_root_dirs = archive.get("root_dir_count", 35)
        ts_total = archive.get("total_files", 1902)
        ts_commands = archive.get("command_count", 207)
        ts_tools = archive.get("tool_count", 184)

        manifest = build_port_manifest()
        py_files = sum(m.file_count for m in manifest.top_level_modules)

        st.subheader("Coverage Gauges")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Python Files", py_files, f"/ {ts_total} TS files")
        with c2:
            st.metric("Commands Mirrored", len(PORTED_COMMANDS), f"/ {ts_commands} original")
        with c3:
            st.metric("Tools Mirrored", len(PORTED_TOOLS), f"/ {ts_tools} original")


# =====================================================================
# 🏗️ ARCHITECTURE
# =====================================================================
elif page == "🏗️ Architecture":
    st.title("🏗️ Architecture Explorer")
    st.caption("Explore the internal architecture of the Claw Code harness.")

    tab_boot, tab_cmd, tab_pool, tab_setup = st.tabs(
        ["Bootstrap Graph", "Command Graph", "Tool Pool", "Setup Report"]
    )

    with tab_boot:
        st.subheader("Bootstrap / Runtime Graph")
        st.caption("The 7-stage startup pipeline mirrored from the original system.")
        graph = build_bootstrap_graph()
        st.code(graph.as_markdown(), language="markdown")

    with tab_cmd:
        st.subheader("Command Graph Segmentation")
        st.caption("Commands segmented into builtins, plugin-provided, and skill-provided.")
        graph = build_command_graph()
        st.code(graph.as_markdown(), language="markdown")

    with tab_pool:
        st.subheader("Assembled Tool Pool")
        st.caption("The default tool pool assembled with standard settings.")
        pool = assemble_tool_pool()
        st.code(pool.as_markdown(), language="markdown")

    with tab_setup:
        st.subheader("Setup Report")
        st.caption("Startup/prefetch setup including deferred init and trust gating.")
        report = run_setup()
        st.code(report.as_markdown(), language="markdown")
