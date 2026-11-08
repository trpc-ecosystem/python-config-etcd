# Tencent is pleased to support the open source community by making tRPC-Config-Etcd available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-Config-Etcd is licensed under Apache-2.0.
"""Constants for the etcd config provider plugin."""

from __future__ import annotations

import enum


class EventType(enum.Enum):
    """Watch event type."""

    NULL = 0
    PUT = 1
    DELETE = 2
