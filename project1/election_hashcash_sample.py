"""
Election + HashCash Sample Code
================================

This file demonstrates the NEW protocol features that bots now support.
Use this as a reference for understanding and integrating with the updated
bot infrastructure.

New capabilities:
  1. Leader Election   — Bots elect a Payment Server via reputation-weighted Bully
  2. HashCash (PoW)    — Messages carry proof-of-work stamps to prevent spam
  3. Payment messages  — The elected Payment Server issues PAYMENT confirmations

Run this file:
    python election_hashcash_sample.py

No AWS credentials needed — this runs entirely in-process.
"""

import hashlib
import json
import time
import sys
import os

# Add parent directory to path so we can import project modules
sys.path.insert(0, os.path.dirname(__file__))

import protocol
from algorithms.hashcash import (
    mine_stamp, verify_stamp, stamp_message, verify_message,
    get_difficulty, DIFFICULTY_MAP,
)
from algorithms.election import ElectionNode


# ═════════════════════════════════════════════════════════════════════
# PART 1: HashCash — Stamping and Verifying Messages
# ═════════════════════════════════════════════════════════════════════

def demo_hashcash_basics():
    """Demonstrate mining and verifying PoW stamps on messages."""
    print("=" * 64)
    print("PART 1: HashCash Basics — Mining and Verifying Stamps")
    print("=" * 64)
    print()

    # Build a standard protocol message
    msg = protocol.view_event(
        sender="hugo",
        event_id="evt-42",
        content_id="show:midnight-run",
        count=1000,
    )
    print("  1a. Original message (no stamp):")
    print(f"      {json.dumps(msg, indent=6)}")
    print()

    # Mine a stamp
    difficulty = get_difficulty("VIEW_EVENT")
    print(f"  1b. Mining difficulty-{difficulty} stamp for VIEW_EVENT...")
    start = time.time()
    pow_data = mine_stamp(msg, difficulty=difficulty)
    elapsed = time.time() - start
    print(f"      Found nonce={pow_data['nonce']:,} in {elapsed:.4f}s")
    print(f"      Hash: {pow_data['hash'][:24]}...")
    print()

    # Attach to message
    msg["pow"] = pow_data
    print("  1c. Stamped message (ready to send):")
    print(f"      {json.dumps(msg, indent=6)}")
    print()

    # Verify
    is_valid = verify_message(msg)
    print(f"  1d. Receiver verifies: valid = {is_valid}")
    print()

    # Tamper test
    tampered = dict(msg)
    tampered["count"] = 9999
    tampered_valid = verify_message(tampered)
    print(f"  1e. Tampered message (count=9999): valid = {tampered_valid}")
    print("      The proof is bound to the exact message content.")
    print()


def demo_hashcash_difficulty_levels():
    """Show how different message types require different PoW levels."""
    print("=" * 64)
    print("PART 2: Variable Difficulty by Message Type")
    print("=" * 64)
    print()

    print("  Difficulty map:")
    for msg_type, diff in sorted(DIFFICULTY_MAP.items(), key=lambda x: x[1]):
        print(f"    {msg_type:15s} -> difficulty {diff}  (~{16**diff:>12,} avg attempts)")
    print()

    # Mine one of each common type and time it
    test_messages = [
        protocol.ping("hugo", seq=1),
        protocol.view_event("hugo", "evt-1", "show:neon-drift", 500),
        protocol.audit_result("hugo", "show:midnight-run", 1000, 0.92, ["sam", "phin"]),
    ]

    for msg in test_messages:
        msg_type = msg["type"]
        difficulty = get_difficulty(msg_type)
        start = time.time()
        pow_data = mine_stamp(msg, difficulty=difficulty)
        elapsed = time.time() - start
        print(f"  {msg_type:15s}  diff={difficulty}  nonce={pow_data['nonce']:>10,}  "
              f"time={elapsed:.4f}s")
    print()
    print("  Notice: AUDIT_RESULT takes significantly longer than PING.")
    print("  This is by design — high-value messages require more work.")
    print()


def demo_stamp_convenience():
    """Show the stamp_message() convenience function used by bots."""
    print("=" * 64)
    print("PART 3: Using stamp_message() — The Bot Pattern")
    print("=" * 64)
    print()

    print("  How bots stamp messages before sending:")
    print()
    print("    # 1. Build the message")
    print("    msg = protocol.audit_result(self.node_id, ...)")
    print()
    print("    # 2. Stamp it (mines PoW and attaches pow field)")
    print("    from algorithms.hashcash import stamp_message")
    print("    stamp_message(msg)")
    print()
    print("    # 3. Send it")
    print("    self.transport.send(target_id, msg)")
    print()

    # Live demo
    msg = protocol.audit_result("hugo", "show:midnight-run", 1000, 0.92, ["sam"])
    stamp_message(msg)
    print(f"  Live: stamped message has pow? {'pow' in msg}")
    print(f"  Live: verify_message() = {verify_message(msg)}")
    print()


