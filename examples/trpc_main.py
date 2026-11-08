# Tencent is pleased to support the open source community by making tRPC-Config-Etcd available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-Config-Etcd is licensed under Apache-2.0.
"""Example: load and watch etcd-backed config through the tRPC loader.

Prerequisites (see examples/README.md): an etcd server at 127.0.0.1:2379
with ``salutation_config.json`` and ``server_config.yaml`` keys preset.

Run:
    python3 examples/trpc_main.py
Then change a key with etcdctl and watch the hot-reload callback fire:
    etcdctl put salutation_config.json '{"hello": "nice to meet you!"}'
"""

from __future__ import annotations

import time

import trpc_config_etcd  # noqa: F401  (importing registers the "etcd" provider)
from trpc_sdk.config import ConfigLoaderFactory
from trpc_sdk.config import TrpcConfig
from trpc_sdk.config import with_codec
from trpc_sdk.config import with_provider


def main() -> None:
    # Load the framework startup YAML so plugins.config.etcd is available.
    TrpcConfig.load("examples/trpc_python.yaml")

    # JSON config: salutation_config.json.
    salutation = ConfigLoaderFactory.sync_load("salutation_config.json", with_provider("etcd"), with_codec("json"))
    print("hello ->", salutation.get("hello", ""))

    # YAML config: server_config.yaml.
    server = ConfigLoaderFactory.sync_load("server_config.yaml", with_provider("etcd"), with_codec("yaml"))
    print(f"server -> {server.get('ip', '')}:{server.get('port', 0)}")

    # Hot reload: the callback receives the newly decoded dict on PUT and
    # None/empty data when the key is deleted.
    salutation.hot_reload(lambda data: print("salutation changed ->", data))

    print("watching salutation_config.json, press Ctrl+C to exit ...")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
