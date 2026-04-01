"""Simple Flask web UI for Claw Code."""

from __future__ import annotations

import io
import contextlib

from flask import Flask, render_template_string, request

from src.main import main as cli_main

app = Flask(__name__)

TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Claw Code</title>
<style>
  :root { --bg: #0d1117; --card: #161b22; --border: #30363d; --text: #c9d1d9;
          --muted: #8b949e; --accent: #58a6ff; --green: #3fb950; --orange: #d29922; }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
         background: var(--bg); color: var(--text); min-height: 100vh; }
  .container { max-width: 960px; margin: 0 auto; padding: 24px 16px; }
  header { display: flex; align-items: center; gap: 12px; margin-bottom: 32px;
           border-bottom: 1px solid var(--border); padding-bottom: 16px; }
  header h1 { font-size: 24px; font-weight: 600; }
  header h1 span { color: var(--accent); }
  .badge { background: var(--accent); color: var(--bg); font-size: 11px; font-weight: 600;
           padding: 2px 8px; border-radius: 12px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(200px, 1fr)); gap: 12px;
          margin-bottom: 32px; }
  .card { background: var(--card); border: 1px solid var(--border); border-radius: 8px;
          padding: 16px; cursor: pointer; transition: border-color 0.15s; text-decoration: none; color: inherit; }
  .card:hover { border-color: var(--accent); }
  .card h3 { font-size: 14px; font-weight: 600; margin-bottom: 4px; color: var(--accent); }
  .card p { font-size: 12px; color: var(--muted); line-height: 1.4; }
  .prompt-section { margin-bottom: 32px; }
  .prompt-section h2 { font-size: 16px; font-weight: 600; margin-bottom: 12px; color: var(--text); }
  .prompt-row { display: flex; gap: 8px; margin-bottom: 8px; }
  .prompt-row select { background: var(--card); border: 1px solid var(--border); color: var(--text);
                       padding: 8px 12px; border-radius: 6px; font-size: 14px; }
  .prompt-row input { flex: 1; background: var(--card); border: 1px solid var(--border); color: var(--text);
                      padding: 8px 12px; border-radius: 6px; font-size: 14px; outline: none; }
  .prompt-row input:focus { border-color: var(--accent); }
  .prompt-row button { background: var(--accent); color: var(--bg); border: none; padding: 8px 20px;
                       border-radius: 6px; font-size: 14px; font-weight: 600; cursor: pointer; }
  .prompt-row button:hover { opacity: 0.9; }
  .output-box { background: var(--card); border: 1px solid var(--border); border-radius: 8px;
                padding: 16px; font-family: 'SF Mono', 'Fira Code', monospace; font-size: 13px;
                line-height: 1.6; white-space: pre-wrap; word-break: break-word; overflow-x: auto;
                max-height: 600px; overflow-y: auto; }
  .output-box:empty { display: none; }
  .stat-row { display: flex; gap: 24px; margin-bottom: 24px; }
  .stat { background: var(--card); border: 1px solid var(--border); border-radius: 8px;
          padding: 16px 20px; flex: 1; text-align: center; }
  .stat .num { font-size: 28px; font-weight: 700; color: var(--green); }
  .stat .label { font-size: 12px; color: var(--muted); margin-top: 4px; }
  .active-badge { background: var(--green); color: var(--bg); font-size: 11px; font-weight: 600;
                  padding: 2px 8px; border-radius: 12px; display: inline-block; margin-left: 8px; }
  footer { margin-top: 40px; border-top: 1px solid var(--border); padding-top: 16px;
           font-size: 12px; color: var(--muted); text-align: center; }
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>🦀 <span>Claw Code</span></h1>
    <span class="badge">Python Harness</span>
  </header>

  <div class="stat-row">
    <div class="stat"><div class="num">{{ stats.modules }}</div><div class="label">Modules</div></div>
    <div class="stat"><div class="num">{{ stats.commands }}</div><div class="label">Commands</div></div>
    <div class="stat"><div class="num">{{ stats.tools }}</div><div class="label">Tools</div></div>
  </div>

  <div class="prompt-section">
    <h2>Run Command</h2>
    <form method="post" action="/">
      <div class="prompt-row">
        <select name="command">
          {% for cmd in commands %}
          <option value="{{ cmd.value }}" {% if cmd.value == active_cmd %}selected{% endif %}>{{ cmd.label }}</option>
          {% endfor %}
        </select>
        <input type="text" name="args" placeholder="Optional arguments…" value="{{ active_args }}">
        <button type="submit">Run</button>
      </div>
    </form>
  </div>

  {% if output is not none %}
  <div class="prompt-section">
    <h2>Output <span class="active-badge">{{ active_label }}</span></h2>
    <div class="output-box">{{ output }}</div>
  </div>
  {% endif %}

  <h2 style="font-size:16px; font-weight:600; margin-bottom:12px;">Quick Actions</h2>
  <div class="grid">
    {% for cmd in commands %}
    <a class="card" href="/?quick={{ cmd.value }}">
      <h3>{{ cmd.label }}</h3>
      <p>{{ cmd.desc }}</p>
    </a>
    {% endfor %}
  </div>

  <footer>Claw Code · Python Porting Workspace</footer>
