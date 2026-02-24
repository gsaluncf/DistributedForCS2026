"""
P2P Node
========

Provides two classes:

  SQSTransport  -- Fully working. Handles all SQS communication.
                   DO NOT MODIFY. You use this through self.transport.

  P2PNode       -- Shell. The polling loop and message dispatcher are
                   already wired. You implement the handlers and
                   periodic tasks inside each method.

Architecture:
  run() polls SQS every few seconds, calls handle_message() for each
  received message, then calls _run_periodic_tasks() for timers.
"""

import json
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import boto3
from botocore.exceptions import ClientError

from config import (
    REGION, ACCOUNT_ID, PREFIX,
    STUDENTS, INSTRUCTOR, BOTS, ALL_NODES,
    node_queue_name, QUEUE_ATTRIBUTES,
)
import protocol
from algorithms.gossip import GossipNode
from algorithms.heartbeat import HeartbeatNode
from algorithms.choking import ChokingNode
from algorithms.reputation import ReputationNode


# ---------------------------------------------------------------------------
# SQSTransport  (fully working — do not modify)
# ---------------------------------------------------------------------------

class SQSTransport:
    """
    Handles all communication with AWS SQS.

    Usage:
        transport = SQSTransport()
        transport.load_resources()             # load queue URLs
        transport.send("hugo", msg_dict)       # send to hugo's queue
        msgs = transport.receive("my_id")      # poll my queue
        transport.delete("my_id", receipt)     # ack a processed message
    """

    def __init__(self, region: str = REGION):
        self.sqs = boto3.Session(region_name=region).client("sqs")
        self._queue_url_cache: Dict[str, str] = {}

    def load_resources(self, resources_file: str = "resources.json") -> bool:
        """Load queue URLs from resources.json."""
        try:
            with open(resources_file) as f:
                data = json.load(f)
            self._queue_url_cache = data.get("queues", {})
            return True
        except FileNotFoundError:
            print(f"[WARN] {resources_file} not found.")
            return False

    def get_queue_url(self, node_id: str) -> Optional[str]:
        """Get the SQS queue URL for a node."""
        if node_id in self._queue_url_cache:
            return self._queue_url_cache[node_id]
        try:
            resp = self.sqs.get_queue_url(QueueName=node_queue_name(node_id))
            url = resp["QueueUrl"]
            self._queue_url_cache[node_id] = url
            return url
        except ClientError:
            return None

    def send(self, target_node_id: str, msg: Dict[str, Any]) -> bool:
        """Send a JSON message to a node's SQS queue."""
        url = self.get_queue_url(target_node_id)
        if not url:
            return False
        try:
            self.sqs.send_message(
                QueueUrl=url,
                MessageBody=protocol.encode(msg),
            )
            return True
        except ClientError as e:
            print(f"[ERR] Send to {target_node_id}: {e}")
            return False

    def receive(self, node_id: str, max_messages: int = 10, wait_seconds: int = 5) -> List[Dict[str, Any]]:
        """Long-poll receive from this node's queue. Returns decoded message dicts."""
        url = self.get_queue_url(node_id)
        if not url:
            return []
        try:
            resp = self.sqs.receive_message(
                QueueUrl=url,
                MaxNumberOfMessages=min(max_messages, 10),
                WaitTimeSeconds=wait_seconds,
            )
            messages = []
            for sqs_msg in resp.get("Messages", []):
                msg = protocol.decode(sqs_msg["Body"])
                msg["_receipt_handle"] = sqs_msg["ReceiptHandle"]
                messages.append(msg)
            return messages
        except ClientError as e:
            print(f"[ERR] Receive for {node_id}: {e}")
            return []

    def delete(self, node_id: str, receipt_handle: str) -> None:
        """Delete a processed message from the queue (acknowledges it)."""
        url = self.get_queue_url(node_id)
        if url:
            try:
                self.sqs.delete_message(QueueUrl=url, ReceiptHandle=receipt_handle)
            except ClientError:
                pass


# ---------------------------------------------------------------------------
# P2PNode  (shell — implement the methods marked TODO)
# ---------------------------------------------------------------------------

