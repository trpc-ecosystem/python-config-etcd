# Tencent is pleased to support the open source community by making tRPC-Config-Etcd available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-Config-Etcd is licensed under Apache-2.0.
"""Configuration model for the etcd config provider.

Fields cover connection options (``endpoints`` / ``dial_timeout`` / auth /
TLS) and key layout (``name`` / ``prefix``):

```yaml
plugins:
  config:
    etcd:
      endpoints:
        - 127.0.0.1:2379
      dial_timeout: 5
      prefix: ""
      # username: ""
      # password: ""
      # ca_cert: ""
      # cert_key: ""
      # cert_cert: ""
```
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field
from dataclasses import replace
from typing import Dict
from typing import List
from typing import Optional
from typing import Tuple
from typing import Union

PLUGIN_NAME = "etcd"
"""Registered ``CONFIG_PROVIDER`` plugin name."""

DEFAULT_ENDPOINT = "127.0.0.1:2379"
DEFAULT_PORT = 2379

# Accepted spellings for each field; the first hit wins.
_KEY_ALIASES = {
    "name": ("name", ),
    "endpoints": ("endpoints", "endpoint"),
    "prefix": ("prefix", ),
    "dial_timeout": ("dial_timeout", "dialtimeout", "dialTimeout", "timeout"),
    "username": ("username", "user"),
    "password": ("password", ),
    "ca_cert": ("ca_cert", "caCert", "ca_file", "cacert"),
    "cert_key": ("cert_key", "certKey", "key_file"),
    "cert_cert": ("cert_cert", "certCert", "cert_file"),
}


def parse_endpoint(endpoint: str) -> Tuple[str, int]:
    """Parse ``[scheme://]host[:port]`` into ``(host, port)``.

    Args:
        endpoint: Endpoint such as ``http://127.0.0.1:2379`` or ``127.0.0.1``.

    Returns:
        Host and port, defaulting the port to 2379.
    """
    text = str(endpoint).strip()
    if "://" in text:
        text = text.split("://", 1)[1]
    text = text.rstrip("/")
    if not text:
        return "127.0.0.1", DEFAULT_PORT
    if text.startswith("["):  # IPv6 literal, e.g. [::1]:2379
        host, _, rest = text.partition("]")
        return host.strip("[]"), int(rest.lstrip(":")) if rest else DEFAULT_PORT
    host, sep, port = text.rpartition(":")
    if sep and port.isdigit():
        return host, int(port)
    return text, DEFAULT_PORT


@dataclass
class EtcdProviderConfig:
    """Connection and key-layout options for one etcd provider instance.

    Attributes:
        name: Provider name. ``"etcd"`` for the registered plugin; direct
            instances may use any name.
        endpoints: etcd endpoints in ``host:port`` or ``scheme://host:port``
            form. Tried in order when connecting.
        prefix: Key prefix prepended to every config key, used to isolate
            different applications sharing one etcd cluster.
        dial_timeout: Connect/get timeout in seconds.
        username: etcd user name, empty disables auth.
        password: etcd password.
        ca_cert: Path to the CA certificate for TLS.
        cert_key: Path to the client key for TLS.
        cert_cert: Path to the client certificate for TLS.
    """

    name: str = PLUGIN_NAME
    endpoints: List[str] = field(default_factory=lambda: [DEFAULT_ENDPOINT])
    prefix: str = ""
    dial_timeout: float = 5.0
    username: str = ""
    password: str = ""
    ca_cert: str = ""
    cert_key: str = ""
    cert_cert: str = ""

    @classmethod
    def from_dict(cls, data: Optional[Dict] = None) -> "EtcdProviderConfig":
        """Build a config from a plain dict (YAML section or load options).

        Unknown keys are ignored so framework-level options can be passed
        through. Both ``endpoint`` (a single value or a list) and
        ``endpoints`` are accepted.

        Args:
            data: Raw option dict, may be ``None``.

        Returns:
            The parsed configuration with defaults filled in.
        """
        if not data:
            return cls()
        picked: Dict = {}
        for field_name, aliases in _KEY_ALIASES.items():
            for alias in aliases:
                if alias in data and data[alias] is not None:
                    picked[field_name] = data[alias]
                    break
        if "endpoints" in picked:
            picked["endpoints"] = cls._normalize_endpoints(picked["endpoints"])
        if "dial_timeout" in picked:
            picked["dial_timeout"] = float(picked["dial_timeout"])
        return cls(**picked)

    @staticmethod
    def _normalize_endpoints(value: Union[str, List[str]]) -> List[str]:
        if isinstance(value, str):
            # Accept a single endpoint or a comma separated list.
            items = [item.strip() for item in value.split(",")]
        else:
            items = [str(item).strip() for item in value]
        return [item for item in items if item] or [DEFAULT_ENDPOINT]

    def merged(self, overrides: Optional[Union[Dict, "EtcdProviderConfig"]]) -> "EtcdProviderConfig":
        """Return a copy with ``overrides`` applied on top of this config.

        Args:
            overrides: A dict of option overrides, another config, or ``None``.

        Returns:
            The merged configuration; ``self`` is left unchanged.
        """
        if overrides is None:
            return replace(self)
        if isinstance(overrides, EtcdProviderConfig):
            return overrides
        other = EtcdProviderConfig.from_dict(overrides)
        # from_dict cannot tell "unset" from "default", so only keys actually
        # present in the dict are allowed to override.
        changes = {}
        for field_name, aliases in _KEY_ALIASES.items():
            if any(alias in overrides for alias in aliases):
                changes[field_name] = getattr(other, field_name)
        return replace(self, **changes)

    def full_key(self, key: str) -> str:
        """Join the configured prefix with a config key."""
        if not self.prefix:
            return key
        prefix = self.prefix.rstrip("/")
        if key == prefix or key.startswith(prefix + "/"):
            return key
        return f"{prefix}/{key.lstrip('/')}"

    def client_kwargs(self, endpoint: str) -> Dict:
        """Build ``etcd3.client(...)`` keyword arguments for one endpoint.

        Args:
            endpoint: A single endpoint from :attr:`endpoints`.

        Returns:
            Keyword arguments accepted by ``etcd3.client``.
        """
        host, port = parse_endpoint(endpoint)
        kwargs: Dict = {"host": host, "port": port, "timeout": self.dial_timeout}
        if self.username:
            kwargs["user"] = self.username
            kwargs["password"] = self.password
        if self.ca_cert:
            kwargs["ca_cert"] = self.ca_cert
        if self.cert_key:
            kwargs["cert_key"] = self.cert_key
        if self.cert_cert:
            kwargs["cert_cert"] = self.cert_cert
        return kwargs
