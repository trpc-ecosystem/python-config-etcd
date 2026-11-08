# Tencent is pleased to support the open source community by making tRPC-Config-Etcd available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-Config-Etcd is licensed under Apache-2.0.
"""Tests for EtcdProviderConfig parsing."""

from trpc_config_etcd import EtcdProviderConfig
from trpc_config_etcd.config import parse_endpoint


def test_defaults():
    cfg = EtcdProviderConfig.from_dict(None)
    assert cfg.name == "etcd"
    assert cfg.endpoints == ["127.0.0.1:2379"]
    assert cfg.prefix == ""
    assert cfg.dial_timeout == 5.0


def test_endpoints_and_dialtimeout_alias():
    cfg = EtcdProviderConfig.from_dict({"endpoints": ["10.0.0.1:2379", "10.0.0.2:2379"], "dialtimeout": "3"})
    assert cfg.endpoints == ["10.0.0.1:2379", "10.0.0.2:2379"]
    assert cfg.dial_timeout == 3.0


def test_single_endpoint_alias():
    cfg = EtcdProviderConfig.from_dict({"endpoint": "http://127.0.0.1:2379", "prefix": "/app"})
    assert cfg.endpoints == ["http://127.0.0.1:2379"]
    assert cfg.prefix == "/app"
    assert cfg.client_kwargs(cfg.endpoints[0])["host"] == "127.0.0.1"
    assert cfg.client_kwargs(cfg.endpoints[0])["port"] == 2379


def test_comma_separated_endpoints_and_auth_tls():
    cfg = EtcdProviderConfig.from_dict({
        "endpoints": "a:2379, b:2380",
        "username": "root",
        "password": "secret",
        "ca_cert": "/tmp/ca.pem",
    })
    assert cfg.endpoints == ["a:2379", "b:2380"]
    kwargs = cfg.client_kwargs("a:2379")
    assert kwargs["user"] == "root"
    assert kwargs["password"] == "secret"
    assert kwargs["ca_cert"] == "/tmp/ca.pem"
    assert "cert_key" not in kwargs


def test_parse_endpoint():
    assert parse_endpoint("http://127.0.0.1:2379") == ("127.0.0.1", 2379)
    assert parse_endpoint("etcd.example.com") == ("etcd.example.com", 2379)
    assert parse_endpoint("[::1]:2380") == ("::1", 2380)


def test_full_key_prefix_join():
    cfg = EtcdProviderConfig(prefix="/app/")
    assert cfg.full_key("a.yaml") == "/app/a.yaml"
    assert cfg.full_key("/app/a.yaml") == "/app/a.yaml"
    assert EtcdProviderConfig().full_key("a.yaml") == "a.yaml"


def test_merged_only_overrides_present_keys():
    base = EtcdProviderConfig.from_dict({"prefix": "/app", "dial_timeout": 9})
    merged = base.merged({"prefix": "/other"})
    assert merged.prefix == "/other"
    assert merged.dial_timeout == 9
    assert base.prefix == "/app"
