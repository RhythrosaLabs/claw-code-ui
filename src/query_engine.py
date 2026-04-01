from __future__ import annotations

import json
from dataclasses import dataclass, field
from uuid import uuid4

from .commands import build_command_backlog
from .llm_client import LLMClient, LLMConfig
from .models import PermissionDenial, UsageSummary
from .port_manifest import PortManifest, build_port_manifest
from .session_store import StoredSession, load_session, save_session
from .tools import build_tool_backlog
from .transcript import TranscriptStore


@dataclass(frozen=True)
class QueryEngineConfig:
    max_turns: int = 8
    max_budget_tokens: int = 2000
    compact_after_turns: int = 12
    structured_output: bool = False
    structured_retry_limit: int = 2


@dataclass(frozen=True)
class TurnResult:
    prompt: str
    output: str
    matched_commands: tuple[str, ...]
    matched_tools: tuple[str, ...]
    permission_denials: tuple[PermissionDenial, ...]
    usage: UsageSummary
    stop_reason: str


@dataclass
class QueryEnginePort:
    manifest: PortManifest
    config: QueryEngineConfig = field(default_factory=QueryEngineConfig)
    session_id: str = field(default_factory=lambda: uuid4().hex)
    mutable_messages: list[str] = field(default_factory=list)
    permission_denials: list[PermissionDenial] = field(default_factory=list)
    total_usage: UsageSummary = field(default_factory=UsageSummary)
    transcript_store: TranscriptStore = field(default_factory=TranscriptStore)
    llm_config: LLMConfig = field(default_factory=LLMConfig)
    _llm_client: LLMClient | None = field(default=None, repr=False)
    _llm_enabled: bool = field(default=False, repr=False)

    @property
    def llm_client(self) -> LLMClient | None:
        if not self._llm_enabled:
            return None
        if self._llm_client is not None:
            return self._llm_client
        if self.llm_config.is_configured:
            self._llm_client = LLMClient(config=self.llm_config)
            return self._llm_client
        return None

    @property
    def llm_active(self) -> bool:
        return self.llm_client is not None

    def set_llm_config(self, config: LLMConfig) -> None:
        self.llm_config = config
        self._llm_client = None  # reset so it picks up new config
        self._llm_enabled = config.is_configured

    def _build_system_prompt(self) -> str:
        n_cmds = len(build_command_backlog().modules)
        n_tools = len(build_tool_backlog().modules)
        n_files = self.manifest.total_python_files
        n_mods = len(self.manifest.top_level_modules)
        return (
            "You are Claw Code, an AI coding agent assistant. "
            "You help users explore, understand, and work with their codebase.\n\n"
            f"Workspace: {n_files} Python files across {n_mods} modules, "
            f"{n_cmds} commands, {n_tools} tools.\n\n"
            "Guidelines:\n"
            "- Answer the user's question directly and concisely.\n"
            "- When matched commands or tools are provided in context, explain what they do and how they relate to the question.\n"
            "- Format responses in Markdown. Use code blocks for code.\n"
            "- If you don't know something, say so rather than guessing.\n"
            "- Be helpful and practical — focus on what the user can do next."
        )

    def _build_llm_messages(self, prompt: str, matched_commands: tuple[str, ...], matched_tools: tuple[str, ...]) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        # Include recent conversation history with proper alternating roles
        history = self.mutable_messages[-20:]  # last 20 entries
        for entry in history:
            role = entry.get("role", "user") if isinstance(entry, dict) else "user"
            content = entry.get("content", entry) if isinstance(entry, dict) else entry
            messages.append({"role": role, "content": content})
        # Add routing context if available
        context_parts = []
        if matched_commands:
            context_parts.append(f"Matched commands: {', '.join(matched_commands)}")
        if matched_tools:
            context_parts.append(f"Matched tools: {', '.join(matched_tools)}")
        user_content = prompt
        if context_parts:
            user_content = f"[Context: {'; '.join(context_parts)}]\n\n{prompt}"
        messages.append({"role": "user", "content": user_content})
        return messages

    @classmethod
    def from_workspace(cls) -> 'QueryEnginePort':
        return cls(manifest=build_port_manifest())

    @classmethod
    def from_saved_session(cls, session_id: str) -> 'QueryEnginePort':
        stored = load_session(session_id)
        transcript = TranscriptStore(entries=list(stored.messages), flushed=True)
        return cls(
            manifest=build_port_manifest(),
            session_id=stored.session_id,
            mutable_messages=list(stored.messages),
            total_usage=UsageSummary(stored.input_tokens, stored.output_tokens),
            transcript_store=transcript,
        )

    def submit_message(
        self,
        prompt: str,
        matched_commands: tuple[str, ...] = (),
        matched_tools: tuple[str, ...] = (),
        denied_tools: tuple[PermissionDenial, ...] = (),
    ) -> TurnResult:
        if len(self.mutable_messages) >= self.config.max_turns:
            output = f'Max turns reached before processing prompt: {prompt}'
            return TurnResult(
                prompt=prompt,
                output=output,
                matched_commands=matched_commands,
                matched_tools=matched_tools,
                permission_denials=denied_tools,
                usage=self.total_usage,
                stop_reason='max_turns_reached',
            )

        # ── Real LLM call if configured ─────────────────────────────
        if self.llm_active:
            return self._submit_with_llm(prompt, matched_commands, matched_tools, denied_tools)

        # ── Shim fallback ───────────────────────────────────────────
        summary_lines = [
            f'Prompt: {prompt}',
            f'Matched commands: {", ".join(matched_commands) if matched_commands else "none"}',
            f'Matched tools: {", ".join(matched_tools) if matched_tools else "none"}',
            f'Permission denials: {len(denied_tools)}',
        ]
        output = self._format_output(summary_lines)
        projected_usage = self.total_usage.add_turn(prompt, output)
        stop_reason = 'completed'
        if projected_usage.input_tokens + projected_usage.output_tokens > self.config.max_budget_tokens:
            stop_reason = 'max_budget_reached'
        self.mutable_messages.append(prompt)
        self.transcript_store.append(prompt)
        self.permission_denials.extend(denied_tools)
        self.total_usage = projected_usage
        self.compact_messages_if_needed()
        return TurnResult(
            prompt=prompt,
            output=output,
            matched_commands=matched_commands,
            matched_tools=matched_tools,
            permission_denials=denied_tools,
            usage=self.total_usage,
            stop_reason=stop_reason,
        )

    def _submit_with_llm(
        self,
        prompt: str,
        matched_commands: tuple[str, ...],
        matched_tools: tuple[str, ...],
        denied_tools: tuple[PermissionDenial, ...],
    ) -> TurnResult:
        client = self.llm_client
        system = self._build_system_prompt()
        messages = self._build_llm_messages(prompt, matched_commands, matched_tools)

        # Update client system prompt
        client.config = LLMConfig(
            provider=self.llm_config.provider,
            model=self.llm_config.model,
            api_key=self.llm_config.api_key,
            max_tokens=self.llm_config.max_tokens,
            temperature=self.llm_config.temperature,
            system_prompt=system,
        )

        response = client.complete(messages)
        output = response.content
        self.total_usage = self.total_usage.add_actual(response.input_tokens, response.output_tokens)
        stop_reason = response.stop_reason

        self.mutable_messages.append({"role": "user", "content": prompt})
        self.mutable_messages.append({"role": "assistant", "content": output})
        self.transcript_store.append(prompt)
        self.permission_denials.extend(denied_tools)
        self.compact_messages_if_needed()

        return TurnResult(
            prompt=prompt,
            output=output,
            matched_commands=matched_commands,
            matched_tools=matched_tools,
            permission_denials=denied_tools,
            usage=self.total_usage,
            stop_reason=stop_reason,
        )

    def stream_submit_message(
        self,
        prompt: str,
        matched_commands: tuple[str, ...] = (),
        matched_tools: tuple[str, ...] = (),
        denied_tools: tuple[PermissionDenial, ...] = (),
    ):
        yield {'type': 'message_start', 'session_id': self.session_id, 'prompt': prompt}
        if matched_commands:
            yield {'type': 'command_match', 'commands': matched_commands}
        if matched_tools:
            yield {'type': 'tool_match', 'tools': matched_tools}
        if denied_tools:
            yield {'type': 'permission_denial', 'denials': [denial.tool_name for denial in denied_tools]}

        # ── Real LLM streaming if configured ────────────────────────
        if self.llm_active:
            yield from self._stream_with_llm(prompt, matched_commands, matched_tools, denied_tools)
            return

        # ── Shim fallback ───────────────────────────────────────────
        result = self.submit_message(prompt, matched_commands, matched_tools, denied_tools)
        yield {'type': 'message_delta', 'text': result.output}
        yield {
            'type': 'message_stop',
            'usage': {'input_tokens': result.usage.input_tokens, 'output_tokens': result.usage.output_tokens},
            'stop_reason': result.stop_reason,
            'transcript_size': len(self.transcript_store.entries),
        }

    def _stream_with_llm(
        self,
        prompt: str,
        matched_commands: tuple[str, ...],
        matched_tools: tuple[str, ...],
        denied_tools: tuple[PermissionDenial, ...],
    ):
        client = self.llm_client
        system = self._build_system_prompt()
        messages = self._build_llm_messages(prompt, matched_commands, matched_tools)

        client.config = LLMConfig(
            provider=self.llm_config.provider,
            model=self.llm_config.model,
            api_key=self.llm_config.api_key,
            max_tokens=self.llm_config.max_tokens,
            temperature=self.llm_config.temperature,
            system_prompt=system,
        )

        full_output = ""
        for event in client.stream(messages):
            if event["type"] == "delta":
                full_output += event["text"]
                yield {'type': 'message_delta', 'text': event["text"]}
            elif event["type"] == "done":
                self.total_usage = self.total_usage.add_actual(
                    event["input_tokens"], event["output_tokens"]
                )
                self.mutable_messages.append({"role": "user", "content": prompt})
                self.mutable_messages.append({"role": "assistant", "content": full_output})
                self.transcript_store.append(prompt)
                self.permission_denials.extend(denied_tools)
                self.compact_messages_if_needed()
                yield {
                    'type': 'message_stop',
                    'usage': {'input_tokens': self.total_usage.input_tokens, 'output_tokens': self.total_usage.output_tokens},
                    'stop_reason': event.get("stop_reason", "end_turn"),
                    'transcript_size': len(self.transcript_store.entries),
                }

    def compact_messages_if_needed(self) -> None:
        if len(self.mutable_messages) > self.config.compact_after_turns:
            self.mutable_messages[:] = self.mutable_messages[-self.config.compact_after_turns :]
        self.transcript_store.compact(self.config.compact_after_turns)

    def replay_user_messages(self) -> tuple[str, ...]:
        return self.transcript_store.replay()

    def flush_transcript(self) -> None:
        self.transcript_store.flush()

    def persist_session(self) -> str:
        self.flush_transcript()
        path = save_session(
            StoredSession(
                session_id=self.session_id,
                messages=tuple(self.mutable_messages),
                input_tokens=self.total_usage.input_tokens,
                output_tokens=self.total_usage.output_tokens,
            )
        )
        return str(path)

    def _format_output(self, summary_lines: list[str]) -> str:
        if self.config.structured_output:
            payload = {
                'summary': summary_lines,
                'session_id': self.session_id,
            }
            return self._render_structured_output(payload)
        return '\n'.join(summary_lines)

    def _render_structured_output(self, payload: dict[str, object]) -> str:
        last_error: Exception | None = None
        for _ in range(self.config.structured_retry_limit):
            try:
                return json.dumps(payload, indent=2)
            except (TypeError, ValueError) as exc:  # pragma: no cover - defensive branch
                last_error = exc
                payload = {'summary': ['structured output retry'], 'session_id': self.session_id}
        raise RuntimeError('structured output rendering failed') from last_error

    def render_summary(self) -> str:
        command_backlog = build_command_backlog()
        tool_backlog = build_tool_backlog()
        sections = [
            '# Python Porting Workspace Summary',
            '',
            self.manifest.to_markdown(),
            '',
            f'Command surface: {len(command_backlog.modules)} mirrored entries',
            *command_backlog.summary_lines()[:10],
            '',
            f'Tool surface: {len(tool_backlog.modules)} mirrored entries',
            *tool_backlog.summary_lines()[:10],
            '',
            f'Session id: {self.session_id}',
            f'Conversation turns stored: {len(self.mutable_messages)}',
            f'Permission denials tracked: {len(self.permission_denials)}',
            f'Usage totals: in={self.total_usage.input_tokens} out={self.total_usage.output_tokens}',
            f'Max turns: {self.config.max_turns}',
            f'Max budget tokens: {self.config.max_budget_tokens}',
            f'Transcript flushed: {self.transcript_store.flushed}',
        ]
        return '\n'.join(sections)
