# Tencent is pleased to support the open source community by making tRPC-Config-Etcd available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-Config-Etcd is licensed under Apache-2.0.
"""etcd config provider plugin for the tRPC Python framework.

Importing this package registers :class:`EtcdConfigProvider` as the
``CONFIG_PROVIDER`` plugin named ``etcd``, so etcd-backed configuration can
be loaded through the framework loader::

    import trpc_config_etcd  # noqa: F401  (registers the plugin)
    from trpc_sdk.config import ConfigLoaderFactory
    from trpc_sdk.config import with_codec
    from trpc_sdk.config import with_provider

    loader = ConfigLoaderFactory.sync_load(
        "salutation_config.json", with_provider("etcd"), with_codec("json"))

Public API:

    EtcdConfigProvider: The registered provider (load / hot_reload).
    EtcdProviderConfig: Connection and prefix options for the provider.
    EtcdClient: Read-only facade (get / watch).
    Response: Value/event/metadata returned by EtcdClient.
    EventType: Watch event type (NULL / PUT / DELETE).
"""

from __future__ import annotations

from ._constants import EventType
from .client import EtcdClient
from .client import Response
from .config import PLUGIN_NAME
from .config import EtcdProviderConfig
from .provider import EtcdConfigProvider
from .version import __version__

__all__ = [
    "PLUGIN_NAME",
    "EtcdClient",
    "EtcdConfigProvider",
    "EtcdProviderConfig",
    "EventType",
    "Response",
    "__version__",
]