class P2PNode:
    """
    A P2P node that participates in the 2032 ad-counting network.

    The polling loop and message dispatcher are already wired up.
    Your job is to implement each handler and periodic task.

    Lifecycle:
      1. __init__:    Set up transport and algorithm modules.
      2. initialize(): Load resources.json, resolve your queue URL.
      3. bootstrap(): Send HELLO to bootstrap nodes.
      4. run():       Enter the main loop.
      5. shutdown():  Ctrl+C triggers this.
    """

    def __init__(self, node_id: str, verbose: bool = False):
        self.node_id = node_id
        self.verbose = verbose
        self.running = False

        # Transport (fully working — use self.transport.send / receive)
        self.transport = SQSTransport()
        self.my_queue_url: Optional[str] = None

        # Algorithm modules — you implement these
        self.gossip     = GossipNode(node_id)
        self.heartbeat  = HeartbeatNode(node_id)
        self.choking    = ChokingNode(node_id)
        self.reputation = ReputationNode(node_id)

        # Periodic task timers (seconds) — tune these if you want
        self.gossip_interval     = 15
        self.heartbeat_interval  = 10
        self.choking_interval    = 30
        self.reputation_interval = 30
        self._last_gossip        = 0.0
        self._last_heartbeat     = 0.0
        self._last_choking       = 0.0
        self._last_reputation    = 0.0

        self._ping_seq = 0
        self.stats = {"messages_received": 0, "messages_sent": 0, "rounds": 0}

    def initialize(self) -> bool:
        """Load resources.json and resolve your own queue URL."""
        if not self.transport.load_resources():
            return False
        self.my_queue_url = self.transport.get_queue_url(self.node_id)
        if not self.my_queue_url:
            print(f"[ERR] No queue URL for {self.node_id}. Check resources.json.")
            return False
        self._log(f"Initialized. Queue: {self.my_queue_url}")
        return True

    # ------------------------------------------------------------------
    # Bootstrap
    # ------------------------------------------------------------------

    def bootstrap(self, bootstrap_nodes: Optional[List[str]] = None) -> None:
        """
        Announce yourself to the network by sending HELLO to bootstrap nodes.

        Default bootstrap targets are the instructor bots (bot-alpha, etc.).
        Each bot will respond with a PEER_LIST so you discover the network.

        TODO: Build a HELLO message using protocol.hello() and send it to
        each bootstrap node via self.transport.send().
        """
        targets = bootstrap_nodes or BOTS
        self._log(f"Bootstrapping via {targets}...")
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Message dispatcher  (wired — do not modify)
    # ------------------------------------------------------------------

    def handle_message(self, msg: Dict[str, Any]) -> None:
        """Route an incoming message to the appropriate handler."""
        msg_type = msg.get("type")
        sender   = msg.get("sender", "?")

        if sender == self.node_id:
            return  # ignore echoes of our own messages

        self.stats["messages_received"] += 1

        handlers = {
            protocol.HELLO:        self._handle_hello,
            protocol.PEER_LIST:    self._handle_peer_list,
            protocol.PING:         self._handle_ping,
            protocol.PONG:         self._handle_pong,
            protocol.VIEW_EVENT:   self._handle_view_event,
            protocol.AUDIT_RESULT: self._handle_audit_result,
            protocol.CHOKE:        self._handle_choke,
            protocol.UNCHOKE:      self._handle_unchoke,
        }

        handler = handlers.get(msg_type)
        if handler:
            if self.verbose:
                self._log(f"<- {protocol.format_msg(msg, compact=True)}")
            handler(msg)
        else:
            self._log(f"Unknown message type: {msg_type}")

    # ------------------------------------------------------------------
    # Message handlers  (TODO: implement each one)
    # ------------------------------------------------------------------

    def _handle_hello(self, msg: Dict[str, Any]) -> None:
        """
        A new node has announced itself.

        What to do:
          - Register the sender in all four algorithm modules
          - Cache their queue_url in self.transport._queue_url_cache
          - Reply with a PEER_LIST so they know who else is on the network

        Message fields: sender, queue_url
        """
        raise NotImplementedError

    def _handle_peer_list(self, msg: Dict[str, Any]) -> None:
        """
        Received a gossip peer list from another node.

        What to do:
          - Merge the incoming peers into self.gossip
          - Register any brand-new peers in heartbeat, choking, reputation
          - Cache their queue URLs

        Message fields: sender, peers (list of {node_id, queue_url})
        """
        raise NotImplementedError

    def _handle_ping(self, msg: Dict[str, Any]) -> None:
        """
        A peer is checking if we are alive.

        What to do:
          - Reply immediately with a PONG (same seq number)
          - Record the sender's contribution in choking and reputation

        Message fields: sender, seq
        """
        raise NotImplementedError

    def _handle_pong(self, msg: Dict[str, Any]) -> None:
        """
        A peer confirmed they are alive.

        What to do:
          - Tell self.heartbeat that we received a PONG from this peer
          - Update reputation for a heartbeat response

        Message fields: sender, seq
        """
        raise NotImplementedError

    def _handle_view_event(self, msg: Dict[str, Any]) -> None:
        """
        A host reported their ad view count for a piece of content.

        What to do:
          - Store the observation for auditing later
          - Record contribution in choking and reputation

        Message fields: sender, content_id, count, event_id
        """
        raise NotImplementedError

    def _handle_audit_result(self, msg: Dict[str, Any]) -> None:
        """
        A peer published their audit conclusion.

        What to do:
          - Log or store the result
          - Record contribution in reputation

        Message fields: sender, content_id, agreed_count, confidence, voters
        """
        raise NotImplementedError

    def _handle_choke(self, msg: Dict[str, Any]) -> None:
        """
        A peer is stopping service to us.

        What to do: log it, update any local state you track about choke status.

        Message fields: sender
        """
        raise NotImplementedError

    def _handle_unchoke(self, msg: Dict[str, Any]) -> None:
        """
        A peer is resuming service to us.

        What to do: log it, update any local state.

        Message fields: sender
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Periodic tasks  (TODO: implement each one)
    # ------------------------------------------------------------------

    def _run_periodic_tasks(self) -> None:
        """Called once per poll loop iteration. Do not modify the timer logic."""
        now = time.time()

        if now - self._last_gossip >= self.gossip_interval:
            self._do_gossip()
            self._last_gossip = now

        if now - self._last_heartbeat >= self.heartbeat_interval:
            self._do_heartbeat()
            self._last_heartbeat = now

        if now - self._last_choking >= self.choking_interval:
            self._do_choking()
            self._last_choking = now

        if now - self._last_reputation >= self.reputation_interval:
            self._do_reputation()
            self._last_reputation = now

    def _do_gossip(self) -> None:
        """
        Send our peer list to a random peer.

        What to do:
          - Pick a gossip target via self.gossip.pick_gossip_target()
          - Build a PEER_LIST message using protocol.peer_list()
          - Send it via self.transport.send()
        """
        raise NotImplementedError

    def _do_heartbeat(self) -> None:
        """
        Ping all alive/suspect peers and record misses.

        What to do:
          - Increment self._ping_seq
          - Call self.heartbeat.send_pings() to get the list of peers to ping
          - For each peer, send a PING via protocol.ping() + self.transport.send()
          - For peers that have not responded recently, call
            self.heartbeat.record_miss()
        """
        raise NotImplementedError

    def _do_choking(self) -> None:
        """
        Recalculate choke/unchoke decisions.

        What to do:
          - Call self.choking.run_choking_round()
          - Log any state changes from self.choking.flush_log()
        """
        raise NotImplementedError

    def _do_reputation(self) -> None:
        """
        Recalculate all trust scores.

        What to do:
          - Call self.reputation.update_all_scores()
        """
        raise NotImplementedError

    # ------------------------------------------------------------------
    # Main loop  (wired — do not modify)
    # ------------------------------------------------------------------

    def run(self) -> None:
        """Poll SQS, dispatch messages, run periodic tasks. Loops until shutdown()."""
        self.running = True
        self._log("Starting main loop...")
        print(f"\n[{self.node_id}] Node running. Press Ctrl+C to stop.\n")

        while self.running:
            self.stats["rounds"] += 1

            messages = self.transport.receive(self.node_id, max_messages=10, wait_seconds=5)

            for msg in messages:
                self.handle_message(msg)
                receipt = msg.pop("_receipt_handle", None)
                if receipt:
                    self.transport.delete(self.node_id, receipt)

            self._run_periodic_tasks()
            self.gossip.age_entries()

        self._log("Main loop exited.")

    def shutdown(self) -> None:
        """Signal the main loop to stop gracefully."""
        self._log("Shutting down...")
        self.running = False

    def print_status(self) -> None:
        """Print current node status. Override in subclass to add your own info."""
        print(f"\n{'='*50}")
        print(f"Node:     {self.node_id}")
        print(f"Rounds:   {self.stats['rounds']}")
        print(f"Messages: {self.stats['messages_received']} in, "
              f"{self.stats['messages_sent']} out")
        print(f"{'='*50}\n")

    def _log(self, message: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        print(f"[{ts}] [{self.node_id}] {message}")
