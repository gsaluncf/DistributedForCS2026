"""
Your P2P Node — The Only File You Edit for Step 4
===================================================

Steps 1-3 had you implement the algorithm modules in algorithms/*.py.
Now you wire them into a live P2P node by overriding every method below.

Run your node:
    python my_node.py --id hugo
    python my_node.py --id hugo --verbose

=============================================================================
API REFERENCE — Library calls you can use
=============================================================================

TRANSPORT (self.transport)
--------------------------
  self.transport.send(target_id, msg_dict) -> bool
      Send a message to another node's SQS queue. Returns True on success.

  self.transport._queue_url_cache[node_id] = url
      Cache a peer's queue URL so future sends to them work.

  self.my_queue_url
      Your own SQS queue URL (set after initialize()).


PROTOCOL (import protocol)
--------------------------
  protocol.hello(sender, queue_url)         -> dict   # HELLO message
  protocol.peer_list(sender, peers_list)    -> dict   # PEER_LIST message
  protocol.ping(sender, seq)                -> dict   # PING message
  protocol.pong(sender, seq)                -> dict   # PONG message
  protocol.view_event(sender, event_id,               # VIEW_EVENT message
                      content_id, count, ad_id="")
  protocol.audit_result(sender, content_id,            # AUDIT_RESULT message
                        agreed_count, confidence,
                        voters=None)
  protocol.choke(sender)                    -> dict   # CHOKE message
  protocol.unchoke(sender)                  -> dict   # UNCHOKE message


GOSSIP (self.gossip) — your algorithms/gossip.py
-------------------------------------------------
  self.gossip.add_peer(node_id, queue_url)
      Register a peer in the gossip table.

  self.gossip.get_peer_list_message() -> list of {"node_id":..., "queue_url":...}
      Build the PEER_LIST payload to send to another node.

  self.gossip.receive_peer_list(incoming_list, sender_id) -> int
      Merge an incoming peer list. Returns count of NEW peers discovered.

  self.gossip.pick_gossip_target() -> str or None
      Pick a random peer to gossip with.

  self.gossip.age_entries()
      Decrement TTLs, remove expired. (Called automatically by the base class.)

  self.gossip.peers -> dict of node_id -> PeerEntry
      The raw gossip table (read-only access is fine).


HEARTBEAT (self.heartbeat) — your algorithms/heartbeat.py
-----------------------------------------------------------
  self.heartbeat.add_peer(node_id)
      Start monitoring a peer.

  self.heartbeat.send_pings(current_round) -> list of peer_ids
      Record that we're sending PINGs. Returns who to ping.

  self.heartbeat.receive_pong(from_node, current_round)
      Record that a peer responded to our PING.

  self.heartbeat.record_miss(peer_id, current_round)
      Record that a peer did NOT respond this round.

  self.heartbeat.get_alive_peers()   -> list of node_ids
  self.heartbeat.get_suspect_peers() -> list of node_ids
  self.heartbeat.get_dead_peers()    -> list of node_ids

  self.heartbeat.flush_log() -> list of status-change messages


CHOKING (self.choking) — your algorithms/choking.py
----------------------------------------------------
  self.choking.add_peer(node_id)
      Register a peer for choking decisions.

  self.choking.record_contribution(from_peer, units=1)
      Record that a peer contributed to us (affects ranking).

  self.choking.record_serving(to_peer, units=1)
      Record that we served a peer.

  self.choking.run_choking_round()
      Recalculate choke/unchoke decisions.

  self.choking.get_unchoked_peers() -> list of node_ids
  self.choking.get_choked_peers()   -> list of node_ids

  self.choking.flush_log() -> list of state-change messages


REPUTATION (self.reputation) — your algorithms/reputation.py
--------------------------------------------------------------
  self.reputation.add_peer(node_id)
      Register a peer with neutral trust (0.5).

  self.reputation.record_report(peer_id, was_accurate: bool)
      Record whether a peer's VIEW_EVENT matched the audit majority.

  self.reputation.record_heartbeat(peer_id, responded: bool)
      Record a heartbeat response (or miss).

  self.reputation.record_contribution(peer_id, units=1)
      Record that a peer contributed data.

  self.reputation.record_consumption(peer_id, units=1)
      Record that a peer consumed our data.

  self.reputation.update_all_scores()
      Recalculate trust scores for all peers.

  self.reputation.weighted_majority_vote(votes_dict) -> (count, confidence)
      Compute weighted majority. votes_dict = {peer_id: their_count}.

  self.reputation.get_ranked_peers() -> list of ReputationRecords (highest first)


SHARED STATE
------------
  self.node_id              Your node ID (e.g. "hugo")
  self.stats["rounds"]      Current poll round number
  self.stats["messages_sent"]       Counter (increment when you send)
  self.stats["messages_received"]   Counter (incremented automatically)
  self._ping_seq            Heartbeat sequence counter (increment before pings)
  self._log(message)        Print a timestamped log line

CONFIG (from config import ...)
-------------------------------
  BOTS                      ["bot-alpha", "bot-bravo", "bot-charlie"]
  STUDENTS                  ["hugo", "phin", "sam", "bilge", "manuel"]
  COMMON_CONTENT_IDS        ["show:midnight-run", "show:neon-drift", "show:binary-sunset"]
  CONTENT_CATALOG           {"show:midnight-run": ["ad-1", "ad-2", ...], ...}

=============================================================================
"""

