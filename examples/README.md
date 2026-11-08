# etcd provider example

This example demonstrates how to use etcd to store and retrieve
configuration in a tRPC-Python program (`salutation_config.json` /
`server_config.yaml`).

## Prerequisites

An etcd cluster running at `127.0.0.1:2379`. For local testing a
single-node etcd is enough; follow the
[etcd quickstart](https://etcd.io/docs/v3.5/quickstart/) to start one.

## Set key-value pairs

```shell
etcdctl --endpoints http://127.0.0.1:2379 put salutation_config.json '{"hello": "nice to meet you!", "goodbye": "see you later!"}'
etcdctl --endpoints http://127.0.0.1:2379 put server_config.yaml "ip: 127.0.0.1
port: 10001"
```

## Run

```shell
pip install trpc-config-etcd
python3 examples/trpc_main.py
```

Expected output:

```text
hello -> nice to meet you!
server -> 127.0.0.1:10001
watching salutation_config.json, press Ctrl+C to exit ...
```

Then update the key and observe the hot-reload callback:

```shell
etcdctl --endpoints http://127.0.0.1:2379 put salutation_config.json '{"hello": "hello again!"}'
# -> salutation changed -> {'hello': 'hello again!'}
```
