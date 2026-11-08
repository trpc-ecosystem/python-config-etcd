# Tencent is pleased to support the open source community by making tRPC-Config-Etcd available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-Config-Etcd is licensed under Apache-2.0.
"""Plugin registration and ConfigLoader integration tests."""

import pytest

from trpc_sdk.abc import PluginType
from trpc_sdk.config import ConfigLoader
from trpc_sdk.config import JsonDecoder
from trpc_sdk.plugin import get_plugin

import trpc_config_etcd
from trpc_config_etcd import EtcdConfigProvider

from conftest import wait_until


def test_plugin_registered_as_config_provider():
    provider = get_plugin(PluginType.CONFIG_PROVIDER, "etcd")
    assert isinstance(provider, EtcdConfigProvider)


def test_config_loader_end_to_end(fake_client):
    provider = EtcdConfigProvider(client=fake_client)
    loader = ConfigLoader("plain", provider=provider, decoder=JsonDecoder())
    fake_client.store["plain"] = b'{"port": 8080}'
    import asyncio

    data = asyncio.run(loader.load())
    assert data == {"port": 8080}
    assert loader.get("port", 0) == 8080

    changed = []
    loader.hot_reload(changed.append)
    assert wait_until(lambda: len(fake_client.watches) == 1)
    fake_client.emit("plain", b'{"port": 9090}')
    assert wait_until(lambda: changed == [{"port": 9090}])
    assert loader.get("port", 0) == 9090
    provider.close()


@pytest.mark.integration
def test_real_etcd_roundtrip():
    """Requires a real etcd at 127.0.0.1:2379 (skipped otherwise)."""
    try:
        import etcd3
    except Exception:
        pytest.skip("etcd3 client not importable (protobuf version conflict?)")
    try:
        raw = etcd3.client(host="127.0.0.1", port=2379, timeout=2)
        raw.status()
    except Exception:
        pytest.skip("no etcd server at 127.0.0.1:2379")

    raw.put("/trpc-config-etcd-test/key.json", '{"hello": "world"}')
    try:
        provider = EtcdConfigProvider()
        assert provider.load("/trpc-config-etcd-test/key.json") == b'{"hello": "world"}'
        provider.close()
    finally:
        raw.delete("/trpc-config-etcd-test/key.json")
