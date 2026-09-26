"""Network collector cadence + link bandwidth envelopes."""

from __future__ import annotations

NET_SAMPLE_INTERVAL_SEC = 60

NET_HISTORY_MINUTES = 60

NET_HISTORY_LEN = NET_HISTORY_MINUTES  # one sample per minute

# Bandwidth (bps) by role — used for util % and Top Talkers

BW_SPINE_UPLINK = 400_000_000_000  # 400GbE leaf↔spine

BW_LEAF_HOST = 100_000_000_000  # 100GbE host/storage

BW_LEAF_PEER = 400_000_000_000

BW_IB_LINK = 400_000_000_000  # NDR class envelope for sim

BW_MGMT = 1_000_000_000

