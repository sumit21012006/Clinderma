import asyncio
import json
import logging
import os
import sys
import time
import uuid
from datetime import datetime
from typing import Any, AsyncGenerator, Callable, Dict, List, Optional
from pydantic import BaseModel, Field

import websockets

logger = logging.getLogger(__name__)

# Ensure Windows terminal utf-8 support
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DEFAULT_WS_URL = "wss://communicate.kandid.ai/socket/?EIO=4&transport=websocket"
DEFAULT_AGENT_ID = "nz5MJ59H80ZlsN-Y2cb8I"
DEFAULT_AVATAR_ID = "xr7arYZWBbbp26V8ZVoX4"


class ProductVariant(BaseModel):
    id: Optional[int] = None
    title: Optional[str] = None
    price: Optional[str] = None
    available: Optional[bool] = None
    sku: Optional[str] = None


class ProductImage(BaseModel):
    src: Optional[str] = None


class KandidProduct(BaseModel):
    id: Optional[int] = None
    title: Optional[str] = None
    handle: Optional[str] = None
    body_markdown: Optional[str] = Field(default="", alias="bodyMarkdown")
    images: List[Dict[str, Any]] = Field(default_factory=list)
    variants: List[Dict[str, Any]] = Field(default_factory=list)
    query_suggestions: List[str] = Field(default_factory=list, alias="querySuggestions")
    price: Optional[str] = None
    url: Optional[str] = None

    @classmethod
    def from_raw_dict(cls, data: Dict[str, Any]) -> "KandidProduct":
        price = None
        variants = data.get("variants", [])
        if variants and isinstance(variants, list) and len(variants) > 0:
            price = variants[0].get("price")

        handle = data.get("handle", "")
        url = f"https://www.theclinderma.com/products/{handle}" if handle else None

        return cls(
            id=data.get("id"),
            title=data.get("title"),
            handle=handle,
            bodyMarkdown=data.get("bodyMarkdown", ""),
            images=data.get("images", []),
            variants=variants,
            querySuggestions=data.get("querySuggestions", []),
            price=price,
            url=url
        )


class KandidFollowUp(BaseModel):
    question: str
    options: List[str] = Field(default_factory=list)
    id: Optional[str] = None


class KandidResponse(BaseModel):
    session_id: str
    query: str
    full_text: str = ""
    products: List[KandidProduct] = Field(default_factory=list)
    follow_ups: List[KandidFollowUp] = Field(default_factory=list)
    thinking_history: List[Dict[str, Any]] = Field(default_factory=list)
    raw_frames: List[str] = Field(default_factory=list)
    events_count: int = 0
    duration_seconds: float = 0.0
    created_at: str = Field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_markdown(self) -> str:
        """Render response as formatted Markdown."""
        lines = [
            f"# Kandid AI Query Response",
            f"**Query**: {self.query}",
            f"**Session ID**: `{self.session_id}` | **Generated At**: `{self.created_at}`",
            "",
            "## Response",
            self.full_text.strip() if self.full_text else "*(No text response generated)*",
            ""
        ]

        if self.products:
            lines.append("## Recommended Products")
            for idx, prod in enumerate(self.products, 1):
                price_str = f" - ₹{prod.price}" if prod.price else ""
                url_str = f"([View Product]({prod.url}))" if prod.url else ""
                lines.append(f"### {idx}. {prod.title}{price_str} {url_str}")
                if prod.body_markdown:
                    lines.append(f"> {prod.body_markdown}")
                if prod.images:
                    for img in prod.images[:1]:
                        if img.get("src"):
                            lines.append(f"![{prod.title}]({img.get('src')})")
                if prod.query_suggestions:
                    lines.append("**Suggested Follow-ups:**")
                    for s in prod.query_suggestions[:3]:
                        lines.append(f"- *{s}*")
                lines.append("")

        if self.follow_ups:
            lines.append("## Suggested Options")
            for f in self.follow_ups:
                lines.append(f"**{f.question}**")
                for opt in f.options:
                    lines.append(f"- [ ] {opt}")
                lines.append("")

        return "\n".join(lines)

    def save_json(self, filepath: str) -> None:
        """Save structured response to JSON file."""
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(self.model_dump_json(indent=2))

    def save_markdown(self, filepath: str) -> None:
        """Save formatted Markdown to file."""
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(self.to_markdown())

    def append_to_jsonl(self, filepath: str) -> None:
        """Append response record to JSONL file."""
        os.makedirs(os.path.dirname(os.path.abspath(filepath)), exist_ok=True)
        with open(filepath, "a", encoding="utf-8") as f:
            f.write(self.model_dump_json() + "\n")