import argparse
import random
import signal
import sys
import time
import uuid

from node import P2PNode
from config import BOTS, STUDENTS, COMMON_CONTENT_IDS, CONTENT_CATALOG
import protocol


class MyNode(P2PNode):
    """
    Your P2P node.  Override every method below.

    The base class (P2PNode in node.py) handles:
      - SQS polling loop
      - Message dispatching (routes to your _handle_* methods)
      - Periodic task timers (calls your _do_* methods on schedule)
      - TTL refresh for active peers
      - Gossip entry aging (called automatically each gossip round)

    You handle:
      - Bootstrapping (announcing yourself to the network)
      - All 8 message handlers
      - 4 periodic tasks (gossip, heartbeat, choking, reputation)
      - Application layer (publishing view counts, running audits)
    """

    def __init__(self, node_id: str, verbose: bool = False):
        super().__init__(node_id, verbose)

        # Application-layer state — add your own variables here:
        # e.g.  self.local_counts: dict = {}
        #       self.observed_counts: dict = {}

        # Application-layer timers
        self.publish_rate   = 15
        self.audit_interval = 45
        self._last_publish  = 0.0
        self._last_audit    = 0.0

        # The content catalog your node tracks
        self.content_catalog = COMMON_CONTENT_IDS

    # ==================================================================
    # BOOTSTRAP
    # ==================================================================

    def bootstrap(self, bootstrap_nodes=None):
        """
        Announce yourself to the network.

        What to do:
          1. Choose targets: use bootstrap_nodes if provided, otherwise BOTS
          2. Build a HELLO message:  protocol.hello(self.node_id, self.my_queue_url)
          3. Send it to each target: self.transport.send(target, msg)
          4. Increment self.stats["messages_sent"] for each successful send

        The bootstrap nodes will reply with a PEER_LIST, which triggers
        _handle_peer_list() and populates your gossip table.
        """
        targets = bootstrap_nodes or BOTS
        self._log(f"Bootstrapping via {targets}...")
        raise NotImplementedError("TODO: send HELLO to each bootstrap node")

    # ==================================================================
    # MESSAGE HANDLERS  (called by the dispatcher in node.py)
    # ==================================================================

    def _handle_hello(self, msg):
        """
        A new node announced itself.

        Message fields:  msg["sender"], msg["queue_url"]

        What to do:
          1. Register the sender in ALL FOUR algorithm modules:
               self.gossip.add_peer(sender, queue_url)
               self.heartbeat.add_peer(sender)
               self.choking.add_peer(sender)
               self.reputation.add_peer(sender)
          2. Cache their queue URL so we can send to them:
               self.transport._queue_url_cache[sender] = queue_url
          3. Reply with our peer list so they discover the network:
               peers_data = self.gossip.get_peer_list_message()
               reply = protocol.peer_list(self.node_id, peers_data)
               self.transport.send(sender, reply)
        """
        raise NotImplementedError("TODO: handle HELLO")

    def _handle_peer_list(self, msg):
        """
        Received a gossip peer list from another node.

        Message fields:  msg["sender"], msg["peers"] (list of {"node_id", "queue_url"})

        What to do:
          1. Merge the incoming list into gossip:
               merged = self.gossip.receive_peer_list(msg["peers"], msg["sender"])
          2. For each peer in the incoming list that is NEW to heartbeat:
               - Add them to heartbeat, choking, and reputation
               - Cache their queue_url in self.transport._queue_url_cache
        """
        raise NotImplementedError("TODO: handle PEER_LIST")

    def _handle_ping(self, msg):
        """
        A peer is checking if we are alive.

        Message fields:  msg["sender"], msg["seq"]

        What to do:
          1. Reply with a PONG (echo the same seq number):
               reply = protocol.pong(self.node_id, msg["seq"])
               self.transport.send(sender, reply)
          2. Record their contribution (pinging is useful work):
               self.choking.record_contribution(sender, 1)
               self.reputation.record_heartbeat(sender, responded=True)
        """
        raise NotImplementedError("TODO: handle PING")

    def _handle_pong(self, msg):
        """
        A peer confirmed they are alive.

        Message fields:  msg["sender"], msg["seq"]

        What to do:
          1. Tell heartbeat we got a response:
               self.heartbeat.receive_pong(sender, self.stats["rounds"])
          2. Update reputation:
               self.reputation.record_heartbeat(sender, responded=True)
        """
        raise NotImplementedError("TODO: handle PONG")

    def _handle_view_event(self, msg):
        """
        A host reported their ad view count.

        Message fields:  msg["sender"], msg["content_id"], msg["count"], msg["event_id"]

        What to do:
          1. Store the observation for auditing later (your own data structure)
          2. Record contribution:
               self.choking.record_contribution(sender, 1)
               self.reputation.record_contribution(sender, 1)
        """
        raise NotImplementedError("TODO: handle VIEW_EVENT")

    def _handle_audit_result(self, msg):
        """
        A peer published their audit conclusion.

        Message fields:  msg["sender"], msg["content_id"],
                         msg["agreed_count"], msg["confidence"], msg["voters"]

        What to do:
          1. Log it: self._log(f"AuditResult from {sender}: ...")
          2. Record contribution:
               self.reputation.record_contribution(sender, 1)
        """
        raise NotImplementedError("TODO: handle AUDIT_RESULT")

    def _handle_choke(self, msg):
        """
        A peer is stopping service to us.

        Message fields:  msg["sender"]

        What to do:  Log it.
        """
        raise NotImplementedError("TODO: handle CHOKE")

    def _handle_unchoke(self, msg):
        """
        A peer is resuming service to us.

        Message fields:  msg["sender"]

        What to do:  Log it.
        """
        raise NotImplementedError("TODO: handle UNCHOKE")

    # ==================================================================
    # PERIODIC TASKS  (called on a timer by node.py)
    # ==================================================================

    def _do_gossip(self):
        """
        Send our peer list to a random peer.

        What to do:
          1. IMPORTANT — call super first (runs age_entries):
               super()._do_gossip()
          2. Pick a target:
               target = self.gossip.pick_gossip_target()
          3. If target exists, build and send a PEER_LIST:
               peers_data = self.gossip.get_peer_list_message()
               msg = protocol.peer_list(self.node_id, peers_data)
               self.transport.send(target, msg)
        """
        super()._do_gossip()  # always call super to run age_entries
        raise NotImplementedError("TODO: gossip to a random peer")

    def _do_heartbeat(self):
        """
        Ping all alive/suspect peers and check for misses.

        What to do:
          1. Increment self._ping_seq
          2. Get the list of peers to ping:
               pinged = self.heartbeat.send_pings(self.stats["rounds"])
          3. For each peer in pinged, send a PING:
               msg = protocol.ping(self.node_id, self._ping_seq)
               self.transport.send(peer_id, msg)
          4. Check for peers who didn't respond last round:
               For each peer in self.heartbeat.peers:
                 if state.last_pong_round < self.stats["rounds"] - 1:
                   self.heartbeat.record_miss(peer_id, self.stats["rounds"])
                   self.reputation.record_heartbeat(peer_id, responded=False)
          5. Log status changes:
               for msg_text in self.heartbeat.flush_log():
                   self._log(f"  {msg_text}")
        """
        raise NotImplementedError("TODO: ping peers and check for misses")

    def _do_choking(self):
        """
        Recalculate choke/unchoke decisions.

        What to do:
          1. Run the choking round:
               self.choking.run_choking_round()
          2. Log any state changes:
               for msg_text in self.choking.flush_log():
                   self._log(f"  {msg_text}")
        """
        raise NotImplementedError("TODO: run choking round")

    def _do_reputation(self):
        """
        Update all trust scores.

        What to do:
          1. Recalculate:
               self.reputation.update_all_scores()
          2. Optionally log the top peer:
               ranked = self.reputation.get_ranked_peers()
        """
        raise NotImplementedError("TODO: update reputation scores")

    # ==================================================================
    # APPLICATION LAYER  (2032 ad-counting)
    # ==================================================================

    def _run_periodic_tasks(self):
        """Add application-layer timers on top of the base node timers."""
        super()._run_periodic_tasks()

        now = time.time()
        if now - self._last_publish >= self.publish_rate:
            self._do_publish()
            self._last_publish = now
        if now - self._last_audit >= self.audit_interval:
            self._do_audit()
            self._last_audit = now

    def _do_publish(self):
        """
        Publish a VIEW_EVENT to all alive peers.

        What to do:
          1. Pick a content_id from self.content_catalog
          2. Increment your local view count for it
          3. Build a VIEW_EVENT:
               msg = protocol.view_event(
                   sender=self.node_id,
                   event_id=f"{self.node_id}-{uuid.uuid4().hex[:8]}",
                   content_id=content_id,
                   count=your_count,
               )
          4. Send to all alive peers:
               for peer in self.heartbeat.get_alive_peers():
                   self.transport.send(peer, msg)
        """
        pass  # TODO: publish view counts

    def _do_audit(self):
        """
        Run a reputation-weighted majority vote and broadcast AUDIT_RESULT.

        What to do:
          1. Find a content_id with at least 2 observations
          2. Collect votes: {peer_id: their_reported_count}
          3. Run weighted vote:
               agreed_count, confidence = self.reputation.weighted_majority_vote(votes)
          4. Update reputation based on who agreed/disagreed:
               self.reputation.record_report(peer_id, was_accurate=True/False)
          5. Broadcast the result:
               msg = protocol.audit_result(self.node_id, content_id,
                                           agreed_count, confidence, voters=...)
               for peer in self.heartbeat.get_alive_peers():
                   self.transport.send(peer, msg)
        """
        pass  # TODO: audit view counts

    # ==================================================================
    # STATUS
    # ==================================================================

    def print_status(self):
        """Print node status. Add your own info below super()."""
        super().print_status()
        # TODO: print your local counts, audit log, trust scores, etc.


# ---------------------------------------------------------------------------
# Main  (do not modify)
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="P2P Node")
    parser.add_argument("--id", required=True, help="Your node ID (e.g., hugo)")
    parser.add_argument("--verbose", "-v", action="store_true")
    parser.add_argument("--bootstrap", nargs="*", default=None)
    args = parser.parse_args()

    if args.id not in STUDENTS:
        print(f"[ERR] Use one of: {STUDENTS}")
        sys.exit(1)

    node = MyNode(node_id=args.id, verbose=args.verbose)
    if not node.initialize():
        sys.exit(1)

    def signal_handler(sig, frame):
        print()
        node.print_status()
        node.shutdown()

    signal.signal(signal.SIGINT, signal_handler)

    node.bootstrap(args.bootstrap)
    try:
        node.run()
    except Exception as e:
        print(f"\n[ERR] {e}")
        node.shutdown()


if __name__ == "__main__":
    main()
