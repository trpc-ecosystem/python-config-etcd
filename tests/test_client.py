# Tencent is pleased to support the open source community by making tRPC-Config-Etcd available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-Config-Etcd is licensed under Apache-2.0.
"""Tests for the EtcdClient facade."""

import pytest

from trpc_config_etcd import EtcdClient
from trpc_config_etcd import EtcdProviderConfig
from trpc_config_etcd import EventType
from trpc_config_etcd import EtcdConfigProvider

from conftest import wait_until


def make_client(fake_client):
    provider = EtcdConfigProvider(config=EtcdProviderConfig(prefix="/app"), client=fake_client)
    return EtcdClient(provider=provider)


def test_get_response_fields(fake_client):
    client = make_client(fake_client)
    rsp = client.get("salutation_config.json")
    assert rsp.value == '{"hello": "world"}'
    assert rsp.raw == b'{"hello": "world"}'
    assert rsp.event is EventType.NULL
    assert rsp.metadata == {}
    assert client.name == "etcd"


def test_watch_response_events(fake_client):
    client = make_client(fake_client)
    responses = []
    cancel = client.watch("salutation_config.json", responses.append)
    assert wait_until(lambda: len(fake_client.watches) == 1)

    fake_client.emit("/app/salutation_config.json", b"new")
    assert wait_until(lambda: len(responses) == 1)
    assert responses[0].event is EventType.PUT
    assert responses[0].value == "new"

    fake_client.emit("/app/salutation_config.json", None, delete=True)
    assert wait_until(lambda: len(responses) == 2)
    assert responses[1].event is EventType.DELETE
    assert responses[1].raw == b""

    cancel()
    client.close()


def test_put_and_delete_not_implemented(fake_client):
    client = make_client(fake_client)
    with pytest.raises(NotImplementedError):
        client.put("k", "v")
    with pytest.raises(NotImplementedError):
        client.delete("k")
    with pytest.raises(NotImplementedError):
        client.del_("k")
