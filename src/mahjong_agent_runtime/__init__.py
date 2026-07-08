"""Stable public package for the current Mahjong Agent Runtime."""

from __future__ import annotations

from .budget import TokenBudget
from .context import AgentContextBuilder, ContextPackingPolicy
from .hooks import HookEvent, HookManager
from .lifecycle import ContextLifecycleManager
from .llm import AgentLLMConfig, OpenAICompatibleAgentClient, StaticAgentClient
from .loop import AgentLoop
from .models import (
    AgentAction,
    AgentRuntimeResult,
    ConversationCheckpoint,
    CustomerProfile,
    CustomerRelationship,
    Game,
    InviteDraft,
    MessageReference,
    OutboundMessageDraft,
    Party,
    PendingMemoryCandidate,
    QuotedMessageRef,
    TaskMemory,
    ToolCall,
    ToolResult,
    UserMessage,
)
from .processing import ActionProcessor, ToolExecutionService
from .runtime import AgentRuntime
from .runtime_components import ActionProcessingResult, ModelActionStep, TurnBudgets
from .sqlite_store import SQLiteAgentStore
from .store import InMemoryAgentStore
from .summary import ContextSummaryManager, ContextSummaryPolicy, ContextSummaryResult
from .tools import ToolGateway
from .tracing import InMemoryTraceRecorder, JsonlTraceRecorder, validate_trace


__all__ = [
    "AgentAction",
    "AgentContextBuilder",
    "AgentLLMConfig",
    "AgentRuntime",
    "AgentRuntimeResult",
    "AgentLoop",
    "ActionProcessingResult",
    "ActionProcessor",
    "ContextPackingPolicy",
    "ContextLifecycleManager",
    "ConversationCheckpoint",
    "ContextSummaryManager",
    "ContextSummaryPolicy",
    "ContextSummaryResult",
    "CustomerProfile",
    "CustomerRelationship",
    "Game",
    "HookEvent",
    "HookManager",
    "InMemoryAgentStore",
    "InMemoryTraceRecorder",
    "InviteDraft",
    "JsonlTraceRecorder",
    "MessageReference",
    "OpenAICompatibleAgentClient",
    "OutboundMessageDraft",
    "Party",
    "PendingMemoryCandidate",
    "QuotedMessageRef",
    "SQLiteAgentStore",
    "StaticAgentClient",
    "TaskMemory",
    "TokenBudget",
    "ToolCall",
    "ToolExecutionService",
    "ToolGateway",
    "ToolResult",
    "ModelActionStep",
    "TurnBudgets",
    "UserMessage",
    "validate_trace",
]
