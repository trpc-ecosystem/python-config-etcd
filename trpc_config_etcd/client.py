# Tencent is pleased to support the open source community by making tRPC-Config-Etcd available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-Config-Etcd is licensed under Apache-2.0.
"""Read-only etcd client facade.

Use this for direct key access instead of the framework's ``ConfigLoader``::

    client = EtcdClient({"endpoints": ["127.0.0.1:2379"], "prefix": "/app"})
    rsp = client.get("server_config.yaml")
    print(rsp.value, rsp.event, rsp.metadata)
    cancel = client.watch("server_config.yaml", lambda rsp: print(rsp.value))

The client is read-only: :meth:`EtcdClient.put` and :meth:`EtcdClient.delete`
raise :class:`NotImplementedError`.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from typing import Callable
from typing import Dict
from typing import Optional
from typing import Union

from ._constants import EventType
from .config import PLUGIN_NAME
from .config import EtcdProviderConfig
from .provider import EtcdConfigProvider


@dataclass
class Response:
    """One etcd get/watch result.

    Attributes:
        raw: Raw value bytes; ``b""`` for delete events and missing keys.
        event: Event type; :attr:`EventType.NULL` for plain gets.
        metadata: Response metadata. Always an empty dict.
    """

    raw: bytes = b""
    event: EventType = EventType.NULL
    metadata: Dict[str, str] = field(default_factory=dict)

    @property
    def value(self) -> str:
        """Return the value decoded as UTF-8 text."""
        return self.raw.decode("utf-8", errors="replace")


class EtcdClient:
    """Direct etcd key reader/watcher built on :class:`EtcdConfigProvider`.

    Args:
        config: Provider configuration as a dict or
            :class:`EtcdProviderConfig`. Defaults to the startup YAML
            ``plugins.config.etcd`` section when omitted.
        provider: Pre-built provider to delegate to (mainly for tests).
    """

    def __init__(self,
                 config: Optional[Union[Dict, EtcdProviderConfig]] = None,
                 provider: Optional[EtcdConfigProvider] = None):
        if provider is not None:
            self._provider = provider
        elif isinstance(config, EtcdProviderConfig):
            self._provider = EtcdConfigProvider(config=config)
        elif isinstance(config, dict):
            self._provider = EtcdConfigProvider(config=EtcdProviderConfig.from_dict(config))
        else:
            self._provider = EtcdConfigProvider()

    @property
    def name(self) -> str:
        """Return the plugin name (``"etcd"``)."""
        return PLUGIN_NAME

    def get(self, key: str) -> Response:
        """Get one config key.

        Args:
            key: Config key, relative to the configured prefix.

        Returns:
            The current value with ``event`` set to ``EventType.NULL``.

        Raises:
            ProviderError: If the key does not exist or etcd is unreachable.
        """
        return Response(raw=self._provider.load(key), event=EventType.NULL)

    def watch(self, key: str, callback: Callable[[Response], None]) -> Callable:
        """Watch one config key and invoke ``callback`` on each change.

        PUT events carry the new value, DELETE events carry ``b""``.

        Args:
            key: Config key, relative to the configured prefix.
            callback: Callable invoked with each :class:`Response`.

        Returns:
            A zero-argument callable that cancels this watch.
        """

        def on_event(event_type: EventType, _full_key: str, value: bytes) -> None:
            callback(Response(raw=value, event=event_type))

        return self._provider.watch(key, on_event)

    def put(self, key: str, value: str) -> None:
        """Not implemented: the plugin is read-only."""
        raise NotImplementedError("etcd config plugin is read-only: put is not implemented")

    def delete(self, key: str) -> None:
        """Not implemented: the plugin is read-only."""
        raise NotImplementedError("etcd config plugin is read-only: delete is not implemented")

    def close(self) -> None:
        """Cancel all watches and close the underlying etcd client."""
        self._provider.close()
