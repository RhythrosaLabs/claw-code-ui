"""Test script for the chat UI backend functionality."""
import sys
sys.path.insert(0, ".")

from src.commands import PORTED_COMMANDS, execute_command, find_commands, get_commands
from src.tools import PORTED_TOOLS, execute_tool, find_tools, get_tools
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
from src.cost_tracker import CostTracker
from src.history import HistoryLog

passed = 0
failed = 0

def check(name, condition, detail=""):
    global passed, failed
    if condition:
        passed += 1
        print(f"  PASS  {name}" + (f" — {detail}" if detail else ""))
    else:
        failed += 1
        print(f"  FAIL  {name}" + (f" — {detail}" if detail else ""))

print("=" * 60)
print("CHAT UI BACKEND TEST SUITE")
print("=" * 60)

# --- 1. Core data ---
print("\n[1] Core data loading")
check("PORTED_COMMANDS loaded", len(PORTED_COMMANDS) > 100, f"{len(PORTED_COMMANDS)} entries")
check("PORTED_TOOLS loaded", len(PORTED_TOOLS) > 100, f"{len(PORTED_TOOLS)} entries")
manifest = build_port_manifest()
check("Manifest built", len(manifest.top_level_modules) > 30, f"{len(manifest.top_level_modules)} modules")

# --- 2. /commands ---
print("\n[2] /commands slash command")
cmds = get_commands()
check("/commands returns list", len(cmds) == len(PORTED_COMMANDS))
unique_names = sorted(set(c.name for c in cmds))
check("/commands unique names", len(unique_names) > 50, f"{len(unique_names)} unique")

# --- 3. /commands <query> ---
print("\n[3] /commands <query>")
agent_cmds = find_commands("agent")
check("/commands agent", len(agent_cmds) > 0, f"{len(agent_cmds)} matches")
review_cmds = find_commands("review")
check("/commands review", len(review_cmds) > 0, f"{len(review_cmds)} matches")
no_cmds = find_commands("xyznonexistent")
check("/commands nonexistent returns empty", len(no_cmds) == 0)

# --- 4. /tools ---
print("\n[4] /tools slash command")
tools = get_tools()
check("/tools returns list", len(tools) == len(PORTED_TOOLS))
tool_names = sorted(set(t.name for t in tools))
check("/tools unique names", len(tool_names) > 30, f"{len(tool_names)} unique")

# --- 5. /tools <query> ---
print("\n[5] /tools <query>")
bash_tools = find_tools("bash")
check("/tools bash", len(bash_tools) > 0, f"{len(bash_tools)} matches")
file_tools = find_tools("file")
check("/tools file", len(file_tools) > 0, f"{len(file_tools)} matches")
no_tools = find_tools("xyznonexistent")
check("/tools nonexistent returns empty", len(no_tools) == 0)

# --- 6. /exec-cmd ---
print("\n[6] /exec-cmd")
result = execute_command("help", "show help")
check("/exec-cmd help", result.handled, result.message[:60])
result2 = execute_command("nonexistent_cmd", "test")
check("/exec-cmd nonexistent", not result2.handled, result2.message[:60])

# --- 7. /exec-tool ---
print("\n[7] /exec-tool")
result = execute_tool("BashTool", '{"command": "ls"}')
check("/exec-tool BashTool", result.handled, result.message[:60])
result2 = execute_tool("nonexistent_tool", "{}")
check("/exec-tool nonexistent", not result2.handled, result2.message[:60])

# --- 8. /route ---
print("\n[8] /route (prompt routing)")
runtime = PortRuntime()
matches = runtime.route_prompt("search for files", limit=8)
check("/route returns results", len(matches) > 0, f"{len(matches)} matches")
has_cmd = any(m.kind == "command" for m in matches)
has_tool = any(m.kind == "tool" for m in matches)
check("/route has command match", has_cmd)
check("/route has tool match", has_tool)
for m in matches[:3]:
    check(f"  match: {m.kind}/{m.name}", m.score > 0, f"score={m.score}, src={m.source_hint}")

# --- 9. /status (query engine) ---
print("\n[9] /status (QueryEnginePort)")
engine = QueryEnginePort.from_workspace()
check("Engine created", engine.session_id is not None, f"id={engine.session_id[:12]}")
check("Initial usage zero", engine.total_usage.input_tokens == 0)
check("Initial messages empty", len(engine.mutable_messages) == 0)

