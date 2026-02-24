"""
Module 2: Heartbeat / Liveness Detection
=========================================

Detects when peers go offline using a PING/PONG protocol.

How it works:
  1. Periodically send PING to every known peer.
  2. Peers that respond with PONG before the next round are ALIVE.
  3. Peers that miss `grace_period` consecutive rounds become SUSPECT.
  4. Peers that miss `miss_threshold` consecutive rounds become DEAD.

State machine:
    ALIVE -> SUSPECT (after grace_period misses)
    SUSPECT -> DEAD  (after miss_threshold misses)
    SUSPECT -> ALIVE (if PONG received while suspect)

Run the Algorithm Labs notebook to see the state machine in action
before implementing it here.
"""

import random
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum


class PeerStatus(str, Enum):
    ALIVE   = "ALIVE"
    SUSPECT = "SUSPECT"
    DEAD    = "DEAD"


@dataclass
class PeerState:
    """Tracked state for a single monitored peer."""
    node_id: str
    status: PeerStatus = PeerStatus.ALIVE
    consecutive_misses: int = 0
    last_pong_round: int = 0
    total_pings_sent: int = 0
    total_pongs_received: int = 0

    def response_rate(self) -> float:
        if self.total_pings_sent == 0:
            return 1.0
        return self.total_pongs_received / self.total_pings_sent

    def __repr__(self) -> str:
        return (f"PeerState({self.node_id}, {self.status}, "
                f"misses={self.consecutive_misses}, "
                f"rate={self.response_rate():.0%})")


class HeartbeatNode:
    """
    Sends PINGs to peers and tracks their liveness status.

    State:
        node_id        - this node's identifier
        peers          - dict of node_id -> PeerState
        miss_threshold - consecutive misses before marking DEAD
        grace_period   - consecutive misses before marking SUSPECT
    """

    def __init__(
        self,
        node_id: str,
        miss_threshold: int = 3,
        grace_period: int = 2,
    ):
        """
        Args:
            node_id:        This node's identifier.
            miss_threshold: Consecutive misses before DEAD (must be > grace_period).
            grace_period:   Consecutive misses before SUSPECT.
        """
        self.node_id = node_id
        self.miss_threshold = miss_threshold
        self.grace_period = grace_period
        self.peers: Dict[str, PeerState] = {}
        self._log: List[str] = []

    def add_peer(self, node_id: str) -> None:
        """Register a new peer to monitor (start in ALIVE state)."""
        raise NotImplementedError

    def send_pings(self, current_round: int) -> List[str]:
        """
        Record that we are sending a PING to every ALIVE and SUSPECT peer.

        Increments total_pings_sent for each peer pinged.
        Dead peers are skipped.

        Returns:
            List of peer_ids that should receive a PING this round.
        """
        raise NotImplementedError

    def receive_pong(self, from_node: str, current_round: int) -> None:
        """
        Process a PONG response from a peer.

        Update the peer's state:
          - Reset consecutive_misses to 0
          - Set status back to ALIVE
          - Update last_pong_round and total_pongs_received

        Args:
            from_node:     node_id of the peer who replied
            current_round: current poll round number
        """
        raise NotImplementedError

    def record_miss(self, peer_id: str, current_round: int) -> None:
        """
        Record that a PING got no PONG from this peer this round.

        Update the peer's state machine:
          - Increment consecutive_misses
          - If misses >= miss_threshold -> DEAD
          - If misses >= grace_period   -> SUSPECT
          - Log any status transition

        Args:
            peer_id:       node_id of the non-responding peer
            current_round: current poll round number
        """
        raise NotImplementedError

    def get_alive_peers(self) -> List[str]:
        """Return node_ids of all ALIVE peers."""
        raise NotImplementedError

    def get_suspect_peers(self) -> List[str]:
        """Return node_ids of all SUSPECT peers."""
        raise NotImplementedError

    def get_dead_peers(self) -> List[str]:
        """Return node_ids of all DEAD peers."""
        raise NotImplementedError

    def prune_dead(self) -> None:
        """Remove DEAD peers from the tracking table."""
        raise NotImplementedError

    def flush_log(self) -> List[str]:
        msgs = list(self._log)
        self._log.clear()
        return msgs

    def __repr__(self) -> str:
        alive = self.get_alive_peers() if self.peers else []
        dead  = self.get_dead_peers()  if self.peers else []
        return f"HeartbeatNode({self.node_id}, alive={alive}, dead={dead})"
