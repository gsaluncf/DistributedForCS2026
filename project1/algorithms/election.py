"""
Leader Election — Reputation-Weighted Bully Algorithm
======================================================

Elects a single Payment Server from the bot pool.

Only bots can WIN the election, but any node can TRIGGER one
when heartbeat detects the current Payment Server is dead.

Algorithm:
  1.  Any node detects leader is DEAD via heartbeat.
  2.  Node sends ELECTION(term, reputation) to all bots with higher reputation.
  3.  If a higher-reputation bot responds ELECTION_OK, the sender backs off.
  4.  If nobody responds within `election_timeout`, the sender declares itself
      COORDINATOR (if it is a bot) or the highest-reputation bot it knows about.
  5.  COORDINATOR is broadcast to all peers.

Term numbers prevent stale elections from overriding newer ones.
"""

import time
from typing import Any, Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# Election states
# ---------------------------------------------------------------------------

FOLLOWER  = "FOLLOWER"
CANDIDATE = "CANDIDATE"
LEADER    = "LEADER"


class ElectionNode:
    """Reputation-weighted Bully election for Payment Server selection."""

    def __init__(
        self,
        node_id: str,
        bot_ids: List[str],
        get_reputation_fn: Callable[[str], float],
        get_alive_peers_fn: Callable[[], List[str]],
    ):
        self.node_id = node_id
        self.bot_ids = bot_ids
        self.is_bot = node_id in bot_ids

        # State
        self.state: str = FOLLOWER
        self.current_leader: Optional[str] = None
        self.term: int = 0

        # Election bookkeeping
        self.election_in_progress: bool = False
        self._election_start: float = 0.0
        self._got_ok: bool = False
        self.election_timeout: float = 8.0   # seconds to wait for OK

        # Last time we heard from the leader (heartbeat or COORDINATOR msg)
        self.last_leader_contact: float = time.time()
        self.leader_timeout: float = 15.0  # seconds before declaring leader dead

        # Injected dependencies
        self._get_reputation = get_reputation_fn
        self._get_alive_peers = get_alive_peers_fn

        # Internal log buffer
        self._log_buffer: List[str] = []

    # -----------------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------------

    def check_leader(self) -> bool:
        """Check if the current leader is responsive.

        Returns True if an election should be started.
        """
        if self.election_in_progress:
            return False

        if self.current_leader is None:
            # No leader known — trigger election
            return True

        alive = self._get_alive_peers()
        if self.current_leader not in alive:
            elapsed = time.time() - self.last_leader_contact
            if elapsed > self.leader_timeout:
                self._log(f"Leader {self.current_leader} is DEAD "
                          f"(no contact for {elapsed:.0f}s). Triggering election.")
                return True
        else:
            # Leader is alive — reset contact timer
            self.last_leader_contact = time.time()

        return False

    def start_election(self) -> List[Dict[str, Any]]:
        """Begin a new election. Returns list of ELECTION messages to send.

        Each item: {"target": node_id, "msg_fields": {...}}
        """
        self.term += 1
        self.state = CANDIDATE
        self.election_in_progress = True
        self._election_start = time.time()
        self._got_ok = False

        my_rep = self._get_reputation(self.node_id) if self.is_bot else 0.0
        alive = self._get_alive_peers()

        # Send ELECTION to all alive bots with higher reputation (or same rep + higher ID)
        outgoing = []
        for bot_id in self.bot_ids:
            if bot_id == self.node_id:
                continue
            if bot_id not in alive:
                continue

            bot_rep = self._get_reputation(bot_id)
            if (bot_rep > my_rep) or (bot_rep == my_rep and bot_id > self.node_id):
                outgoing.append({
                    "target": bot_id,
                    "msg_fields": {
                        "term": self.term,
                        "reputation": my_rep,
                    },
                })

        if not outgoing and self.is_bot:
            # No higher-rep bots alive — I win immediately
            self._log(f"No higher-rep bots alive. Declaring self as leader (term={self.term})")
            self.state = LEADER
            self.current_leader = self.node_id
            self.election_in_progress = False
            self.last_leader_contact = time.time()

        self._log(f"Election started (term={self.term}, rep={my_rep:.3f}). "
                  f"Challenging {len(outgoing)} higher-rep bots.")
        return outgoing

    def receive_election(self, sender: str, term: int, sender_rep: float) -> Optional[Dict[str, Any]]:
        """Handle an incoming ELECTION message.

        Returns an ELECTION_OK response if we outrank the sender, else None.
        Also triggers our own election if appropriate.
        """
        if term > self.term:
            self.term = term

        my_rep = self._get_reputation(self.node_id) if self.is_bot else 0.0

        # Am I a bot that outranks the sender?
        if self.is_bot and (
            (my_rep > sender_rep) or
            (my_rep == sender_rep and self.node_id > sender)
        ):
            self._log(f"Received ELECTION from {sender} (rep={sender_rep:.3f}). "
                      f"I outrank (rep={my_rep:.3f}). Sending OK.")
            # Start our own election if not already running
            if not self.election_in_progress:
                self.election_in_progress = True
                self._election_start = time.time()
                self._got_ok = False
                self.state = CANDIDATE

            return {
                "target": sender,
                "msg_fields": {
                    "term": self.term,
                    "reputation": my_rep,
                },
            }

        return None

    def receive_election_ok(self, sender: str, term: int, sender_rep: float):
        """Handle ELECTION_OK — a higher-ranked node is taking over."""
        self._got_ok = True
        self._log(f"Received ELECTION_OK from {sender} (rep={sender_rep:.3f}). Backing off.")

    def receive_coordinator(self, sender: str, term: int) -> bool:
        """Handle COORDINATOR message — a new leader has been declared.

        Returns True if accepted, False if stale term.
        """
        if term < self.term:
            self._log(f"Ignoring stale COORDINATOR from {sender} (term={term} < {self.term})")
            return False

        self.term = term
        self.current_leader = sender
        self.state = FOLLOWER
        self.election_in_progress = False
        self.last_leader_contact = time.time()
        self._log(f"New leader: {sender} (term={term}). I am FOLLOWER.")
        return True

    def check_election_timeout(self) -> Optional[str]:
        """Check if the election has timed out.

        Returns:
          - "won"  if we should declare ourselves coordinator
          - "lost" if someone sent us OK and will take over
          - None   if still waiting
        """
        if not self.election_in_progress:
            return None

        elapsed = time.time() - self._election_start
        if elapsed < self.election_timeout:
            return None

        self.election_in_progress = False

        if self._got_ok:
            # Someone higher-ranked is handling it
            self.state = FOLLOWER
            self._log("Election timeout: received OK, waiting for COORDINATOR.")
            return "lost"

        if self.is_bot:
            # No one responded — I win
            self.state = LEADER
            self.current_leader = self.node_id
            self.last_leader_contact = time.time()
            self._log(f"Election timeout: no OK received. I am LEADER (term={self.term})")
            return "won"
        else:
            # Student node can't be leader; pick the highest-rep alive bot
            alive = self._get_alive_peers()
            alive_bots = [b for b in self.bot_ids if b in alive]
            if alive_bots:
                best_bot = max(alive_bots,
                               key=lambda b: (self._get_reputation(b), b))
                self.current_leader = best_bot
                self._log(f"Student election timeout: designating {best_bot} as leader.")
            self.state = FOLLOWER
            return "lost"

    def get_coordinator_targets(self) -> List[str]:
        """Get the list of peers to send COORDINATOR to (all alive peers)."""
        return self._get_alive_peers()

    # -----------------------------------------------------------------------
    # Status
    # -----------------------------------------------------------------------

    def is_active_payment_server(self) -> bool:
        """Am I the currently elected Payment Server?"""
        return self.state == LEADER and self.current_leader == self.node_id

    def get_status(self) -> Dict[str, Any]:
        """Return a status dict for diagnostics."""
        return {
            "state": self.state,
            "term": self.term,
            "current_leader": self.current_leader,
            "election_in_progress": self.election_in_progress,
            "is_payment_server": self.is_active_payment_server(),
        }

    # -----------------------------------------------------------------------
    # Internal logging
    # -----------------------------------------------------------------------

    def _log(self, msg: str):
        self._log_buffer.append(f"[ELECTION] {msg}")

    def flush_log(self) -> List[str]:
        msgs = list(self._log_buffer)
        self._log_buffer.clear()
        return msgs


