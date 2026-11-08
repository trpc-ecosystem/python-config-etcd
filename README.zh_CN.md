[English](README.md) | 中文

# tRPC-Python etcd 配置插件

[![LICENSE](https://img.shields.io/badge/license-Apache--2.0-green.svg)](LICENSE)

本插件封装了 [etcd3](https://github.com/kragniz/python-etcd3) 客户端，便于在 tRPC-Python 框架中快速访问 etcd 中的配置

## 功能特性

- 以 `CONFIG_PROVIDER` 插件形式注册，插件名为 `etcd`，
  import 包即完成注册。
- `load`：按 key 读取一份配置的原始字节（自动拼接 `prefix`），配合框架的
  `ConfigLoaderFactory` 与 YAML/JSON 解码器使用。
- `hot_reload`：在守护线程中监听单个 key；PUT 事件回调新字节、DELETE 事件回调 `b""`，断线后指数退避重连并从上次 revision 续订。

## 快速开始

### 第一步：安装

```shell
pip install trpc-config-etcd
```

### 第二步：配置

在 `trpc_python.yaml` 启动配置的 `plugins.config.etcd` 下设置 etcd 地址：

```yaml
plugins:
  config:
    etcd:
      endpoints:
        - 127.0.0.1:2379
      dial_timeout: 5
      prefix: ""
```

配置项说明：

- `name`（string，默认 `etcd`）：provider 名称。
- `endpoints`（string 列表，默认 `["127.0.0.1:2379"]`）：etcd 地址，
  格式为 `host:port` 或 `http://host:port`，建连时按顺序逐个尝试；
- `prefix`（string，默认 `""`）：所有配置 key 的统一前缀，用于在同一
  etcd 集群中隔离不同应用的数据。
- `dial_timeout`（number，默认 `5`）：连接/读取超时时间（秒），
- `username` / `password`（string，默认 `""`）：etcd 账号密码。
- `ca_cert` / `cert_key` / `cert_cert`（string，默认 `""`）：TLS 证书路径。

`load(key, options)` / `hot_reload(key, cb, options)` 传入的 per-call
options 会覆盖启动配置中的同名项。

### 第三步：使用

框架启动配置加载完成后，即可读取 etcd 中的配置项：

```python
import trpc_config_etcd  # noqa: F401（import 即注册 etcd provider）
from trpc_sdk.config import ConfigLoaderFactory, TrpcConfig
from trpc_sdk.config import with_codec, with_provider

TrpcConfig.load("trpc_python.yaml")

# 获取 key 为 "salutation_config.json" 的配置项
loader = ConfigLoaderFactory.sync_load(
    "salutation_config.json", with_provider("etcd"), with_codec("json"))
print(loader.get("hello", ""))

# 监听同一 key 的变更，回调收到解码后的 dict
loader.hot_reload(lambda data: print("changed:", data))
```

解码器名称使用框架已注册的名称：`json`、`yaml`、`noop`。

也可以不用 Loader 直接按 key 访问：

```python
from trpc_config_etcd import EtcdClient

client = EtcdClient({"endpoints": ["127.0.0.1:2379"], "prefix": "/app"})
rsp = client.get("server_config.yaml")
print(rsp.value, rsp.event, rsp.metadata)
cancel = client.watch("server_config.yaml", lambda rsp: print(rsp.value))
```

如需多 provider 隔离，可直接实例化多个
`EtcdConfigProvider(config=EtcdProviderConfig(...))` 并传入
`ConfigLoader(path, provider=..., decoder=...)`；框架的命名注册表中只保留一个名为 `etcd` 的实例。

## 示例

可运行的完整示例见 [examples](examples/README.md)，使用
`salutation_config.json` 与 `server_config.yaml` 两个 key 演示。

## 开发

```bash
# 安装本包和测试依赖
pip install -e .
pip install -r requirements-test.txt

# 运行测试
pytest

# 格式化代码
./format.sh
```

## 许可证

本项目采用 Apache-2.0 许可证。
