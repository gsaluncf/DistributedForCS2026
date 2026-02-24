"""
Module 3: Choking / Unchoking (BitTorrent-style)
=================================================

Enforces reciprocity by limiting service to peers who contribute.

How it works:
  1. Track how much each peer has contributed (data, messages, etc.).
  2. Periodically rank peers by contribution and unchoke the top N.
  3. Choke everyone else (stop serving them).
  4. Every `optimistic_interval` rounds, randomly unchoke one choked peer
     to give new peers a chance (optimistic unchoke).

This is the mechanism BitTorrent uses to prevent free-riding.
Peers who only download and never upload will eventually get choked
by everyone and stall.

Run the Algorithm Labs notebook before implementing this.
"""

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class PeerTracker:
    """Tracks a single peer's contribution and choking state."""
    node_id: str
    contributed: int = 0         # units this peer has given us
    received: int = 0            # units we have given this peer
    is_choked: bool = True       # True = we are NOT serving this peer
    is_interested: bool = True   # True = this peer wants service
    rounds_choked: int = 0       # consecutive rounds spent choked

    def reciprocity_ratio(self) -> float:
        """How much they give vs. how much they take. Higher is better."""
        if self.received == 0:
            return float(self.contributed)
        return self.contributed / self.received

    def __repr__(self) -> str:
        state = "unchoked" if not self.is_choked else "CHOKED"
        return (f"PeerTracker({self.node_id}, contributed={self.contributed}, "
                f"received={self.received}, {state})")


class ChokingNode:
    """
    Implements BitTorrent-style tit-for-tat choking.

    State:
        node_id            - this node's identifier
        max_unchoked       - max simultaneous unchoked peers
        optimistic_interval - rounds between optimistic unchoke rotations
        peers              - dict of node_id -> PeerTracker
        _round             - current round counter
        _optimistic_peer   - node_id of the current lucky optimistic unchoke
    """

    def __init__(
        self,
        node_id: str,
        max_unchoked: int = 4,
        optimistic_interval: int = 3,
    ):
        """
        Args:
            node_id:             This node's identifier.
            max_unchoked:        Max simultaneous unchoked peers (BitTorrent default: 4).
            optimistic_interval: Rounds between optimistic unchoke rotations.
        """
        self.node_id = node_id
        self.max_unchoked = max_unchoked
        self.optimistic_interval = optimistic_interval
        self.peers: Dict[str, PeerTracker] = {}
        self._round = 0
        self._optimistic_peer: Optional[str] = None
        self._log: List[str] = []

    def add_peer(self, node_id: str, interested: bool = True) -> None:
        """Register a new peer. New peers start choked."""
        raise NotImplementedError

    def record_contribution(self, from_peer: str, units: int = 1) -> None:
        """Record that a peer contributed `units` to us."""
        raise NotImplementedError

    def record_serving(self, to_peer: str, units: int = 1) -> None:
        """Record that we served `units` to a peer."""
        raise NotImplementedError

    def run_choking_round(self) -> None:
        """
        Recalculate choke/unchoke decisions for this round.

        Algorithm:
          1. Increment round counter.
          2. Sort interested peers by reciprocity_ratio (descending).
          3. Unchoke the top `max_unchoked - 1` peers.
          4. Every `optimistic_interval` rounds, pick one random choked peer
             as the optimistic unchoke (gives new peers a chance).
          5. Choke everyone else.
          6. Send CHOKE / UNCHOKE messages to peers whose state changed.
             Log those changes via self._log.

        Note: Only unchoke peers where is_interested == True.
        """
        raise NotImplementedError

    def get_unchoked_peers(self) -> List[str]:
        """Return node_ids of all currently unchoked peers."""
        raise NotImplementedError

    def get_choked_peers(self) -> List[str]:
        """Return node_ids of all currently choked peers."""
        raise NotImplementedError

    def flush_log(self) -> List[str]:
        msgs = list(self._log)
        self._log.clear()
        return msgs

    def __repr__(self) -> str:
        unchoked = self.get_unchoked_peers() if self.peers else []
        return f"ChokingNode({self.node_id}, unchoked={unchoked})"
