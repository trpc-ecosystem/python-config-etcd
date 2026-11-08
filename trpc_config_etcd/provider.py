# Tencent is pleased to support the open source community by making tRPC-Config-Etcd available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-Config-Etcd is licensed under Apache-2.0.
"""etcd implementation of the tRPC-Python config provider interface.

:class:`EtcdConfigProvider` is registered as the ``CONFIG_PROVIDER`` plugin
named ``etcd``, so business code loads
etcd-backed configuration through the framework loader::

    from trpc_sdk.config import ConfigLoaderFactory
    from trpc_sdk.config import with_codec
    from trpc_sdk.config import with_provider

    loader = ConfigLoaderFactory.sync_load(
        "salutation_config.json", with_provider("etcd"), with_codec("json"))
    loader.hot_reload(lambda data: print("changed:", data))

The provider is read-only: it implements ``load``
(one key) and ``hot_reload`` (watch one key) on top of the synchronous
``etcd3`` client. The etcd client is created lazily on first use, in the
order: explicit constructor config, then ``plugins.config.etcd`` from the
startup YAML, then ``set_options`` / per-call options overrides.
"""

from __future__ import annotations

import threading
from typing import Callable
from typing import Dict
from typing import Optional

from trpc_sdk.abc import BaseConfigProvider
from trpc_sdk.abc import PluginType
from trpc_sdk.config import ProviderError
from trpc_sdk.log import logger
from trpc_sdk.plugin import register_plugin

from ._constants import EventType
from .config import PLUGIN_NAME
from .config import EtcdProviderConfig
from .version import __version__

# Handler invoked for every watch event: (event_type, full_key, value_bytes).
EventHandler = Callable[[EventType, str, bytes], None]


def _default_client_factory(config: EtcdProviderConfig, endpoint: str):
    """Create a real etcd3 client for one endpoint (imported lazily)."""
    import etcd3  # pylint: disable=import-outside-toplevel

    return etcd3.client(**config.client_kwargs(endpoint))


def _is_delete_event(event) -> bool:
    """Tell whether an etcd3 watch event is a deletion."""
    event_type = getattr(event, "type", None)
    if event_type is not None:
        name = getattr(event_type, "name", str(event_type)).upper()
        if "DELETE" in name or "DEL" in name:
            return True
        if "PUT" in name:
            return False
    if type(event).__name__.endswith("DeleteEvent"):
        return True
    # A PUT always carries a value; a DELETE carries none.
    return getattr(event, "value", None) is None


def _event_value(event) -> bytes:
    value = getattr(event, "value", None)
    if value is None:
        return b""
    if isinstance(value, bytes):
        return value
    return str(value).encode("utf-8")


class _WatchHandle:
    """State of one running watch: stop flag, cancel hook and thread."""

    def __init__(self, key: str):
        self.key = key
        self.stop_event = threading.Event()
        self.thread: Optional[threading.Thread] = None
        self.last_revision: int = 0
        self._cancel_fn: Optional[Callable] = None
        self._lock = threading.Lock()

    def set_cancel_fn(self, cancel_fn: Optional[Callable]) -> None:
        with self._lock:
            self._cancel_fn = cancel_fn

    def cancel(self) -> None:
        """Stop the watch loop and cancel the underlying etcd watch."""
        self.stop_event.set()
        with self._lock:
            cancel_fn, self._cancel_fn = self._cancel_fn, None
        if cancel_fn is not None:
            try:
                cancel_fn()
            except Exception:  # pylint: disable=broad-except
                logger.debug("cancel etcd watch for %s failed", self.key, exc_info=True)


