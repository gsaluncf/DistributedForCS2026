"""
Your P2P Node — Entry Point
============================

This is where you run your node. Subclass P2PNode and add the
2032 application layer (ViewEvent publishing and auditing), then
run it from the command line:

    python my_node.py --id hugo
    python my_node.py --id hugo --verbose

See node.py for the list of methods you need to implement.
See protocol.py for all 8 message builders.
See algorithms/ for the modules you need to implement.
"""

import argparse
import signal
import sys

from node import P2PNode
from config import STUDENTS


class MyNode(P2PNode):
    """
    Extend P2PNode with your 2032 host behavior.

    You need to add:
      - State variables for tracking view counts and observations
      - _handle_view_event: store observations for auditing
      - _do_publish: broadcast your view counts periodically
      - _do_audit: collect reports, vote, broadcast AUDIT_RESULT

    Everything in P2PNode (gossip, heartbeat, choking, reputation)
    is available via self.gossip, self.heartbeat, self.choking,
    self.reputation. You implement those algorithm modules in
    algorithms/*.py first.
    """

    def __init__(self, node_id: str, verbose: bool = False):
        super().__init__(node_id, verbose)

        # Add your state here:
        # e.g.  self.local_counts: dict = {}
        #       self.observed_counts: dict = {}

        # Publish and audit rates (seconds)
        self.publish_rate   = 15
        self.audit_interval = 45
        self._last_publish  = 0.0
        self._last_audit    = 0.0

        # The content catalog your node tracks
        self.content_catalog = [
            "show:midnight-run",
            "show:neon-drift",
            "show:binary-sunset",
        ]

    def _run_periodic_tasks(self):
        """Add your application-layer timers on top of the base node timers."""
        super()._run_periodic_tasks()

        import time
        now = time.time()

        if now - self._last_publish >= self.publish_rate:
            self._do_publish()
            self._last_publish = now

        if now - self._last_audit >= self.audit_interval:
            self._do_audit()
            self._last_audit = now

    def _handle_view_event(self, msg):
        """Store an incoming ViewEvent for auditing."""
        super()._handle_view_event(msg)
        # TODO: record msg["content_id"] and msg["count"] from msg["sender"]

    def _do_publish(self):
        """Publish a VIEW_EVENT to all alive peers."""
        # TODO: pick content, increment local count, send to alive peers
        pass

    def _do_audit(self):
        """Run a reputation-weighted majority vote and broadcast AUDIT_RESULT."""
        # TODO: collect votes, compute majority, broadcast, update reputation
        pass

    def print_status(self):
        super().print_status()
        # TODO: add your own status output (counts, audit log, etc.)


# ---------------------------------------------------------------------------
# Main
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
