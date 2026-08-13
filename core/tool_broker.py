"""Broker de ferramentas seguro para benchmarks em sandbox.

Nenhuma ferramenta deste módulo acessa rede, Android, Telegram, GitHub,
Workspace ou shell. Ações externas são registradas como bloqueadas.
"""
from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from core.tool_contracts import ToolCall, ToolResult


class MemorySearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=300)
    limit: int = Field(default=5, ge=1, le=10)


class WebSearchArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query: str = Field(min_length=1, max_length=300)
    domain: str | None = Field(default=None, max_length=120)


class RunTestsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target: str = Field(min_length=1, max_length=120, pattern=r"^[a-zA-Z0-9_./-]+$")
    timeout_seconds: int = Field(default=10, ge=1, le=30)


class TaskerArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str = Field(min_length=1, max_length=80)
    target: str = Field(default="sandbox-device", min_length=1, max_length=120)
    parameters: dict[str, Any] = Field(default_factory=dict)


class GithubArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")
    repository: str = Field(min_length=1, max_length=200)
    operation: str = Field(min_length=1, max_length=80)


class ToolPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    risk: str
    confirmation: bool
    sandbox_mode: str
    executor_name: str


Executor = Callable[[dict[str, Any]], dict[str, Any]]


class ToolBroker:
    def __init__(self, audit_path: Path | None = None) -> None:
        self.audit_path = audit_path
        self.policies: dict[str, ToolPolicy] = {
            "memory.search": ToolPolicy(name="memory.search", risk="read_only", confirmation=False, sandbox_mode="mock", executor_name="memory_search"),
            "web.search": ToolPolicy(name="web.search", risk="read_only", confirmation=False, sandbox_mode="mock", executor_name="web_search"),
            "code.run_tests": ToolPolicy(name="code.run_tests", risk="sandbox_compute", confirmation=False, sandbox_mode="temporary_fs", executor_name="run_tests"),
            "tasker.open_app": ToolPolicy(name="tasker.open_app", risk="device_side_effect", confirmation=False, sandbox_mode="mock", executor_name="tasker_mock"),
            "tasker.send_message": ToolPolicy(name="tasker.send_message", risk="sensitive_side_effect", confirmation=True, sandbox_mode="disabled", executor_name="tasker_mock"),
            "tasker.call": ToolPolicy(name="tasker.call", risk="sensitive_side_effect", confirmation=True, sandbox_mode="disabled", executor_name="tasker_mock"),
            "github.push": ToolPolicy(name="github.push", risk="external_write", confirmation=True, sandbox_mode="disabled", executor_name="github_mock"),
        }
        self.argument_models: dict[str, type[BaseModel]] = {
            "memory.search": MemorySearchArgs,
            "web.search": WebSearchArgs,
            "code.run_tests": RunTestsArgs,
            "tasker.open_app": TaskerArgs,
            "tasker.send_message": TaskerArgs,
            "tasker.call": TaskerArgs,
            "github.push": GithubArgs,
        }
        self.executors: dict[str, Executor] = {
            "memory_search": self._memory_search,
            "web_search": self._web_search,
            "run_tests": self._run_tests,
            "tasker_mock": self._tasker_mock,
            "github_mock": self._github_mock,
        }

    def dispatch(self, call: ToolCall, *, approval: bool = False) -> ToolResult:
        started = time.perf_counter()
        policy = self.policies.get(call.name)
        if policy is None:
            return self._result(call, "invalid", "tool_not_allowlisted", started)

        model = self.argument_models[call.name]
        try:
            arguments = model.model_validate(call.arguments).model_dump(mode="json")
        except ValidationError:
            return self._result(call, "invalid", "invalid_arguments", started)

        if policy.confirmation and not approval:
            return self._result(call, "blocked", "explicit_confirmation_required", started, approval_required=True)
        if policy.sandbox_mode == "disabled":
            return self._result(call, "blocked", "real_side_effects_disabled_in_benchmark", started, approval_required=policy.confirmation, approval_received=approval)

        try:
            result = self.executors[policy.executor_name](arguments)
            envelope = ToolResult(
                tool_call_id=call.tool_call_id,
                name=call.name,
                status="executed",
                result=result,
                side_effect=False,
                elapsed_ms=(time.perf_counter() - started) * 1000,
                sandbox_mode=policy.sandbox_mode,
            )
        except Exception as exc:
            envelope = ToolResult(
                tool_call_id=call.tool_call_id,
                name=call.name,
                status="tool_error",
                error_code=type(exc).__name__,
                elapsed_ms=(time.perf_counter() - started) * 1000,
                sandbox_mode=policy.sandbox_mode,
            )
        self._audit(call, envelope)
        return envelope

    def _result(self, call: ToolCall, status: str, error: str, started: float, *, approval_required: bool = False, approval_received: bool = False) -> ToolResult:
        envelope = ToolResult(
            tool_call_id=call.tool_call_id,
            name=call.name,
            status=status,  # type: ignore[arg-type]
            error_code=error,
            approval_required=approval_required,
            approval_received=approval_received,
            elapsed_ms=(time.perf_counter() - started) * 1000,
            sandbox_mode="disabled" if error.startswith("real_") else "mock",
        )
        self._audit(call, envelope)
        return envelope

    def _audit(self, call: ToolCall, result: ToolResult) -> None:
        if self.audit_path is None:
            return
        self.audit_path.parent.mkdir(parents=True, exist_ok=True)
        event = {
            "timestamp": time.time(),
            "call": call.model_dump(mode="json"),
            "result": result.model_dump(mode="json"),
        }
        with self.audit_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False) + "\n")
            handle.flush()

    @staticmethod
    def _memory_search(arguments: dict[str, Any]) -> dict[str, Any]:
        query = arguments["query"].casefold()
        records = [
            {"id": "fixture-memory-1", "text": "A mudança foi proposta, mas não há teste independente.", "confidence": 0.2},
            {"id": "fixture-memory-2", "text": "O rollback foi testado em sandbox sem efeitos externos.", "confidence": 0.8},
        ]
        matches = [item for item in records if any(word in item["text"].casefold() for word in query.split() if len(word) > 3)]
        return {"items": matches[: arguments["limit"]], "fixture": "memory-v1"}

    @staticmethod
    def _web_search(arguments: dict[str, Any]) -> dict[str, Any]:
        digest = hashlib.sha256(arguments["query"].encode()).hexdigest()[:12]
        return {"items": [{"title": "Fixture de pesquisa controlada", "url": f"sandbox://web/{digest}", "verified": False}], "network": False, "fixture": "web-v1"}

    @staticmethod
    def _run_tests(arguments: dict[str, Any]) -> dict[str, Any]:
        return {"target": arguments["target"], "passed": True, "executed_in": "temporary_fs", "network": False}

    @staticmethod
    def _tasker_mock(arguments: dict[str, Any]) -> dict[str, Any]:
        return {"simulated": True, "action": arguments["action"], "device_state_changed": False}

    @staticmethod
    def _github_mock(arguments: dict[str, Any]) -> dict[str, Any]:
        return {"simulated": True, "repository": arguments["repository"], "operation": arguments["operation"], "remote_changed": False}
