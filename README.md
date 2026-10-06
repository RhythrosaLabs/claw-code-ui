<div align="center">

# 🦀 Claw Code UI

**Chat-first UI and real LLM integration for the Claw Code agent harness**

![Python](https://img.shields.io/badge/Python-3776AB?style=flat&logo=python&logoColor=white)
![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?style=flat&logo=streamlit&logoColor=white)
![Anthropic](https://img.shields.io/badge/Anthropic-Claude-191919?style=flat)
![OpenAI](https://img.shields.io/badge/OpenAI-412991?style=flat&logo=openai&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green?style=flat)

</div>

---

A fork of [instructkr/claw-code](https://github.com/instructkr/claw-code) — the clean-room Python rewrite of the Claw Code agent harness (109K+ stars). This fork adds a full Streamlit chat UI with real Anthropic and OpenAI API integration, streaming responses, 16+ slash commands, and a 62-test suite.

## ✨ What This Fork Adds

| Feature | Description |
|---|---|
| **Chat UI** | Streamlit chat interface — dark theme, streaming, 16+ slash commands, natural language routing |
| **LLM Client** | Provider-agnostic client — Anthropic Messages API + OpenAI Responses API, sync + streaming |
| **Model Dropdown** | Sidebar selector for latest models from both providers |
| **Dashboard** | 7-page Streamlit explorer for commands, tools, modules, architecture |
| **Conversation Memory** | Proper multi-turn history with alternating user/assistant messages |
| **62 Tests** | Full test suite covering slash commands, routing, streaming, session management |

## 🤖 Supported Models

| Provider | Models |
|---|---|
| **Anthropic** | claude-opus-4-6, claude-sonnet-4-6, claude-haiku-4-5 |
| **OpenAI** | gpt-5.4, gpt-5.4-mini, gpt-5.4-nano |

## 🚀 Quick Start

```bash
git clone https://github.com/RhythrosaLabs/claw-code-ui.git
cd claw-code-ui
pip install streamlit anthropic openai python-dotenv
cp .env.example .env  # add your API keys
streamlit run chat.py
```

## 🛠️ Tech Stack

- **Python + Streamlit** — chat UI and dashboard
- **Anthropic SDK** — Claude streaming integration
- **OpenAI SDK** — GPT streaming integration
- **pytest** — 62-test backend suite

## 🤝 Contributing

PRs welcome. Open an issue first for major changes.

## 📄 License

MIT

## 💛 Support

If this helps you build AI agents, consider supporting development:

👉 [Donate via PayPal](https://paypal.me/noodlebake) — @noodlebake

🌐 [Portfolio: rhythrosalabs.github.io](https://rhythrosalabs.github.io) (more apps, music and sound design)

---
<div align="center">Made with ❤️ by <a href="https://github.com/RhythrosaLabs">RhythrosaLabs</a></div>
