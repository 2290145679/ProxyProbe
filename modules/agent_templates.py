# -*- coding: utf-8 -*-
"""
ProxyProbe 探针被控节点一键安装与守护进程模板 (Agent Templates)
包含:
- PROXY_AGENT_SH: 远程节点 Linux (Debian/Ubuntu/CentOS/Alpine) 一键对接脚本
- PROXY_AGENT_PY: 远程节点守护进程 (监控心跳、Xray/Sing-box/Realm 同步、Traffic Control 流量控制)
"""

PROXY_AGENT_SH = """#!/usr/bin/env bash

# ==============================================================================
# Monitor 探针节点一键代理服务部署脚本 (Xray-Core + Sing-box + Realm + Proxy Agent)
# ==============================================================================

HUB_SERVER=""
HUB_TOKEN=""
INSTALL_XRAY=0
INSTALL_SINGBOX=0
INSTALL_REALM=0
EXPLICIT_CORES=0
INSECURE=0
CURL_OPTS="curl -fsSL"

while [ $# -gt 0 ]; do
  case "$1" in
    --server) HUB_SERVER="$2"; shift 2 ;;
    --token) HUB_TOKEN="$2"; shift 2 ;;
    --insecure) INSECURE=1; CURL_OPTS="curl -fsSLk"; shift ;;
    --xray) INSTALL_XRAY=1; EXPLICIT_CORES=1; shift ;;
    --skip-xray | --no-xray) INSTALL_XRAY=0; EXPLICIT_CORES=1; shift ;;
    --singbox) INSTALL_SINGBOX=1; EXPLICIT_CORES=1; shift ;;
    --skip-singbox | --no-singbox) INSTALL_SINGBOX=0; EXPLICIT_CORES=1; shift ;;
    --realm) INSTALL_REALM=1; EXPLICIT_CORES=1; shift ;;
    --skip-realm | --no-realm) INSTALL_REALM=0; EXPLICIT_CORES=1; shift ;;
    --no-proxy | --skip-proxy)
      echo "[+] 已指定 --no-proxy，跳过代理核心与守护程序安装。"
      exit 0
      ;;
    *) shift ;;
  esac
done

# 如果完全未显式指定核心选项（向后兼容默认）：Xray=1, Singbox=1, Realm=0
if [ $EXPLICIT_CORES -eq 0 ]; then
  INSTALL_XRAY=1
  INSTALL_SINGBOX=1
  INSTALL_REALM=0
fi

# 自动从本机已有的探针服务中探测主控端地址与 Token (优先 /opt/proxyprobe，兼容 /opt/monitor)
if [ -z "$HUB_SERVER" ] || [ -z "$HUB_TOKEN" ]; then
  for env_file in /opt/proxyprobe/agent.env /opt/monitor/agent.env; do
    if [ -f "$env_file" ]; then
      echo "[+] 检测到 $env_file 探针配置，正在自动提取环境参数..."
      ENV_SERVER=$(grep -E '^MONITOR_SERVER=' "$env_file" 2>/dev/null | cut -d'=' -f2- | tr -d '"' | tr -d "'" || true)
      ENV_TOKEN=$(grep -E '^MONITOR_TOKEN=' "$env_file" 2>/dev/null | cut -d'=' -f2- | tr -d '"' | tr -d "'" || true)
      [ -n "$ENV_SERVER" ] && HUB_SERVER="$ENV_SERVER"
      [ -n "$ENV_TOKEN" ] && HUB_TOKEN="$ENV_TOKEN"
      [ -n "$HUB_SERVER" ] && [ -n "$HUB_TOKEN" ] && break
    fi
  done
  if [ -z "$HUB_SERVER" ] || [ -z "$HUB_TOKEN" ]; then
    for svc_file in /etc/systemd/system/proxyprobe-agent.service /etc/systemd/system/monitor-agent.service; do
      if [ -f "$svc_file" ]; then
        echo "[+] 检测到 $svc_file，正在自动解析参数..."
        EXEC_LINE=$(grep 'ExecStart=' "$svc_file" 2>/dev/null || true)
        if [ -z "$HUB_SERVER" ]; then
          HUB_SERVER=$(echo "$EXEC_LINE" | grep -oE '--server [^ ]+' | awk '{print $2}' || true)
        fi
        if [ -z "$HUB_TOKEN" ]; then
          HUB_TOKEN=$(echo "$EXEC_LINE" | grep -oE '--token [^ ]+' | awk '{print $2}' || true)
        fi
        [ -n "$HUB_SERVER" ] && [ -n "$HUB_TOKEN" ] && break
      fi
    done
  fi
fi

if [ -z "$HUB_SERVER" ] || [ -z "$HUB_TOKEN" ]; then
  echo "[-] 错误：无法自动获取主控端地址或节点 Token！" >&2
  echo "    请手动指定参数运行：" >&2
  echo "    curl -fsSL <主控地址>/proxy-agent.sh | bash -s -- --server <主控地址> --token <TOKEN>" >&2
  exit 1
fi

HUB_SERVER="${HUB_SERVER%/}"
echo "=================================================="
echo "  主控端地址: $HUB_SERVER"
echo "  节点 Token: $(echo "$HUB_TOKEN" | cut -c1-8)******"
echo "  组件安装选项:"
[ "$INSTALL_XRAY" = "1" ] && echo "    [✓] Xray-Core" || echo "    [ ] Xray-Core (跳过)"
[ "$INSTALL_SINGBOX" = "1" ] && echo "    [✓] Sing-box" || echo "    [ ] Sing-box (跳过)"
[ "$INSTALL_REALM" = "1" ] && echo "    [✓] Realm 端口转发" || echo "    [ ] Realm 端口转发 (跳过)"
echo "=================================================="

# 如果所有核心都未选择，直接退出（用户仅加探针，不装代理核心）
if [ "$INSTALL_XRAY" -eq 0 ] && [ "$INSTALL_SINGBOX" -eq 0 ] && [ "$INSTALL_REALM" -eq 0 ]; then
  echo "[+] 所有代理核心均未选择，该服务器仅作为监控探针使用。"
  exit 0
fi

INIT="systemd"
if command -v systemctl >/dev/null 2>&1 && [ -d /run/systemd/system ]; then
  INIT="systemd"
elif command -v rc-update >/dev/null 2>&1 || [ -f /sbin/openrc-run ] || [ -d /run/openrc ]; then
  INIT="openrc"
elif command -v systemctl >/dev/null 2>&1; then
  INIT="systemd"
fi

# 1. 安装基础依赖 python3, curl, unzip, tar, openssl, iproute2
if ! command -v python3 >/dev/null 2>&1 || ! command -v curl >/dev/null 2>&1 || ! command -v unzip >/dev/null 2>&1 || ! command -v tar >/dev/null 2>&1 || (command -v apk >/dev/null 2>&1 && (! command -v openssl >/dev/null 2>&1 || ! command -v ss >/dev/null 2>&1)); then
  echo "[+] 正在安装系统基础依赖 (python3, curl, unzip, tar, openssl, iproute2)..."
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update -y && apt-get install -y python3 curl unzip tar iptables openssl iproute2 || true
  elif command -v yum >/dev/null 2>&1; then
    yum install -y python3 curl unzip tar iptables openssl iproute || true
  elif command -v apk >/dev/null 2>&1; then
    apk update >/dev/null 2>&1 || true
    apk add python3 curl unzip tar iptables gcompat openssl iproute2 bash ca-certificates || true
  fi
fi

# DNS64 / NAT64 自动容灾探测与 udhcpc 防冲掉保护
if ! curl -fsSL -m 4 "$HUB_SERVER" >/dev/null 2>&1; then
  if [ -f /etc/resolv.conf ] && ! grep -q "2a00:1098" /etc/resolv.conf; then
    echo "[*] 检测到主控连接异常，正在自动配置 DNS64 加速/NAT64 兼容通道..."
    printf "nameserver 2a00:1098:2b::1\nnameserver 2a01:4f9:c010:3f02::1\nnameserver 2001:67c:2b0::4\n" > /etc/resolv.conf
    [ -d /etc/udhcpc ] && echo 'RESOLV_CONF="no"' > /etc/udhcpc/udhcpc.conf
  fi
fi

ARCH=$(uname -m)

# 2. 按需安装 Xray 核心 (解压包括 geoip.dat 与 geosite.dat)
if [ "$INSTALL_XRAY" = "1" ]; then
  mkdir -p /etc/xray /var/log/xray /opt/proxyprobe /opt/monitor /usr/local/share/xray /usr/local/etc/xray
  XRAY_ARCH="64"
  if [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
    XRAY_ARCH="arm64-v8a"
  fi

  if [ -x /usr/local/bin/xray ]; then
    echo "[+] 检测到已存在 Xray-core 可执行文件: $(/usr/local/bin/xray version 2>/dev/null | head -n 1 || echo 'Xray')"
  else
    TMP_DIR="/tmp/xray_install"
    rm -rf "$TMP_DIR"
    mkdir -p "$TMP_DIR"
    TMP_ZIP="/tmp/xray.zip"

    echo "[+] 正在下载并配置最新版 Xray-core..."
    $CURL_OPTS "$HUB_SERVER/Xray-linux-${XRAY_ARCH}.zip" -o "$TMP_ZIP" 2>/dev/null || \
    $CURL_OPTS "https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-${XRAY_ARCH}.zip" -o "$TMP_ZIP" 2>/dev/null || \
    $CURL_OPTS "https://ghproxy.net/https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-${XRAY_ARCH}.zip" -o "$TMP_ZIP" 2>/dev/null || true

    if [ -f "$TMP_ZIP" ]; then
      if command -v unzip >/dev/null 2>&1; then
        unzip -o "$TMP_ZIP" -d "$TMP_DIR/" >/dev/null 2>&1 || true
      else
        python3 -c "import zipfile; zipfile.ZipFile('$TMP_ZIP').extractall('$TMP_DIR/')" 2>/dev/null || true
      fi

      [ -f "$TMP_DIR/xray" ] && install -m 0755 "$TMP_DIR/xray" /usr/local/bin/xray
      [ -f "$TMP_DIR/geoip.dat" ] && cp -f "$TMP_DIR/geoip.dat" /usr/local/share/xray/ 2>/dev/null || true
      [ -f "$TMP_DIR/geosite.dat" ] && cp -f "$TMP_DIR/geosite.dat" /usr/local/share/xray/ 2>/dev/null || true
      rm -rf "$TMP_DIR" "$TMP_ZIP"
      [ -x /usr/local/bin/xray ] && echo "[+] Xray 核心已就绪: $(/usr/local/bin/xray version | head -n 1)"
    fi
  fi

  # 规范化 Xray 系统服务单元
  if [ "$INIT" = "systemd" ]; then
    cat > /etc/systemd/system/xray.service << 'EOF'
[Unit]
Description=Xray Service
After=network.target nss-lookup.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/xray run -config /etc/xray/config.json
Restart=always
RestartSec=3
LimitNPROC=10000
LimitNOFILE=1000000

[Install]
WantedBy=multi-user.target
EOF
  else
    cat > /etc/init.d/xray << 'EOF'
#!/sbin/openrc-run
name="xray"
description="Xray Service"
command="/usr/local/bin/xray"
command_args="run -config /etc/xray/config.json"
command_background=true
pidfile="/run/xray.pid"
output_log="/var/log/xray/access.log"
error_log="/var/log/xray/error.log"

depend() {
    need net
    after firewall
}
EOF
    chmod +x /etc/init.d/xray
  fi

  if [ ! -f /etc/xray/config.json ]; then
    cat > /etc/xray/config.json << 'EOF'
{
  "log": { "loglevel": "warning" },
  "inbounds": [
    { "tag": "dummy", "listen": "127.0.0.1", "port": 39999, "protocol": "socks", "settings": { "auth": "noauth" } }
  ],
  "outbounds": [
    { "protocol": "freedom", "tag": "direct", "settings": { "domainStrategy": "AsIs" } },
    { "protocol": "blackhole", "tag": "block" }
  ]
}
EOF
  fi
  ln -sf /etc/xray/config.json /usr/local/etc/xray/config.json 2>/dev/null || true

  if [ "$INIT" = "systemd" ]; then
    systemctl daemon-reload 2>/dev/null || true
    systemctl enable xray 2>/dev/null || true
    systemctl restart xray 2>/dev/null || true
  else
    rc-update add xray default 2>/dev/null || true
    rc-service xray restart 2>/dev/null || rc-service xray start 2>/dev/null || true
  fi
else
  echo "[*] 根据选项：跳过 Xray-Core 核心安装"
fi

# 3. 按需安装并配置 Sing-box 核心 (处理 Hysteria 2 / QUIC UDP 协议)
if [ "$INSTALL_SINGBOX" = "1" ]; then
  mkdir -p /etc/sing-box /var/log/sing-box
  SARCH="amd64"
  if [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
    SARCH="arm64"
  fi

  if [ -x /usr/local/bin/sing-box ]; then
    echo "[+] 检测到已存在 Sing-box 核心: $(/usr/local/bin/sing-box version 2>/dev/null | head -n 1 || echo 'Sing-box')"
  else
    TMP_SB_DIR="/tmp/singbox_install"
    rm -rf "$TMP_SB_DIR"
    mkdir -p "$TMP_SB_DIR"
    TMP_SB_TAR="$TMP_SB_DIR/sing-box.tar.gz"
    echo "[+] 正在下载并配置最新版 Sing-box 核心..."
    LATEST_SB_TAG=$($CURL_OPTS "https://api.github.com/repos/SagerNet/sing-box/releases/latest" 2>/dev/null | grep '"tag_name":' | head -n 1 | cut -d'"' -f4 || echo "v1.14.1")
    SB_VER="${LATEST_SB_TAG#v}"
    [ -z "$SB_VER" ] && SB_VER="1.14.1"

    $CURL_OPTS "$HUB_SERVER/sing-box-linux-${SARCH}.tar.gz" -o "$TMP_SB_TAR" 2>/dev/null || \
    $CURL_OPTS "https://github.com/SagerNet/sing-box/releases/download/v${SB_VER}/sing-box-${SB_VER}-linux-${SARCH}.tar.gz" -o "$TMP_SB_TAR" 2>/dev/null || \
    $CURL_OPTS "https://ghproxy.net/https://github.com/SagerNet/sing-box/releases/download/v${SB_VER}/sing-box-${SB_VER}-linux-${SARCH}.tar.gz" -o "$TMP_SB_TAR" 2>/dev/null || true

    if [ -f "$TMP_SB_TAR" ]; then
      tar -xzf "$TMP_SB_TAR" -C "$TMP_SB_DIR/" >/dev/null 2>&1 || true
      SB_BIN=$(find "$TMP_SB_DIR" -name "sing-box" -type f | head -n 1)
      if [ -n "$SB_BIN" ]; then
        install -m 0755 "$SB_BIN" /usr/local/bin/sing-box
        echo "[+] Sing-box 核心已就绪: $(/usr/local/bin/sing-box version | head -n 1)"
      fi
    fi
    rm -rf "$TMP_SB_DIR"
  fi

  if [ ! -f /etc/sing-box/cert.pem ] || [ ! -f /etc/sing-box/key.pem ]; then
    openssl ecparam -name prime256v1 -genkey -noout -out /etc/sing-box/key.pem 2>/dev/null || true
    openssl req -new -x509 -key /etc/sing-box/key.pem -out /etc/sing-box/cert.pem -days 36500 -subj "/CN=bing.com" -addext "subjectAltName=DNS:bing.com" 2>/dev/null || \
    openssl req -new -x509 -key /etc/sing-box/key.pem -out /etc/sing-box/cert.pem -days 36500 -subj "/CN=bing.com" 2>/dev/null || true
  fi

  if [ ! -f /etc/sing-box/config.json ]; then
    cat > /etc/sing-box/config.json << 'EOF'
{
  "log": { "level": "warn" },
  "inbounds": [],
  "outbounds": [{ "type": "direct", "tag": "direct" }, { "type": "block", "tag": "block" }]
}
EOF
  fi

  if [ "$INIT" = "systemd" ]; then
    cat > /etc/systemd/system/sing-box.service << 'EOF'
[Unit]
Description=sing-box Service
Documentation=https://sing-box.sagernet.org/
After=network.target nss-lookup.target

[Service]
Type=simple
User=root
WorkingDirectory=/etc/sing-box
ExecStart=/usr/local/bin/sing-box run -c /etc/sing-box/config.json
Restart=always
RestartSec=3
LimitNPROC=10000
LimitNOFILE=1000000

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload 2>/dev/null || true
    systemctl enable sing-box 2>/dev/null || true
    systemctl restart sing-box 2>/dev/null || true
  else
    cat > /etc/init.d/sing-box << 'EOF'
#!/sbin/openrc-run
name="sing-box"
description="Sing-box Service"
command="/usr/local/bin/sing-box"
command_args="run -c /etc/sing-box/config.json"
directory="/etc/sing-box"
command_background=true
pidfile="/run/sing-box.pid"
output_log="/var/log/sing-box/access.log"
error_log="/var/log/sing-box/error.log"

depend() {
    need net
    after firewall
}
EOF
    chmod +x /etc/init.d/sing-box
    rc-update add sing-box default 2>/dev/null || true
    rc-service sing-box restart 2>/dev/null || rc-service sing-box start 2>/dev/null || true
  fi
else
  echo "[*] 根据选项：跳过 Sing-box 核心安装"
fi

# 4. 按需安装并配置 Realm 端口转发核心 (TCP/UDP 高速端口转发)
if [ "$INSTALL_REALM" = "1" ]; then
  mkdir -p /etc/realm /opt/proxyprobe /opt/monitor
  R_ARCH="x86_64"
  if [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
    R_ARCH="aarch64"
  fi

  if [ -x /usr/local/bin/realm ]; then
    echo "[+] 检测到已存在 Realm 核心: $(/usr/local/bin/realm --version 2>/dev/null || echo 'Realm')"
  else
    TMP_REALM_DIR="/tmp/realm_inst"
    rm -rf "$TMP_REALM_DIR"
    mkdir -p "$TMP_REALM_DIR"
    TMP_REALM_TAR="/tmp/realm.tar.gz"

    echo "[+] 正在下载并配置最新版 Realm 端口转发核心..."
    $CURL_OPTS "$HUB_SERVER/realm-${R_ARCH}-unknown-linux-musl.tar.gz" -o "$TMP_REALM_TAR" 2>/dev/null || \
    $CURL_OPTS "https://github.com/zhboner/realm/releases/latest/download/realm-${R_ARCH}-unknown-linux-musl.tar.gz" -o "$TMP_REALM_TAR" 2>/dev/null || \
    $CURL_OPTS "https://ghproxy.net/https://github.com/zhboner/realm/releases/latest/download/realm-${R_ARCH}-unknown-linux-musl.tar.gz" -o "$TMP_REALM_TAR" 2>/dev/null || true

    if [ -f "$TMP_REALM_TAR" ]; then
      tar -xzf "$TMP_REALM_TAR" -C "$TMP_REALM_DIR/" >/dev/null 2>&1 || true
      REALM_BIN_F=$(find "$TMP_REALM_DIR" -name "realm" -type f | head -n 1)
      if [ -n "$REALM_BIN_F" ]; then
        install -m 0755 "$REALM_BIN_F" /usr/local/bin/realm
        echo "[+] Realm 核心已就绪: $(/usr/local/bin/realm --version 2>/dev/null || echo 'Realm')"
      fi
    fi
    rm -rf "$TMP_REALM_DIR" "$TMP_REALM_TAR"
  fi

  if [ ! -f /etc/realm/config.json ]; then
    cat > /etc/realm/config.json << 'EOF'
{
  "log": { "level": "warn" },
  "network": { "no_tcp": false, "use_udp": true },
  "endpoints": [
    { "listen": "127.0.0.1:39998", "remote": "127.0.0.1:39998" }
  ]
}
EOF
  fi

  if [ "$INIT" = "systemd" ]; then
    cat > /etc/systemd/system/realm.service << 'EOF'
[Unit]
Description=Realm Port Forwarding Service
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/local/bin/realm -c /etc/realm/config.json
Restart=always
RestartSec=3
LimitNOFILE=1000000

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload 2>/dev/null || true
    systemctl enable realm 2>/dev/null || true
    systemctl restart realm 2>/dev/null || true
  else
    cat > /etc/init.d/realm << 'EOF'
#!/sbin/openrc-run
name="realm"
description="Realm Port Forwarding Service"
command="/usr/local/bin/realm"
command_args="-c /etc/realm/config.json"
command_background=true
pidfile="/run/realm.pid"

depend() {
    need net
    after firewall
}
EOF
    chmod +x /etc/init.d/realm
    rc-update add realm default 2>/dev/null || true
    rc-service realm restart 2>/dev/null || rc-service realm start 2>/dev/null || true
  fi
else
  echo "[*] 根据选项：跳过 Realm 端口转发核心安装"
fi

# 5. 下载远端代理守护进程脚本
TARGET_AGENT_DIR="/opt/proxyprobe"
mkdir -p "$TARGET_AGENT_DIR"
echo "[+] 正在拉取代理同步守护程序..."
$CURL_OPTS "$HUB_SERVER/api/proxy/agent-client-script" -o "$TARGET_AGENT_DIR/proxy_agent.py" 2>/dev/null || true
chmod +x "$TARGET_AGENT_DIR/proxy_agent.py" 2>/dev/null || true

# 6. 配置 proxy-agent 守护进程服务
PY_BIN=$(command -v python3 || echo "/usr/bin/python3")
if [ "$INIT" = "systemd" ]; then
  cat > /etc/systemd/system/proxy-agent.service << EOF
[Unit]
Description=ProxyProbe Agent Daemon
After=network.target

[Service]
Type=simple
User=root
EnvironmentFile=-/opt/proxyprobe/agent.env
EnvironmentFile=-/opt/monitor/agent.env
ExecStart=$PY_BIN -u $TARGET_AGENT_DIR/proxy_agent.py --server $HUB_SERVER --token $HUB_TOKEN
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

  systemctl daemon-reload 2>/dev/null || true
  systemctl enable proxy-agent.service 2>/dev/null || true
  systemctl restart proxy-agent.service 2>/dev/null || true
else
  cat > /etc/init.d/proxy-agent << EOF
#!/sbin/openrc-run
name="proxy-agent"
description="ProxyProbe Agent Daemon"
supervisor="supervise-daemon"
respawn_delay=5
respawn_max=0
command="$PY_BIN"
command_args="-u $TARGET_AGENT_DIR/proxy_agent.py --server $HUB_SERVER --token $HUB_TOKEN"
output_log="/var/log/proxy-agent.log"
error_log="/var/log/proxy-agent.log"

depend() {
    need net
    after firewall
}
EOF
  chmod +x /etc/init.d/proxy-agent
  rc-update add proxy-agent default 2>/dev/null || true
  rc-service proxy-agent restart 2>/dev/null || rc-service proxy-agent start 2>/dev/null || true
fi

echo ""
echo "=================================================="
echo "  [OK] 代理管理服务部署完成！"
echo "  已连接主控端: $HUB_SERVER"
echo "  组件安装状态核验:"
if [ "$INSTALL_XRAY" = "1" ]; then
  if [ -x /usr/local/bin/xray ]; then
    echo "  - Xray-Core: 已安装并就绪 ($(/usr/local/bin/xray version 2>/dev/null | head -n 1 || echo 'Xray'))"
  else
    echo "  - Xray-Core: [警告] 核心文件缺失或网络下载失败！"
  fi
fi
if [ "$INSTALL_SINGBOX" = "1" ]; then
  if [ -x /usr/local/bin/sing-box ]; then
    echo "  - Sing-box: 已安装并就绪 ($(/usr/local/bin/sing-box version 2>/dev/null | head -n 1 || echo 'Sing-box'))"
  else
    echo "  - Sing-box: [警告] 核心文件缺失或网络下载失败！"
  fi
fi
if [ "$INSTALL_REALM" = "1" ]; then
  if [ -x /usr/local/bin/realm ]; then
    echo "  - Realm: 已安装并就绪 ($(/usr/local/bin/realm --version 2>/dev/null || echo 'Realm'))"
  else
    echo "  - Realm: [警告] 核心文件缺失或网络下载失败！"
  fi
fi
if [ -f "$TARGET_AGENT_DIR/proxy_agent.py" ]; then
  echo "  - 守护进程: proxy-agent 已就绪并启动"
else
  echo "  - 守护进程: [警告] proxy_agent.py 拉取失败，请检查主控连接！"
fi
echo "  后续在管理后台为此服务器创建的所有节点，将自动实时下发生效！"
echo "=================================================="
"""

