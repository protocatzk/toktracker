"""
TokTracker - Shared Contracts & Constants
Definiert Redis-Keys, Channel-Namen, RPC-Methoden und Event-Typen.
"""

# Redis Streams & PubSub
STREAM_EVENTS = "tt:events"
CHANNEL_COMMANDS = "tt:cmd:broadcast"
CHANNEL_RECONCILE = "tt:cmd:reconcile"
CHANNEL_SETTINGS_CHANGED = "tt:cmd:settings_changed"

# Bot RPC
RPC_BOT_QUEUE = "tt:rpc:bot:requests"
RPC_BOT_REPLY_PREFIX = "tt:rpc:bot:reply:"

# Key Prefixes
PREFIX_LEASE = "tt:lease:"                     # tt:lease:<username> -> instance_id
PREFIX_DIAG_WORKER = "tt:diag:worker:"         # tt:diag:worker:<username> -> JSON
KEY_DIAG_BOT = "tt:diag:bot"                   # JSON
PREFIX_HEARTBEAT_INGEST = "tt:hb:ingest:"      # tt:hb:ingest:<instance_id> -> ISO ts
KEY_HEARTBEAT_BOT = "tt:hb:bot"
KEY_HEARTBEAT_SCHEDULER = "tt:hb:scheduler"

# Leader Locks
LOCK_BOT = "tt:lock:bot:leader"
LOCK_SCHEDULER = "tt:lock:scheduler:leader"

# Auth Challenges
PREFIX_AUTH_CHALLENGE = "tt:auth:challenge:"   # tt:auth:challenge:<cid> -> JSON
KEY_AUTH_RECENT_LIST = "tt:auth:recent"        # Redis List von challenge_ids

# Event Typen
EVENT_GIFT = "gift"
EVENT_LIVE_STATUS = "live_status"
EVENT_BATTLE_START = "battle_start"
EVENT_BATTLE_FINISH = "battle_finish"
EVENT_WHALE = "whale"
