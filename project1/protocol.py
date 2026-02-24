"""
P2P Message Protocol
====================

Builders and parsers for the 8 P2P message types.
All messages are JSON dicts sent as SQS message bodies.

Every message has:
  - type:      one of MESSAGE_TYPES
  - sender:    node_id of the sender
  - timestamp: ISO 8601 UTC timestamp

Type-specific fields are documented on each builder function.
"""

import json
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Message type constants
# ---------------------------------------------------------------------------

HELLO = "HELLO"
PEER_LIST = "PEER_LIST"
PING = "PING"
PONG = "PONG"
VIEW_EVENT = "VIEW_EVENT"
AUDIT_RESULT = "AUDIT_RESULT"
CHOKE = "CHOKE"
UNCHOKE = "UNCHOKE"

ALL_TYPES = [HELLO, PEER_LIST, PING, PONG, VIEW_EVENT, AUDIT_RESULT, CHOKE, UNCHOKE]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _base(msg_type: str, sender: str) -> Dict[str, Any]:
    """Create the base message dict with common fields."""
    return {
        "type": msg_type,
        "sender": sender,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "msg_id": str(uuid.uuid4())[:8],
    }


def encode(msg: Dict[str, Any]) -> str:
    """Serialize a message dict to a JSON string (for SQS body)."""
    return json.dumps(msg)


def decode(body: str) -> Dict[str, Any]:
    """Deserialize a JSON string back to a message dict."""
    return json.loads(body)


# ---------------------------------------------------------------------------
# Message Builders
# ---------------------------------------------------------------------------

def hello(sender: str, queue_url: str) -> Dict[str, Any]:
    """
    HELLO -- initial handshake.
    Sent when a node starts up, to announce itself to a bootstrap node.

    Fields:
      queue_url: the sender's SQS queue URL so others can message it
    """
    msg = _base(HELLO, sender)
    msg["queue_url"] = queue_url
    return msg


def peer_list(sender: str, peers: List[Dict[str, str]]) -> Dict[str, Any]:
    """
    PEER_LIST -- gossip exchange.
    Shares known peers with another node.

    Fields:
      peers: list of {"node_id": str, "queue_url": str}
    """
    msg = _base(PEER_LIST, sender)
    msg["peers"] = peers
    return msg


def ping(sender: str, seq: int) -> Dict[str, Any]:
    """
    PING -- heartbeat probe.
    Sent periodically to check if a peer is alive.

    Fields:
      seq: sequence number (for matching PONG responses)
    """
    msg = _base(PING, sender)
    msg["seq"] = seq
    return msg


def pong(sender: str, seq: int) -> Dict[str, Any]:
    """
    PONG -- heartbeat response.
    Sent in reply to a PING.

    Fields:
      seq: echoed sequence number from the PING
    """
    msg = _base(PONG, sender)
    msg["seq"] = seq
    return msg


def view_event(
    sender: str,
    event_id: str,
    content_id: str,
    count: int,
    ad_id: str = "",
) -> Dict[str, Any]:
    """
    VIEW_EVENT -- a host reports a view.
    The core 2032 data message.

    Fields:
      event_id:   unique event identifier
      content_id: which content was viewed
      count:      the host's reported view count for this content
      ad_id:      (optional) associated ad
    """
    msg = _base(VIEW_EVENT, sender)
    msg["event_id"] = event_id
    msg["content_id"] = content_id
    msg["count"] = count
    msg["ad_id"] = ad_id
    return msg


def audit_result(
    sender: str,
    content_id: str,
    agreed_count: int,
    confidence: float,
    voters: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    AUDIT_RESULT -- a node's audit conclusion.
    Published after collecting VIEW_EVENTs and computing weighted majority.

    Fields:
      content_id:   which content was audited
      agreed_count: the reputation-weighted majority count
      confidence:   confidence level (0.0 to 1.0)
      voters:       (optional) list of node_ids who participated
    """
    msg = _base(AUDIT_RESULT, sender)
    msg["content_id"] = content_id
    msg["agreed_count"] = agreed_count
    msg["confidence"] = round(confidence, 4)
    msg["voters"] = voters or []
    return msg


def choke(sender: str) -> Dict[str, Any]:
    """
    CHOKE -- stop serving a peer.
    Sent when a peer is being choked (no longer receiving service).
    """
    return _base(CHOKE, sender)


def unchoke(sender: str) -> Dict[str, Any]:
    """
    UNCHOKE -- resume serving a peer.
    Sent when a peer is being unchoked (service resumed).
    """
    return _base(UNCHOKE, sender)


# ---------------------------------------------------------------------------
# Pretty printing
# ---------------------------------------------------------------------------

def format_msg(msg: Dict[str, Any], compact: bool = False) -> str:
    """Format a message for display."""
    if compact:
        t = msg.get("type", "?")
        s = msg.get("sender", "?")
        mid = msg.get("msg_id", "")
        extra = ""
        if t == HELLO:
            extra = f" queue={msg.get('queue_url', '?')[-30:]}"
        elif t == PEER_LIST:
            peers = msg.get("peers", [])
            extra = f" peers={[p['node_id'] for p in peers]}"
        elif t in (PING, PONG):
            extra = f" seq={msg.get('seq', '?')}"
        elif t == VIEW_EVENT:
            extra = f" content={msg.get('content_id', '?')} count={msg.get('count', '?')}"
        elif t == AUDIT_RESULT:
            extra = f" content={msg.get('content_id', '?')} agreed={msg.get('agreed_count', '?')}"
        return f"[{t}] {s} ({mid}){extra}"
    else:
        return json.dumps(msg, indent=2)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== P2P Message Protocol - Self Test ===\n")

    # Build one of each message type
    messages = [
        hello("hugo", "https://sqs.us-east-1.amazonaws.com/194722398367/ds2032-node-hugo-p2p"),
        peer_list("hugo", [
            {"node_id": "sam", "queue_url": "https://sqs.../ds2032-node-sam-p2p"},
            {"node_id": "phin", "queue_url": "https://sqs.../ds2032-node-phin-p2p"},
        ]),
        ping("hugo", seq=1),
        pong("sam", seq=1),
        view_event("hugo", event_id="evt-001", content_id="video-42", count=150, ad_id="ad-7"),
        audit_result("hugo", content_id="video-42", agreed_count=150, confidence=0.92, voters=["sam", "phin"]),
        choke("hugo"),
        unchoke("hugo"),
    ]

    for msg in messages:
        # Test encode/decode roundtrip
        encoded = encode(msg)
        decoded = decode(encoded)
        assert decoded == msg, f"Roundtrip failed for {msg['type']}"

        # Pretty print
        print(format_msg(msg, compact=True))

    print(f"\nAll {len(messages)} message types pass encode/decode roundtrip.")
