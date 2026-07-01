from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Protocol
from zoneinfo import ZoneInfo

from .models import ChannelType, Message


TZ = ZoneInfo("Asia/Shanghai")


class ControlledWorkflowServiceLike(Protocol):
    def handle_message(self, message: Message, *, now: datetime, trace_id: str) -> Any:
        ...


class TrialResponseAdapterLike(Protocol):
    def build(
        self,
        *,
        workflow_result: Any,
        source_text: str,
        sender_id: str,
        sender_name: str,
        trace_id: str,
        now: datetime,
    ) -> dict[str, Any]:
        ...


TraceIdFactory = Callable[[], str]
NowFactory = Callable[[], datetime]
DateTimeParser = Callable[[Any], datetime | None]
LifecycleRunner = Callable[[datetime], Any]
CustomerReloader = Callable[[], None]


@dataclass(frozen=True)
class TrialControlledAnalyzeRequest:
    text: str
    trace_id: str
    sender_id: str
    sender_name: str
    conversation_id: str
    now: datetime
    message: Message


@dataclass
class TrialControlledRequestBuilder:
    trace_id_factory: TraceIdFactory
    now_factory: NowFactory
    parse_datetime: DateTimeParser

    def build(self, payload: dict[str, Any]) -> TrialControlledAnalyzeRequest:
        text = str(payload.get("text") or "").strip()
        if not text:
            raise ValueError("消息不能为空")
        trace_id = str(payload.get("trace_id") or self.trace_id_factory())
        sender_id = str(payload.get("sender_id") or "trial_customer")
        sender_name = str(payload.get("sender_name") or "试用客户")
        conversation_id = str(
            payload.get("conversation_id")
            or payload.get("conversationId")
            or "boss_trial"
        ).strip() or "boss_trial"
        channel_id = str(payload.get("channel_id") or payload.get("channelId") or conversation_id).strip() or conversation_id
        channel_type = _channel_type(payload.get("channel_type") or payload.get("channelType"))
        source_message_id = _first_text(
            payload,
            "source_message_id",
            "sourceMessageId",
            "message_id",
            "messageId",
            "platform_message_id",
            "platformMessageId",
        )
        sequence = _first_value(payload, "sequence", "seq", "message_sequence", "messageSequence")
        tenant_id = _first_text(payload, "tenant_id", "tenantId", "store_id", "storeId")
        now = self.parse_datetime(payload.get("now")) or self.now_factory()
        metadata = {
            "conversation_id": conversation_id,
            "trace_id": trace_id,
            "source": "boss_trial_controlled",
        }
        if source_message_id:
            metadata["source_message_id"] = source_message_id
            metadata["message_id"] = source_message_id
        if sequence is not None:
            metadata["sequence"] = sequence
        if tenant_id:
            metadata["tenant_id"] = tenant_id
        message = Message(
            text=text,
            sender_id=sender_id,
            sender_name=sender_name,
            channel_id=channel_id,
            channel_type=channel_type,
            sent_at=now,
            metadata=metadata,
        )
        return TrialControlledAnalyzeRequest(
            text=text,
            trace_id=trace_id,
            sender_id=sender_id,
            sender_name=sender_name,
            conversation_id=conversation_id,
            now=now,
            message=message,
        )


@dataclass
class TrialControlledEntryAdapter:
    workflow_service: ControlledWorkflowServiceLike
    response_adapter: TrialResponseAdapterLike
    request_builder: TrialControlledRequestBuilder
    customer_reloader: CustomerReloader | None = None
    lifecycle_runner: LifecycleRunner | None = None

    def analyze(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.customer_reloader:
            self.customer_reloader()
        request = self.request_builder.build(payload)
        if self.lifecycle_runner:
            self.lifecycle_runner(request.now)
        workflow_result = self.workflow_service.handle_message(
            request.message,
            now=request.now,
            trace_id=request.trace_id,
        )
        return self.response_adapter.build(
            workflow_result=workflow_result,
            source_text=request.text,
            sender_id=request.sender_id,
            sender_name=request.sender_name,
            trace_id=request.trace_id,
            now=request.now,
        )


def default_trial_now() -> datetime:
    return datetime.now(TZ)


def parse_iso_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None


def _channel_type(value: Any) -> ChannelType:
    if value in (None, ""):
        return ChannelType.WEB_CONSOLE
    try:
        return ChannelType(str(value).strip())
    except ValueError:
        return ChannelType.WEB_CONSOLE


def _first_text(payload: dict[str, Any], *keys: str) -> str | None:
    value = _first_value(payload, *keys)
    if value in (None, ""):
        return None
    text = str(value).strip()
    return text or None


def _first_value(payload: dict[str, Any], *keys: str) -> Any | None:
    for key in keys:
        if key in payload:
            return payload.get(key)
    return None
    try:
        text = str(value).strip()
        if text.endswith("Z"):
            text = f"{text[:-1]}+00:00"
        return datetime.fromisoformat(text)
    except (TypeError, ValueError):
        return None
