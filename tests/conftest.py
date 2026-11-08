# Tencent is pleased to support the open source community by making tRPC-Config-Etcd available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-Config-Etcd is licensed under Apache-2.0.
"""Test fixtures: an in-memory fake of the etcd3 client used by the provider."""

from __future__ import annotations

import os
import queue
import sys
import threading

import pytest

# Make the package and (in a monorepo checkout) the sibling trpc_sdk
# importable without installing anything.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_WORKSPACE_ROOT = os.path.dirname(_REPO_ROOT)
for _path in (_REPO_ROOT, _WORKSPACE_ROOT):
    if os.path.isdir(_path) and _path not in sys.path:
        sys.path.insert(0, _path)


class FakeEvent:
    """Minimal stand-in for an etcd3 watch event."""

    def __init__(self, key, value, mod_revision=0, delete=False):
        self.key = key.encode() if isinstance(key, str) else key
        # etcd3 exposes PutEvent/DeleteEvent classes; mirror the class name.
        self.__class__ = FakeDeleteEvent if delete else FakePutEvent
        self.value = value
        self.mod_revision = mod_revision


class FakePutEvent(FakeEvent):
    pass


class FakeDeleteEvent(FakeEvent):
    pass


class _FakeWatch:

    def __init__(self):
        self.events = queue.Queue()
        self.cancelled = threading.Event()

    def iterator(self):
        while not self.cancelled.is_set():
            try:
                event = self.events.get(timeout=0.05)
            except queue.Empty:
                continue
            if event is None:
                return
            yield event

    def cancel(self):
        self.cancelled.set()
        self.events.put(None)


class FakeEtcdClient:
    """In-memory fake implementing the subset of etcd3 the provider uses."""

    def __init__(self, store=None):
        self.store = dict(store or {})
        self.watches = []
        self.watch_calls = 0
        self.watch_failures = 0  # number of initial watch() calls that raise
        self.closed = False
        self._lock = threading.Lock()

    # etcd3.KV
    def get(self, key):
        value = self.store.get(key)
        return (value, None) if value is not None else (None, None)

    def put(self, key, value):
        self.store[key] = value

    # etcd3 status probe used for endpoint failover
    def status(self):
        return object()

    # etcd3.Watcher
    def watch(self, key, start_revision=None):
        with self._lock:
            self.watch_calls += 1
            if self.watch_failures > 0:
                self.watch_failures -= 1
                raise RuntimeError("watch stream unavailable")
            watch = _FakeWatch()
            watch.key = key
            watch.start_revision = start_revision
            self.watches.append(watch)
        return watch.iterator(), watch.cancel

    def emit(self, key, value, delete=False, mod_revision=0):
        for watch in list(self.watches):
            if watch.key == key and not watch.cancelled.is_set():
                watch.events.put(FakeEvent(key, value, mod_revision=mod_revision, delete=delete))

    def close(self):
        self.closed = True
        for watch in list(self.watches):
            watch.cancel()


@pytest.fixture()
def fake_client():
    return FakeEtcdClient({"/app/salutation_config.json": b'{"hello": "world"}', "plain": b"plain-value"})


def wait_until(predicate, timeout=5.0):
    """Poll ``predicate`` until it is true or ``timeout`` seconds elapse."""
    import time

    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()
