"""
Module 1: Gossip Protocol
=========================

Simulates peer-list gossip among a network of nodes.

How gossip works:
  1. Each node maintains a list of peers it knows about.
  2. Periodically, a node picks a random peer and shares its peer list.
  3. The receiving node merges the incoming list with its own.
  4. Over time, all nodes converge to a complete view of the network.

Real-world systems that use gossip:
  - Apache Cassandra (cluster membership)
  - Amazon DynamoDB (ring topology)
  - Consul (membership and health)

Run the Algorithm Labs notebook to see gossip convergence in action
before implementing it here.
"""

import random
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


@dataclass
class PeerEntry:
    """A single known peer in the gossip table."""
    node_id: str
    queue_url: str
    last_seen: float
    ttl: int = 5   # rounds until expiry (refreshed on re-gossip)

    def is_expired(self) -> bool:
        return self.ttl <= 0

    def __repr__(self) -> str:
        return f"PeerEntry({self.node_id}, ttl={self.ttl})"


class GossipNode:
    """
    A node that participates in gossip-based peer discovery.

    State:
        node_id   - this node's identifier
        peers     - dict of node_id -> PeerEntry for all known peers
    """

    def __init__(self, node_id: str, queue_url: str = ""):
        self.node_id = node_id
        self.queue_url = queue_url or f"sqs://fake/{node_id}"
        self.peers: Dict[str, PeerEntry] = {}
        self._log: List[str] = []

    def add_peer(self, node_id: str, queue_url: str = "") -> None:
        """
        Manually add or refresh a peer (bootstrap / initial knowledge).

        Called when:
          - We receive a HELLO from a new node
          - We are told about a peer via PEER_LIST

        Args:
            node_id:   The peer's identifier
            queue_url: The peer's SQS queue URL
        """
        raise NotImplementedError

    def get_peer_list_message(self) -> List[dict]:
        """
        Build a PEER_LIST message payload (list of dicts to send over SQS).

        Returns a list of {"node_id": ..., "queue_url": ...} dicts for all
        known non-expired peers. Include yourself so recipients know your URL.
        """
        raise NotImplementedError

    def receive_peer_list(self, incoming: List[dict], sender_id: str) -> int:
        """
        Merge an incoming peer list with our own.

        For each peer in the incoming list:
          - If we don't know them, add them (TTL = 5)
          - If we already know them, refresh their TTL

        Args:
            incoming:  List of {"node_id": str, "queue_url": str} dicts
            sender_id: node_id of the peer who sent this list

        Returns:
            Number of new peers discovered (not previously in our table)
        """
        raise NotImplementedError

    def age_entries(self) -> None:
        """
        Decrement TTL on all entries; remove expired ones.
        Called once per poll round.

        A peer that has not been mentioned in any gossip for `ttl` rounds
        should be removed from the table.
        """
        raise NotImplementedError

    def pick_gossip_target(self) -> Optional[str]:
        """
        Pick a random peer to send a PEER_LIST to.
        Returns None if no peers are known yet.
        """
        raise NotImplementedError

    def known_peer_count(self) -> int:
        return len(self.peers)

    def __repr__(self) -> str:
        return f"GossipNode({self.node_id}, peers={list(self.peers.keys())})"