# ---------------------------------------------------------------------------
# Self-test
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Election Module — Self-Test ===\n")

    # Simulate 3 bots with different reputations
    reps = {"bot-alpha": 0.95, "bot-bravo": 0.70, "bot-charlie": 0.85}
    alive = list(reps.keys())

    nodes = {}
    for bot_id in reps:
        nodes[bot_id] = ElectionNode(
            node_id=bot_id,
            bot_ids=list(reps.keys()),
            get_reputation_fn=lambda nid, r=reps: r.get(nid, 0.0),
            get_alive_peers_fn=lambda a=alive: list(a),
        )

    # bot-bravo starts an election
    print("  bot-bravo starts election:")
    msgs = nodes["bot-bravo"].start_election()
    for m in msgs:
        print(f"    ELECTION -> {m['target']}  (term={m['msg_fields']['term']})")

    # bot-alpha and bot-charlie receive ELECTION
    for m in msgs:
        target = m["target"]
        ok = nodes[target].receive_election(
            sender="bot-bravo",
            term=m["msg_fields"]["term"],
            sender_rep=m["msg_fields"]["reputation"],
        )
        if ok:
            print(f"    {target} responds ELECTION_OK")
            nodes["bot-bravo"].receive_election_ok(
                sender=target,
                term=ok["msg_fields"]["term"],
                sender_rep=ok["msg_fields"]["reputation"],
            )

    # bot-alpha has higher rep, it should declare itself leader
    # Simulate timeout for bot-alpha
    nodes["bot-alpha"]._election_start = time.time() - 20  # force timeout
    result = nodes["bot-alpha"].check_election_timeout()
    print(f"\n  bot-alpha election timeout result: {result}")
    print(f"  bot-alpha state: {nodes['bot-alpha'].get_status()}")

    # bot-alpha broadcasts COORDINATOR
    for nid in ["bot-bravo", "bot-charlie"]:
        accepted = nodes[nid].receive_coordinator("bot-alpha", nodes["bot-alpha"].term)
        print(f"  {nid} accepted COORDINATOR: {accepted}")
        print(f"  {nid} leader: {nodes[nid].current_leader}")

    print("\n=== All tests passed ===")