# ═════════════════════════════════════════════════════════════════════
# PART 4: Leader Election — Payment Server Selection
# ═════════════════════════════════════════════════════════════════════

def demo_election_scenario():
    """Simulate a full leader election scenario among 3 bots."""
    print("=" * 64)
    print("PART 4: Leader Election — Payment Server Failover")
    print("=" * 64)
    print()

    # Setup: 3 bots with different reputations
    reputations = {
        "bot-alpha":   0.95,  # current leader (will "crash")
        "bot-bravo":   0.70,  # low reputation
        "bot-charlie": 0.85,  # medium reputation
    }
    bot_ids = list(reputations.keys())
    alive_bots = list(bot_ids)  # all alive initially

    print("  SETUP:")
    for bot_id, rep in reputations.items():
        print(f"    {bot_id:15s}  reputation = {rep}")
    print()

    # Create election nodes for each bot
    nodes = {}
    for bid in bot_ids:
        nodes[bid] = ElectionNode(
            node_id=bid,
            bot_ids=bot_ids,
            get_reputation_fn=lambda nid, r=reputations: r.get(nid, 0.0),
            get_alive_peers_fn=lambda a=alive_bots: list(a),
        )

    # STEP 1: bot-alpha is initial leader
    for nid in bot_ids:
        nodes[nid].current_leader = "bot-alpha"
        nodes[nid].state = "FOLLOWER"
    nodes["bot-alpha"].state = "LEADER"
    print("  STEP 1: bot-alpha is the initial Payment Server")
    print()

    # STEP 2: bot-alpha crashes
    print("  STEP 2: bot-alpha crashes!")
    alive_bots.remove("bot-alpha")
    print(f"    Alive bots: {alive_bots}")
    print()

    # Wait for leader timeout (simulate)
    for nid in alive_bots:
        nodes[nid].last_leader_contact = time.time() - 100  # simulate timeout

    # STEP 3: bot-bravo detects leader is dead and starts election
    print("  STEP 3: bot-bravo detects leader is dead, starts election")
    should_elect = nodes["bot-bravo"].check_leader()
    print(f"    Should start election? {should_elect}")

    outgoing = nodes["bot-bravo"].start_election()
    for item in outgoing:
        print(f"    ELECTION -> {item['target']}  "
              f"(term={item['msg_fields']['term']}, rep={item['msg_fields']['reputation']})")
    print()

    # STEP 4: bot-charlie receives ELECTION, outranks bot-bravo
    print("  STEP 4: bot-charlie receives ELECTION from bot-bravo")
    for item in outgoing:
        if item["target"] == "bot-charlie":
            response = nodes["bot-charlie"].receive_election(
                sender="bot-bravo",
                term=item["msg_fields"]["term"],
                sender_rep=item["msg_fields"]["reputation"],
            )
            if response:
                print(f"    bot-charlie sends ELECTION_OK (rep={response['msg_fields']['reputation']})")
                nodes["bot-bravo"].receive_election_ok(
                    sender="bot-charlie",
                    term=response["msg_fields"]["term"],
                    sender_rep=response["msg_fields"]["reputation"],
                )
    print()

    # STEP 5: bot-charlie wins (no higher-rep bots to challenge)
    print("  STEP 5: bot-charlie election timeout (no one outranks it)")
    nodes["bot-charlie"]._election_start = time.time() - 20  # force timeout
    result = nodes["bot-charlie"].check_election_timeout()
    print(f"    Election result: {result}")
    status = nodes["bot-charlie"].get_status()
    print(f"    bot-charlie state: {status['state']}")
    print(f"    bot-charlie is Payment Server: {status['is_payment_server']}")
    print()

    # STEP 6: bot-charlie broadcasts COORDINATOR
    print("  STEP 6: bot-charlie broadcasts COORDINATOR")
    accepted = nodes["bot-bravo"].receive_coordinator("bot-charlie", nodes["bot-charlie"].term)
    print(f"    bot-bravo accepted: {accepted}")
    print(f"    bot-bravo leader: {nodes['bot-bravo'].current_leader}")
    print()

    # Print final state
    print("  FINAL STATE:")
    for nid in bot_ids:
        s = nodes[nid].get_status()
        tag = "CRASHED" if nid == "bot-alpha" else s["state"]
        leader_tag = " (PAYMENT SERVER)" if s["is_payment_server"] else ""
        print(f"    {nid:15s}  {tag}{leader_tag}  leader={s['current_leader']}")
    print()


# ═════════════════════════════════════════════════════════════════════
# PART 5: New Protocol Messages
# ═════════════════════════════════════════════════════════════════════

def demo_new_protocol_messages():
    """Show how to build and format the new message types."""
    print("=" * 64)
    print("PART 5: New Protocol Messages")
    print("=" * 64)
    print()

    messages = [
        ("ELECTION",     protocol.election("bot-bravo", term=3, reputation=0.70)),
        ("ELECTION_OK",  protocol.election_ok("bot-charlie", term=3, reputation=0.85)),
        ("COORDINATOR",  protocol.coordinator("bot-charlie", term=3)),
        ("PAYMENT",      protocol.payment("bot-charlie", "show:midnight-run",
                                          agreed_count=1000, amount=0.085,
                                          audit_ref="abc123")),
    ]

    for label, msg in messages:
        # Stamp it
        stamp_message(msg)
        compact = protocol.format_msg(msg, compact=True)
        print(f"  {compact}")

    print()
    print("  All 4 new message types built, stamped, and formatted successfully.")
    print()


