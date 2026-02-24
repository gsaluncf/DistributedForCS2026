"""
Shared configuration for the P2P lab.
All AWS resource names, student list, bot list, and common settings.

Naming convention:  ds2032-node-{name}-p2p   (standard queues, NOT FIFO)
This distinguishes P2P queues from the pub/sub FIFO queues (ds2032-node-{name}.fifo).
"""

# AWS
REGION = "us-east-1"
ACCOUNT_ID = "194722398367"

# Naming prefix (shared with pub/sub track)
PREFIX = "ds2032"

# Students
STUDENTS = ["hugo", "phin", "sam", "bilge", "manuel"]

# Instructor
INSTRUCTOR = "gil"

# Bot nodes (always-on bootstrap peers run by instructor)
BOTS = ["bot-alpha", "bot-bravo", "bot-charlie"]

# ---------------------------------------------------------------------------
# Queue naming
# ---------------------------------------------------------------------------

def node_queue_name(node_id: str) -> str:
    """SQS queue name for a P2P node (standard, not FIFO)."""
    return f"{PREFIX}-node-{node_id}-p2p"


# All node IDs (students + instructor + bots)
ALL_NODES = STUDENTS + [INSTRUCTOR] + BOTS

# All queue names for provisioning
ALL_QUEUE_NAMES = [node_queue_name(n) for n in ALL_NODES]

# ---------------------------------------------------------------------------
# P2P message protocol
# ---------------------------------------------------------------------------

MESSAGE_TYPES = [
    "HELLO",         # Initial handshake: "I exist, here's my node_id and queue"
    "PEER_LIST",     # Gossip: share known peers
    "PING",          # Heartbeat: are you alive?
    "PONG",          # Heartbeat: yes I am
    "VIEW_EVENT",    # 2032 content: a host reports a view
    "AUDIT_RESULT",  # 2032 audit: a node's count/agreement for a content_id
    "CHOKE",         # Choking: I'm stopping service to you
    "UNCHOKE",       # Choking: I'm resuming service to you
]

# ---------------------------------------------------------------------------
# Content catalog — shared across all nodes
# ---------------------------------------------------------------------------

# Common shows: every node on the network reports on these.
# Auditing requires multiple nodes to report on the same content_id.
CONTENT_CATALOG = {
    "show:midnight-run":   ["ad-1", "ad-2", "ad-3"],
    "show:neon-drift":     ["ad-4", "ad-5"],
    "show:binary-sunset":  ["ad-6", "ad-7"],
}

# Regional shows: bots may also report on these.
# Nodes are not required to cover these, but they add realism.
REGIONAL_CONTENT = {
    "show:echo-valley":    ["ad-8", "ad-9"],
    "show:ghost-protocol": ["ad-10"],
}

COMMON_CONTENT_IDS = list(CONTENT_CATALOG.keys())

# ---------------------------------------------------------------------------
# Queue defaults
# ---------------------------------------------------------------------------

QUEUE_ATTRIBUTES = {
    "VisibilityTimeout": "30",
    "MessageRetentionPeriod": "86400",  # 1 day
}