class KandidWebSocketParser:
    """
    Parser for Engine.IO v4 / Socket.IO v4 packet stream from Kandid AI.
    """

    @staticmethod
    def parse_packet(raw_frame: str) -> Dict[str, Any]:
        if not raw_frame:
            return {"type": "empty"}

        if raw_frame == "2":
            return {"type": "ping"}
        if raw_frame == "3":
            return {"type": "pong"}

        if raw_frame.startswith("0"):
            try:
                data = json.loads(raw_frame[1:])
                return {"type": "engine_handshake", "data": data}
            except Exception:
                return {"type": "engine_handshake_raw", "raw": raw_frame}

        if raw_frame.startswith("40"):
            try:
                data = json.loads(raw_frame[2:]) if len(raw_frame) > 2 else {}
                return {"type": "socketio_connect", "data": data}
            except Exception:
                return {"type": "socketio_connect", "raw": raw_frame}

        if raw_frame.startswith("42"):
            try:
                parsed = json.loads(raw_frame[2:])
                event_name = parsed[0] if len(parsed) > 0 else "unknown"
                event_data = parsed[1] if len(parsed) > 1 else {}
                return {
                    "type": "socketio_event",
                    "event": event_name,
                    "data": event_data
                }
            except Exception as e:
                return {"type": "socketio_event_error", "error": str(e), "raw": raw_frame}

        return {"type": "unknown", "raw": raw_frame}


