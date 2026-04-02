# Claw Code — Chat UI Fork

<p align="center">
  <img src="assets/clawd-hero.jpeg" alt="Claw" width="300" />
</p>

<p align="center">
  <strong>A chat-first UI and real LLM integration layer for the Claw Code agent harness</strong>
</p>

> **Fork of [instructkr/claw-code](https://github.com/instructkr/claw-code)** — the clean-room Python rewrite of the Claw Code agent harness (109K+ GitHub stars). This fork adds a Streamlit chat interface with real Anthropic and OpenAI API integration.

---

## What this fork adds

| Feature | Description |
|---|---|
| **Chat UI** (`chat.py`) | Streamlit-based chat interface with dark theme, streaming responses, 16+ slash commands, and natural language routing |
| **LLM Client** (`src/llm_client.py`) | Provider-agnostic client supporting **Anthropic Messages API** and **OpenAI Responses API** with both sync and streaming |
| **Model Dropdown** | Sidebar model selector with latest models from both providers |
| **Dashboard** (`app.py`) | 7-page Streamlit explorer for commands, tools, modules, and architecture |
| **Conversation Memory** | Proper alternating user/assistant message history for multi-turn conversations |
| **`.env` Config** | Secure API key management — keys stay local, never committed |
| **62 Tests** (`test_chat_ui.py`) | Full backend test suite covering all slash commands, routing, streaming, and session management |

## Supported Models

| Provider | Models | Pricing (per MTok) |
|---|---|---|
| **Anthropic** | `claude-opus-4-6`, `claude-sonnet-4-6`, `claude-haiku-4-5` | $1–$25 |
| **OpenAI** | `gpt-5.4`, `gpt-5.4-mini`, `gpt-5.4-nano` | $0.20–$15 |

## Quickstart

### 1. Install dependencies

```bash
pip install streamlit anthropic openai python-dotenv
```

### 2. Configure API keys

Copy the example and add your key(s):

```bash
cp .env.example .env
```

Edit `.env`:

```env
ANTHROPIC_API_KEY=sk-ant-api03-...
OPENAI_API_KEY=sk-proj-...
```

You only need one provider. The key you set determines which provider is available.

### 3. Launch the chat UI

```bash
streamlit run chat.py --server.port 8502
```

Open **http://localhost:8502** in your browser.

### 4. Select your model

Open the sidebar (top-left arrow) → **🤖 AI Provider** → pick provider and model → click **💾 Apply**.

If your `.env` key is set, LLM mode activates automatically on page load.

## Slash Commands

| Command | Description |
|---|---|
| `/help` | Show all available commands |
| `/status` | Session stats (model, tokens, turns) |
| `/new` / `/reset` | Start a fresh session |
| `/commands [query]` | List or search 207 mirrored commands |
| `/tools [query]` | List or search 184 mirrored tools |
| `/route <prompt>` | Route a prompt to matching commands & tools |
| `/run <prompt>` | Full bootstrap session (route → execute → persist) |
| `/exec-cmd <name>` | Execute a specific command shim |
| `/exec-tool <name>` | Execute a specific tool shim |
| `/parity` | Run parity audit against upstream |
| `/architecture` | Show bootstrap graph |
| `/subsystems` | List all Python modules |
| `/compact` | Compact session context |

Or just **type naturally** — messages are auto-routed to the best matching commands and tools, then answered by the LLM.

## Dashboard

A separate 7-page explorer for browsing the harness internals:

```bash
streamlit run app.py --server.port 8501
```

## Running Tests

```bash
python3 test_chat_ui.py
```

Expected output: `RESULTS: 62/62 passed, 0 failed`

## Architecture

```
chat.py                    # Chat UI (Streamlit)
app.py                     # Dashboard explorer (Streamlit)
src/
├── llm_client.py          # LLM client (Anthropic + OpenAI)
├── query_engine.py        # Query engine with LLM integration
├── models.py              # Data models (UsageSummary, etc.)
├── commands.py            # 207 mirrored command shims
├── tools.py               # 184 mirrored tool shims
├── runtime.py             # Routing, bootstrap sessions
├── main.py                # CLI entrypoint
└── ...                    # 60+ additional modules
rust/                      # Upstream Rust port
test_chat_ui.py            # 62-test backend suite
.env.example               # API key template
```

## How the LLM integration works

1. **User types a message** → chat.py receives it
2. **Routing** → `PortRuntime.route_prompt()` matches against 207 commands + 184 tools by keyword scoring
3. **Query engine** → `QueryEnginePort.submit_message()` builds a system prompt with workspace context, attaches the matched commands/tools, and sends to the LLM
4. **LLM responds** → streamed back through Streamlit's `st.write_stream()` with real-time rendering
5. **History** → both user and assistant messages are stored with proper roles for multi-turn context

When no API key is configured, the system falls back to a **shim mode** that returns structured routing info without making API calls.

---

## Upstream

This fork is based on [instructkr/claw-code](https://github.com/instructkr/claw-code) — a clean-room Python rewrite of the Claw Code agent harness by [@instructkr](https://github.com/instructkr), built using [oh-my-codex (OmX)](https://github.com/Yeachan-Heo/oh-my-codex). See the upstream repo for the full backstory, Rust port, and community links.

## Ownership / Affiliation Disclaimer

- This repository does **not** claim ownership of the original Claw Code source material.
- This repository is **not affiliated with, endorsed by, or maintained by the original authors**.