# ═════════════════════════════════════════════════════════════════════
# PART 6: The Full Picture — Election + PoW + Payment
# ═════════════════════════════════════════════════════════════════════

def demo_full_flow():
    """Walk through the complete flow: audit -> election -> payment with PoW."""
    print("=" * 64)
    print("PART 6: Full Flow — Audit to Payment with PoW")
    print("=" * 64)
    print()

    print("  SCENARIO: hugo audits content, bot-charlie (Payment Server) issues payment")
    print()

    # Step 1: hugo produces an AUDIT_RESULT with PoW
    print("  1. hugo mines PoW stamp for AUDIT_RESULT...")
    audit_msg = protocol.audit_result(
        sender="hugo",
        content_id="show:midnight-run",
        agreed_count=1500,
        confidence=0.92,
        voters=["hugo", "sam", "phin"],
    )
    start = time.time()
    stamp_message(audit_msg)
    print(f"     Difficulty: {audit_msg['pow']['difficulty']}")
    print(f"     Nonce: {audit_msg['pow']['nonce']:,}")
    print(f"     Time: {time.time() - start:.4f}s")
    print()

    # Step 2: bot-charlie verifies the PoW and processes
    print("  2. bot-charlie receives and verifies PoW...")
    valid = verify_message(audit_msg)
    print(f"     PoW valid: {valid}")
    if valid:
        print("     Processing audit result...")
        agreed_count = audit_msg["agreed_count"]
        confidence = audit_msg["confidence"]
        amount = round((agreed_count / 100) * 0.01 * confidence, 4)
        print(f"     Payment calculated: {agreed_count} views * $0.01/100 * {confidence} = ${amount}")
    print()

    # Step 3: bot-charlie issues a PAYMENT with its own PoW
    print("  3. bot-charlie issues PAYMENT with PoW...")
    payment_msg = protocol.payment(
        sender="bot-charlie",
        content_id="show:midnight-run",
        agreed_count=agreed_count,
        amount=amount,
        audit_ref=audit_msg.get("msg_id", ""),
    )
    start = time.time()
    stamp_message(payment_msg)
    print(f"     Difficulty: {payment_msg['pow']['difficulty']}")
    print(f"     Nonce: {payment_msg['pow']['nonce']:,}")
    print(f"     Time: {time.time() - start:.4f}s")
    print()

    # Step 4: hugo receives and verifies
    print("  4. hugo receives PAYMENT and verifies PoW...")
    valid = verify_message(payment_msg)
    print(f"     PoW valid: {valid}")
    print(f"     Payment from: {payment_msg['sender']}")
    print(f"     Content: {payment_msg['content_id']}")
    print(f"     Amount: ${payment_msg['amount']}")
    print()

    print("  COMPLETE: the creator has been paid exactly ONCE by the elected")
    print("  Payment Server, and every message was verified with proof-of-work.")
    print()


# ═════════════════════════════════════════════════════════════════════
# MAIN
# ═════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print()
    print("  Election + HashCash Sample Code")
    print("  AdFlow 2032 — Distributed Systems Lab")
    print()

    demo_hashcash_basics()
    demo_hashcash_difficulty_levels()
    demo_stamp_convenience()
    demo_election_scenario()
    demo_new_protocol_messages()
    demo_full_flow()

    print("=" * 64)
    print("  SUMMARY")
    print("=" * 64)
    print()
    print("  New modules:")
    print("    algorithms/hashcash.py   — PoW stamping (mine + verify)")
    print("    algorithms/election.py   — Reputation-weighted Bully election")
    print()
    print("  New protocol messages:")
    print("    ELECTION      — 'I am starting an election, here is my reputation'")
    print("    ELECTION_OK   — 'I outrank you, back off'")
    print("    COORDINATOR   — 'I won, I am the Payment Server for term T'")
    print("    PAYMENT       — 'Payment issued for content X (only from leader)'")
    print()
    print("  New bot behaviors:")
    print("    - Bots stamp ALL outgoing messages with proof-of-work")
    print("    - Bots verify incoming PoW (drop invalid VIEW_EVENT/AUDIT_RESULT)")
    print("    - Bots participate in leader election for Payment Server role")
    print("    - The elected leader processes audits into payments")
    print("    - Standby bots log audits but do not issue payments")
    print()
    print("  What students need to do:")
    print("    - Handle ELECTION, ELECTION_OK, COORDINATOR messages")
    print("    - Handle PAYMENT messages (log/display them)")
    print("    - (Optional) Stamp outgoing messages with hashcash.stamp_message()")
    print("    - (Optional) Verify incoming PoW with hashcash.verify_message()")
    print("=" * 64)