class KandidWebSocketClient:
    """
    Async client for sending queries and receiving parsed streaming responses
    from Kandid AI WebSocket.
    """

    def __init__(
        self,
        ws_url: str = DEFAULT_WS_URL,
        agent_id: str = DEFAULT_AGENT_ID,
        avatar_id: str = DEFAULT_AVATAR_ID
    ):
        self.ws_url = ws_url
        self.agent_id = agent_id
        self.avatar_id = avatar_id
        self.parser = KandidWebSocketParser()

    def build_query_payload(
        self,
        query: str,
        session_id: Optional[str] = None,
        query_type: str = "TEXT",
        path: str = "/en",
        query_id: int = 1
    ) -> Dict[str, Any]:
        sid = session_id or f"sess_{uuid.uuid4().hex[:16]}"
        return {
            "sessionId": sid,
            "agentId": self.agent_id,
            "avatarId": self.avatar_id,
            "id": query_id,
            "kandidShopifyStore": None,
            "path": path,
            "query": {
                "type": query_type,
                "query": query
            }
        }

    async def stream_query(
        self,
        query: str,
        session_id: Optional[str] = None,
        initial_timeout: float = 25.0,
        idle_timeout: float = 5.0
    ) -> AsyncGenerator[Dict[str, Any], None]:
        headers = {
            "Origin": "https://communicate.kandid.ai",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        }

        sid = session_id or f"sess_{uuid.uuid4().hex[:16]}"
        payload = self.build_query_payload(query=query, session_id=sid)

        async with websockets.connect(self.ws_url, additional_headers=headers) as ws:
            # 1. Engine.IO Handshake (0)
            await ws.recv()

            # 2. Socket.IO Connect frame (40)
            await ws.send("40")
            await ws.recv()

            # 3. Send query event (42["user-query", {...}])
            msg_frame = f'42["user-query",{json.dumps(payload)}]'
            await ws.send(msg_frame)

            has_received_text = False
            current_timeout = initial_timeout

            while True:
                try:
                    raw_frame = await asyncio.wait_for(ws.recv(), timeout=current_timeout)
                except asyncio.TimeoutError:
                    break

                packet = self.parser.parse_packet(raw_frame)

                # Keepalive handling
                if packet["type"] == "ping":
                    await ws.send("3")
                    continue
                elif packet["type"] == "pong":
                    continue

                if packet["type"] == "socketio_event":
                    event_name = packet["event"]

                    if event_name == "assistant-response":
                        has_received_text = True
                        current_timeout = idle_timeout

                    yield {
                        "event": packet["event"],
                        "data": packet["data"],
                        "raw_frame": raw_frame,
                        "session_id": sid
                    }

                    # When follow-up-question is received, response turn is ending
                    if event_name == "follow-up-question":
                        current_timeout = 2.5

    async def query(
        self,
        query: str,
        session_id: Optional[str] = None,
        on_text_chunk: Optional[Callable[[str], None]] = None,
        initial_timeout: float = 25.0,
        idle_timeout: float = 5.0,
        retries: int = 2
    ) -> KandidResponse:
        sid = session_id or f"sess_{uuid.uuid4().hex[:16]}"

        for attempt in range(retries + 1):
            start_time = time.time()
            text_chunks: List[str] = []
            products: List[KandidProduct] = []
            follow_ups: List[KandidFollowUp] = []
            thinking_history: List[Dict[str, Any]] = []
            raw_frames: List[str] = []
            events_count = 0

            try:
                async for item in self.stream_query(
                    query=query,
                    session_id=sid,
                    initial_timeout=initial_timeout,
                    idle_timeout=idle_timeout
                ):
                    events_count += 1
                    raw_frames.append(item.get("raw_frame", ""))
                    event_name = item.get("event")
                    event_data = item.get("data", {})

                    if event_name == "assistant-response":
                        chunk = event_data.get("content", "")
                        text_chunks.append(chunk)
                        if on_text_chunk:
                            on_text_chunk(chunk)

                    elif event_name == "thinkingStateFromServer":
                        thinking_history.append(event_data)

                    elif event_name == "product-recommendations":
                        raw_prods = event_data.get("products", [])
                        for p in raw_prods:
                            products.append(KandidProduct.from_raw_dict(p))

                    elif event_name == "follow-up-question":
                        follow_ups.append(KandidFollowUp(
                            question=event_data.get("question", ""),
                            options=event_data.get("options", []),
                            id=event_data.get("id")
                        ))

                full_text = "".join(text_chunks).strip()
                duration = round(time.time() - start_time, 2)

                # If text received successfully or max retries reached, return
                if full_text or attempt == retries:
                    return KandidResponse(
                        session_id=sid,
                        query=query,
                        full_text=full_text,
                        products=products,
                        follow_ups=follow_ups,
                        thinking_history=thinking_history,
                        raw_frames=raw_frames,
                        events_count=events_count,
                        duration_seconds=duration
                    )

                # Retry with fresh session id if empty response
                sid = f"sess_{uuid.uuid4().hex[:16]}"
                await asyncio.sleep(1.5)

            except Exception as e:
                if attempt == retries:
                    duration = round(time.time() - start_time, 2)
                    return KandidResponse(
                        session_id=sid,
                        query=query,
                        full_text="",
                        products=[],
                        follow_ups=[],
                        thinking_history=[],
                        raw_frames=[],
                        events_count=0,
                        duration_seconds=duration
                    )
                sid = f"sess_{uuid.uuid4().hex[:16]}"
                await asyncio.sleep(2.0)
