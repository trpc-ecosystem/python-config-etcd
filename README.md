English | [中文](README.zh_CN.md)

# tRPC-Python etcd configuration plugin

[![LICENSE](https://img.shields.io/badge/license-Apache--2.0-green.svg)](LICENSE)

This plugin wraps the [etcd3](https://github.com/kragniz/python-etcd3)
client so you can quickly read configurations stored in etcd from the
tRPC-Python framework.

## Features

- Registered as a `CONFIG_PROVIDER` plugin named `etcd`. Importing the package registers it.
- `load`: read the raw bytes of one configuration by key (the `prefix` is
  applied automatically), for use with the framework's
  `ConfigLoaderFactory` and YAML/JSON decoders.
- `hot_reload`: watch a single key on a daemon thread. A PUT event
  delivers the new bytes, a DELETE event delivers `b""`, and after a
  disconnect the watch reconnects with exponential backoff and resumes
  from the last revision.

## Quick start

### Step 1: install

```shell
pip install trpc-config-etcd
```

### Step 2: configure

In the `trpc_python.yaml` startup configuration, set the etcd address
under `plugins.config.etcd`:

```yaml
plugins:
  config:
    etcd:
      endpoints:
        - 127.0.0.1:2379
      dial_timeout: 5
      prefix: ""
```

Configuration fields:

- `name` (string, default `etcd`): provider name.
- `endpoints` (list of strings, default `["127.0.0.1:2379"]`): etcd
  addresses in `host:port` or `http://host:port` form, tried in order
  when connecting.
- `prefix` (string, default `""`): a shared prefix prepended to every
  configuration key, used to isolate data of different applications in
  the same etcd cluster.
- `dial_timeout` (number, default `5`): connect and read timeout, in
  seconds.
- `username` / `password` (string, default `""`): etcd username and
  password.
- `ca_cert` / `cert_key` / `cert_cert` (string, default `""`): TLS
  certificate paths.

Per-call options passed to `load(key, options)` /
`hot_reload(key, cb, options)` override the startup configuration fields
of the same name.

### Step 3: use

After the framework has loaded the startup configuration, read a
configuration item from etcd:

```python
import trpc_config_etcd  # noqa: F401  (importing registers the etcd provider)
from trpc_sdk.config import ConfigLoaderFactory, TrpcConfig
from trpc_sdk.config import with_codec, with_provider

TrpcConfig.load("trpc_python.yaml")

# Get the configuration item whose key is "salutation_config.json"
loader = ConfigLoaderFactory.sync_load(
    "salutation_config.json", with_provider("etcd"), with_codec("json"))
print(loader.get("hello", ""))

# Watch the same key; the callback receives the decoded dict
loader.hot_reload(lambda data: print("changed:", data))
```

Decoder names are those already registered by the framework: `json`,
`yaml`, and `noop`.

You can also access a key directly without a Loader:

```python
from trpc_config_etcd import EtcdClient

client = EtcdClient({"endpoints": ["127.0.0.1:2379"], "prefix": "/app"})
rsp = client.get("server_config.yaml")
print(rsp.value, rsp.event, rsp.metadata)
cancel = client.watch("server_config.yaml", lambda rsp: print(rsp.value))
```

To isolate multiple providers, instantiate several
`EtcdConfigProvider(config=EtcdProviderConfig(...))` objects and pass
them to `ConfigLoader(path, provider=..., decoder=...)`. The framework's
named registry keeps only one instance named `etcd`.

## Example

A runnable example is in [examples](examples/README.md). It demonstrates
the two keys `salutation_config.json` and `server_config.yaml`.

## Development setup

```bash
# Install this package and the test dependencies
pip install -e .
pip install -r requirements-test.txt

# Run tests
pytest

# Format the code
./format.sh
```

## License

This project is licensed under Apache-2.0.
