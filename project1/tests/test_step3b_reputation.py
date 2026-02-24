"""
Step 3b Tests: ReputationNode
Run from the project1/ directory:

    python tests/test_step3b_reputation.py

All tests must PASS before moving to Step 4.
"""

import sys
sys.path.insert(0, ".")
from algorithms.reputation import ReputationNode

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

def test_new_peer_neutral_trust():
    r = ReputationNode("node-a")
    r.add_peer("node-b")
    ranked = r.get_ranked_peers()
    assert len(ranked) == 1, f"Expected 1 peer in ranked list, got {len(ranked)}"
    score = ranked[0].trust_score
    # New peer should have a neutral score around 0.5
    assert 0.3 <= score <= 0.7, \
        f"New peer trust score should be near 0.5 (neutral), got {score:.3f}"

def test_accurate_peer_gains_trust():
    r = ReputationNode("node-a")
    r.add_peer("node-b")
    for _ in range(10):
        r.record_report("node-b", was_accurate=True)
    r.update_all_scores()
    ranked = r.get_ranked_peers()
    score = ranked[0].trust_score
    assert score > 0.5, \
        f"A peer correct 10/10 times should have trust > 0.5, got {score:.3f}"

def test_inaccurate_peer_loses_trust():
    r = ReputationNode("node-a")
    r.add_peer("node-b")
    for _ in range(10):
        r.record_report("node-b", was_accurate=False)
    r.update_all_scores()
    ranked = r.get_ranked_peers()
    score = ranked[0].trust_score
    assert score < 0.5, \
        f"A peer wrong 10/10 times should have trust < 0.5, got {score:.3f}"

def test_ranking_order():
    r = ReputationNode("node-a")
    r.add_peer("node-b")
    r.add_peer("node-c")
    # node-b: always accurate; node-c: always inaccurate
    for _ in range(10):
        r.record_report("node-b", was_accurate=True)
        r.record_report("node-c", was_accurate=False)
    r.update_all_scores()
    ranked = r.get_ranked_peers()
    assert ranked[0].node_id == "node-b", \
        f"Accurate peer (node-b) should rank highest, got {ranked[0].node_id}"
    assert ranked[-1].node_id == "node-c", \
        f"Inaccurate peer (node-c) should rank lowest, got {ranked[-1].node_id}"

def test_weighted_vote_honest_beats_liar():
    r = ReputationNode("node-a")
    r.add_peer("node-b")   # honest
    r.add_peer("node-c")   # liar
    for _ in range(10):
        r.record_report("node-b", was_accurate=True)
        r.record_report("node-c", was_accurate=False)
    r.update_all_scores()
    # node-b says 100 (truth), node-c says 9999 (lie)
    result, confidence = r.weighted_majority_vote({"node-b": 100, "node-c": 9999})
    assert result == 100, \
        f"Honest node-b (higher trust) should win the vote, got agreed={result}"
    assert 0.0 < confidence <= 1.0, \
        f"Confidence should be between 0 and 1, got {confidence}"

def test_weighted_vote_returns_tuple():
    r = ReputationNode("node-a")
    r.add_peer("node-b")
    r.record_report("node-b", was_accurate=True)
    r.update_all_scores()
    result = r.weighted_majority_vote({"node-b": 42})
    assert isinstance(result, tuple) and len(result) == 2, \
        "weighted_majority_vote() must return a (count, confidence) tuple"

def test_confidence_higher_when_unanimous():
    r = ReputationNode("node-a")
    for peer in ["node-b", "node-c", "node-d"]:
        r.add_peer(peer)
        r.record_report(peer, was_accurate=True)
    r.update_all_scores()
    # All 3 agree on 100
    _, conf_unanimous = r.weighted_majority_vote(
        {"node-b": 100, "node-c": 100, "node-d": 100}
    )
    # Split vote: 2 say 100, 1 dissents
    _, conf_split = r.weighted_majority_vote(
        {"node-b": 100, "node-c": 100, "node-d": 999}
    )
    assert conf_unanimous > conf_split, \
        f"Unanimous vote should have higher confidence than split: " \
        f"{conf_unanimous:.2f} vs {conf_split:.2f}"

def test_heartbeat_uptime_affects_trust():
    r = ReputationNode("node-a")
    r.add_peer("node-reliable")
    r.add_peer("node-offline")
    for _ in range(10):
        r.record_heartbeat("node-reliable", responded=True)
        r.record_heartbeat("node-offline",  responded=False)
    r.update_all_scores()
    ranked = r.get_ranked_peers()
    ids = [p.node_id for p in ranked]
    assert ids[0] == "node-reliable", \
        f"Node with perfect uptime should rank higher than one that never responds. Got: {ids}"


# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    tests = [
        ("new peer has neutral trust score",          test_new_peer_neutral_trust),
        ("accurate peer gains trust over time",       test_accurate_peer_gains_trust),
        ("inaccurate peer loses trust over time",     test_inaccurate_peer_loses_trust),
        ("get_ranked_peers orders by trust",          test_ranking_order),
        ("weighted vote: honest beats liar",          test_weighted_vote_honest_beats_liar),
        ("weighted_majority_vote returns tuple",      test_weighted_vote_returns_tuple),
        ("unanimous vote has higher confidence",      test_confidence_higher_when_unanimous),
        ("heartbeat uptime affects trust ranking",    test_heartbeat_uptime_affects_trust),
    ]

    print(f"\n{'='*55}")
    print("  Step 3b: ReputationNode tests")
    print(f"{'='*55}")
    passed = sum(run(name, fn) for name, fn in tests)
    total = len(tests)
    print(f"{'='*55}")
    print(f"  {passed}/{total} passed")
    if passed < total:
        print("  Fix the failures above before moving to Step 4.")
        sys.exit(1)
    else:
        print("  All passing — move on to Step 4.")
    print(f"{'='*55}\n")
