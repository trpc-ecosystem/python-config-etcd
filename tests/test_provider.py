# Tencent is pleased to support the open source community by making tRPC-Config-Etcd available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-Config-Etcd is licensed under Apache-2.0.
"""Tests for EtcdConfigProvider load / hot_reload behaviour."""

import pytest

from trpc_sdk.config import ProviderError

from trpc_config_etcd import EtcdProviderConfig
from trpc_config_etcd import EventType
from trpc_config_etcd import EtcdConfigProvider

from conftest import wait_until


def make_provider(fake_client, **config_kwargs):
    return EtcdConfigProvider(config=EtcdProviderConfig(**config_kwargs), client=fake_client)


def test_load_hit_with_prefix(fake_client):
    provider = make_provider(fake_client, prefix="/app")
    assert provider.load("salutation_config.json") == b'{"hello": "world"}'


def test_load_without_prefix_and_options_fallback(fake_client):
    provider = make_provider(fake_client)
    assert provider.load("plain") == b"plain-value"
    assert provider.load("", {"file_path": "plain"}) == b"plain-value"


def test_load_missing_key_raises_provider_error(fake_client):
    provider = make_provider(fake_client)
    with pytest.raises(ProviderError):
        provider.load("does-not-exist")


def test_load_empty_key_raises_provider_error(fake_client):
    provider = make_provider(fake_client)
    with pytest.raises(ProviderError):
        provider.load("")


def test_load_per_call_options_override_prefix(fake_client):
    fake_client.store["/other/plain"] = b"other-value"
    provider = make_provider(fake_client, prefix="/app")
    assert provider.load("plain", {"prefix": "/other"}) == b"other-value"


def test_load_etcd_failure_wrapped_as_provider_error(fake_client):

    class BrokenClient:

        def get(self, key):
            raise RuntimeError("connection refused")

    provider = EtcdConfigProvider(client=BrokenClient())
    with pytest.raises(ProviderError):
        provider.load("plain")


def test_set_options_supplies_endpoints_and_prefix(fake_client):
    provider = EtcdConfigProvider(client=fake_client)
    provider.set_options({"prefix": "/app"})
    assert provider.load("salutation_config.json") == b'{"hello": "world"}'


def test_global_plugins_config_section(fake_client, monkeypatch):
    from trpc_sdk.config import TrpcConfig

    monkeypatch.setattr(TrpcConfig, "_plugins_config", {"config": {"etcd": {"prefix": "/app"}}})
    provider = EtcdConfigProvider(client=fake_client)
    assert provider.load("salutation_config.json") == b'{"hello": "world"}'


def test_global_providers_list(fake_client, monkeypatch):
    from trpc_sdk.config import TrpcConfig

    monkeypatch.setattr(
        TrpcConfig, "_plugins_config",
        {"config": {
            "etcd": {
                "providers": [{
                    "name": "other",
                    "prefix": "/no"
                }, {
                    "name": "etcd",
                    "prefix": "/app"
                }]
            }
        }})
    provider = EtcdConfigProvider(client=fake_client)
    assert provider.load("salutation_config.json") == b'{"hello": "world"}'


def test_hot_reload_put_and_delete(fake_client):
    provider = make_provider(fake_client, prefix="/app")
    received = []
    provider.hot_reload("salutation_config.json", received.append)
    assert wait_until(lambda: len(fake_client.watches) == 1)
    # Registering the watch must not fire the callback.
    assert received == []

    fake_client.emit("/app/salutation_config.json", b'{"hello": "etcd"}')
    assert wait_until(lambda: received == [b'{"hello": "etcd"}'])

    fake_client.emit("/app/salutation_config.json", None, delete=True)
    assert wait_until(lambda: received == [b'{"hello": "etcd"}', b""])
    provider.close()


def test_watch_typed_events_and_cancel(fake_client):
    provider = make_provider(fake_client)
    events = []
    cancel = provider.watch("plain", lambda event_type, key, value: events.append((event_type, key, value)))
    assert wait_until(lambda: len(fake_client.watches) == 1)
    fake_client.emit("plain", b"v2", mod_revision=7)
    assert wait_until(lambda: events == [(EventType.PUT, "plain", b"v2")])
    cancel()
    assert fake_client.watches[0].cancelled.is_set()
    provider.close()


def test_watch_reconnects_after_stream_failure(fake_client):
    fake_client.watch_failures = 1
    provider = make_provider(fake_client)
    received = []
    provider.hot_reload("plain", received.append)
    assert wait_until(lambda: fake_client.watch_calls >= 2, timeout=10)
    assert wait_until(lambda: len(fake_client.watches) == 1)
    fake_client.emit("plain", b"after-reconnect")
    assert wait_until(lambda: received == [b"after-reconnect"])
    provider.close()


def test_watch_resumes_from_last_revision(fake_client):
    provider = make_provider(fake_client)
    received = []
    provider.hot_reload("plain", received.append)
    assert wait_until(lambda: len(fake_client.watches) == 1)
    fake_client.emit("plain", b"v1", mod_revision=41)
    assert wait_until(lambda: received == [b"v1"])
    # Simulate the stream ending: the next watch must resume at revision 42.
    fake_client.watches[0].cancel()
    assert wait_until(lambda: len(fake_client.watches) >= 2, timeout=10)
    assert fake_client.watches[-1].start_revision == 42
    provider.close()


def test_close_is_idempotent_and_terminal(fake_client):
    provider = make_provider(fake_client)
    provider.hot_reload("plain", lambda data: None)
    assert wait_until(lambda: len(fake_client.watches) == 1)
    provider.close()
    provider.close()
    assert fake_client.watches[0].cancelled.is_set()
    with pytest.raises(ProviderError):
        provider.load("plain")


def test_client_created_by_factory_with_endpoint_failover():
    created = []

    class FactoryClient:

        def __init__(self, endpoint):
            self.endpoint = endpoint

        def status(self):
            if self.endpoint.startswith("bad"):
                raise RuntimeError("unreachable")
            return object()

        def get(self, key):
            return (b"ok", None)

    def factory(cfg, endpoint):
        created.append(endpoint)
        return FactoryClient(endpoint)

    provider = EtcdConfigProvider(config=EtcdProviderConfig(endpoints=["bad:2379", "good:2379"]),
                                  client_factory=factory)
    assert provider.load("anything") == b"ok"
    assert created == ["bad:2379", "good:2379"]
    provider.close()