PROXY_AGENT_PY = """#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import hashlib
import json
import os
import re
import shutil
import socket
import ssl
import struct
import subprocess
import sys
import time
import urllib.parse
import urllib.request

_last_agent_sb_up = 0
_last_agent_sb_down = 0
_agent_sb_conns = {}
_agent_last_sb_user = 1
_agent_last_sb_node = None
_agent_sb_log_offset = 0
_agent_xr_log_offset = 0
_agent_sb_pending_sessions = {}
_agent_sb_ip_to_user = {}
_agent_sb_ipport_to_user = {}
_agent_sb_ipport_to_node = {}
_agent_sb_initialized = False
_agent_user_active_ips = {}
_agent_tc_manager = None

class TCManager:
    def __init__(self):
        self.iface = None
        self.is_active = False
        self.last_applied_nodes = {}
        self.last_applied_users = {}

    def get_iface(self):
        if not self.iface:
            try:
                res = subprocess.run(["ip", "route", "show", "default"], capture_output=True, text=True, timeout=3)
                if res.returncode == 0 and res.stdout:
                    m = re.search(r'dev\\s+([^\\s]+)', res.stdout)
                    if m:
                        self.iface = m.group(1).strip()
            except Exception:
                pass
            if not self.iface:
                self.iface = "eth0"
        return self.iface

    def ensure_root(self):
        iface = self.get_iface()
        try:
            res = subprocess.run(["tc", "qdisc", "show", "dev", iface], capture_output=True, text=True, timeout=3)
            if "qdisc htb 1:" not in res.stdout:
                subprocess.run(["tc", "qdisc", "del", "dev", iface, "root"], capture_output=True, timeout=3)
                subprocess.run(["tc", "qdisc", "add", "dev", iface, "root", "handle", "1:", "htb", "default", "10", "r2q", "100"], capture_output=True, timeout=3)
                subprocess.run(["tc", "class", "replace", "dev", iface, "parent", "1:", "classid", "1:1", "htb", "rate", "10000mbit", "ceil", "10000mbit"], capture_output=True, timeout=3)
                subprocess.run(["tc", "class", "replace", "dev", iface, "parent", "1:1", "classid", "1:10", "htb", "rate", "10000mbit", "ceil", "10000mbit"], capture_output=True, timeout=3)
            self.is_active = True
        except Exception:
            pass

    def teardown(self):
        if not self.is_active:
            return
        iface = self.get_iface()
        try:
            subprocess.run(["tc", "qdisc", "del", "dev", iface, "root"], capture_output=True, timeout=3)
            subprocess.run(["tc", "qdisc", "add", "dev", iface, "root", "fq"], capture_output=True, timeout=3)
        except Exception:
            pass
        self.is_active = False
        self.last_applied_nodes.clear()
        self.last_applied_users.clear()

    @staticmethod
    def ip_to_handle(ip_str):
        try:
            return struct.unpack("!I", socket.inet_aton(ip_str))[0] & 0x7FFFFFFF
        except Exception:
            return abs(hash(ip_str)) & 0x7FFFFFFF

    def sync(self, desired_nodes, desired_users):
        if not desired_nodes and not desired_users:
            if self.is_active:
                self.teardown()
            return

        iface = self.get_iface()
        self.ensure_root()

        # 1. Sync Nodes (Port-level rate limits)
        removed_nodes = set(self.last_applied_nodes.keys()) - set(desired_nodes.keys())
        for nid in removed_nodes:
            try:
                subprocess.run(["tc", "filter", "del", "dev", iface, "protocol", "ip", "parent", "1:", "prio", "100", "handle", str(5000 + nid * 2), "flower"], capture_output=True, timeout=3)
                subprocess.run(["tc", "filter", "del", "dev", iface, "protocol", "ip", "parent", "1:", "prio", "100", "handle", str(5000 + nid * 2 + 1), "flower"], capture_output=True, timeout=3)
                subprocess.run(["tc", "class", "del", "dev", iface, "parent", "1:1", "classid", f"1:{1000 + nid}"], capture_output=True, timeout=3)
            except Exception:
                pass

        for nid, info in desired_nodes.items():
            prev = self.last_applied_nodes.get(nid)
            if not prev or prev != info:
                port = info["port"]
                mbps = info["mbps"]
                classid = f"1:{1000 + nid}"
                try:
                    subprocess.run(["tc", "class", "replace", "dev", iface, "parent", "1:1", "classid", classid, "htb", "rate", f"{mbps}mbit", "ceil", f"{mbps}mbit", "burst", "256k"], capture_output=True, timeout=3)
                    subprocess.run(["tc", "filter", "replace", "dev", iface, "protocol", "ip", "parent", "1:", "prio", "100", "handle", str(5000 + nid * 2), "flower", "ip_proto", "tcp", "src_port", str(port), "classid", classid], capture_output=True, timeout=3)
                    subprocess.run(["tc", "filter", "replace", "dev", iface, "protocol", "ip", "parent", "1:", "prio", "100", "handle", str(5000 + nid * 2 + 1), "flower", "ip_proto", "udp", "src_port", str(port), "classid", classid], capture_output=True, timeout=3)
                except Exception:
                    pass

        # 2. Sync Users (Client IP-level rate limits)
        removed_users = set(self.last_applied_users.keys()) - set(desired_users.keys())
        for uid in removed_users:
            u_info = self.last_applied_users[uid]
            for ip in u_info.get("ips", set()):
                handle = self.ip_to_handle(ip)
                proto = "ipv6" if ":" in ip else "ip"
                try:
                    subprocess.run(["tc", "filter", "del", "dev", iface, "protocol", proto, "parent", "1:", "prio", "50", "handle", str(handle), "flower"], capture_output=True, timeout=3)
                except Exception:
                    pass
            try:
                subprocess.run(["tc", "class", "del", "dev", iface, "parent", "1:1", "classid", f"1:{2000 + uid}"], capture_output=True, timeout=3)
            except Exception:
                pass

        for uid, info in desired_users.items():
            mbps = info["mbps"]
            ips = info.get("ips", set())
            classid = f"1:{2000 + uid}"
            prev = self.last_applied_users.get(uid)

            if not prev or prev["mbps"] != mbps:
                try:
                    subprocess.run(["tc", "class", "replace", "dev", iface, "parent", "1:1", "classid", classid, "htb", "rate", f"{mbps}mbit", "ceil", f"{mbps}mbit", "burst", "256k"], capture_output=True, timeout=3)
                except Exception:
                    pass

            prev_ips = prev["ips"] if prev else set()
            for dead_ip in (prev_ips - ips):
                handle = self.ip_to_handle(dead_ip)
                proto = "ipv6" if ":" in dead_ip else "ip"
                try:
                    subprocess.run(["tc", "filter", "del", "dev", iface, "protocol", proto, "parent", "1:", "prio", "50", "handle", str(handle), "flower"], capture_output=True, timeout=3)
                except Exception:
                    pass

            for new_ip in (ips - prev_ips):
                handle = self.ip_to_handle(new_ip)
                proto = "ipv6" if ":" in new_ip else "ip"
                try:
                    subprocess.run(["tc", "filter", "replace", "dev", iface, "protocol", proto, "parent", "1:", "prio", "50", "handle", str(handle), "flower", "dst_ip", new_ip, "classid", classid], capture_output=True, timeout=3)
                except Exception:
                    pass

        self.last_applied_nodes = {nid: dict(info) for nid, info in desired_nodes.items()}
        self.last_applied_users = {uid: { "mbps": info["mbps"], "ips": set(info["ips"]) } for uid, info in desired_users.items()}

XRAY_BIN = "/usr/local/bin/xray"
XRAY_CONFIG = "/etc/xray/config.json"
SINGBOX_BIN = "/usr/local/bin/sing-box"
SINGBOX_CONFIG = "/etc/sing-box/config.json"
REALM_BIN = "/usr/local/bin/realm"
REALM_CONFIG = "/etc/realm/config.json"
HASH_FILE = "/opt/proxyprobe/.proxy_config.hash" if os.path.exists("/opt/proxyprobe") else "/opt/monitor/.proxy_config.hash"

def read_saved_hash():
    if os.path.exists(HASH_FILE):
        try:
            with open(HASH_FILE, "r", encoding="utf-8") as f:
                return f.read().strip()
        except Exception:
            pass
    return None

def save_saved_hash(h):
    if not h:
        return
    try:
        os.makedirs(os.path.dirname(HASH_FILE), exist_ok=True)
        with open(HASH_FILE, "w", encoding="utf-8") as f:
            f.write(h.strip())
    except Exception:
        pass

def get_agent_public_ip():
    try:
        target = ("8.8.8.8", 80)
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(1.0)
        s.connect(target)
        ip = s.getsockname()[0]
        s.close()
        import ipaddress
        if not ipaddress.ip_address(ip).is_private:
            return ip
    except Exception:
        pass
    for url in ("https://api.ipify.org", "https://icanhazip.com", "https://ip.sb"):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/7.68.0"})
            with urllib.request.urlopen(req, timeout=2) as resp:
                text = resp.read().decode("utf-8").strip()
                if text:
                    return text
        except Exception:
            continue
    return ""

def is_systemd():
    return os.path.exists("/run/systemd/system") or (shutil.which("systemctl") is not None and os.path.exists("/etc/systemd"))

def service_action(action, name):
    if is_systemd():
        if action in ("reload_restart", "restart"):
            subprocess.run(["systemctl", "daemon-reload"], capture_output=True)
            subprocess.run(["systemctl", "restart", name], capture_output=True)
        elif action == "start":
            subprocess.run(["systemctl", "start", name], capture_output=True)
        elif action == "stop":
            subprocess.run(["systemctl", "stop", name], capture_output=True)
        elif action == "enable":
            subprocess.run(["systemctl", "enable", name], capture_output=True)
    else:
        if action in ("reload_restart", "restart"):
            res = subprocess.run(["rc-service", name, "restart"], capture_output=True)
            if res.returncode != 0:
                subprocess.run(["rc-service", name, "start"], capture_output=True)
        elif action == "start":
            subprocess.run(["rc-service", name, "start"], capture_output=True)
        elif action == "stop":
            subprocess.run(["rc-service", name, "stop"], capture_output=True)
        elif action == "enable":
            subprocess.run(["rc-update", "add", name, "default"], capture_output=True)

def service_is_active(name):
    if is_systemd():
        return subprocess.run(["systemctl", "is-active", "--quiet", name]).returncode == 0
    else:
        res = subprocess.run(["rc-service", name, "status"], capture_output=True, text=True)
        if res.returncode == 0:
            return True
        pid_file = f"/run/{name}.pid"
        if os.path.exists(pid_file):
            try:
                with open(pid_file) as f:
                    pid = int(f.read().strip())
                os.kill(pid, 0)
                return True
            except Exception:
                pass
        return False

def register_service_if_missing(name, exec_start, desc="", working_dir=""):
    if is_systemd():
        svc_path = f"/etc/systemd/system/{name}.service"
        if not os.path.exists(svc_path):
            lines = ["[Unit]", f"Description={desc or name}", "After=network.target nss-lookup.target", "", "[Service]", "Type=simple", "User=root"]
            if working_dir:
                lines.append(f"WorkingDirectory={working_dir}")
            lines.extend([f"ExecStart={exec_start}", "Restart=always", "RestartSec=3", "LimitNPROC=10000", "LimitNOFILE=1000000", "", "[Install]", "WantedBy=multi-user.target", ""])
            try:
                with open(svc_path, "w", encoding="utf-8") as f:
                    f.write("\\n".join(lines))
                subprocess.run(["systemctl", "daemon-reload"], capture_output=True)
                subprocess.run(["systemctl", "enable", name], capture_output=True)
            except Exception:
                pass
    else:
        init_path = f"/etc/init.d/{name}"
        if not os.path.exists(init_path):
            parts = exec_start.split()
            init_lines = [
                "#!/sbin/openrc-run",
                f'name="{name}"',
                f'description="{desc or name}"',
                f'command="{parts[0]}"',
                f'command_args="{" ".join(parts[1:])}"',
                "command_background=true",
                f'pidfile="/run/{name}.pid"'
            ]
            if working_dir:
                init_lines.append(f'directory="{working_dir}"')
            init_lines.extend(["", "depend() {", "    need net", "    after firewall", "}", ""])
            try:
                with open(init_path, "w", encoding="utf-8") as f:
                    f.write("\\n".join(init_lines))
                os.chmod(init_path, 0o755)
                subprocess.run(["rc-update", "add", name, "default"], capture_output=True)
            except Exception:
                pass

def read_env_file():
    srv, tok = "", ""
    for env_file in ("/opt/proxyprobe/agent.env", "/opt/monitor/agent.env"):
        if os.path.exists(env_file):
            try:
                with open(env_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line.startswith("MONITOR_SERVER="):
                            srv = line.split("=", 1)[1].strip("'").strip('"')
                        elif line.startswith("MONITOR_TOKEN="):
                            tok = line.split("=", 1)[1].strip("'").strip('"')
                if srv and tok:
                    break
            except Exception:
                pass
    return srv.rstrip("/"), tok

def get_params():
    server = os.environ.get("HUB_SERVER", "")
    token = os.environ.get("HUB_TOKEN", "")
    for i in range(len(sys.argv)):
        if sys.argv[i] == "--server" and i + 1 < len(sys.argv):
            server = sys.argv[i + 1]
        elif sys.argv[i] == "--token" and i + 1 < len(sys.argv):
            token = sys.argv[i + 1]
    env_srv, env_tok = read_env_file()
    if env_srv:
        server = env_srv
    if env_tok:
        token = env_tok
    return server.rstrip("/"), token

def allow_ports(ports):
    for p in ports:
        try:
            subprocess.run(["iptables", "-I", "INPUT", "-p", "tcp", "--dport", str(p), "-j", "ACCEPT"], capture_output=True)
            subprocess.run(["iptables", "-I", "INPUT", "-p", "udp", "--dport", str(p), "-j", "ACCEPT"], capture_output=True)
            subprocess.run(["iptables", "-I", "OUTPUT", "-p", "tcp", "--sport", str(p), "-j", "ACCEPT"], capture_output=True)
            subprocess.run(["iptables", "-I", "OUTPUT", "-p", "udp", "--sport", str(p), "-j", "ACCEPT"], capture_output=True)
        except Exception:
            pass
        try:
            subprocess.run(["ufw", "allow", f"{p}/tcp"], capture_output=True)
            subprocess.run(["ufw", "allow", f"{p}/udp"], capture_output=True)
        except Exception:
            pass
        try:
            subprocess.run(["nft", "add", "rule", "inet", "filter", "input", "tcp", "dport", str(p), "accept"], capture_output=True)
        except Exception:
            pass

def check_port_listening(port):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.3)
        res = s.connect_ex(('127.0.0.1', port))
        s.close()
        if res == 0:
            return True
    except Exception:
        pass
    try:
        res = subprocess.run(["ss", "-tulpn"], capture_output=True, text=True)
        target = f":{port}"
        for line in (res.stdout or "").splitlines():
            if target in line:
                return True
    except Exception:
        pass
    try:
        res_ns = subprocess.run(["netstat", "-tlun"], capture_output=True, text=True)
        target = f":{port}"
        for line in (res_ns.stdout or "").splitlines():
            if target in line:
                return True
    except Exception:
        pass
    return False

def ensure_xray_installed(server):
    if os.path.exists(XRAY_BIN):
        return True
    try:
        print("[+] 探针节点检测到 Xray 规则但未安装核心，正在自动下载安装 Xray-core...", flush=True)
        import platform
        import zipfile
        arch = platform.machine().lower()
        xarch = "arm64-v8a" if arch in ("aarch64", "arm64") else "64"
        tmp_dir = "/tmp/xray_agent_dl"
        os.makedirs(tmp_dir, exist_ok=True)
        zip_file = os.path.join(tmp_dir, "xray.zip")
        urls = [
            f"{server}/Xray-linux-{xarch}.zip",
            f"https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-{xarch}.zip",
            f"https://ghproxy.net/https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-{xarch}.zip"
        ]
        downloaded = False
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        for u in urls:
            try:
                req = urllib.request.Request(u, headers={"User-Agent": "curl/7.68.0"})
                with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
                    with open(zip_file, "wb") as f:
                        f.write(resp.read())
                downloaded = True
                break
            except Exception:
                pass
        if not downloaded or not os.path.exists(zip_file):
            return False

        with zipfile.ZipFile(zip_file, "r") as zf:
            zf.extractall(tmp_dir)

        xr_bin = os.path.join(tmp_dir, "xray")
        if os.path.exists(xr_bin):
            shutil.copy(xr_bin, XRAY_BIN)
            os.chmod(XRAY_BIN, 0o755)
        for dat in ("geoip.dat", "geosite.dat"):
            dp = os.path.join(tmp_dir, dat)
            if os.path.exists(dp):
                os.makedirs("/usr/local/share/xray", exist_ok=True)
                shutil.copy(dp, os.path.join("/usr/local/share/xray", dat))
        shutil.rmtree(tmp_dir, ignore_errors=True)

        register_service_if_missing("xray", "/usr/local/bin/xray run -config /etc/xray/config.json", desc="Xray Service")
        print("[+] 探针节点 Xray-core 核心自动部署就绪", flush=True)
        return True
    except Exception as e:
        print(f"[-] 自动安装 Xray 失败: {e}", flush=True)
        return False

def ensure_singbox_installed(server):
    if os.path.exists(SINGBOX_BIN):
        return True
    try:
        print("[+] 探针节点检测到 Sing-box 协议规则，正在自动下载安装 sing-box 核心...", flush=True)
        import platform
        arch = platform.machine().lower()
        sarch = "arm64" if arch in ("aarch64", "arm64") else "amd64"
        tmp_dir = "/tmp/sb_agent_dl"
        os.makedirs(tmp_dir, exist_ok=True)
        tar_file = os.path.join(tmp_dir, "sing-box.tar.gz")
        urls = [
            f"{server}/sing-box-linux-{sarch}.tar.gz",
            f"https://github.com/SagerNet/sing-box/releases/download/v1.14.1/sing-box-1.14.1-linux-{sarch}.tar.gz",
            f"https://ghproxy.net/https://github.com/SagerNet/sing-box/releases/download/v1.14.1/sing-box-1.14.1-linux-{sarch}.tar.gz"
        ]
        downloaded = False
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        for u in urls:
            try:
                req = urllib.request.Request(u, headers={"User-Agent": "curl/7.68.0"})
                with urllib.request.urlopen(req, timeout=30, context=ctx) as resp:
                    with open(tar_file, "wb") as f:
                        f.write(resp.read())
                downloaded = True
                break
            except Exception:
                pass
        if not downloaded or not os.path.exists(tar_file):
            return False

        import tarfile
        with tarfile.open(tar_file, "r:gz") as tar:
            tar.extractall(tmp_dir)
        sb_bin = None
        for root, dirs, files in os.walk(tmp_dir):
            if "sing-box" in files:
                sb_bin = os.path.join(root, "sing-box")
                break
        if sb_bin:
            shutil.copy(sb_bin, SINGBOX_BIN)
            os.chmod(SINGBOX_BIN, 0o755)
        shutil.rmtree(tmp_dir, ignore_errors=True)

        os.makedirs("/etc/sing-box", exist_ok=True)
        cert_file = "/etc/sing-box/cert.pem"
        key_file = "/etc/sing-box/key.pem"
        if not os.path.exists(cert_file) or not os.path.exists(key_file):
            subprocess.run([
                "openssl", "req", "-x509", "-nodes", "-newkey", "ec",
                "-pkeyopt", "ec_paramgen_curve:prime256v1",
                "-keyout", key_file, "-out", cert_file,
                "-subj", "/CN=bing.com", "-days", "36500",
                "-addext", "subjectAltName=DNS:bing.com"
            ], capture_output=True)

        register_service_if_missing("sing-box", "/usr/local/bin/sing-box run -c /etc/sing-box/config.json", desc="sing-box Service", working_dir="/etc/sing-box")
        print("[+] 探针节点 Sing-box 核心自动部署就绪", flush=True)
        return True
    except Exception as e:
        print(f"[-] 自动安装 sing-box 失败: {e}", flush=True)
        return False

def sync_step(server, token, last_hash):
    # 1. 拉取节点配置 (忽略 SSL 证书校验，保障自签或反代证书正常同步)
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    url = f"{server}/api/proxy/agent-sync?token={urllib.parse.quote(token)}"
    req = urllib.request.Request(url, headers={"User-Agent": "ProxyAgent/1.0"})
    with urllib.request.urlopen(req, timeout=10, context=ctx) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    if not data.get("ok"):
        return last_hash

    inbounds = data.get("inbounds", [])
    singbox_inbounds = data.get("singbox_inbounds", [])
    realm_endpoints = data.get("realm_endpoints", [])
    config_repr = json.dumps({"xray": inbounds, "singbox": singbox_inbounds, "realm": realm_endpoints}, sort_keys=True)
    curr_hash = hashlib.sha256(config_repr.encode("utf-8")).hexdigest()

    if curr_hash != last_hash:
        print(f"[{time.strftime('%X')}] 收到新节点配置，共 {len(inbounds)} 个规则，应用中...")
        applied_inbounds = list(inbounds)
        if not applied_inbounds:
            applied_inbounds = [{
                "tag": "dummy", "listen": "127.0.0.1", "port": 39999, "protocol": "socks", "settings": {"auth": "noauth"}
            }]
            ports = []
        else:
            ports = [inb.get("port") for inb in applied_inbounds if inb.get("port")]
            allow_ports(ports)

        if inbounds and not os.path.exists(XRAY_BIN):
            ensure_xray_installed(server)

        os.makedirs("/var/log/xray", exist_ok=True)
        full_config = {
            "log": { "loglevel": "warning", "access": "/var/log/xray/access.log" },
            "stats": {},
            "api": {
                "tag": "api",
                "services": ["StatsService"]
            },
            "policy": {
                "levels": {
                    "0": {
                        "statsUserUplink": True,
                        "statsUserDownlink": True
                    }
                },
                "system": {
                    "statsInboundUplink": True,
                    "statsInboundDownlink": True
                }
            },
            "inbounds": [{
                "tag": "api",
                "listen": "127.0.0.1",
                "port": 10085,
                "protocol": "dokodemo-door",
                "settings": {"address": "127.0.0.1"}
            }] + applied_inbounds,
            "outbounds": [
                { "protocol": "freedom", "tag": "direct", "settings": { "domainStrategy": "AsIs" } },
                { "protocol": "blackhole", "tag": "block" },
                { "protocol": "freedom", "tag": "api" }
            ],
            "routing": {
                "rules": [
                    { "inboundTag": ["api"], "outboundTag": "api", "type": "field" }
                ]
            }
        }

        os.makedirs(os.path.dirname(XRAY_CONFIG), exist_ok=True)
        tmp_cfg = os.path.join(os.path.dirname(XRAY_CONFIG), "config.tmp.json")
        with open(tmp_cfg, "w", encoding="utf-8") as f:
            json.dump(full_config, f, indent=2)

        xray_ok = True
        if os.path.exists(XRAY_BIN):
            existing_xray_cfg = ""
            if os.path.exists(XRAY_CONFIG):
                try:
                    with open(XRAY_CONFIG, "r", encoding="utf-8") as f:
                        existing_xray_cfg = f.read()
                except Exception:
                    pass

            with open(tmp_cfg, "r", encoding="utf-8") as f:
                new_xray_cfg = f.read()

            if existing_xray_cfg.strip() == new_xray_cfg.strip():
                try:
                    os.remove(tmp_cfg)
                except Exception:
                    pass
                print(f"[{time.strftime('%X')}] Xray 配置内容完全一致，跳过重启，保障长连接零中断", flush=True)
            else:
                test_res = subprocess.run([XRAY_BIN, "run", "-test", "-config", tmp_cfg, "-format", "json"], capture_output=True, text=True)
                if test_res.returncode == 0:
                    os.replace(tmp_cfg, XRAY_CONFIG)
                    try:
                        os.makedirs("/usr/local/etc/xray", exist_ok=True)
                        shutil.copyfile(XRAY_CONFIG, "/usr/local/etc/xray/config.json")
                    except Exception:
                        pass
                    service_action("reload_restart", "xray")
                    time.sleep(1)
                    print(f"[{time.strftime('%X')}] Xray 配置变更生效并重载成功", flush=True)
                else:
                    xray_ok = False
                    err_msg = (test_res.stdout + " " + test_res.stderr).strip()
                    print(f"[{time.strftime('%X')}] Xray 配置校验失败: {err_msg}", flush=True)

        if singbox_inbounds and not os.path.exists(SINGBOX_BIN):
            ensure_singbox_installed(server)

        if os.path.exists(SINGBOX_BIN) and singbox_inbounds:
            os.makedirs("/etc/sing-box", exist_ok=True)
            cert_file = "/etc/sing-box/cert.pem"
            key_file = "/etc/sing-box/key.pem"
            if not os.path.exists(cert_file) or not os.path.exists(key_file):
                subprocess.run([
                    "openssl", "req", "-x509", "-nodes", "-newkey", "ec",
                    "-pkeyopt", "ec_paramgen_curve:prime256v1",
                    "-keyout", key_file, "-out", cert_file,
                    "-subj", "/CN=bing.com", "-days", "36500",
                    "-addext", "subjectAltName=DNS:bing.com"
                ], capture_output=True)
            sb_ports = [inb.get("listen_port") for inb in singbox_inbounds if inb.get("listen_port")]
            if sb_ports:
                allow_ports(sb_ports)
            os.makedirs("/var/log/sing-box", exist_ok=True)
            sb_config = {
                "log": { "level": "info", "output": "/var/log/sing-box/access.log" },
                "experimental": {
                    "clash_api": {
                        "external_controller": "127.0.0.1:9095"
                    }
                },
                "inbounds": singbox_inbounds,
                "outbounds": [{ "type": "direct", "tag": "direct" }, { "type": "block", "tag": "block" }]
            }
            tmp_sb = "/etc/sing-box/config.tmp.json"
            os.makedirs("/etc/sing-box", exist_ok=True)
            with open(tmp_sb, "w", encoding="utf-8") as f:
                json.dump(sb_config, f, indent=2)

            existing_sb_cfg = ""
            if os.path.exists(SINGBOX_CONFIG):
                try:
                    with open(SINGBOX_CONFIG, "r", encoding="utf-8") as f:
                        existing_sb_cfg = f.read()
                except Exception:
                    pass

            with open(tmp_sb, "r", encoding="utf-8") as f:
                new_sb_cfg = f.read()

            if existing_sb_cfg.strip() == new_sb_cfg.strip():
                try:
                    os.remove(tmp_sb)
                except Exception:
                    pass
                print(f"[{time.strftime('%X')}] Sing-box 配置内容完全一致，跳过重启，保障长连接零中断", flush=True)
            else:
                sb_chk = subprocess.run([SINGBOX_BIN, "check", "-c", tmp_sb], capture_output=True, text=True)
                if sb_chk.returncode == 0:
                    os.replace(tmp_sb, SINGBOX_CONFIG)
                    service_action("restart", "sing-box")
                    print(f"[{time.strftime('%X')}] Sing-box 配置变更生效并重启成功", flush=True)
                else:
                    print(f"[{time.strftime('%X')}] Sing-box 配置校验失败: {sb_chk.stderr}", flush=True)

        # 3. Realm 端口转发中转规则同步
        realm_installed = os.path.exists(REALM_BIN)
        if realm_installed:
            active_eps = [
                {"listen": ep["listen"], "remote": ep["remote"]}
                for ep in realm_endpoints
                if ep.get("listen") and ep.get("remote")
            ]
            if not active_eps:
                active_eps = [{"listen": "127.0.0.1:39998", "remote": "127.0.0.1:39999"}]
            realm_cfg = {
                "log": {"level": "warn"},
                "network": {"no_tcp": False, "use_udp": True},
                "endpoints": active_eps
            }
            try:
                os.makedirs(os.path.dirname(REALM_CONFIG), exist_ok=True)
                tmp_realm = os.path.join(os.path.dirname(REALM_CONFIG), "config.tmp.json")
                with open(tmp_realm, "w", encoding="utf-8") as f:
                    json.dump(realm_cfg, f, indent=2)

                existing_realm_cfg = ""
                if os.path.exists(REALM_CONFIG):
                    try:
                        with open(REALM_CONFIG, "r", encoding="utf-8") as f:
                            existing_realm_cfg = f.read()
                    except Exception:
                        pass

                with open(tmp_realm, "r", encoding="utf-8") as f:
                    new_realm_cfg = f.read()

                if existing_realm_cfg.strip() == new_realm_cfg.strip():
                    try:
                        os.remove(tmp_realm)
                    except Exception:
                        pass
                    print(f"[{time.strftime('%X')}] Realm 配置内容完全一致，跳过重启", flush=True)
                else:
                    os.replace(tmp_realm, REALM_CONFIG)
                    register_service_if_missing("realm", f"{REALM_BIN} -c {REALM_CONFIG}", desc="Realm Port Forwarding Service")
                    
                    r_ports = []
                    for ep in realm_endpoints:
                        try:
                            p = int(ep["listen"].split(":")[-1])
                            if p > 0:
                                r_ports.append(p)
                        except Exception:
                            pass
                    if r_ports:
                        allow_ports(r_ports)
                    service_action("restart", "realm")
                    print(f"[{time.strftime('%X')}] Realm 转发配置已生效并重启成功，共 {len(realm_endpoints)} 个转发规则", flush=True)
            except Exception as e:
                print(f"[{time.strftime('%X')}] Realm 配置更新失败: {e}", flush=True)

        if xray_ok:
            last_hash = curr_hash
            save_saved_hash(curr_hash)

    # 2. 状态检测与端口监听真实检测
    is_xr_active = service_is_active("xray")
    is_sb_active = service_is_active("sing-box") if singbox_inbounds else True
    is_active = is_xr_active or is_sb_active
    version = "unknown"
    try:
        ver_res = subprocess.run([XRAY_BIN, "version"], capture_output=True, text=True)
        if ver_res.stdout:
            version = ver_res.stdout.splitlines()[0]
    except Exception:
        pass

    xr_ports = [inb.get("port") for inb in inbounds if inb.get("port")]
    sb_ports = [inb.get("listen_port") for inb in singbox_inbounds if inb.get("listen_port")]
    realm_ports = []
    for ep in realm_endpoints:
        try:
            p = int(ep["listen"].split(":")[-1])
            if p > 0:
                realm_ports.append(p)
        except Exception:
            pass
    target_ports = xr_ports + sb_ports + realm_ports
    listening_ports = [p for p in target_ports if check_port_listening(p)]
    
    # 自动自愈：若有目标端口未正常监听，强制刷新防火墙规则并重启服务
    if xr_ports and any(not check_port_listening(p) for p in xr_ports):
        allow_ports(xr_ports)
        service_action("reload_restart", "xray")
        time.sleep(1)
    if sb_ports and any(not check_port_listening(p) for p in sb_ports):
        allow_ports(sb_ports)
        service_action("restart", "sing-box")
        time.sleep(1)
    if realm_ports and any(not check_port_listening(p) for p in realm_ports):
        allow_ports(realm_ports)
        service_action("restart", "realm")
        time.sleep(1)
    listening_ports = [p for p in target_ports if check_port_listening(p)]
    is_active = service_is_active("xray") or service_is_active("sing-box") or (service_is_active("realm") if realm_endpoints else False)

    status = "running" if (is_active and (len(listening_ports) == len(target_ports) or not target_ports)) else "stopped"
    if not is_active:
        status = "stopped"
    elif target_ports and not listening_ports:
        status = "port_error"

    # 自动无缝升级：若主控端发布了更新的代理同步程序，自动保存并重启
    try:
        remote_sc_url = f"{server}/api/proxy/agent-client-script"
        req_sc = urllib.request.Request(remote_sc_url, headers={"User-Agent": "ProxyAgent/1.0"})
        with urllib.request.urlopen(req_sc, timeout=5, context=ctx) as sc_resp:
            new_code = sc_resp.read().decode("utf-8")
        current_file = os.path.abspath(__file__)
        with open(current_file, "r", encoding="utf-8") as f:
            cur_code = f.read()
        if new_code and len(new_code) > 500 and new_code.strip() != cur_code.strip():
            with open(current_file + ".new", "w", encoding="utf-8") as f:
                f.write(new_code)
            chk = subprocess.run([sys.executable, "-m", "py_compile", current_file + ".new"], capture_output=True)
            if chk.returncode == 0:
                os.replace(current_file + ".new", current_file)
                print(f"[{time.strftime('%X')}] 代理守护程序已更新，正在无缝热重载自身...", flush=True)
                try:
                    os.execv(sys.executable, [sys.executable] + sys.argv)
                except Exception:
                    service_action("restart", "proxy-agent")
            else:
                try:
                    os.remove(current_file + ".new")
                except Exception:
                    pass
    except Exception:
        pass

    diag = {}
    def run_cmd(cmd):
        try:
            return subprocess.run(cmd, capture_output=True, text=True).stdout
        except Exception as ex:
            return f"ERR: {ex}"

    diag["ss"] = run_cmd(["ss", "-tulpn"])
    diag["ip"] = run_cmd(["ip", "-brief", "addr"])
    diag["ps"] = run_cmd(["ps", "aux"])
    diag["nft"] = run_cmd(["nft", "list", "ruleset"])[:1000]
    try:
        if os.path.exists(XRAY_CONFIG):
            with open(XRAY_CONFIG) as f:
                diag["cfg"] = f.read()
    except Exception as e:
        diag["cfg_err"] = str(e)
    xray_log = json.dumps(diag)

    sb_installed = os.path.exists(SINGBOX_BIN)
    sb_running = False
    sb_version = ""
    if sb_installed:
        sb_running = service_is_active("sing-box")
        try:
            sb_out = subprocess.run([SINGBOX_BIN, "version"], capture_output=True, text=True).stdout
            if sb_out:
                sb_version = sb_out.splitlines()[0]
        except Exception:
            pass

    xr_installed = os.path.exists(XRAY_BIN)
    xr_running = is_active
    realm_installed = os.path.exists(REALM_BIN)
    realm_running = False
    if realm_installed:
        if not os.path.exists(REALM_CONFIG):
            try:
                os.makedirs(os.path.dirname(REALM_CONFIG), exist_ok=True)
                with open(REALM_CONFIG, "w", encoding="utf-8") as f:
                    json.dump({"log": {"level": "warn"}, "network": {"no_tcp": False, "use_udp": True}, "endpoints": [{"listen": "127.0.0.1:39998", "remote": "127.0.0.1:39998"}]}, f, indent=2)
            except Exception:
                pass
        register_service_if_missing("realm", f"{REALM_BIN} -c {REALM_CONFIG}", desc="Realm Port Forwarding Service")
        realm_running = service_is_active("realm")
        if not realm_running:
            service_action("start", "realm")
            time.sleep(0.5)
            realm_running = service_is_active("realm")

    user_stats = []
    node_stats = []
    user_traffic = {}
    node_traffic = {}
    active_uids = set()

    global _agent_xr_log_offset, _agent_user_active_ips
    now_ts = time.time()
    xray_log = "/var/log/xray/access.log"
    if os.path.exists(xray_log):
        try:
            sz = os.path.getsize(xray_log)
            if sz < _agent_xr_log_offset:
                _agent_xr_log_offset = 0
            with open(xray_log, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(_agent_xr_log_offset)
                for line in f:
                    if "accepted" in line and "email:" in line:
                        m_email = re.search(r'email:\\s*([^\\s]+)', line)
                        m_ip = re.search(r'(?:from\\s+|^)([\\d\\.:a-fA-F]+):\\d+\\s+accepted', line)
                        if m_email and m_ip:
                            email = m_email.group(1).strip()
                            ip = m_ip.group(1).strip()
                            uid = None
                            if email.startswith("user_"):
                                try:
                                    uid = int(email.split("_")[1])
                                except ValueError:
                                    pass
                            elif email in ("default", "default@vless", "default@trojan", "default@vmess"):
                                uid = 1
                            if uid is not None and ip not in ("127.0.0.1", "::1"):
                                if uid not in _agent_user_active_ips:
                                    _agent_user_active_ips[uid] = {}
                                _agent_user_active_ips[uid][ip] = now_ts
                _agent_xr_log_offset = f.tell()
        except Exception:
            pass

    if xr_running:
        try:
            res = subprocess.run(
                [XRAY_BIN, "api", "statsquery", "--server=127.0.0.1:10085", "-reset=true"],
                capture_output=True, text=True, timeout=5
            )
            if res.returncode == 0 and res.stdout:
                st_data = json.loads(res.stdout)
                raw_stats = st_data.get("stat") or []
                for item in raw_stats:
                    name = item.get("name", "")
                    val = int(item.get("value", 0))
                    if val <= 0:
                        continue
                    parts = name.split(">>>")
                    if len(parts) >= 4 and parts[0] == "user" and parts[2] == "traffic":
                        email = parts[1]
                        direction = parts[3]
                        uid = None
                        if email.startswith("user_"):
                            try:
                                uid = int(email.split("_")[1])
                            except ValueError:
                                pass
                        elif email in ("default", "default@vless", "default@trojan", "default@vmess"):
                            uid = 1
                        if uid is not None:
                            if uid not in user_traffic:
                                user_traffic[uid] = {"user_id": uid, "upload": 0, "download": 0}
                            if direction == "uplink":
                                user_traffic[uid]["upload"] += val
                            elif direction == "downlink":
                                user_traffic[uid]["download"] += val
                    elif len(parts) >= 4 and parts[0] == "inbound" and parts[2] == "traffic":
                        tag = parts[1]
                        direction = parts[3]
                        nid = None
                        if tag.startswith("inbound-"):
                            try:
                                nid = int(tag.split("-")[1])
                            except ValueError:
                                pass
                        if nid is not None:
                            if nid not in node_traffic:
                                node_traffic[nid] = {"node_id": nid, "upload": 0, "download": 0}
                            if direction == "uplink":
                                node_traffic[nid]["upload"] += val
                            elif direction == "downlink":
                                node_traffic[nid]["download"] += val
        except Exception:
            pass

    if sb_running:
        global _last_agent_sb_up, _last_agent_sb_down, _agent_sb_conns, _agent_last_sb_user, _agent_last_sb_node, _agent_sb_initialized
        global _agent_sb_log_offset, _agent_sb_pending_sessions, _agent_sb_ip_to_user, _agent_sb_ipport_to_user, _agent_sb_ipport_to_node
        sb_log = "/var/log/sing-box/access.log"
        if os.path.exists(sb_log):
            try:
                sz = os.path.getsize(sb_log)
                if sz < _agent_sb_log_offset:
                    _agent_sb_log_offset = 0
                with open(sb_log, "r", encoding="utf-8", errors="ignore") as f:
                    f.seek(_agent_sb_log_offset)
                    for line in f:
                        m_cid = re.search(r'\\[(\\d+)\\s+[^\\]]+\\]', line)
                        m_tag = re.search(r'inbound/\\w+\\[([^\\]]+)\\]', line)
                        m_conn_from = re.search(r'inbound connection from ([\\d\\.:a-fA-F]+):(\\d+)', line)
                        m_user = re.search(r'\\[(user_\\d+|default)\\]', line)

                        cid = m_cid.group(1) if m_cid else None
                        inb_tag = m_tag.group(1) if m_tag else ""
                        m_n = re.search(r'in-(\\d+)', inb_tag)
                        nid_found = int(m_n.group(1)) if m_n else None

                        if cid:
                            if m_conn_from:
                                ip = m_conn_from.group(1).strip()
                                port = m_conn_from.group(2).strip()
                                if cid in _agent_sb_pending_sessions and "uid" in _agent_sb_pending_sessions[cid]:
                                    uid_f = _agent_sb_pending_sessions.pop(cid)["uid"]
                                    _agent_sb_ip_to_user[ip] = uid_f
                                    _agent_sb_ipport_to_user[f"{ip}:{port}"] = uid_f
                                    _agent_last_sb_user = uid_f
                                    if uid_f is not None and ip not in ("127.0.0.1", "::1"):
                                        if uid_f not in _agent_user_active_ips:
                                            _agent_user_active_ips[uid_f] = {}
                                        _agent_user_active_ips[uid_f][ip] = now_ts
                                    if nid_found:
                                        _agent_last_sb_node = nid_found
                                        _agent_sb_ipport_to_node[f"{ip}:{port}"] = nid_found
                                else:
                                    _agent_sb_pending_sessions[cid] = {"ip": ip, "port": port, "nid": nid_found, "time": time.time()}
                            elif m_user:
                                u_str = m_user.group(1)
                                uid_f = 1 if u_str == "default" else int(u_str.split("_")[1])
                                if cid in _agent_sb_pending_sessions and "ip" in _agent_sb_pending_sessions[cid]:
                                    sess = _agent_sb_pending_sessions.pop(cid)
                                    ip = sess["ip"]
                                    port = sess["port"]
                                    if not nid_found:
                                        nid_found = sess.get("nid")
                                    _agent_sb_ip_to_user[ip] = uid_f
                                    _agent_sb_ipport_to_user[f"{ip}:{port}"] = uid_f
                                    _agent_last_sb_user = uid_f
                                    if uid_f is not None and ip not in ("127.0.0.1", "::1"):
                                        if uid_f not in _agent_user_active_ips:
                                            _agent_user_active_ips[uid_f] = {}
                                        _agent_user_active_ips[uid_f][ip] = now_ts
                                    if nid_found:
                                        _agent_last_sb_node = nid_found
                                        _agent_sb_ipport_to_node[f"{ip}:{port}"] = nid_found
                                else:
                                    _agent_sb_pending_sessions[cid] = {"uid": uid_f, "nid": nid_found, "time": time.time()}
                                    _agent_last_sb_user = uid_f
                                    if nid_found:
                                        _agent_last_sb_node = nid_found
                        else:
                            m_ip = re.search(r'\\[([\\d\\.:a-fA-F]+):(\\d+)\\s*->', line)
                            m_u = re.search(r'user:\\s*([^\\s\\)]+)', line)
                            if m_ip and m_u:
                                ip = m_ip.group(1).strip()
                                port = m_ip.group(2).strip()
                                u_str = m_u.group(1).strip()
                                uid_f = 1 if u_str == "default" else (int(u_str.split("_")[1]) if u_str.startswith("user_") else 1)
                                _agent_sb_ip_to_user[ip] = uid_f
                                _agent_sb_ipport_to_user[f"{ip}:{port}"] = uid_f
                                _agent_last_sb_user = uid_f
                                if uid_f is not None and ip not in ("127.0.0.1", "::1"):
                                    if uid_f not in _agent_user_active_ips:
                                        _agent_user_active_ips[uid_f] = {}
                                    _agent_user_active_ips[uid_f][ip] = now_ts

                    _agent_sb_log_offset = f.tell()
                    for c_k in list(_agent_sb_pending_sessions.keys()):
                        if time.time() - _agent_sb_pending_sessions[c_k].get("time", 0) > 60:
                            _agent_sb_pending_sessions.pop(c_k, None)
            except Exception:
                pass

        try:
            req_sb = urllib.request.Request("http://127.0.0.1:9095/connections")
            with urllib.request.urlopen(req_sb, timeout=3) as resp_sb:
                sb_data = json.loads(resp_sb.read().decode("utf-8"))
                curr_sb_up = int(sb_data.get("uploadTotal", 0))
                curr_sb_down = int(sb_data.get("downloadTotal", 0))
                if not _agent_sb_initialized:
                    _agent_sb_initialized = True
                    _last_agent_sb_up = curr_sb_up
                    _last_agent_sb_down = curr_sb_down
                    delta_sb_up = 0
                    delta_sb_down = 0
                else:
                    if curr_sb_up < _last_agent_sb_up or curr_sb_down < _last_agent_sb_down:
                        delta_sb_up = curr_sb_up
                        delta_sb_down = curr_sb_down
                        _agent_sb_conns.clear()
                    else:
                        delta_sb_up = max(0, curr_sb_up - _last_agent_sb_up)
                        delta_sb_down = max(0, curr_sb_down - _last_agent_sb_down)
                    _last_agent_sb_up = curr_sb_up
                    _last_agent_sb_down = curr_sb_down

                if not _agent_last_sb_node and singbox_inbounds:
                    for inb in singbox_inbounds:
                        m = re.search(r'in-(\\d+)', inb.get("tag", ""))
                        if m:
                            _agent_last_sb_node = int(m.group(1))
                            break

                conns = sb_data.get("connections", [])
                curr_conn_ids = set()
                sum_active_up = 0
                sum_active_down = 0

                active_uids = set()
                for c in conns:
                    cid = c.get("id")
                    if not cid:
                        continue
                    curr_conn_ids.add(cid)
                    c_up = int(c.get("upload", 0))
                    c_down = int(c.get("download", 0))
                    meta = c.get("metadata", {})
                    inb_type = meta.get("type", "")
                    src_ip = meta.get("sourceIP", "")
                    src_port = str(meta.get("sourcePort", ""))
                    m_nid = re.search(r'in-(\\d+)', inb_type)
                    nid = int(m_nid.group(1)) if m_nid else (_agent_sb_ipport_to_node.get(f"{src_ip}:{src_port}") or _agent_last_sb_node)
                    if nid:
                        _agent_last_sb_node = nid

                    uid = _agent_sb_ipport_to_user.get(f"{src_ip}:{src_port}") or _agent_sb_ip_to_user.get(src_ip) or _agent_last_sb_user or 1
                    _agent_last_sb_user = uid
                    if uid:
                        active_uids.add(uid)

                    prev_up, prev_down, _, _ = _agent_sb_conns.get(cid, (0, 0, uid, nid))
                    d_up = max(0, c_up - prev_up)
                    d_down = max(0, c_down - prev_down)
                    _agent_sb_conns[cid] = (c_up, c_down, uid, nid)

                    if d_up > 0 or d_down > 0:
                        sum_active_up += d_up
                        sum_active_down += d_down
                        if uid not in user_traffic:
                            user_traffic[uid] = {"user_id": uid, "upload": 0, "download": 0}
                        user_traffic[uid]["upload"] += d_up
                        user_traffic[uid]["download"] += d_down
                        if nid:
                            if nid not in node_traffic:
                                node_traffic[nid] = {"node_id": nid, "upload": 0, "download": 0}
                            node_traffic[nid]["upload"] += d_up
                            node_traffic[nid]["download"] += d_down

                for closed_id in set(_agent_sb_conns.keys()) - curr_conn_ids:
                    _agent_sb_conns.pop(closed_id, None)

                rem_up = max(0, delta_sb_up - sum_active_up)
                rem_down = max(0, delta_sb_down - sum_active_down)
                if rem_up > 0 or rem_down > 0:
                    uid = _agent_last_sb_user or 1
                    nid = _agent_last_sb_node
                    if not nid and singbox_inbounds:
                        for inb in singbox_inbounds:
                            m = re.search(r'in-(\\d+)', inb.get("tag", ""))
                            if m:
                                nid = int(m.group(1))
                                _agent_last_sb_node = nid
                                break
                    if uid not in user_traffic:
                        user_traffic[uid] = {"user_id": uid, "upload": 0, "download": 0}
                    user_traffic[uid]["upload"] += rem_up
                    user_traffic[uid]["download"] += rem_down
                    if nid:
                        if nid not in node_traffic:
                            node_traffic[nid] = {"node_id": nid, "upload": 0, "download": 0}
                        node_traffic[nid]["upload"] += rem_up
                        node_traffic[nid]["download"] += rem_down
        except Exception as ex:
            diag["sb_conns_err"] = str(ex)

    if user_traffic:
        user_stats = list(user_traffic.values())
        active_uids.update(user_traffic.keys())
    if node_traffic:
        node_stats = list(node_traffic.values())

    diag["sb_log_tail"] = run_cmd(["tail", "-n", "30", "/var/log/sing-box/access.log"])
    diag["sb_conns"] = run_cmd(["curl", "-s", "http://127.0.0.1:9095/connections"])
    diag["sb_cfg"] = run_cmd(["cat", "/etc/sing-box/config.json"])
    diag["agent_journal"] = run_cmd(["journalctl", "-u", "proxy-agent", "-n", "25", "--no-pager"])
    xray_log = json.dumps(diag)

    post_url = f"{server}/api/proxy/agent-sync"
    payload = json.dumps({
        "token": token,
        "status": status,
        "version": version,
        "ipv4": get_agent_public_ip(),
        "ports": target_ports,
        "listening_ports": listening_ports,
        "xray_installed": 1 if xr_installed else 0,
        "xray_running": 1 if xr_running else 0,
        "singbox_installed": 1 if sb_installed else 0,
        "singbox_running": 1 if sb_running else 0,
        "singbox_version": sb_version,
        "realm_installed": 1 if realm_installed else 0,
        "realm_running": 1 if realm_running else 0,
        "realm_version": "Realm 2.9.6" if realm_installed else "",
        "log": xray_log,
        "user_stats": user_stats,
        "node_stats": node_stats,
        "active_users": list(active_uids)
    }).encode("utf-8")
    
    post_req = urllib.request.Request(
        post_url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "ProxyAgent/1.0"}
    )
    with urllib.request.urlopen(post_req, timeout=10, context=ctx) as resp:
        pass

    # Clean up inactive client IPs (> 180s)
    for u_id in list(_agent_user_active_ips.keys()):
        _agent_user_active_ips[u_id] = {cip: t for cip, t in _agent_user_active_ips[u_id].items() if now_ts - t < 180}
        if not _agent_user_active_ips[u_id]:
            _agent_user_active_ips.pop(u_id, None)

    # Apply Traffic Control (Kernel TC / HTB / cls_flower)
    global _agent_tc_manager
    if _agent_tc_manager is None:
        _agent_tc_manager = TCManager()

    user_speed_limits = data.get("user_speed_limits") or {}
    node_speed_limits = data.get("node_speed_limits") or {}

    desired_nodes = {}
    for nid_str, info in node_speed_limits.items():
        try:
            desired_nodes[int(nid_str)] = { "port": int(info["port"]), "mbps": int(info["mbps"]) }
        except Exception:
            pass

    desired_users = {}
    for uid_str, mbps_val in user_speed_limits.items():
        try:
            uid_val = int(uid_str)
            mbps_val = int(mbps_val)
            if mbps_val > 0:
                user_ips = _agent_user_active_ips.get(uid_val, {})
                active_ips = {cip for cip, t in user_ips.items() if now_ts - t < 180 and cip not in ("127.0.0.1", "::1")}
                if active_ips:
                    desired_users[uid_val] = { "mbps": mbps_val, "ips": active_ips }
        except Exception:
            pass

    try:
        _agent_tc_manager.sync(desired_nodes, desired_users)
    except Exception:
        pass

    return last_hash

def main():
    server, token = get_params()
    if not server or not token:
        print("Missing --server or --token", flush=True)
        sys.exit(1)

    print(f"Proxy agent started. Hub: {server}, Token: {token[:8]}...", flush=True)
    last_hash = read_saved_hash()
    while True:
        try:
            # 动态检测 /opt/monitor/agent.env 是否切换了面板（例如从面板A重新对接到面板B）
            cur_srv, cur_tok = read_env_file()
            if cur_srv and cur_tok and (cur_srv != server or cur_tok != token):
                print(f"[!] 检测到主控端环境发生变更: {server} -> {cur_srv}，立即重绑新主控端并重新拉取生效节点！", flush=True)
                server, token = cur_srv, cur_tok
                last_hash = None  # 强制刷新配置并推送到新面板

            last_hash = sync_step(server, token, last_hash)
        except Exception as e:
            print(f"[{time.strftime('%X')}] 代理同步异常: {e}", flush=True)
        time.sleep(5)

if __name__ == "__main__":
    main()
"""

