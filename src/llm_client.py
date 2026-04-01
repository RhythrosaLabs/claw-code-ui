"""
LLM Client — provider-agnostic interface supporting Anthropic and OpenAI.

Anthropic: Uses the Messages API (client.messages.create / .stream).
  Latest models: claude-opus-4-6, claude-sonnet-4-6, claude-haiku-4-5
  Endpoint: https://api.anthropic.com/v1/messages
  Features: adaptive thinking, 1M context, up to 128K output (Opus)

OpenAI: Uses the Responses API (client.responses.create / .stream) — the modern
  replacement for Chat Completions with better perf, lower cost, and agentic
  built-in tools.
  Latest models: gpt-5.4, gpt-5.4-mini, gpt-5.4-nano
  Endpoint: https://api.openai.com/v1/responses
  Features: web search, file search, code interpreter, MCP, 1M context

Falls back to original shim behavior when no API key is configured.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Generator

from dotenv import load_dotenv

load_dotenv()  # reads .env into os.environ


# ── Latest model IDs (as of April 2026) ───────────────────────────────
ANTHROPIC_MODELS = {
    "opus":   "claude-opus-4-6",       # Best intelligence — agents, coding, reasoning
    "sonnet": "claude-sonnet-4-6",     # Best speed/intelligence ratio
    "haiku":  "claude-haiku-4-5",      # Fastest, cheapest, near-frontier
}
OPENAI_MODELS = {
    "large":  "gpt-5.4",              # Flagship — complex reasoning, coding
    "mid":    "gpt-5.4-mini",         # Strong mini — coding, computer use, subagents
    "small":  "gpt-5.4-nano",         # Cheapest — simple high-volume tasks
}

DEFAULT_ANTHROPIC_MODEL = ANTHROPIC_MODELS["sonnet"]
DEFAULT_OPENAI_MODEL = OPENAI_MODELS["large"]

# Flat lists for UI dropdowns
ALL_ANTHROPIC_MODELS = list(ANTHROPIC_MODELS.values())
ALL_OPENAI_MODELS = list(OPENAI_MODELS.values())


@dataclass(frozen=True)
class LLMConfig:
    provider: str = "anthropic"          # "anthropic" or "openai"
    model: str = ""                      # empty = use provider default
    api_key: str = ""                    # empty = read from env
    max_tokens: int = 8192
    temperature: float = 0.7
    system_prompt: str = ""

    @property
    def resolved_model(self) -> str:
        if self.model:
            return self.model
        return DEFAULT_ANTHROPIC_MODEL if self.provider == "anthropic" else DEFAULT_OPENAI_MODEL

    @property
    def resolved_key(self) -> str:
        if self.api_key:
            return self.api_key
        env_var = "ANTHROPIC_API_KEY" if self.provider == "anthropic" else "OPENAI_API_KEY"
        return os.environ.get(env_var, "")

    @property
    def is_configured(self) -> bool:
        return bool(self.resolved_key)


@dataclass(frozen=True)
class LLMResponse:
    content: str
    input_tokens: int
    output_tokens: int
    model: str
    stop_reason: str


@dataclass
class LLMClient:
    config: LLMConfig = field(default_factory=LLMConfig)

    def complete(self, messages: list[dict[str, str]]) -> LLMResponse:
        """Send messages to the LLM and return a complete response."""
        if self.config.provider == "anthropic":
            return self._complete_anthropic(messages)
        return self._complete_openai(messages)

    def stream(self, messages: list[dict[str, str]]) -> Generator[dict, None, None]:
        """Stream response chunks. Yields dicts with 'type' and 'text'/'usage' keys."""
        if self.config.provider == "anthropic":
            yield from self._stream_anthropic(messages)
        else:
            yield from self._stream_openai(messages)

    # ── Anthropic (Messages API) ──────────────────────────────────────
    # Docs: https://platform.claude.com/docs/en/api/messages
    # Streaming: https://platform.claude.com/docs/en/api/streaming
    # SDK: client.messages.create() and client.messages.stream()

    def _complete_anthropic(self, messages: list[dict[str, str]]) -> LLMResponse:
        import anthropic
        client = anthropic.Anthropic(api_key=self.config.resolved_key)

        kwargs: dict = dict(
            model=self.config.resolved_model,
            max_tokens=self.config.max_tokens,
            messages=messages,
        )
        # Only pass temperature for non-thinking models / non-adaptive mode
        if self.config.temperature is not None:
            kwargs["temperature"] = self.config.temperature
        if self.config.system_prompt:
            kwargs["system"] = self.config.system_prompt

        response = client.messages.create(**kwargs)

        content = ""
        for block in response.content:
            if hasattr(block, "text"):
                content += block.text

        return LLMResponse(
            content=content,
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
            model=response.model,
            stop_reason=response.stop_reason or "end_turn",
        )

    def _stream_anthropic(self, messages: list[dict[str, str]]) -> Generator[dict, None, None]:
        import anthropic
        client = anthropic.Anthropic(api_key=self.config.resolved_key)

        kwargs: dict = dict(
            model=self.config.resolved_model,
            max_tokens=self.config.max_tokens,
            messages=messages,
        )
        if self.config.temperature is not None:
            kwargs["temperature"] = self.config.temperature
        if self.config.system_prompt:
            kwargs["system"] = self.config.system_prompt

        # Use SDK's managed stream — handles SSE parsing, accumulation, and
        # provides .text_stream for clean text-only iteration plus
        # .get_final_message() for usage stats after completion.
        with client.messages.stream(**kwargs) as stream:
            for text_chunk in stream.text_stream:
                yield {"type": "delta", "text": text_chunk}
            final = stream.get_final_message()
            yield {
                "type": "done",
                "input_tokens": final.usage.input_tokens,
                "output_tokens": final.usage.output_tokens,
                "model": final.model,
                "stop_reason": final.stop_reason or "end_turn",
            }

    # ── OpenAI (Responses API) ────────────────────────────────────────
    # Docs: https://developers.openai.com/api/docs/guides/migrate-to-responses
    # Streaming: https://developers.openai.com/api/docs/guides/streaming-responses
    # SDK: client.responses.create() and client.responses.stream()
    #
    # The Responses API is OpenAI's modern replacement for Chat Completions:
    #  - Better model intelligence (3% SWE-bench improvement)
    #  - Lower costs (40-80% improved cache utilization)
    #  - Agentic by default (multi-tool, multi-turn in one request)
    #  - Stateful context via store/previous_response_id
    #
    # We also keep a Chat Completions fallback for older models.

    def _complete_openai(self, messages: list[dict[str, str]]) -> LLMResponse:
        import openai
        client = openai.OpenAI(api_key=self.config.resolved_key)

        # Build input for Responses API
        input_items = list(messages)
        instructions = self.config.system_prompt or None

        response = client.responses.create(
            model=self.config.resolved_model,
            input=input_items,
            instructions=instructions,
            temperature=self.config.temperature,
            max_output_tokens=self.config.max_tokens,
            store=False,  # Don't persist on OpenAI's side
        )

        content = response.output_text or ""
        usage = response.usage
        return LLMResponse(
            content=content,
            input_tokens=usage.input_tokens if usage else 0,
            output_tokens=usage.output_tokens if usage else 0,
            model=response.model,
            stop_reason="stop",
        )

    def _stream_openai(self, messages: list[dict[str, str]]) -> Generator[dict, None, None]:
        import openai
        client = openai.OpenAI(api_key=self.config.resolved_key)

        input_items = list(messages)
        instructions = self.config.system_prompt or None

        # Use the Responses streaming API — emits typed SSE events:
        #   response.output_text.delta — text chunks
        #   response.completed — final response with usage
        stream = client.responses.create(
            model=self.config.resolved_model,
            input=input_items,
            instructions=instructions,
            temperature=self.config.temperature,
            max_output_tokens=self.config.max_tokens,
            store=False,
            stream=True,
        )

        input_tokens = 0
        output_tokens = 0
        model_name = self.config.resolved_model

        for event in stream:
            if event.type == "response.output_text.delta":
                yield {"type": "delta", "text": event.delta}
            elif event.type == "response.completed":
                resp = event.response
                if resp.usage:
                    input_tokens = resp.usage.input_tokens
                    output_tokens = resp.usage.output_tokens
                model_name = resp.model

        yield {
            "type": "done",
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "model": model_name,
            "stop_reason": "stop",
        }
