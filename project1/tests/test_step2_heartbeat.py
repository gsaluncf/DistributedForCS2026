"""
Step 2 Tests: HeartbeatNode
Run from the project1/ directory:

    python tests/test_step2_heartbeat.py

All tests must PASS before moving to Step 3.
"""

import sys
sys.path.insert(0, ".")
from algorithms.heartbeat import HeartbeatNode, PeerStatus

PASS = "\033[32m[PASS]\033[0m"
FAIL = "\033[31m[FAIL]\033[0m"

def run(name, fn):
    try:
        fn()
        print(f"  {PASS}  {name}")
        return True
    except AssertionError as e:
        print(f"  {FAIL}  {name}")
        print(f"         {e}")
        return False
    except NotImplementedError:
        print(f"  {FAIL}  {name}: not implemented yet")
        return False
    except Exception as e:
        print(f"  {FAIL}  {name}: unexpected error — {e}")
        return False


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_new_peer_is_alive():
    h = HeartbeatNode("node-a", miss_threshold=3, grace_period=2)
    h.add_peer("node-b")
    assert "node-b" in h.get_alive_peers(), \
        "A newly added peer should start as ALIVE"

def test_send_pings_returns_alive_peers():
    h = HeartbeatNode("node-a", miss_threshold=3, grace_period=2)
    h.add_peer("node-b")
    h.add_peer("node-c")
    pinged = h.send_pings(current_round=1)
    assert isinstance(pinged, list), "send_pings() must return a list"
    assert "node-b" in pinged and "node-c" in pinged, \
        f"send_pings() should return all alive peers, got {pinged}"

def test_pong_keeps_peer_alive():
    h = HeartbeatNode("node-a", miss_threshold=3, grace_period=2)
    h.add_peer("node-b")
    h.send_pings(current_round=1)
    h.receive_pong("node-b", current_round=1)
    assert "node-b" in h.get_alive_peers(), \
        "A peer that sends a PONG should remain ALIVE"

def test_grace_period_misses_produces_suspect():
    h = HeartbeatNode("node-a", miss_threshold=5, grace_period=2)
    h.add_peer("node-b")
    # Record exactly grace_period misses
    for r in range(1, 3):     # rounds 1 and 2
        h.send_pings(current_round=r)
        h.record_miss("node-b", current_round=r)
    assert "node-b" in h.get_suspect_peers(), \
        f"After {2} consecutive misses (grace_period=2), node-b should be SUSPECT"
    assert "node-b" not in h.get_dead_peers(), \
        "SUSPECT peers should not also appear in dead peers list"

def test_threshold_misses_produces_dead():
    h = HeartbeatNode("node-a", miss_threshold=3, grace_period=2)
    h.add_peer("node-b")
    for r in range(1, 4):    # rounds 1, 2, 3 — hits miss_threshold=3
        h.send_pings(current_round=r)
        h.record_miss("node-b", current_round=r)
    assert "node-b" in h.get_dead_peers(), \
        f"After {3} consecutive misses (miss_threshold=3), node-b should be DEAD"

def test_pong_after_suspect_restores_alive():
    h = HeartbeatNode("node-a", miss_threshold=5, grace_period=2)
    h.add_peer("node-b")
    for r in range(1, 3):
        h.send_pings(current_round=r)
        h.record_miss("node-b", current_round=r)
    # Confirm suspect
    assert "node-b" in h.get_suspect_peers(), "Should be SUSPECT before PONG"
    # Now PONG arrives
    h.receive_pong("node-b", current_round=3)
    assert "node-b" in h.get_alive_peers(), \
        "A PONG from a SUSPECT peer should restore it to ALIVE"
    assert "node-b" not in h.get_suspect_peers(), \
        "ALIVE peer must not remain in suspect list"

def test_dead_peers_not_pinged():
    h = HeartbeatNode("node-a", miss_threshold=3, grace_period=2)
    h.add_peer("node-b")
    for r in range(1, 4):
        h.send_pings(current_round=r)
        h.record_miss("node-b", current_round=r)
    # node-b is DEAD — should not appear in the next ping round
    pinged = h.send_pings(current_round=4)
    assert "node-b" not in pinged, \
        "DEAD peers must not receive PINGs (they are already removed from active monitoring)"

def test_lists_are_disjoint():
    h = HeartbeatNode("node-a", miss_threshold=3, grace_period=2)
    h.add_peer("node-b")
    h.add_peer("node-c")
    h.add_peer("node-d")
    # Make node-b suspect, node-c dead, node-d alive
    for r in range(1, 3):
        h.record_miss("node-b", current_round=r)
    for r in range(1, 4):
        h.record_miss("node-c", current_round=r)
    alive   = set(h.get_alive_peers())
    suspect = set(h.get_suspect_peers())
    dead    = set(h.get_dead_peers())
    assert alive.isdisjoint(suspect), "A peer cannot be both ALIVE and SUSPECT"
    assert alive.isdisjoint(dead),    "A peer cannot be both ALIVE and DEAD"
    assert suspect.isdisjoint(dead),  "A peer cannot be both SUSPECT and DEAD"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        ("new peer starts ALIVE",                      test_new_peer_is_alive),
        ("send_pings returns all alive peers",         test_send_pings_returns_alive_peers),
        ("PONG keeps peer ALIVE",                      test_pong_keeps_peer_alive),
        ("grace_period misses -> SUSPECT",             test_grace_period_misses_produces_suspect),
        ("miss_threshold misses -> DEAD",              test_threshold_misses_produces_dead),
        ("PONG after SUSPECT -> back to ALIVE",        test_pong_after_suspect_restores_alive),
        ("DEAD peers not included in send_pings",      test_dead_peers_not_pinged),
        ("ALIVE / SUSPECT / DEAD are disjoint",        test_lists_are_disjoint),
    ]

    print(f"\n{'='*55}")
    print("  Step 2: HeartbeatNode tests")
    print(f"{'='*55}")
    passed = sum(run(name, fn) for name, fn in tests)
    total = len(tests)
    print(f"{'='*55}")
    print(f"  {passed}/{total} passed")
    if passed < total:
        print("  Fix the failures above before moving to Step 3.")
        sys.exit(1)
    else:
        print("  All passing — move on to Step 3.")
    print(f"{'='*55}\n")
