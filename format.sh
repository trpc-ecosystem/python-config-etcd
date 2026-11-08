#!/bin/bash
#
# Tencent is pleased to support the open source community by making tRPC-Config-Etcd available.
#
# Copyright (C) 2026 Tencent. All rights reserved.
#
# tRPC-Config-Etcd is licensed under Apache-2.0.

set -e
cd "$(dirname "$0")"

python3 -m yapf -i -r trpc_config_etcd tests examples