# --- 10. Natural language (submit_message) ---
print("\n[10] Natural language message handling")
result = engine.submit_message(
    "search for files in the project",
    matched_commands=("files",),
    matched_tools=("GrepTool",),
)
check("submit_message returns TurnResult", result.output is not None)
check("stop_reason is completed", result.stop_reason == "completed", result.stop_reason)
check("usage updated", engine.total_usage.input_tokens > 0, f"{engine.total_usage.input_tokens} in")
check("message tracked", len(engine.mutable_messages) == 1)
check("transcript tracked", len(engine.transcript_store.entries) == 1)

# --- 11. Multi-turn loop ---
print("\n[11] Multi-turn conversation")
for i in range(3):
    r = engine.submit_message(f"turn {i+2}", matched_commands=(), matched_tools=())
    check(f"turn {i+2} ok", r.output is not None, f"stop={r.stop_reason}")
check("Messages accumulated", len(engine.mutable_messages) == 4, f"{len(engine.mutable_messages)} messages")

# --- 12. /compact ---
print("\n[12] /compact")
before = len(engine.mutable_messages)
engine.compact_messages_if_needed()
after = len(engine.mutable_messages)
check("/compact runs", after <= before, f"{before} -> {after}")

# --- 13. Session persist ---
print("\n[13] Session persistence")
path = engine.persist_session()
check("Session persisted", path is not None and len(path) > 0, path)
check("Transcript flushed", engine.transcript_store.flushed)

# --- 14. /run (bootstrap session) ---
print("\n[14] /run (bootstrap session)")
session = PortRuntime().bootstrap_session("explain the codebase", limit=5)
check("Bootstrap returns session", session is not None)
check("Has routed matches", len(session.routed_matches) > 0, f"{len(session.routed_matches)} matches")
check("Has turn result", session.turn_result is not None)
check("Has stream events", len(session.stream_events) > 0, f"{len(session.stream_events)} events")
check("Has persisted path", len(session.persisted_session_path) > 0)
check("Command executions present", session.command_execution_messages is not None)
check("Tool executions present", session.tool_execution_messages is not None)

# --- 15. /parity ---
print("\n[15] /parity")
audit = run_parity_audit()
md = audit.to_markdown()
check("/parity produces output", len(md) > 50, f"{len(md)} chars")

# --- 16. /architecture ---
print("\n[16] /architecture")
graph = build_bootstrap_graph()
check("Bootstrap graph", len(graph.as_markdown()) > 50)

# --- 17. /graph ---
print("\n[17] /graph")
cmd_graph = build_command_graph()
check("Command graph", len(cmd_graph.as_markdown()) > 50)

# --- 18. /pool ---
print("\n[18] /pool")
pool = assemble_tool_pool()
check("Tool pool", len(pool.as_markdown()) > 50)

# --- 19. /setup ---
print("\n[19] /setup")
setup = run_setup()
check("Setup report", len(setup.as_markdown()) > 50)

# --- 20. /subsystems ---
print("\n[20] /subsystems")
mods = manifest.top_level_modules
check("Subsystems listed", len(mods) > 30, f"{len(mods)} modules")

# --- 21. CostTracker ---
print("\n[21] CostTracker")
cost = CostTracker()
cost.record("turn", 1)
cost.record("bootstrap", 1)
check("Cost tracks events", len(cost.events) == 2, f"total={cost.total_units}")

# --- 22. HistoryLog ---
print("\n[22] HistoryLog")
log = HistoryLog()
log.add("message", "test prompt")
log.add("bootstrap", "another prompt")
check("History tracks events", len(log.events) == 2)
check("History renders markdown", "Session History" in log.as_markdown())

# --- 23. Stream events ---
print("\n[23] Streaming (stream_submit_message)")
engine2 = QueryEnginePort.from_workspace()
events = list(engine2.stream_submit_message("test stream", matched_commands=("help",), matched_tools=("BashTool",)))
event_types = [e["type"] for e in events]
check("Has message_start", "message_start" in event_types)
check("Has command_match", "command_match" in event_types)
check("Has tool_match", "tool_match" in event_types)
check("Has message_delta", "message_delta" in event_types)
check("Has message_stop", "message_stop" in event_types)

# --- 24. Permission filtering ---
print("\n[24] Permission filtering")
perm = ToolPermissionContext.from_iterables(["BashTool"], ["MCP"])
check("Blocks exact name", perm.blocks("BashTool"))
check("Blocks prefix", perm.blocks("MCPTool"))
check("Allows others", not perm.blocks("FileReadTool"))

# --- Results ---
print("\n" + "=" * 60)
total = passed + failed
print(f"RESULTS: {passed}/{total} passed, {failed} failed")
if failed == 0:
    print("ALL TESTS PASSED!")
else:
    print(f"FAILURES: {failed}")
print("=" * 60)