class EtcdConfigProvider(BaseConfigProvider):
    """Reads config bytes from etcd and watches them for changes.

    Args:
        config: Explicit provider configuration. When given it takes
            precedence over the startup YAML section.
        client: Pre-built etcd client (mainly for tests). When given,
            ``client_factory`` is not used.
        client_factory: Callable ``(config, endpoint) -> client`` used to
            build the etcd client lazily. Defaults to ``etcd3.client``.
    """

    def __init__(self,
                 config: Optional[EtcdProviderConfig] = None,
                 client=None,
                 client_factory: Optional[Callable] = None):
        super().__init__()
        self._explicit_config = config
        self._injected_client = client
        self._client_factory = client_factory or _default_client_factory
        self._options: Dict = {}
        self._client = client
        self._client_config: Optional[EtcdProviderConfig] = None
        self._client_lock = threading.Lock()
        self._watches: Dict[str, _WatchHandle] = {}
        self._watches_lock = threading.Lock()
        self._closed = False

    def set_options(self, options: Dict) -> None:
        """Store framework/provider options, invalidating the cached client.

        Called by ``TrpcConfigParser`` before ``load``; the options are
        merged over the startup YAML section on every resolve.

        Args:
            options: Provider-specific options (same keys as
                :class:`EtcdProviderConfig`).
        """
        self._options = dict(options or {})
        with self._client_lock:
            if self._injected_client is None:
                self._client = None
                self._client_config = None

    def load(self, file_path: str, options: Optional[Dict] = None) -> bytes:
        """Load the raw value bytes stored under one etcd key.

        Args:
            file_path: Config key, interpreted relative to the configured
                prefix. When empty, ``file_path``/``key`` is taken from
                ``options``.
            options: Optional per-call overrides (see
                :class:`EtcdProviderConfig` fields).

        Returns:
            The raw config bytes stored in etcd.

        Raises:
            ProviderError: If the key does not exist or etcd is unreachable.
        """
        cfg = self._resolve_config(options)
        key = file_path or (options or {}).get("file_path") or (options or {}).get("key") or ""
        if not key:
            raise ProviderError(PLUGIN_NAME, "etcd datasource options should contain file_path")
        full_key = cfg.full_key(key)
        try:
            client = self._get_client(cfg)
            result = client.get(full_key)
        except ProviderError:
            raise
        except Exception as exc:  # pylint: disable=broad-except
            raise ProviderError(PLUGIN_NAME, f"get key {full_key} from etcd failed: {exc}") from exc
        value = self._extract_value(result, full_key)
        if value is None:
            raise ProviderError(PLUGIN_NAME, f"config key {full_key} not found in etcd")
        return value

    def hot_reload(self, key: str, callback: Callable, options: Optional[Dict] = None) -> None:
        """Watch one config key and invoke ``callback`` on every change.

        A PUT event delivers the new raw bytes, a DELETE event delivers
        ``b""``, and registering the watch does not fire the callback.
        The watch runs on a daemon thread and reconnects with exponential
        backoff (1s, capped at 30s) when the etcd stream breaks.

        Args:
            key: Config key, interpreted relative to the configured prefix.
            callback: Callable invoked with the new raw config bytes.
            options: Optional per-call overrides.
        """

        def on_event(event_type: EventType, _full_key: str, value: bytes) -> None:
            callback(b"" if event_type is EventType.DELETE else value)

        self.watch(key, on_event, options)

    def watch(self, key: str, handler: EventHandler, options: Optional[Dict] = None) -> Callable:
        """Watch one key, reporting typed events to ``handler``.

        Args:
            key: Config key, interpreted relative to the configured prefix.
            handler: Callable ``(event_type, full_key, value_bytes)``.
            options: Optional per-call overrides.

        Returns:
            A zero-argument callable that cancels this watch.
        """
        cfg = self._resolve_config(options)
        full_key = cfg.full_key(key)
        handle = _WatchHandle(full_key)
        with self._watches_lock:
            old = self._watches.pop(full_key, None)
            self._watches[full_key] = handle
        if old is not None:
            old.cancel()
        thread = threading.Thread(
            target=self._watch_loop,
            args=(handle, cfg, handler),
            name=f"etcd-watch-{full_key}",
            daemon=True,
        )
        handle.thread = thread
        thread.start()
        return handle.cancel

    def _watch_loop(self, handle: _WatchHandle, cfg: EtcdProviderConfig, handler: EventHandler) -> None:
        backoff = 1.0
        while not handle.stop_event.is_set() and not self._closed:
            try:
                client = self._get_client(cfg)
                events, cancel = self._open_watch(client, handle)
                handle.set_cancel_fn(cancel)
                backoff = 1.0
                for event in events:
                    if handle.stop_event.is_set():
                        break
                    revision = getattr(event, "mod_revision", None)
                    if revision:
                        handle.last_revision = int(revision)
                    event_type = EventType.DELETE if _is_delete_event(event) else EventType.PUT
                    try:
                        handler(event_type, handle.key, _event_value(event))
                    except Exception:  # pylint: disable=broad-except
                        logger.error("etcd watch callback for %s failed", handle.key, exc_info=True)
                # The stream ended: fall through to reconnect.
            except Exception:  # pylint: disable=broad-except
                if handle.stop_event.is_set() or self._closed:
                    break
                logger.warning("etcd watch for %s interrupted, retry in %.0fs", handle.key, backoff, exc_info=True)
            if handle.stop_event.wait(backoff):
                break
            backoff = min(backoff * 2, 30.0)
        handle.set_cancel_fn(None)

    @staticmethod
    def _open_watch(client, handle: _WatchHandle):
        """Open an etcd watch iterator, resuming from the last revision."""
        try:
            if handle.last_revision:
                return client.watch(handle.key, start_revision=handle.last_revision + 1)
            return client.watch(handle.key)
        except TypeError:
            return client.watch(handle.key)

    def _get_client(self, cfg: EtcdProviderConfig):
        """Return the cached etcd client, building it lazily if needed."""
        if self._closed:
            raise ProviderError(PLUGIN_NAME, "etcd provider is closed")
        with self._client_lock:
            if self._client is not None and self._client_config == cfg:
                return self._client
            client = self._create_client(cfg)
            self._client = client
            self._client_config = cfg
            return client

    def _create_client(self, cfg: EtcdProviderConfig):
        """Create a client, trying each endpoint in order until one answers."""
        if self._injected_client is not None:
            return self._injected_client
        last_exc: Optional[Exception] = None
        for endpoint in cfg.endpoints:
            try:
                client = self._client_factory(cfg, endpoint)
                # etcd3 connects lazily; probe so endpoint failover is real.
                status = getattr(client, "status", None)
                if callable(status):
                    status()
                return client
            except Exception as exc:  # pylint: disable=broad-except
                last_exc = exc
                logger.warning("connect etcd endpoint %s failed: %s", endpoint, exc)
        raise ProviderError(PLUGIN_NAME, f"connect etcd {cfg.endpoints} failed: {last_exc}") from last_exc

    @staticmethod
    def _extract_value(result, full_key: str) -> Optional[bytes]:
        """Normalize the return value of ``etcd3``'s ``get`` to bytes."""
        if result is None:
            return None
        if isinstance(result, (bytes, bytearray)):
            return bytes(result)
        if isinstance(result, tuple):  # etcd3: (value, metadata)
            value = result[0] if result else None
            if value is None:
                return None
            return value if isinstance(value, bytes) else str(value).encode("utf-8")
        kvs = getattr(result, "kvs", None)  # gRPC GetResponse style
        if kvs:
            if len(kvs) > 1:
                logger.warning("etcd key %s matched %d values, using the first", full_key, len(kvs))
            return _event_value(kvs[0])
        value = getattr(result, "value", None)
        return None if value is None else (value if isinstance(value, bytes) else str(value).encode("utf-8"))

    def _resolve_config(self, overrides: Optional[Dict] = None) -> EtcdProviderConfig:
        """Merge defaults, startup YAML, set_options and per-call options."""
        if self._explicit_config is not None:
            cfg = self._explicit_config
        else:
            merged: Dict = {}
            merged.update(self._global_section())
            merged.update(self._options)
            cfg = EtcdProviderConfig.from_dict(merged)
        return cfg.merged(overrides)

    def _global_section(self) -> Dict:
        """Read ``plugins.config.etcd`` from the startup YAML, if loaded."""
        try:
            from trpc_sdk.config import TrpcConfig  # pylint: disable=import-outside-toplevel

            plugins = TrpcConfig.plugins_config() or {}
        except Exception:  # pylint: disable=broad-except
            return {}
        section = None
        config_section = plugins.get("config") if isinstance(plugins, dict) else None
        if isinstance(config_section, dict):
            section = config_section.get(PLUGIN_NAME)
        if section is None and isinstance(plugins, dict):
            section = plugins.get(PLUGIN_NAME)
        if not isinstance(section, dict):
            return {}
        providers = section.get("providers")
        if isinstance(providers, list) and providers:
            # If a providers list is present, prefer the entry named "etcd".
            for item in providers:
                if isinstance(item, dict) and item.get("name", PLUGIN_NAME) == PLUGIN_NAME:
                    return item
            return providers[0] if isinstance(providers[0], dict) else {}
        return section

    def close(self) -> None:
        """Cancel all watches and close the etcd client. Idempotent."""
        with self._watches_lock:
            handles = list(self._watches.values())
            self._watches.clear()
        for handle in handles:
            handle.cancel()
        with self._client_lock:
            client, self._client = self._client, None
            self._client_config = None
        self._closed = True
        if client is not None and client is not self._injected_client:
            close = getattr(client, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:  # pylint: disable=broad-except
                    logger.debug("close etcd client failed", exc_info=True)

    def stop(self) -> None:
        """Plugin lifecycle hook: release etcd resources."""
        self.close()


# Registration is a plain decorator (not attached above the class) so the
# class body stays readable. Importing this module registers the plugin.
register_plugin(PluginType.CONFIG_PROVIDER, PLUGIN_NAME, version=__version__, report=True)(EtcdConfigProvider)
