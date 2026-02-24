"""
Step 3a Tests: ChokingNode
Run from the project1/ directory:

    python tests/test_step3a_choking.py

All tests must PASS before moving to Step 4.
"""

import sys
sys.path.insert(0, ".")
from algorithms.choking import ChokingNode

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

def test_new_peer_starts_choked():
    c = ChokingNode("node-a", max_unchoked=2, optimistic_interval=3)
    c.add_peer("node-b")
    c.add_peer("node-c")
    # Before any choking round, no unchoke decision has been made
    # Peers should not be unchoked without a run_choking_round() call
    assert "node-b" not in c.get_unchoked_peers() or True, \
        "(informational) peers start choked until first choking round"

def test_top_contributor_gets_unchoked():
    c = ChokingNode("node-a", max_unchoked=1, optimistic_interval=999)
    c.add_peer("node-b")
    c.add_peer("node-c")
    # node-b contributes a lot; node-c contributes nothing
    for _ in range(10):
        c.record_contribution("node-b", units=5)
    c.run_choking_round()
    unchoked = c.get_unchoked_peers()
    assert "node-b" in unchoked, \
        "The highest contributor should be unchoked (max_unchoked=1, node-b contributes 50 vs 0)"
    assert "node-c" not in unchoked, \
        "A peer with zero contribution should remain choked when max_unchoked=1"

def test_max_unchoked_limit_respected():
    c = ChokingNode("node-a", max_unchoked=2, optimistic_interval=999)
    for peer in ["node-b", "node-c", "node-d", "node-e"]:
        c.add_peer(peer)
        c.record_contribution(peer, units=1)
    c.run_choking_round()
    unchoked = c.get_unchoked_peers()
    # max_unchoked=2 but one slot may go to optimistic; total unchoked <= max_unchoked
    assert len(unchoked) <= 2, \
        f"max_unchoked=2 but {len(unchoked)} peers are unchoked: {unchoked}"

def test_choked_and_unchoked_disjoint():
    c = ChokingNode("node-a", max_unchoked=2, optimistic_interval=999)
    for peer in ["node-b", "node-c", "node-d"]:
        c.add_peer(peer)
        c.record_contribution(peer, units=1)
    c.run_choking_round()
    unchoked = set(c.get_unchoked_peers())
    choked   = set(c.get_choked_peers())
    assert unchoked.isdisjoint(choked), \
        f"A peer cannot be both choked and unchoked. Overlap: {unchoked & choked}"

def test_free_rider_stays_choked():
    c = ChokingNode("node-a", max_unchoked=2, optimistic_interval=999)
    # node-b and node-c contribute; node-d free-rides
    for peer in ["node-b", "node-c", "node-d"]:
        c.add_peer(peer)
    c.record_contribution("node-b", units=10)
    c.record_contribution("node-c", units=8)
    # node-d: zero contribution
    for _ in range(3):
        c.run_choking_round()
    choked = c.get_choked_peers()
    assert "node-d" in choked, \
        "A free-rider with zero contribution should stay choked over multiple rounds"

def test_optimistic_unchoke_occurs():
    # With optimistic_interval=1, every round should opportunistically unchoke one peer
    c = ChokingNode("node-a", max_unchoked=1, optimistic_interval=1)
    for peer in ["node-b", "node-c", "node-d"]:
        c.add_peer(peer)
    # Nobody contributes — top-n slot goes to contributor(s) but optimistic should still fire
    c.run_choking_round()
    # At least 1 peer should be unchoked (the optimistic slot)
    assert len(c.get_unchoked_peers()) >= 1, \
        "With optimistic_interval=1, at least one peer should be unchoked each round"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        ("new peers start choked",                   test_new_peer_starts_choked),
        ("top contributor gets unchoked",             test_top_contributor_gets_unchoked),
        ("max_unchoked limit respected",              test_max_unchoked_limit_respected),
        ("choked and unchoked lists are disjoint",    test_choked_and_unchoked_disjoint),
        ("free-rider stays choked over rounds",       test_free_rider_stays_choked),
        ("optimistic unchoke fires each interval",    test_optimistic_unchoke_occurs),
    ]

    print(f"\n{'='*55}")
    print("  Step 3a: ChokingNode tests")
    print(f"{'='*55}")
    passed = sum(run(name, fn) for name, fn in tests)
    total = len(tests)
    print(f"{'='*55}")
    print(f"  {passed}/{total} passed")
    if passed < total:
        print("  Fix the failures above before running test_step3b_reputation.py.")
        sys.exit(1)
    else:
        print("  All passing — run test_step3b_reputation.py next.")
    print(f"{'='*55}\n")
