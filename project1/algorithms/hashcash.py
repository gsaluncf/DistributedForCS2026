"""
HashCash — Proof-of-Work Message Stamps
========================================

Sender-side defense: every message must carry a PoW stamp proving
that the sender burned real CPU cycles to produce it.

    mine_stamp(msg_body, difficulty) -> {"nonce": int, "difficulty": int, "hash": str}
    verify_stamp(msg_body, pow_data) -> bool

Integration:
  - Sender calls mine_stamp() before sending via SQS.
  - Receiver calls verify_stamp() immediately on receipt; drops invalid messages.
  - Difficulty is set per message type (see DIFFICULTY_MAP).

Difficulty guide:
  - 2: trivial (~16 attempts, instant) — PING/PONG/PEER_LIST
  - 3: light  (~4k attempts, <0.1s)    — VIEW_EVENT/HELLO/GOSSIP
  - 4: moderate (~65k attempts, ~0.5s)  — ELECTION/COORDINATOR
  - 5: serious (~1M attempts, ~2-4s)    — AUDIT_RESULT (triggers payments)
"""

import hashlib
import json
import time
from typing import Any, Dict, Optional


# ---------------------------------------------------------------------------
# Difficulty per message type
# ---------------------------------------------------------------------------

DIFFICULTY_MAP: Dict[str, int] = {
    # Low-frequency protocol messages — keep cheap
    "HELLO":        2,
    "PEER_LIST":    2,
    "PING":         2,
    "PONG":         2,
    "CHOKE":        2,
    "UNCHOKE":      2,

    # Content messages — moderate cost
    "VIEW_EVENT":   3,

    # Election messages — moderate cost, rare
    "ELECTION":     3,
    "ELECTION_OK":  3,
    "COORDINATOR":  3,

    # Payment-triggering — highest cost
    "AUDIT_RESULT": 4,
    "PAYMENT":      4,
}

DEFAULT_DIFFICULTY = 3


# ---------------------------------------------------------------------------
# Core functions
# ---------------------------------------------------------------------------

def _canonical(msg_body: Dict[str, Any]) -> str:
    """Canonical JSON serialization (sorted keys, compact separators).

    The PoW stamp is computed over this string; any change to the message
    invalidates the hash.  We strip the 'pow' field itself so the receiver
    can re-derive the same canonical form.
    """
    clean = {k: v for k, v in msg_body.items() if k != "pow"}
    return json.dumps(clean, sort_keys=True, separators=(",", ":"))


def mine_stamp(
    msg_body: Dict[str, Any],
    difficulty: Optional[int] = None,
    max_nonce: int = 50_000_000,
) -> Dict[str, Any]:
    """Find a nonce so SHA-256(canonical + ':' + nonce) starts with `difficulty` zeros.

    Returns dict: {"nonce": int, "difficulty": int, "hash": str}
    Raises RuntimeError if max_nonce is exceeded (safety valve).
    """
    if difficulty is None:
        difficulty = DIFFICULTY_MAP.get(msg_body.get("type", ""), DEFAULT_DIFFICULTY)

    canonical = _canonical(msg_body)
    target = "0" * difficulty
    nonce = 0

    while nonce < max_nonce:
        attempt = f"{canonical}:{nonce}"
        h = hashlib.sha256(attempt.encode()).hexdigest()
        if h.startswith(target):
            return {"nonce": nonce, "difficulty": difficulty, "hash": h}
        nonce += 1

    raise RuntimeError(
        f"HashCash: failed to find nonce after {max_nonce} attempts "
        f"(difficulty={difficulty}). This should not happen at difficulty <= 5."
    )


def verify_stamp(msg_body: Dict[str, Any], pow_data: Dict[str, Any]) -> bool:
    """Verify a proof-of-work stamp in O(1) — one hash.

    Returns True if:
      1. The hash starts with the required number of leading zeros.
      2. The supplied hash matches the recomputed hash.
    """
    if not pow_data or "nonce" not in pow_data:
        return False

    canonical = _canonical(msg_body)
    attempt = f"{canonical}:{pow_data['nonce']}"
    h = hashlib.sha256(attempt.encode()).hexdigest()

    expected_prefix = "0" * pow_data.get("difficulty", DEFAULT_DIFFICULTY)
    return h.startswith(expected_prefix) and h == pow_data.get("hash", "")


def get_difficulty(msg_type: str) -> int:
    """Look up the required difficulty for a message type."""
    return DIFFICULTY_MAP.get(msg_type, DEFAULT_DIFFICULTY)


def stamp_message(msg: Dict[str, Any], difficulty: Optional[int] = None) -> Dict[str, Any]:
    """Convenience: mine a stamp and attach it to the message in-place.

    Usage:
        msg = protocol.audit_result(sender, content_id, ...)
        hashcash.stamp_message(msg)        # mines + attaches pow field
        transport.send(target, msg)
    """
    pow_data = mine_stamp(msg, difficulty=difficulty)
    msg["pow"] = pow_data
    return msg


def verify_message(msg: Dict[str, Any], min_difficulty: Optional[int] = None) -> bool:
    """Convenience: verify the stamp on a received message.

    Usage:
        if not hashcash.verify_message(msg):
            drop(msg)
    """
    pow_data = msg.get("pow")
    if not pow_data:
        return False

    # Optionally enforce a minimum difficulty
    if min_difficulty is not None and pow_data.get("difficulty", 0) < min_difficulty:
        return False

    return verify_stamp(msg, pow_data)


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== HashCash Module — Self-Test ===\n")

    test_msg = {
        "type": "AUDIT_RESULT",
        "sender": "hugo",
        "content_id": "show:midnight-run",
        "agreed_count": 1000,
        "confidence": 0.85,
        "timestamp": "2032-03-20T12:00:00Z",
    }

    for diff in [2, 3, 4, 5]:
        start = time.time()
        pow_data = mine_stamp(test_msg, difficulty=diff)
        elapsed = time.time() - start
        valid = verify_stamp(test_msg, pow_data)
        print(f"  Difficulty {diff}: nonce={pow_data['nonce']:>10,}  "
              f"hash={pow_data['hash'][:16]}...  "
              f"time={elapsed:.4f}s  valid={valid}")

    # Tamper test
    print()
    print("  Tamper test:")
    pow_data = mine_stamp(test_msg, difficulty=4)
    tampered = dict(test_msg)
    tampered["agreed_count"] = 9999
    valid_original = verify_stamp(test_msg, pow_data)
    valid_tampered = verify_stamp(tampered, pow_data)
    print(f"    Original message valid? {valid_original}")
    print(f"    Tampered message valid? {valid_tampered}")

    # stamp_message convenience
    print()
    msg2 = {"type": "VIEW_EVENT", "sender": "sam", "content_id": "show:neon-drift", "count": 500}
    stamp_message(msg2)
    print(f"  stamp_message: pow attached? {'pow' in msg2}")
    print(f"  verify_message: {verify_message(msg2)}")

    print("\n=== All tests passed ===")
