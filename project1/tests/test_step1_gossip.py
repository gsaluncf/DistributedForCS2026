"""
Step 1 Tests: GossipNode
Run from the project1/ directory:

    python tests/test_step1_gossip.py

All tests must PASS before moving to Step 2.
"""

import sys
sys.path.insert(0, ".")
from algorithms.gossip import GossipNode

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

def test_add_peer_increases_count():
    g = GossipNode("node-a")
    g.add_peer("node-b", "https://sqs.fake/b")
    assert g.known_peer_count() == 1, \
        f"After add_peer, known_peer_count() should be 1, got {g.known_peer_count()}"

def test_add_same_peer_twice_no_duplicate():
    g = GossipNode("node-a")
    g.add_peer("node-b", "https://sqs.fake/b")
    g.add_peer("node-b", "https://sqs.fake/b")
    assert g.known_peer_count() == 1, \
        "Adding the same peer twice must not create duplicates"

def test_pick_target_returns_known_peer():
    g = GossipNode("node-a")
    g.add_peer("node-b", "https://sqs.fake/b")
    g.add_peer("node-c", "https://sqs.fake/c")
    target = g.pick_gossip_target()
    assert target in ("node-b", "node-c"), \
        f"pick_gossip_target() must return a known peer, got {target!r}"

def test_pick_target_none_when_empty():
    g = GossipNode("node-a")
    result = g.pick_gossip_target()
    assert result is None, \
        f"pick_gossip_target() must return None when no peers known, got {result!r}"

def test_peer_list_message_format():
    g = GossipNode("node-a", queue_url="https://sqs.fake/a")
    g.add_peer("node-b", "https://sqs.fake/b")
    msg = g.get_peer_list_message()
    assert isinstance(msg, list), \
        f"get_peer_list_message() must return a list, got {type(msg).__name__}"
    assert len(msg) >= 1, "List must have at least one entry"
    for entry in msg:
        assert "node_id" in entry, f"Each entry must have 'node_id', got {entry}"
        assert "queue_url" in entry, f"Each entry must have 'queue_url', got {entry}"

def test_receive_discovers_new_peer():
    g = GossipNode("node-a")
    g.add_peer("node-b", "https://sqs.fake/b")
    incoming = [{"node_id": "node-c", "queue_url": "https://sqs.fake/c"}]
    new = g.receive_peer_list(incoming, sender_id="node-b")
    assert g.known_peer_count() >= 2, \
        f"Should know node-b and node-c after merge, got {g.known_peer_count()}"
    assert new == 1, \
        f"receive_peer_list() should return number of NEW peers discovered, got {new}"

def test_receive_no_false_new_for_existing_peer():
    g = GossipNode("node-a")
    g.add_peer("node-b", "https://sqs.fake/b")
    incoming = [{"node_id": "node-b", "queue_url": "https://sqs.fake/b"}]
    new = g.receive_peer_list(incoming, sender_id="node-b")
    assert new == 0, \
        f"node-b is already known; new discoveries should be 0, got {new}"

def test_age_entries_expires_peers():
    g = GossipNode("node-a")
    g.add_peer("node-b", "https://sqs.fake/b")
    for _ in range(10):    # more than any reasonable TTL
        g.age_entries()
    assert g.known_peer_count() == 0, \
        "Peer should be removed after enough aging rounds (TTL exhausted)"

def test_does_not_target_self():
    # Even if self is accidentally added, gossip target must never be self
    g = GossipNode("node-a")
    g.add_peer("node-b", "https://sqs.fake/b")
    for _ in range(20):
        target = g.pick_gossip_target()
        assert target != "node-a", \
            "pick_gossip_target() must never return your own node_id"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        ("add_peer increases count",                  test_add_peer_increases_count),
        ("no duplicates when same peer added twice",  test_add_same_peer_twice_no_duplicate),
        ("pick_gossip_target returns a known peer",   test_pick_target_returns_known_peer),
        ("pick_gossip_target returns None when empty",test_pick_target_none_when_empty),
        ("get_peer_list_message format is correct",   test_peer_list_message_format),
        ("receive_peer_list discovers new peers",     test_receive_discovers_new_peer),
        ("receive_peer_list does not re-count known", test_receive_no_false_new_for_existing_peer),
        ("age_entries expires peers after many rounds",test_age_entries_expires_peers),
        ("never gossips with self",                   test_does_not_target_self),
    ]

    print(f"\n{'='*55}")
    print("  Step 1: GossipNode tests")
    print(f"{'='*55}")
    passed = sum(run(name, fn) for name, fn in tests)
    total = len(tests)
    print(f"{'='*55}")
    print(f"  {passed}/{total} passed")
    if passed < total:
        print("  Fix the failures above before moving to Step 2.")
        sys.exit(1)
    else:
        print("  All passing — move on to Step 2.")
    print(f"{'='*55}\n")