</div>
</body>
</html>
"""

COMMANDS = [
    {"value": "summary", "label": "Summary", "desc": "Markdown overview of the workspace"},
    {"value": "manifest", "label": "Manifest", "desc": "Current workspace manifest"},
    {"value": "parity-audit", "label": "Parity Audit", "desc": "Compare Python vs TS archive"},
    {"value": "setup-report", "label": "Setup Report", "desc": "Startup/prefetch setup report"},
    {"value": "command-graph", "label": "Command Graph", "desc": "Command graph segmentation"},
    {"value": "tool-pool", "label": "Tool Pool", "desc": "Assembled tool pool overview"},
    {"value": "bootstrap-graph", "label": "Bootstrap Graph", "desc": "Bootstrap/runtime graph stages"},
    {"value": "subsystems", "label": "Subsystems", "desc": "List Python modules"},
    {"value": "commands", "label": "Commands", "desc": "Mirrored command entries"},
    {"value": "tools", "label": "Tools", "desc": "Mirrored tool entries"},
    {"value": "route", "label": "Route", "desc": "Route a prompt to commands/tools"},
    {"value": "bootstrap", "label": "Bootstrap", "desc": "Build a runtime session report"},
    {"value": "turn-loop", "label": "Turn Loop", "desc": "Run a stateful turn loop"},
]

# Commands that require a text argument
NEEDS_ARGS = {"route", "bootstrap", "turn-loop", "flush-transcript"}


def _run_cli(argv: list[str]) -> str:
    """Capture CLI output by redirecting stdout."""
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            cli_main(argv)
    except SystemExit:
        pass
    except Exception as exc:
        buf.write(f"Error: {exc}")
    return buf.getvalue()


def _get_stats() -> dict:
    """Gather quick stats for the dashboard."""
    modules = _run_cli(["subsystems", "--limit", "999"])
    commands = _run_cli(["commands", "--limit", "0"])
    tools = _run_cli(["tools", "--limit", "0"])

    def _extract_count(text: str) -> int:
        for line in text.splitlines():
            if "entries:" in line:
                for part in line.split():
                    if part.isdigit():
                        return int(part)
        return 0

    return {
        "modules": len([l for l in modules.strip().splitlines() if l.strip()]),
        "commands": _extract_count(commands),
        "tools": _extract_count(tools),
    }


@app.route("/", methods=["GET", "POST"])
def index():
    output = None
    active_cmd = ""
    active_args = ""
    active_label = ""

    # Handle quick-action card clicks
    quick = request.args.get("quick")
    if quick:
        active_cmd = quick
        active_label = next((c["label"] for c in COMMANDS if c["value"] == quick), quick)
        if quick not in NEEDS_ARGS:
            output = _run_cli([quick])
        else:
            output = f"(Enter a prompt/argument above and press Run)"

    # Handle form submission
    if request.method == "POST":
        active_cmd = request.form.get("command", "")
        active_args = request.form.get("args", "").strip()
        active_label = next((c["label"] for c in COMMANDS if c["value"] == active_cmd), active_cmd)

        argv = [active_cmd]
        if active_args:
            argv.extend(active_args.split())
        output = _run_cli(argv)

    stats = _get_stats()
    return render_template_string(
        TEMPLATE,
        commands=COMMANDS,
        output=output,
        active_cmd=active_cmd,
        active_args=active_args,
        active_label=active_label,
        stats=stats,
    )


if __name__ == "__main__":
    print("Starting Claw Code UI at http://127.0.0.1:5001")
    app.run(host="127.0.0.1", port=5001, debug=True)
