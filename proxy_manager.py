import gzip
import json
import os
import random
import re
import secrets
import socket
import sqlite3
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse
import license_guard

DB_PATH = "/opt/monitor/data/monitor.db"
XRAY_BIN = "/usr/local/bin/xray"
XRAY_CONFIG = "/etc/xray/config.json"
SINGBOX_BIN = "/usr/local/bin/sing-box"
SINGBOX_CONFIG = "/etc/sing-box/config.json"
SINGBOX_CERT = "/etc/sing-box/cert.pem"
SINGBOX_KEY = "/etc/sing-box/key.pem"
REALM_BIN = "/usr/local/bin/realm"
REALM_CONFIG = "/etc/realm/config.json"
import sys
PORT = int(os.environ.get("PROXY_MANAGER_PORT", 28090))
for _i, _arg in enumerate(sys.argv):
    if _arg == "--port" and _i + 1 < len(sys.argv):
        try:
            PORT = int(sys.argv[_i + 1])
        except ValueError:
            pass
LOCAL_HOSTS = {"189.24.108.25", "127.0.0.1", "localhost", "test.yohoo.xyz", "tz.yohoo.xyz", ""}

def get_request_base_url(headers=None):
    if headers:
        host = headers.get("X-Forwarded-Host") or headers.get("Host") or ""
        host = host.split(",")[0].strip()
        proto = headers.get("X-Forwarded-Proto") or ("https" if headers.get("X-Forwarded-Ssl") == "on" else "http")
        proto = proto.split(",")[0].strip()
        if host:
            return f"{proto}://{host}"
    local_ip = get_local_ip() or "127.0.0.1"
    return f"http://{local_ip}"

def get_local_ip(family=socket.AF_INET):
    try:
        target = ("8.8.8.8", 80) if family == socket.AF_INET else ("2001:4860:4860::8888", 80)
        s = socket.socket(family, socket.SOCK_DGRAM)
        s.settimeout(1.0)
        s.connect(target)
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return ""

def format_host_for_uri(host):
    if not host:
        return "127.0.0.1"
    host_str = str(host).strip()
    if ":" in host_str and not host_str.startswith("["):
        return f"[{host_str}]"
    return host_str


PROXY_AGENT_SH = """#!/usr/bin/env bash
set -e

# ==============================================================================
# Monitor 探针节点一键代理服务部署脚本 (Xray-Core + Sing-box + Realm + Proxy Agent)
# ==============================================================================

HUB_SERVER=""
HUB_TOKEN=""
INSTALL_XRAY=0
INSTALL_SINGBOX=0
INSTALL_REALM=0
EXPLICIT_CORES=0

while [ $# -gt 0 ]; do
  case "$1" in
    --server) HUB_SERVER="$2"; shift 2 ;;
    --token) HUB_TOKEN="$2"; shift 2 ;;
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

# 自动从本机已有的 monitor-agent 探针服务中探测主控端地址与 Token
if [ -z "$HUB_SERVER" ] || [ -z "$HUB_TOKEN" ]; then
  if [ -f /opt/monitor/agent.env ]; then
    echo "[+] 检测到 /opt/monitor/agent.env 探针配置，正在自动提取环境参数..."
    ENV_SERVER=$(grep -E '^MONITOR_SERVER=' /opt/monitor/agent.env 2>/dev/null | cut -d'=' -f2- | tr -d '"' | tr -d "'" || true)
    ENV_TOKEN=$(grep -E '^MONITOR_TOKEN=' /opt/monitor/agent.env 2>/dev/null | cut -d'=' -f2- | tr -d '"' | tr -d "'" || true)
    [ -n "$ENV_SERVER" ] && HUB_SERVER="$ENV_SERVER"
    [ -n "$ENV_TOKEN" ] && HUB_TOKEN="$ENV_TOKEN"
  fi
  if [ -z "$HUB_SERVER" ] || [ -z "$HUB_TOKEN" ]; then
    if [ -f /etc/systemd/system/monitor-agent.service ]; then
      echo "[+] 检测到 /etc/systemd/system/monitor-agent.service，正在自动解析参数..."
      EXEC_LINE=$(grep 'ExecStart=' /etc/systemd/system/monitor-agent.service 2>/dev/null || true)
      if [ -z "$HUB_SERVER" ]; then
        HUB_SERVER=$(echo "$EXEC_LINE" | grep -oE '--server [^ ]+' | awk '{print $2}' || true)
      fi
      if [ -z "$HUB_TOKEN" ]; then
        HUB_TOKEN=$(echo "$EXEC_LINE" | grep -oE '--token [^ ]+' | awk '{print $2}' || true)
      fi
    fi
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

# 1. 安装基础依赖 python3, curl, unzip
if ! command -v python3 >/dev/null 2>&1 || ! command -v curl >/dev/null 2>&1; then
  echo "[+] 正在安装系统基础依赖..."
  if command -v apt-get >/dev/null 2>&1; then
    apt-get update -y && apt-get install -y python3 curl unzip iptables || true
  elif command -v yum >/dev/null 2>&1; then
    yum install -y python3 curl unzip iptables || true
  elif command -v apk >/dev/null 2>&1; then
    apk add python3 curl unzip iptables || true
  fi
fi

ARCH=$(uname -m)

# 2. 按需安装 Xray 核心 (解压包括 geoip.dat 与 geosite.dat)
if [ "$INSTALL_XRAY" = "1" ]; then
  mkdir -p /etc/xray /var/log/xray /opt/monitor /usr/local/share/xray /usr/local/etc/xray
  XRAY_ARCH="64"
  if [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
    XRAY_ARCH="arm64-v8a"
  fi

  TMP_DIR="/tmp/xray_install"
  rm -rf "$TMP_DIR"
  mkdir -p "$TMP_DIR"
  TMP_ZIP="/tmp/xray.zip"

  echo "[+] 正在下载并配置最新版 Xray-core..."
  curl -fsSL "$HUB_SERVER/Xray-linux-${XRAY_ARCH}.zip" -o "$TMP_ZIP" 2>/dev/null || \
  curl -fsSL "https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-${XRAY_ARCH}.zip" -o "$TMP_ZIP" || \
  curl -fsSL "https://ghproxy.net/https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-${XRAY_ARCH}.zip" -o "$TMP_ZIP"

  if command -v unzip >/dev/null 2>&1; then
    unzip -o "$TMP_ZIP" -d "$TMP_DIR/"
  else
    python3 -c "import zipfile; zipfile.ZipFile('$TMP_ZIP').extractall('$TMP_DIR/')"
  fi

  install -m 0755 "$TMP_DIR/xray" /usr/local/bin/xray
  [ -f "$TMP_DIR/geoip.dat" ] && cp -f "$TMP_DIR/geoip.dat" /usr/local/share/xray/
  [ -f "$TMP_DIR/geosite.dat" ] && cp -f "$TMP_DIR/geosite.dat" /usr/local/share/xray/
  rm -rf "$TMP_DIR" "$TMP_ZIP"
  echo "[+] Xray 核心已就绪: $(/usr/local/bin/xray version | head -n 1)"

  # 规范化 Xray 系统服务单元
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

  if [ ! -f /etc/xray/config.json ]; then
    cat > /etc/xray/config.json << 'EOF'
{
  "log": { "loglevel": "warning" },
  "inbounds": [
    { "tag": "dummy", "listen": "127.0.0.1", "port": 39999, "protocol": "socks", "settings": { "auth": "noauth" } }
  ],
  "outbounds": [
    { "protocol": "freedom", "tag": "direct", "settings": { "domainStrategy": "UseIPv4" } },
    { "protocol": "blackhole", "tag": "block" }
  ]
}
EOF
  fi
  ln -sf /etc/xray/config.json /usr/local/etc/xray/config.json

  systemctl daemon-reload
  systemctl enable xray
  systemctl restart xray
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
  TMP_SB_DIR="/tmp/singbox_install"
  rm -rf "$TMP_SB_DIR"
  mkdir -p "$TMP_SB_DIR"
  TMP_SB_TAR="$TMP_SB_DIR/sing-box.tar.gz"
  echo "[+] 正在下载并配置最新版 Sing-box 核心..."
  LATEST_SB_TAG=$(curl -sSL "https://api.github.com/repos/SagerNet/sing-box/releases/latest" 2>/dev/null | grep '"tag_name":' | head -n 1 | cut -d'"' -f4 || echo "v1.14.1")
  SB_VER="${LATEST_SB_TAG#v}"
  [ -z "$SB_VER" ] && SB_VER="1.14.1"

  curl -fsSL "$HUB_SERVER/sing-box-linux-${SARCH}.tar.gz" -o "$TMP_SB_TAR" 2>/dev/null || \
  curl -fsSL "https://github.com/SagerNet/sing-box/releases/download/v${SB_VER}/sing-box-${SB_VER}-linux-${SARCH}.tar.gz" -o "$TMP_SB_TAR" || \
  curl -fsSL "https://ghproxy.net/https://github.com/SagerNet/sing-box/releases/download/v${SB_VER}/sing-box-${SB_VER}-linux-${SARCH}.tar.gz" -o "$TMP_SB_TAR" || true

  if [ -f "$TMP_SB_TAR" ]; then
    tar -xzf "$TMP_SB_TAR" -C "$TMP_SB_DIR/"
    SB_BIN=$(find "$TMP_SB_DIR" -name "sing-box" -type f | head -n 1)
    if [ -n "$SB_BIN" ]; then
      install -m 0755 "$SB_BIN" /usr/local/bin/sing-box
      echo "[+] Sing-box 核心已就绪: $(/usr/local/bin/sing-box version | head -n 1)"
    fi
  fi
  rm -rf "$TMP_SB_DIR"

  if [ ! -f /etc/sing-box/cert.pem ] || [ ! -f /etc/sing-box/key.pem ]; then
    openssl req -x509 -nodes -newkey ec:<(openssl ecparam -name prime256v1) \
      -keyout /etc/sing-box/key.pem -out /etc/sing-box/cert.pem \
      -subj "/CN=bing.com" -days 36500 \
      -addext "subjectAltName=DNS:bing.com" 2>/dev/null || true
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

  systemctl daemon-reload
  systemctl enable sing-box
  systemctl restart sing-box
else
  echo "[*] 根据选项：跳过 Sing-box 核心安装"
fi

# 4. 按需安装并配置 Realm 端口转发核心 (TCP/UDP 高速端口转发)
if [ "$INSTALL_REALM" = "1" ]; then
  mkdir -p /etc/realm /opt/monitor
  R_ARCH="x86_64"
  if [ "$ARCH" = "aarch64" ] || [ "$ARCH" = "arm64" ]; then
    R_ARCH="aarch64"
  fi
  TMP_REALM_DIR="/tmp/realm_inst"
  rm -rf "$TMP_REALM_DIR"
  mkdir -p "$TMP_REALM_DIR"
  TMP_REALM_TAR="/tmp/realm.tar.gz"

  echo "[+] 正在下载并配置最新版 Realm 端口转发核心..."
  curl -fsSL "$HUB_SERVER/realm-${R_ARCH}-unknown-linux-musl.tar.gz" -o "$TMP_REALM_TAR" 2>/dev/null || \
  curl -fsSL "https://github.com/zhboner/realm/releases/latest/download/realm-${R_ARCH}-unknown-linux-musl.tar.gz" -o "$TMP_REALM_TAR" || \
  curl -fsSL "https://ghproxy.net/https://github.com/zhboner/realm/releases/latest/download/realm-${R_ARCH}-unknown-linux-musl.tar.gz" -o "$TMP_REALM_TAR" || true

  if [ -f "$TMP_REALM_TAR" ]; then
    tar -xzf "$TMP_REALM_TAR" -C "$TMP_REALM_DIR/" || true
    REALM_BIN_F=$(find "$TMP_REALM_DIR" -name "realm" -type f | head -n 1)
    if [ -n "$REALM_BIN_F" ]; then
      install -m 0755 "$REALM_BIN_F" /usr/local/bin/realm
      echo "[+] Realm 核心已就绪: $(/usr/local/bin/realm --version 2>/dev/null || echo 'Realm')"
    fi
  fi
  rm -rf "$TMP_REALM_DIR" "$TMP_REALM_TAR"

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

  systemctl daemon-reload
  systemctl enable realm
  systemctl restart realm
else
  echo "[*] 根据选项：跳过 Realm 端口转发核心安装"
fi

# 5. 下载远端代理守护进程脚本
echo "[+] 正在拉取代理同步守护程序..."
curl -fsSL "$HUB_SERVER/api/proxy/agent-client-script" -o /opt/monitor/proxy_agent.py
chmod +x /opt/monitor/proxy_agent.py

# 6. 配置 proxy-agent.service
cat > /etc/systemd/system/proxy-agent.service << EOF
[Unit]
Description=Monitor Proxy Agent Daemon
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/python3 -u /opt/monitor/proxy_agent.py --server $HUB_SERVER --token $HUB_TOKEN
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable proxy-agent.service
systemctl restart proxy-agent.service

echo ""
echo "=================================================="
echo "  [OK] 代理管理服务部署成功！"
echo "  已成功连接到主控端: $HUB_SERVER"
echo "  同步守护进程已启动: proxy-agent.service"
[ "$INSTALL_XRAY" = "1" ] && echo "  - Xray-Core: 已安装并运行"
[ "$INSTALL_SINGBOX" = "1" ] && echo "  - Sing-box: 已安装并运行"
[ "$INSTALL_REALM" = "1" ] && echo "  - Realm: 已安装并运行"
echo "  后续在管理后台为此服务器创建的所有节点，将自动实时生效！"
echo "=================================================="
"""

PROXY_AGENT_PY = """import hashlib
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request

XRAY_BIN = "/usr/local/bin/xray"
XRAY_CONFIG = "/etc/xray/config.json"
SINGBOX_BIN = "/usr/local/bin/sing-box"
SINGBOX_CONFIG = "/etc/sing-box/config.json"
REALM_BIN = "/usr/local/bin/realm"
REALM_CONFIG = "/etc/realm/config.json"

def get_params():
    server = os.environ.get("HUB_SERVER", "")
    token = os.environ.get("HUB_TOKEN", "")
    for i in range(len(sys.argv)):
        if sys.argv[i] == "--server" and i + 1 < len(sys.argv):
            server = sys.argv[i + 1]
        elif sys.argv[i] == "--token" and i + 1 < len(sys.argv):
            token = sys.argv[i + 1]
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
        s.settimeout(0.5)
        res = s.connect_ex(('127.0.0.1', port))
        s.close()
        return res == 0
    except Exception:
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
        for u in urls:
            try:
                req = urllib.request.Request(u, headers={"User-Agent": "curl/7.68.0"})
                with urllib.request.urlopen(req, timeout=30) as resp:
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

        svc = "\\n".join([
            "[Unit]",
            "Description=sing-box Service",
            "After=network.target nss-lookup.target",
            "",
            "[Service]",
            "Type=simple",
            "User=root",
            "WorkingDirectory=/etc/sing-box",
            "ExecStart=/usr/local/bin/sing-box run -c /etc/sing-box/config.json",
            "Restart=always",
            "RestartSec=3",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            ""
        ])
        with open("/etc/systemd/system/sing-box.service", "w") as f:
            f.write(svc)
        subprocess.run(["systemctl", "daemon-reload"], capture_output=True)
        subprocess.run(["systemctl", "enable", "sing-box"], capture_output=True)
        print("[+] 探针节点 Sing-box 核心自动部署就绪", flush=True)
        return True
    except Exception as e:
        print(f"[-] 自动安装 sing-box 失败: {e}", flush=True)
        return False

def sync_step(server, token, last_hash):
    # 1. 拉取节点配置
    url = f"{server}/api/proxy/agent-sync?token={urllib.parse.quote(token)}"
    req = urllib.request.Request(url, headers={"User-Agent": "ProxyAgent/1.0"})
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    if not data.get("ok"):
        return last_hash

    inbounds = data.get("inbounds", [])
    singbox_inbounds = data.get("singbox_inbounds", [])
    config_repr = json.dumps({"xray": inbounds, "singbox": singbox_inbounds}, sort_keys=True)
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
                { "protocol": "freedom", "tag": "direct", "settings": { "domainStrategy": "UseIPv4" } },
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

        test_res = subprocess.run([XRAY_BIN, "run", "-test", "-config", tmp_cfg, "-format", "json"], capture_output=True, text=True)
        if test_res.returncode == 0:
            os.replace(tmp_cfg, XRAY_CONFIG)
            try:
                os.makedirs("/usr/local/etc/xray", exist_ok=True)
                shutil.copyfile(XRAY_CONFIG, "/usr/local/etc/xray/config.json")
            except Exception:
                pass
            subprocess.run(["systemctl", "daemon-reload"], capture_output=True)
            subprocess.run(["systemctl", "restart", "xray"], capture_output=True)
            time.sleep(1)
            print(f"[{time.strftime('%X')}] Xray 配置生效并重启成功", flush=True)
        else:
            err_msg = (test_res.stdout + " " + test_res.stderr).strip()
            print(f"[{time.strftime('%X')}] Xray 配置校验失败: {err_msg}", flush=True)

        if singbox_inbounds and not os.path.exists(SINGBOX_BIN):
            ensure_singbox_installed(server)

        if os.path.exists(SINGBOX_BIN) and singbox_inbounds:
            sb_ports = [inb.get("listen_port") for inb in singbox_inbounds if inb.get("listen_port")]
            allow_ports(sb_ports)
            os.makedirs("/var/log/sing-box", exist_ok=True)
            sb_config = {
                "log": { "level": "warn", "output": "/var/log/sing-box/access.log" },
                "inbounds": singbox_inbounds,
                "outbounds": [{ "type": "direct", "tag": "direct" }, { "type": "block", "tag": "block" }]
            }
            tmp_sb = "/etc/sing-box/config.tmp.json"
            os.makedirs("/etc/sing-box", exist_ok=True)
            with open(tmp_sb, "w", encoding="utf-8") as f:
                json.dump(sb_config, f, indent=2)
            sb_chk = subprocess.run([SINGBOX_BIN, "check", "-c", tmp_sb], capture_output=True, text=True)
            if sb_chk.returncode == 0:
                os.replace(tmp_sb, SINGBOX_CONFIG)
                subprocess.run(["systemctl", "restart", "sing-box"], capture_output=True)
                print(f"[{time.strftime('%X')}] Sing-box 配置生效并重启成功", flush=True)
            else:
                print(f"[{time.strftime('%X')}] Sing-box 配置校验失败: {sb_chk.stderr}", flush=True)

        last_hash = curr_hash

    # 2. 状态检测与端口监听真实检测
    is_active = subprocess.run(["systemctl", "is-active", "--quiet", "xray"]).returncode == 0
    version = "unknown"
    try:
        ver_res = subprocess.run([XRAY_BIN, "version"], capture_output=True, text=True)
        if ver_res.stdout:
            version = ver_res.stdout.splitlines()[0]
    except Exception:
        pass

    target_ports = [inb.get("port") for inb in inbounds if inb.get("port")]
    listening_ports = [p for p in target_ports if check_port_listening(p)]
    
    # 自动自愈：若有目标端口未正常监听，强制刷新防火墙规则并重启 Xray
    if target_ports and len(listening_ports) < len(target_ports):
        allow_ports(target_ports)
        subprocess.run(["systemctl", "daemon-reload"], capture_output=True)
        subprocess.run(["systemctl", "restart", "xray"], capture_output=True)
        time.sleep(1)
        listening_ports = [p for p in target_ports if check_port_listening(p)]
        is_active = subprocess.run(["systemctl", "is-active", "--quiet", "xray"]).returncode == 0

    status = "running" if (is_active and (len(listening_ports) == len(target_ports) or not target_ports)) else "stopped"
    if not is_active:
        status = "stopped"
    elif target_ports and not listening_ports:
        status = "port_error"

    # 自动无缝升级：若主控端发布了更新的代理同步程序，自动保存并重启
    try:
        remote_sc_url = f"{server}/api/proxy/agent-client-script"
        req_sc = urllib.request.Request(remote_sc_url, headers={"User-Agent": "ProxyAgent/1.0"})
        with urllib.request.urlopen(req_sc, timeout=5) as sc_resp:
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
                subprocess.run(["systemctl", "restart", "proxy-agent"], capture_output=True)
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
        sb_running = subprocess.run(["systemctl", "is-active", "--quiet", "sing-box"]).returncode == 0
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
        realm_running = subprocess.run(["systemctl", "is-active", "--quiet", "realm"]).returncode == 0

    user_stats = []
    if xr_running:
        try:
            res = subprocess.run(
                [XRAY_BIN, "api", "statsquery", "--server=127.0.0.1:10085", "-reset=true"],
                capture_output=True, text=True, timeout=5
            )
            if res.returncode == 0 and res.stdout:
                st_data = json.loads(res.stdout)
                raw_stats = st_data.get("stat") or []
                user_traffic = {}
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
                if user_traffic:
                    user_stats = list(user_traffic.values())
        except Exception:
            pass

    post_url = f"{server}/api/proxy/agent-sync"
    payload = json.dumps({
        "token": token,
        "status": status,
        "version": version,
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
        "user_stats": user_stats
    }).encode("utf-8")
    
    post_req = urllib.request.Request(
        post_url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "ProxyAgent/1.0"}
    )
    with urllib.request.urlopen(post_req, timeout=10) as resp:
        pass

    return last_hash

def main():
    server, token = get_params()
    if not server or not token:
        print("Missing --server or --token", flush=True)
        sys.exit(1)

    print(f"Proxy agent started. Hub: {server}, Token: {token[:8]}...", flush=True)
    last_hash = None
    while True:
        try:
            last_hash = sync_step(server, token, last_hash)
        except Exception as e:
            print(f"[{time.strftime('%X')}] 代理同步异常: {e}", flush=True)
        time.sleep(5)

if __name__ == "__main__":
    main()
"""

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    with conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS proxy_node (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            server_id INTEGER DEFAULT 0,
            server_name TEXT DEFAULT '本机',
            server_host TEXT DEFAULT '189.24.108.25',
            name TEXT NOT NULL,
            protocol TEXT NOT NULL,
            port INTEGER NOT NULL,
            uuid TEXT NOT NULL,
            flow TEXT DEFAULT 'xtls-rprx-vision',
            sni TEXT DEFAULT 'www.apple.com',
            dest TEXT DEFAULT 'www.apple.com:443',
            public_key TEXT,
            private_key TEXT,
            short_id TEXT,
            ws_path TEXT DEFAULT '/ws-proxy',
            enabled INTEGER DEFAULT 1,
            created_at INTEGER NOT NULL
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS node_proxy_status (
            node_id INTEGER PRIMARY KEY,
            status TEXT,
            version TEXT,
            ports TEXT,
            listening_ports TEXT,
            log TEXT,
            last_seen INTEGER
        )
        """)
        # Schema migration
        try:
            conn.execute("ALTER TABLE node_proxy_status ADD COLUMN listening_ports TEXT")
        except Exception:
            pass
        try:
            conn.execute("ALTER TABLE node_proxy_status ADD COLUMN log TEXT")
        except Exception:
            pass
        # Multi-protocol support columns for proxy_node
        for col_name, col_type in [
            ("method", "TEXT DEFAULT '2022-blake3-aes-128-gcm'"),
            ("password", "TEXT DEFAULT ''"),
            ("username", "TEXT DEFAULT ''"),
            ("extra_json", "TEXT DEFAULT ''"),
            ("is_relay", "INTEGER DEFAULT 0"),
            ("relay_server_id", "INTEGER DEFAULT 0"),
            ("relay_port", "INTEGER DEFAULT 0"),
            ("remote_host", "TEXT DEFAULT ''"),
            ("remote_port", "INTEGER DEFAULT 0"),
            ("target_node_id", "INTEGER DEFAULT 0")
        ]:
            try:
                conn.execute(f"ALTER TABLE proxy_node ADD COLUMN {col_name} {col_type}")
            except Exception:
                pass

        # Multi-core tracking columns for node_proxy_status
        for col_name, col_type in [
            ("xray_installed", "INTEGER DEFAULT 0"),
            ("xray_running", "INTEGER DEFAULT 0"),
            ("singbox_installed", "INTEGER DEFAULT 0"),
            ("singbox_running", "INTEGER DEFAULT 0"),
            ("singbox_version", "TEXT DEFAULT ''"),
            ("realm_installed", "INTEGER DEFAULT 0"),
            ("realm_running", "INTEGER DEFAULT 0"),
            ("realm_version", "TEXT DEFAULT ''")
        ]:
            try:
                conn.execute(f"ALTER TABLE node_proxy_status ADD COLUMN {col_name} {col_type}")
            except Exception:
                pass
        conn.execute("""
        CREATE TABLE IF NOT EXISTS node_unlock_status (
            node_id INTEGER PRIMARY KEY,
            netflix_ok INTEGER DEFAULT 0,
            netflix_msg TEXT DEFAULT '',
            chatgpt_ok INTEGER DEFAULT 0,
            chatgpt_msg TEXT DEFAULT '',
            youtube_ok INTEGER DEFAULT 0,
            youtube_msg TEXT DEFAULT '',
            disney_ok INTEGER DEFAULT 0,
            disney_msg TEXT DEFAULT '',
            region TEXT DEFAULT '',
            data_json TEXT DEFAULT '',
            updated_at INTEGER DEFAULT 0
        )
        """)
        try:
            conn.execute("ALTER TABLE node_unlock_status ADD COLUMN data_json TEXT DEFAULT ''")
        except Exception:
            pass
        conn.execute("""
        CREATE TABLE IF NOT EXISTS setting (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """)
        # Check if sub_token exists in setting
        cur = conn.execute("SELECT value FROM setting WHERE key = 'proxy_sub_token'")
        tok_row = cur.fetchone()
        sub_tok = tok_row[0] if tok_row else secrets.token_hex(16)
        if not tok_row:
            conn.execute("INSERT OR REPLACE INTO setting (key, value) VALUES ('proxy_sub_token', ?)", (sub_tok,))

        # Multi-user & traffic accounting tables
        conn.execute("""
        CREATE TABLE IF NOT EXISTS proxy_user (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            sub_token TEXT UNIQUE NOT NULL,
            traffic_limit_bytes INTEGER DEFAULT 214748364800,
            upload_bytes INTEGER DEFAULT 0,
            download_bytes INTEGER DEFAULT 0,
            expires_at INTEGER DEFAULT 0,
            enabled INTEGER DEFAULT 1,
            is_admin INTEGER DEFAULT 0,
            created_at INTEGER NOT NULL,
            device_limit INTEGER DEFAULT 0
        )
        """)
        conn.execute("""
        CREATE TABLE IF NOT EXISTS proxy_session_user (
            token_hash TEXT PRIMARY KEY,
            user_id INTEGER NOT NULL,
            created_at INTEGER NOT NULL
        )
        """)

        # Migration: ensure device_limit exists
        try:
            conn.execute("ALTER TABLE proxy_user ADD COLUMN device_limit INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass

        # Migration: ensure theme_style exists
        try:
            conn.execute("ALTER TABLE proxy_user ADD COLUMN theme_style TEXT DEFAULT 'default'")
        except sqlite3.OperationalError:
            pass

        # Migration: ensure admin user exists in proxy_user
        cur_adm = conn.execute("SELECT id FROM proxy_user WHERE username = 'admin'")
        if not cur_adm.fetchone():
            adm_hash = hash_password("admin123")
            conn.execute("""
                INSERT INTO proxy_user (username, password_hash, sub_token, traffic_limit_bytes, upload_bytes, download_bytes, expires_at, enabled, is_admin, created_at, device_limit, theme_style)
                VALUES ('admin', ?, ?, 0, 0, 0, 0, 1, 1, ?, 0, 'default')
            """, (adm_hash, sub_tok, int(time.time())))
    conn.close()

def get_setting(key, default=""):
    try:
        conn = get_db()
        cur = conn.execute("SELECT value FROM setting WHERE key = ?", (key,))
        row = cur.fetchone()
        conn.close()
        return row["value"] if row else default
    except Exception:
        return default

def set_setting(key, value):
    try:
        conn = get_db()
        with conn:
            conn.execute("INSERT OR REPLACE INTO setting (key, value) VALUES (?, ?)", (key, str(value)))
        conn.close()
        return True
    except Exception as e:
        print(f"[set_setting error] {e}")
        return False

def generate_backup_gz():
    fd, tmp_db = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        dst = sqlite3.connect(tmp_db)
        src = sqlite3.connect(DB_PATH)
        try:
            src.backup(dst)
        finally:
            src.close()
            dst.close()

        with open(tmp_db, "rb") as f_in:
            raw_data = f_in.read()

        gz_data = gzip.compress(raw_data, compresslevel=6)
        raw_size = len(raw_data)
        gz_size = len(gz_data)
        return gz_data, raw_size, gz_size
    finally:
        if os.path.exists(tmp_db):
            try:
                os.remove(tmp_db)
            except Exception:
                pass

def send_telegram_document(token, chat_id, doc_bytes, filename, caption=""):
    boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"
    body = bytearray()

    # chat_id
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(f'Content-Disposition: form-data; name="chat_id"\r\n\r\n{chat_id}\r\n'.encode("utf-8"))

    # caption
    if caption:
        body.extend(f"--{boundary}\r\n".encode("utf-8"))
        body.extend(f'Content-Disposition: form-data; name="caption"\r\n\r\n{caption}\r\n'.encode("utf-8"))

    # document
    body.extend(f"--{boundary}\r\n".encode("utf-8"))
    body.extend(f'Content-Disposition: form-data; name="document"; filename="{filename}"\r\n'.encode("utf-8"))
    body.extend(b"Content-Type: application/gzip\r\n\r\n")
    body.extend(doc_bytes)
    body.extend(b"\r\n")

    body.extend(f"--{boundary}--\r\n".encode("utf-8"))

    url = f"https://api.telegram.org/bot{token}/sendDocument"
    req = urllib.request.Request(
        url,
        data=bytes(body),
        headers={
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "User-Agent": "ProxyProbe-Backup/1.0"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=35) as resp:
            res = json.loads(resp.read().decode("utf-8"))
            if not res.get("ok"):
                desc = res.get("description", "Telegram API returned error")
                raise RuntimeError(desc)
            return res
    except urllib.error.HTTPError as e:
        err_msg = str(e)
        try:
            err_data = json.loads(e.read().decode("utf-8"))
            err_msg = err_data.get("description", err_msg)
        except Exception:
            pass
        raise RuntimeError(f"Telegram API 报错: {err_msg}")
    except Exception as e:
        raise RuntimeError(f"发送失败: {e}")

def perform_telegram_backup(custom_chat_id=None):
    token = get_setting("notify_telegram_token", "").strip()
    chat_id = (custom_chat_id or get_setting("backup_tg_chat", "") or get_setting("notify_telegram_chat", "")).strip()

    if not token:
        raise ValueError("尚未配置 Telegram Bot Token，请在通知设置中填写并保存")
    if not chat_id:
        raise ValueError("尚未配置 Telegram Chat ID，请在通知设置中填写并保存")

    gz_data, raw_size, gz_size = generate_backup_gz()

    server_count = 0
    node_count = 0
    user_count = 0
    try:
        conn = get_db()
        cur = conn.execute("SELECT COUNT(*) FROM node")
        server_count = cur.fetchone()[0]
        cur = conn.execute("SELECT COUNT(*) FROM proxy_node")
        node_count = cur.fetchone()[0]
        cur = conn.execute("SELECT COUNT(*) FROM proxy_user")
        user_count = cur.fetchone()[0]
        conn.close()
    except Exception:
        pass

    site_name = get_setting("site_name", "ProxyProbe")
    ts_now = int(time.time())
    time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts_now))
    file_time_str = time.strftime("%Y%m%d_%H%M%S", time.localtime(ts_now))
    filename = f"monitor_backup_{file_time_str}.db.gz"

    caption = (
        f"📦 ProxyProbe 数据库自动备份\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🌐 站点: {site_name}\n"
        f"📅 时间: {time_str}\n"
        f"💾 大小: {gz_size / 1024:.1f} KB (原始: {raw_size / 1024:.1f} KB)\n"
        f"📊 资产: {server_count} 台服务器 · {node_count} 个代理节点 · {user_count} 位用户\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"💡 还原说明:\n"
        f"登录管理后台「数据」->「备份」-> 点击「导入备份」上传此 .db.gz 文件即可一键无缝还原；亦可解压为 monitor.db 覆盖 /opt/monitor/data/monitor.db。"
    )

    send_telegram_document(token, chat_id, gz_data, filename, caption)

    # 联动备份发卡中心卡密数据库 (若存在)
    lic_db_paths = [
        os.environ.get("LICENSE_CENTER_DB", ""),
        "/opt/license-center/license_center.db",
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "license-center", "license_center.db"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "license_center.db")
    ]
    lic_db = None
    for p in lic_db_paths:
        if p and os.path.exists(p):
            lic_db = p
            break

    if lic_db:
        try:
            fd, tmp_lic = tempfile.mkstemp(suffix=".db")
            os.close(fd)
            try:
                dst = sqlite3.connect(tmp_lic)
                src = sqlite3.connect(lic_db)
                try:
                    src.backup(dst)
                finally:
                    src.close()
                    dst.close()

                with open(tmp_lic, "rb") as f_in:
                    lic_raw = f_in.read()

                lic_gz = gzip.compress(lic_raw, compresslevel=6)
                lic_raw_size = len(lic_raw)
                lic_gz_size = len(lic_gz)

                # 统计卡密数量
                lic_conn = sqlite3.connect(tmp_lic)
                cur = lic_conn.execute("SELECT COUNT(*) FROM licenses")
                total_cards = cur.fetchone()[0]
                cur = lic_conn.execute("SELECT COUNT(*) FROM licenses WHERE status='active'")
                active_cards = cur.fetchone()[0]
                lic_conn.close()

                lic_filename = f"license_center_backup_{file_time_str}.db.gz"
                lic_caption = (
                    f"🎫 ProxyProbe 发号中心卡密数据库自动备份\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"🌐 站点: {site_name}\n"
                    f"📅 时间: {time_str}\n"
                    f"💾 大小: {lic_gz_size / 1024:.1f} KB (原始: {lic_raw_size / 1024:.1f} KB)\n"
                    f"📊 资产: 共 {total_cards} 张卡密（{active_cards} 张有效）\n"
                    f"━━━━━━━━━━━━━━━━━━━━\n"
                    f"💡 还原说明:\n"
                    f"解压后覆盖至 /opt/license-center/license_center.db 并重启发卡中心服务即可。"
                )
                send_telegram_document(token, chat_id, lic_gz, lic_filename, lic_caption)
            finally:
                if os.path.exists(tmp_lic):
                    try:
                        os.remove(tmp_lic)
                    except Exception:
                        pass
        except Exception as e:
            print(f"[Backup] 发卡中心卡密数据库推送 Telegram 异常: {e}")

    set_setting("backup_tg_last_time", str(ts_now))
    set_setting("backup_tg_last_status", f"成功 ({time_str}, {gz_size / 1024:.1f} KB)")
    return True, f"备份成功并已推送至 Telegram ({gz_size / 1024:.1f} KB)", gz_size

def telegram_backup_loop():
    while True:
        try:
            time.sleep(60)
            enabled = get_setting("backup_tg_enabled", "0") == "1"
            if not enabled:
                continue

            token = get_setting("notify_telegram_token", "").strip()
            chat_id = (get_setting("backup_tg_chat", "") or get_setting("notify_telegram_chat", "")).strip()
            if not token or not chat_id:
                continue

            try:
                interval_hours = int(get_setting("backup_tg_interval_hours", "24"))
                if interval_hours <= 0:
                    interval_hours = 24
            except ValueError:
                interval_hours = 24

            last_time = 0
            try:
                last_time = int(get_setting("backup_tg_last_time", "0"))
            except ValueError:
                last_time = 0

            now = int(time.time())
            if now - last_time >= interval_hours * 3600:
                print(f"[Backup] 触发定时备份 (周期 {interval_hours} 小时)...")
                try:
                    perform_telegram_backup()
                    print(f"[Backup] 数据库定时备份已成功推送到 Telegram")
                except Exception as e:
                    print(f"[Backup Error] 定时备份失败: {e}")
                    set_setting("backup_tg_last_status", f"失败 ({time.strftime('%Y-%m-%d %H:%M:%S')}: {str(e)[:80]})")
        except Exception as e:
            print(f"[Backup Worker Error] {e}")

def hash_password(password, salt=None):
    if not salt:
        salt = secrets.token_hex(16)
    h = sha256((salt + password).encode("utf-8")).hexdigest()
    return f"{salt}:{h}"

def verify_password(password, stored_hash):
    if not stored_hash or ":" not in stored_hash:
        return False
    salt, h = stored_hash.split(":", 1)
    expected = sha256((salt + password).encode("utf-8")).hexdigest()
    return secrets.compare_digest(h, expected)

# =============================================================================
# 流媒体与 AI 解锁检测（支持 Gemini、ChatGPT、Claude、Netflix 等预设与自定义扩展）
# =============================================================================

DEFAULT_UNLOCK_PRESETS = [
    {"id": "gemini", "name": "Gemini", "shortName": "Gemini", "category": "ai", "color": "blue", "desc": "Google Gemini AI 大模型"},
    {"id": "chatgpt", "name": "ChatGPT", "shortName": "GPT", "category": "ai", "color": "emerald", "desc": "OpenAI ChatGPT Web & App"},
    {"id": "claude", "name": "Claude", "shortName": "Claude", "category": "ai", "color": "amber", "desc": "Anthropic Claude AI"},
    {"id": "netflix", "name": "Netflix", "shortName": "Netflix", "category": "media", "color": "rose", "desc": "Netflix 原生/自制全解锁"},
    {"id": "youtube", "name": "YouTube", "shortName": "YouTube", "category": "media", "color": "red", "desc": "YouTube Premium 会员服务"},
    {"id": "disney", "name": "Disney+", "shortName": "Disney+", "category": "media", "color": "sky", "desc": "Disney+ 区域流媒体服务"},
    {"id": "tiktok", "name": "TikTok", "shortName": "TikTok", "category": "media", "color": "purple", "desc": "TikTok 国际版视频"},
    {"id": "spotify", "name": "Spotify", "shortName": "Spotify", "category": "media", "color": "green", "desc": "Spotify 音乐服务"}
]

def get_unlock_config():
    """获取当前生效的检测配置与启用列表"""
    try:
        raw_enabled = get_setting("unlock_enabled_items", "")
        if raw_enabled:
            enabled = json.loads(raw_enabled)
        else:
            enabled = ["gemini", "chatgpt", "netflix", "youtube"]
    except Exception:
        enabled = ["gemini", "chatgpt", "netflix", "youtube"]

    try:
        raw_custom = get_setting("unlock_custom_items", "")
        custom = json.loads(raw_custom) if raw_custom else []
    except Exception:
        custom = []

    return enabled, custom

def check_single_unlock_item(item_id: str, custom_info=None):
    """检测单一预设项或自定义 URL 项"""
    import ssl
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    ua = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    headers = {"User-Agent": ua}

    if item_id == "gemini":
        try:
            req = urllib.request.Request("https://gemini.google.com/", headers=headers)
            with urllib.request.urlopen(req, timeout=3.5, context=ctx) as resp:
                url = resp.geturl()
                if "error" in url or "unsupported" in url:
                    return {"ok": False, "msg": "地区受限", "region": ""}
                return {"ok": True, "msg": "完整可用", "region": ""}
        except Exception:
            return {"ok": False, "msg": "连接超时", "region": ""}

    elif item_id == "chatgpt":
        try:
            req = urllib.request.Request("https://chatgpt.com/cdn-cgi/trace", headers=headers)
            with urllib.request.urlopen(req, timeout=3.5, context=ctx) as resp:
                text = resp.read().decode("utf-8", errors="ignore")
                loc = ""
                for line in text.splitlines():
                    if line.startswith("loc="):
                        loc = line.split("=")[1].strip()
                if loc:
                    return {"ok": True, "msg": f"支持 ({loc})", "region": loc}
                return {"ok": True, "msg": "支持", "region": ""}
        except Exception:
            try:
                req2 = urllib.request.Request("https://ios.chat.openai.com/", headers=headers)
                with urllib.request.urlopen(req2, timeout=3.5, context=ctx) as resp2:
                    return {"ok": True, "msg": "支持", "region": ""}
            except Exception:
                return {"ok": False, "msg": "IP 受阻", "region": ""}

    elif item_id == "claude":
        try:
            req = urllib.request.Request("https://claude.ai/", headers=headers)
            with urllib.request.urlopen(req, timeout=3.5, context=ctx) as resp:
                url = resp.geturl()
                if "unavailable" in url:
                    return {"ok": False, "msg": "地区受限", "region": ""}
                return {"ok": True, "msg": "可用", "region": ""}
        except urllib.error.HTTPError as e:
            if e.code in (403, 451):
                return {"ok": False, "msg": "地区封锁", "region": ""}
            return {"ok": False, "msg": f"HTTP {e.code}", "region": ""}
        except Exception:
            return {"ok": False, "msg": "连接超时", "region": ""}

    elif item_id == "netflix":
        try:
            req = urllib.request.Request("https://www.netflix.com/title/80018499", headers=headers)
            with urllib.request.urlopen(req, timeout=3.5, context=ctx) as resp:
                if resp.getcode() == 200:
                    return {"ok": True, "msg": "原生全解锁", "region": ""}
                return {"ok": False, "msg": f"HTTP {resp.getcode()}", "region": ""}
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return {"ok": False, "msg": "未解锁", "region": ""}
            return {"ok": False, "msg": f"HTTP {e.code}", "region": ""}
        except Exception:
            return {"ok": False, "msg": "连接超时", "region": ""}

    elif item_id == "youtube":
        try:
            req = urllib.request.Request("https://www.youtube.com/premium", headers=headers)
            with urllib.request.urlopen(req, timeout=3.5, context=ctx) as resp:
                content = resp.read().decode("utf-8", errors="ignore")
                if "Premium is not available" in content:
                    return {"ok": False, "msg": "不支持", "region": ""}
                return {"ok": True, "msg": "支持 Premium", "region": ""}
        except Exception:
            return {"ok": False, "msg": "连接超时", "region": ""}

    elif item_id == "disney":
        try:
            req = urllib.request.Request("https://www.disneyplus.com/", headers=headers)
            with urllib.request.urlopen(req, timeout=3.5, context=ctx) as resp:
                url = resp.geturl()
                if "unavailable" in url:
                    return {"ok": False, "msg": "地区不支持", "region": ""}
                return {"ok": True, "msg": "支持 Disney+", "region": ""}
        except urllib.error.HTTPError as e:
            if e.code in (403, 451):
                return {"ok": False, "msg": "地区封锁", "region": ""}
            return {"ok": False, "msg": f"HTTP {e.code}", "region": ""}
        except Exception:
            return {"ok": False, "msg": "连接超时", "region": ""}

    elif item_id == "tiktok":
        try:
            req = urllib.request.Request("https://www.tiktok.com/about?lang=en", headers=headers)
            with urllib.request.urlopen(req, timeout=3.5, context=ctx) as resp:
                if resp.getcode() == 200:
                    return {"ok": True, "msg": "可用", "region": ""}
                return {"ok": False, "msg": f"HTTP {resp.getcode()}", "region": ""}
        except Exception:
            return {"ok": False, "msg": "连接超时", "region": ""}

    elif item_id == "spotify":
        try:
            req = urllib.request.Request("https://open.spotify.com/", headers=headers)
            with urllib.request.urlopen(req, timeout=3.5, context=ctx) as resp:
                if resp.getcode() == 200:
                    return {"ok": True, "msg": "可用", "region": ""}
                return {"ok": False, "msg": f"HTTP {resp.getcode()}", "region": ""}
        except Exception:
            return {"ok": False, "msg": "连接超时", "region": ""}

    elif custom_info and custom_info.get("url"):
        try:
            target_url = custom_info["url"]
            req = urllib.request.Request(target_url, headers=headers)
            with urllib.request.urlopen(req, timeout=3.5, context=ctx) as resp:
                if resp.getcode() in (200, 204, 301, 302):
                    return {"ok": True, "msg": f"正常响应 ({resp.getcode()})", "region": ""}
                return {"ok": False, "msg": f"HTTP {resp.getcode()}", "region": ""}
        except Exception as e:
            return {"ok": False, "msg": "无法访问", "region": ""}

    return {"ok": False, "msg": "未检测", "region": ""}

def check_node_streaming_unlock(node_or_server, target_items=None):
    """
    根据用户配置动态并发检测流媒体与 AI 项
    """
    from concurrent.futures import ThreadPoolExecutor

    enabled, custom = get_unlock_config()
    items_to_check = target_items or enabled

    results = {
        "updated_at": int(time.time()),
        "region": ""
    }

    # 预设任务映射
    def run_check(key):
        if key.startswith("custom_"):
            # 自定义项
            cust_obj = next((c for c in custom if c.get("id") == key), None)
            return key, check_single_unlock_item(key, cust_obj)
        else:
            return key, check_single_unlock_item(key)

    with ThreadPoolExecutor(max_workers=min(len(items_to_check) + 1, 8)) as executor:
        futures = [executor.submit(run_check, k) for k in items_to_check]
        for f in futures:
            k, r = f.result()
            results[k] = r
            if r.get("region") and not results.get("region"):
                results["region"] = r["region"]

    return results

def save_node_unlock_status(node_id: int, res: dict):
    try:
        conn = get_db()
        data_json = json.dumps(res, ensure_ascii=False)
        nf = res.get("netflix", {})
        gpt = res.get("chatgpt", {})
        yt = res.get("youtube", {})
        dis = res.get("disney", {})
        conn.execute("""
            INSERT OR REPLACE INTO node_unlock_status
            (node_id, netflix_ok, netflix_msg, chatgpt_ok, chatgpt_msg, youtube_ok, youtube_msg, disney_ok, disney_msg, region, updated_at, data_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            node_id,
            1 if nf.get("ok") else 0, nf.get("msg", ""),
            1 if gpt.get("ok") else 0, gpt.get("msg", ""),
            1 if yt.get("ok") else 0, yt.get("msg", ""),
            1 if dis.get("ok") else 0, dis.get("msg", ""),
            res.get("region", ""),
            res.get("updated_at", int(time.time())),
            data_json
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[save_node_unlock_status error] {e}")

def send_telegram_msg(token: str, chat_id: str, text: str):
    """发送纯文本或 HTML 格式的 Telegram 轻量通知"""
    try:
        url = f"https://api.telegram.org/bot{token}/sendMessage"
        payload = json.dumps({
            "chat_id": chat_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True
        }).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "HHUB-Bot/2.0"}
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            return data.get("ok", False), data.get("description", "")
    except urllib.error.HTTPError as e:
        try:
            err_data = json.loads(e.read().decode("utf-8"))
            return False, err_data.get("description", str(e))
        except Exception:
            return False, str(e)
    except Exception as e:
        return False, str(e)

_NODE_ALERT_STATE = {}  # { node_id: "down" | "up" }

def telegram_node_alert_loop():
    """静默守护：每 30 秒轮询所有服务器，节点断网离线 > 75 秒推送告警，恢复在线自动推送恢复信令"""
    while True:
        try:
            time.sleep(30)
            token = get_setting("notify_telegram_token", "").strip()
            chat_id = (get_setting("notify_telegram_chat", "") or get_setting("backup_tg_chat", "")).strip()
            if not token or not chat_id:
                continue

            now = int(time.time())
            conn = get_db()
            cur = conn.execute("SELECT id, name, ip, last_seen FROM node")
            rows = cur.fetchall()
            conn.close()

            for row in rows:
                nid, name, ip, last_seen = row[0], row[1], row[2], row[3]
                if not last_seen or last_seen == 0:
                    continue

                is_offline = (now - last_seen) > 75
                prev_state = _NODE_ALERT_STATE.get(nid, "up")

                if is_offline and prev_state != "down":
                    _NODE_ALERT_STATE[nid] = "down"
                    time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now))
                    text = (
                        f"⚠️ <b>[HHUB 告警] 节点发生离线</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"🖥️ <b>服务器:</b> {name}\n"
                        f"🌐 <b>IP 地址:</b> <code>{ip}</code>\n"
                        f"⏱️ <b>状态:</b> 心跳中断已超过 75 秒\n"
                        f"📅 <b>时间:</b> {time_str}\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"💡 <i>建议: 请排查网络连接或机器运行状态</i>"
                    )
                    send_telegram_msg(token, chat_id, text)

                elif not is_offline and prev_state == "down":
                    _NODE_ALERT_STATE[nid] = "up"
                    time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(now))
                    text = (
                        f"✅ <b>[HHUB 恢复] 节点已恢复在线</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"🖥️ <b>服务器:</b> {name}\n"
                        f"🌐 <b>IP 地址:</b> <code>{ip}</code>\n"
                        f"⏱️ <b>状态:</b> 重新连通正常\n"
                        f"📅 <b>时间:</b> {time_str}\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"🎉 <i>探针已恢复打卡，监控运行中</i>"
                    )
                    send_telegram_msg(token, chat_id, text)
        except Exception:
            pass


def get_sub_token():
    conn = get_db()
    cur = conn.execute("SELECT value FROM setting WHERE key = 'proxy_sub_token'")
    row = cur.fetchone()
    conn.close()
    return row[0] if row else "default-token"

def get_current_user(headers):
    try:
        cookie_str = headers.get("Cookie", "")
        session_token = None
        for item in cookie_str.split(";"):
            item = item.strip()
            if item.startswith("monitor_session="):
                session_token = item.split("=", 1)[1].strip()
                break
        if not session_token:
            auth_header = headers.get("Authorization", "").strip()
            if auth_header.startswith("Bearer "):
                b_tok = auth_header.split(" ", 1)[1].strip()
                token_hash = sha256(b_tok.encode()).hexdigest()
                now = int(time.time())
                conn = get_db()
                row = conn.execute("SELECT 1 FROM session WHERE token_hash = ? AND expires_at > ?", (token_hash, now)).fetchone()
                if row:
                    session_token = b_tok
                    conn.close()
                else:
                    u_row = conn.execute("SELECT * FROM proxy_user WHERE sub_token = ? AND is_admin = 1", (b_tok,)).fetchone()
                    conn.close()
                    if u_row:
                        return dict(u_row)
            if not session_token:
                return None
        
        token_hash = sha256(session_token.encode()).hexdigest()
        now = int(time.time())
        conn = get_db()
        cur = conn.execute("SELECT 1 FROM session WHERE token_hash = ? AND expires_at > ?", (token_hash, now))
        row = cur.fetchone()
        if not row:
            conn.close()
            return None

        # Check proxy_session_user
        u_cur = conn.execute("""
            SELECT u.* FROM proxy_user u
            JOIN proxy_session_user s ON u.id = s.user_id
            WHERE s.token_hash = ?
        """, (token_hash,))
        user_row = u_cur.fetchone()
        if user_row:
            u = dict(user_row)
            conn.close()
            return u
        
        # If in session table but not in proxy_session_user: emergency admin login
        admin_cur = conn.execute("SELECT * FROM proxy_user WHERE is_admin = 1 ORDER BY id ASC LIMIT 1")
        admin_row = admin_cur.fetchone()
        conn.close()
        if admin_row:
            return dict(admin_row)
        return {
            "id": 0, "username": "admin", "is_admin": 1, "enabled": 1,
            "traffic_limit_bytes": 0, "upload_bytes": 0, "download_bytes": 0,
            "expires_at": 0, "sub_token": get_sub_token()
        }
    except Exception as e:
        print("get_current_user error:", e)
        return None

def check_auth(headers):
    user = get_current_user(headers)
    return user is not None and user.get("is_admin") == 1

def ensure_user_credentials(user):
    user_id = user["id"]
    sub_token = user.get("sub_token") or f"user_{user_id}"
    u_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"monitor_user_{user_id}_{sub_token}"))
    u_pwd = f"u{user_id}_{sub_token[:12]}"
    return u_uuid, u_pwd

_user_active_ips = {}  # { user_id: { ip_str: last_seen_epoch } }
_last_xray_log_offset = 0
_last_singbox_log_offset = 0

def update_device_tracker():
    global _user_active_ips, _last_xray_log_offset, _last_singbox_log_offset
    now = int(time.time())

    # 1. Parse Xray access log
    xray_log = "/var/log/xray/access.log"
    if os.path.exists(xray_log):
        try:
            size = os.path.getsize(xray_log)
            if size < _last_xray_log_offset:
                _last_xray_log_offset = 0
            with open(xray_log, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(_last_xray_log_offset)
                lines = f.readlines()
                _last_xray_log_offset = f.tell()
                for line in lines:
                    if "accepted" in line and "email:" in line:
                        m_email = re.search(r'email:\s*([^\s]+)', line)
                        m_ip = re.search(r'(?:from\s+|^)([\d\.:a-fA-F]+):\d+\s+accepted', line)
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
                                if uid not in _user_active_ips:
                                    _user_active_ips[uid] = {}
                                _user_active_ips[uid][ip] = now
        except Exception:
            pass

    # 2. Parse Sing-box access log if present
    sb_log = "/var/log/sing-box/access.log"
    if os.path.exists(sb_log):
        try:
            size = os.path.getsize(sb_log)
            if size < _last_singbox_log_offset:
                _last_singbox_log_offset = 0
            with open(sb_log, "r", encoding="utf-8", errors="ignore") as f:
                f.seek(_last_singbox_log_offset)
                lines = f.readlines()
                _last_singbox_log_offset = f.tell()
                for line in lines:
                    m_ip = re.search(r'\[([\d\.:a-fA-F]+):\d+\s*->', line)
                    m_user = re.search(r'user:\s*([^\s\)]+)', line)
                    if m_ip and m_user:
                        ip = m_ip.group(1).strip()
                        u_name = m_user.group(1).strip()
                        uid = None
                        if u_name.startswith("user_"):
                            try:
                                uid = int(u_name.split("_")[1])
                            except ValueError:
                                pass
                        elif u_name == "default":
                            uid = 1
                        if uid is not None and ip not in ("127.0.0.1", "::1"):
                            if uid not in _user_active_ips:
                                _user_active_ips[uid] = {}
                            _user_active_ips[uid][ip] = now
        except Exception:
            pass

    # 3. Prune IPs inactive for more than 180s (3 minutes)
    for uid in list(_user_active_ips.keys()):
        _user_active_ips[uid] = {ip: t for ip, t in _user_active_ips[uid].items() if now - t < 180}
        if not _user_active_ips[uid]:
            _user_active_ips.pop(uid, None)

def get_user_online_device_count(user_id):
    now = int(time.time())
    ips = _user_active_ips.get(user_id, {})
    return len([ip for ip, t in ips.items() if now - t < 180])

def is_user_over_device_limit(user):
    limit = user.get("device_limit", 0)
    if limit is not None and limit > 0:
        count = get_user_online_device_count(user["id"])
        return count > limit
    return False

def get_active_users():
    conn = get_db()
    cur = conn.execute("SELECT * FROM proxy_user")
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    now = int(time.time())
    active = []
    for u in rows:
        used = u.get("upload_bytes", 0) + u.get("download_bytes", 0)
        limit = u.get("traffic_limit_bytes", 0)
        is_over = (limit > 0 and used >= limit)
        is_exp = (u.get("expires_at", 0) > 0 and now > u.get("expires_at", 0))
        is_dis = (u.get("enabled", 1) == 0)
        is_dev_over = is_user_over_device_limit(u)
        if not is_over and not is_exp and not is_dis and not is_dev_over:
            active.append(u)
    return active

_last_active_user_ids = set()

def traffic_collector_loop():
    global _last_active_user_ids
    time.sleep(3)
    try:
        _last_active_user_ids = {u["id"] for u in get_active_users()}
    except Exception:
        pass

    while True:
        try:
            time.sleep(3)
            # 0. Update device tracker from logs
            update_device_tracker()

            # 1. Query Xray StatsService via local API
            if os.path.exists(XRAY_BIN):
                res = subprocess.run(
                    [XRAY_BIN, "api", "statsquery", "--server=127.0.0.1:10085", "-reset=true"],
                    capture_output=True, text=True, timeout=5
                )
                if res.returncode == 0 and res.stdout:
                    try:
                        data = json.loads(res.stdout)
                        stats = data.get("stat") or []
                        user_traffic = {}
                        for item in stats:
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
                                        user_traffic[uid] = {"up": 0, "down": 0}
                                    if direction == "uplink":
                                        user_traffic[uid]["up"] += val
                                    elif direction == "downlink":
                                        user_traffic[uid]["down"] += val
                        
                        if user_traffic:
                            conn = get_db()
                            with conn:
                                for uid, tf in user_traffic.items():
                                    conn.execute("""
                                        UPDATE proxy_user
                                        SET upload_bytes = upload_bytes + ?, download_bytes = download_bytes + ?
                                        WHERE id = ?
                                    """, (tf["up"], tf["down"], uid))
                            conn.close()
                    except Exception as e:
                        pass

            # 2. Check if active user set changed (e.g. user reached quota or renewed/restored)
            curr_active_users = get_active_users()
            curr_active_ids = {u["id"] for u in curr_active_users}
            if curr_active_ids != _last_active_user_ids:
                print(f"[*] User active set changed from {_last_active_user_ids} to {curr_active_ids}. Re-applying configs...")
                _last_active_user_ids = curr_active_ids
                apply_all_configs()

        except Exception as e:
            time.sleep(3)

def gen_ss2022_key(method="2022-blake3-aes-128-gcm"):
    import base64
    if "128" in method:
        return base64.b64encode(secrets.token_bytes(16)).decode('utf-8')
    else:
        return base64.b64encode(secrets.token_bytes(32)).decode('utf-8')

def gen_random_password(length=16):
    return secrets.token_urlsafe(length)[:length]

def gen_xray_keys():
    try:
        res = subprocess.run([XRAY_BIN, "x25519"], capture_output=True, text=True, check=True)
        priv = ""
        pub = ""
        for line in res.stdout.splitlines():
            line = line.strip()
            if "PrivateKey:" in line:
                priv = line.split("PrivateKey:", 1)[1].strip()
            elif "PublicKey):" in line or "PublicKey:" in line:
                pub = line.split(":", 1)[1].strip()
        short_id = secrets.token_hex(8)
        return priv, pub, short_id
    except Exception as e:
        print("x25519 error:", e)
        return "", "", secrets.token_hex(8)

def gen_uuid():
    try:
        res = subprocess.run([XRAY_BIN, "uuid"], capture_output=True, text=True, check=True)
        return res.stdout.strip()
    except Exception:
        import uuid
        return str(uuid.uuid4())

def get_free_port():
    conn = get_db()
    used_ports = set(r[0] for r in conn.execute("SELECT port FROM proxy_node").fetchall())
    conn.close()
    for _ in range(100):
        p = random.randint(20000, 45000)
        if p not in used_ports:
            return p
    return 20443

def is_private_ip(addr):
    if not addr: return True
    try:
        import ipaddress
        ip = ipaddress.ip_address(addr.strip())
        return ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local
    except Exception:
        return False

def resolve_server_host(r):
    ipv4 = (r.get("ipv4") or "").strip()
    pub_ip = (r.get("ip") or r.get("country_ip") or "").strip()
    if ipv4 and not is_private_ip(ipv4):
        return ipv4
    if pub_ip and not is_private_ip(pub_ip):
        return pub_ip
    return ipv4 or pub_ip or "127.0.0.1"

def test_node_connectivity(node):
    host = node.get("server_host") or "127.0.0.1"
    port = int(node.get("port", 0))
    proto = node.get("protocol", "vless_reality")
    node_id = node.get("id", 0)

    is_ipv6 = ":" in host
    sock_family = socket.AF_INET6 if is_ipv6 else socket.AF_INET

    # 0. Hysteria 2 / TUIC (UDP 协议检测)
    if proto in ("hysteria2", "tuic"):
        t0 = time.time()
        if is_local_node(node):
            res = subprocess.run(["ss", "-ulpn"], capture_output=True, text=True)
            port_str = f":{port}"
            if port_str in res.stdout and ("sing-box" in res.stdout or "hysteria" in res.stdout or "realm" in res.stdout):
                return True, f"连通正常，UDP 端口 {port} 监听就绪 (延迟 ~0ms)", 0
            else:
                return False, f"未能在 UDP 端口 {port} 正常监听，请检查核心服务状态或端口占用", 0
        else:
            try:
                s = socket.socket(sock_family, socket.SOCK_DGRAM)
                s.settimeout(2.0)
                s.connect((host, port))
                s.send(b"\x00")
                s.close()
                udp_ms = max(1, int((time.time() - t0) * 1000))
                return True, f"UDP 端口连通正常 (延迟 ~{udp_ms}ms)", udp_ms
            except Exception as e:
                return False, f"UDP 连接异常: {e}", 0

    # 1. TCP 端口连通性检测
    t0 = time.time()
    try:
        s = socket.socket(sock_family, socket.SOCK_STREAM)
        s.settimeout(2.5)
        res = s.connect_ex((host, port))
        s.close()
        tcp_ms = int((time.time() - t0) * 1000)
    except Exception as e:
        return False, f"TCP 连接异常: {e}", 0

    if res != 0:
        return False, f"TCP 端口 {port} 无法连通 (超时或拒绝连接)。若是 NAT 服务器请确认端口是否在服务商映射范围内；若是常规 VPS 请确认云服务商安全组已放行入站", 0

    # 2. VLESS Reality 握手与真实流量测试
    if proto == "vless_reality":
        test_port = random.randint(18000, 19999)
        test_client_cfg = {
            "log": { "loglevel": "warning" },
            "inbounds": [{
                "port": test_port,
                "listen": "127.0.0.1",
                "protocol": "socks",
                "settings": { "auth": "noauth" }
            }],
            "outbounds": [{
                "protocol": "vless",
                "settings": {
                    "vnext": [{
                        "address": host,
                        "port": port,
                        "users": [{
                            "id": node.get("uuid"),
                            "flow": node.get("flow") or "xtls-rprx-vision",
                            "encryption": "none"
                        }]
                    }]
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "reality",
                    "realitySettings": {
                        "show": False,
                        "fingerprint": "chrome",
                        "serverName": node.get("sni") or "www.apple.com",
                        "publicKey": node.get("public_key"),
                        "shortId": node.get("short_id") or "",
                        "spiderX": "/"
                    }
                }
            }]
        }
        cfg_path = f"/tmp/test_client_{node_id}_{int(time.time())}.json"
        try:
            with open(cfg_path, "w") as f:
                json.dump(test_client_cfg, f)
            p = subprocess.Popen([XRAY_BIN, "run", "-config", cfg_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            time.sleep(1.0)

            curl_res = subprocess.run([
                "curl", "-x", f"socks5h://127.0.0.1:{test_port}",
                "https://www.cloudflare.com", "-I", "-m", "5"
            ], capture_output=True, text=True)
            p.kill()
            if os.path.exists(cfg_path):
                os.remove(cfg_path)

            if "HTTP/" in curl_res.stdout or "200" in curl_res.stdout:
                return True, f"连通正常，Reality 握手成功 (延迟 ~{tcp_ms}ms)", tcp_ms
            else:
                err = curl_res.stderr.strip() or "握手超时"
                return False, f"TCP 端口已通，但 Reality 握手未完成: {err}", tcp_ms
        except Exception as e:
            return False, f"握手测试执行异常: {e}", tcp_ms
    else:
        return True, f"TCP 端口连通正常 (延迟 ~{tcp_ms}ms)", tcp_ms

def format_node_link(node, user=None, server_country_map=None):
    proto = node["protocol"]
    uuid_str = node.get("uuid") or ""
    pwd_str = node.get("password") or uuid_str
    if user:
        u_uuid, u_pwd = ensure_user_credentials(user)
        uuid_str = u_uuid
        pwd_str = u_pwd

    host = node.get("server_host") or "189.24.108.25"
    uri_host = format_host_for_uri(host)
    port = node.get("port") or 20443
    name_raw = format_node_display_name(node, server_country_map)
    name = quote(name_raw, safe=":/[] -_()@➔")
    
    if proto == "vless_reality":
        pbk = node.get("public_key") or ""
        sid = node.get("short_id") or ""
        sni = node.get("sni") or "www.apple.com"
        flow = node.get("flow") or "xtls-rprx-vision"
        flow_param = f"&flow={flow}" if flow else ""
        spx = node.get("spider_x") or ""
        spx_param = f"&spx={quote(spx)}" if (spx and spx != "/") else ""
        return f"vless://{uuid_str}@{uri_host}:{port}?security=reality&encryption=none&pbk={pbk}&headerType=none&fp=chrome{spx_param}&type=tcp{flow_param}&sni={sni}&sid={sid}#{name}"
    
    elif proto == "vless_reality_xhttp":
        pbk = node.get("public_key") or ""
        sid = node.get("short_id") or ""
        sni = node.get("sni") or "www.apple.com"
        xpath = quote(node.get("ws_path") or "/xhttp")
        spx = node.get("spider_x") or ""
        spx_param = f"&spx={quote(spx)}" if (spx and spx != "/") else ""
        return f"vless://{uuid_str}@{uri_host}:{port}?security=reality&encryption=none&pbk={pbk}&headerType=none&fp=chrome{spx_param}&type=xhttp&sni={sni}&sid={sid}&path={xpath}&mode=auto#{name}"

    elif proto == "vless_ws":
        ws_path = quote(node.get("ws_path") or "/ws-proxy")
        return f"vless://{uuid_str}@{uri_host}:{port}?security=none&encryption=none&type=ws&path={ws_path}#{name}"

    elif proto == "vmess_ws":
        ps_label = name_raw
        vmess_data = {
            "v": "2",
            "ps": ps_label,
            "add": host,
            "port": str(port),
            "id": uuid_str,
            "aid": "0",
            "scy": "auto",
            "net": "ws",
            "type": "none",
            "host": node.get("sni") or "",
            "path": node.get("ws_path") or "/vmess-ws",
            "tls": ""
        }
        b64_json = base64.b64encode(json.dumps(vmess_data, ensure_ascii=False).encode('utf-8')).decode('utf-8')
        return f"vmess://{b64_json}"

    elif proto == "trojan":
        return f"trojan://{pwd_str}@{uri_host}:{port}?security=none&headerType=none&type=tcp#{name}"

    elif proto == "ss2022":
        import base64
        method = node.get("method") or "2022-blake3-aes-128-gcm"
        userinfo = base64.b64encode(f"{method}:{pwd_str}".encode('utf-8')).decode('utf-8')
        return f"ss://{userinfo}@{uri_host}:{port}#{name}"

    elif proto == "socks5":
        uname = (node.get("username") or "").strip()
        if user:
            uname = user.get("username", "")
        if uname:
            return f"socks5://{quote(uname)}:{quote(pwd_str)}@{uri_host}:{port}#{name}"
        else:
            return f"socks5://{uri_host}:{port}#{name}"

    elif proto == "hysteria2":
        sni = node.get("sni") or "bing.com"
        return f"hysteria2://{pwd_str}@{uri_host}:{port}/?sni={sni}&alpn=h3&insecure=1#{name}"

    elif proto == "tuic":
        uid_val = uuid_str or gen_random_password(16)
        sni = node.get("sni") or "bing.com"
        return f"tuic://{uid_val}:{pwd_str}@{uri_host}:{port}?congestion_control=bbr&alpn=h3&sni={sni}&udp_relay_mode=native&allow_insecure=1#{name}"

    return ""

def build_subscription_info_nodes(user):
    """
    生成用于展示给用户的订阅流量与到期时间虚拟节点
    让用户在客户端刷新订阅时，直接在节点列表顶部看到自己的剩余流量和到期时间
    """
    if not user:
        return []

    u_bytes = user.get("upload_bytes", 0) or 0
    d_bytes = user.get("download_bytes", 0) or 0
    total_used = u_bytes + d_bytes
    limit = user.get("traffic_limit_bytes", 0) or 0
    exp_time = user.get("expires_at", 0) or 0

    def format_bytes(b):
        if b >= 1024**3:
            return f"{b / (1024**3):.2f} GB"
        elif b >= 1024**2:
            return f"{b / (1024**2):.1f} MB"
        elif b >= 1024:
            return f"{b / 1024:.1f} KB"
        else:
            return f"{b} B"

    used_str = format_bytes(total_used)

    if limit > 0:
        remaining = max(0, limit - total_used)
        rem_str = format_bytes(remaining)
        limit_str = format_bytes(limit)
        traffic_title = f"📊 剩余流量 | {rem_str} (总计 {limit_str})"
    else:
        traffic_title = f"📊 剩余流量 | 不限量 (已用 {used_str})"

    if exp_time > 0:
        exp_date = time.strftime("%Y-%m-%d", time.localtime(exp_time))
        expire_title = f"⏳ 订阅到期 | {exp_date}"
    else:
        expire_title = "⏳ 订阅到期 | 永久有效"

    return [traffic_title, expire_title]


def country_code_to_flag(code: str) -> str:
    """将两字母国家代码 (如 HK, JP, US) 转换为对应的 Emoji 国旗 (如 🇭🇰, 🇯🇵, 🇺🇸)"""
    if not code or len(code) != 2:
        return ""
    code = code.upper()
    try:
        return "".join(chr(0x1F1E6 + ord(c) - ord('A')) for c in code)
    except Exception:
        return ""

KEYWORD_FLAG_MAP = [
    ("香港", "🇭🇰"), ("hong kong", "🇭🇰"), ("hk", "🇭🇰"),
    ("日本", "🇯🇵"), ("japan", "🇯🇵"), ("tokyo", "🇯🇵"), ("osaka", "🇯🇵"), ("jp", "🇯🇵"),
    ("台湾", "🇹🇼"), ("taiwan", "🇹🇼"), ("tw", "🇹🇼"),
    ("新加坡", "🇸🇬"), ("singapore", "🇸🇬"), ("sg", "🇸🇬"),
    ("美国", "🇺🇸"), ("america", "🇺🇸"), ("united states", "🇺🇸"), ("us", "🇺🇸"),
    ("韩国", "🇰🇷"), ("korea", "🇰🇷"), ("seoul", "🇰🇷"), ("kr", "🇰🇷"),
    ("英国", "🇬🇧"), ("london", "🇬🇧"), ("united kingdom", "🇬🇧"), ("uk", "🇬🇧"), ("gb", "🇬🇧"),
    ("德国", "🇩🇪"), ("germany", "🇩🇪"), ("frankfurt", "🇩🇪"), ("de", "🇩🇪"),
    ("法国", "🇫🇷"), ("france", "🇫🇷"), ("paris", "🇫🇷"), ("fr", "🇫🇷"),
    ("加拿大", "🇨🇦"), ("canada", "🇨🇦"), ("ca", "🇨🇦"),
    ("澳大利亚", "🇦🇺"), ("australia", "🇦🇺"), ("sydney", "🇦🇺"), ("au", "🇦🇺"),
    ("俄罗斯", "🇷🇺"), ("russia", "🇷🇺"), ("moscow", "🇷🇺"), ("ru", "🇷🇺"),
    ("荷兰", "🇳🇱"), ("netherlands", "🇳🇱"), ("amsterdam", "🇳🇱"), ("nl", "🇳🇱"),
    ("土耳其", "🇹🇷"), ("turkey", "🇹🇷"), ("istanbul", "🇹🇷"), ("tr", "🇹🇷"),
    ("阿根廷", "🇦🇷"), ("argentina", "🇦🇷"), ("ar", "🇦🇷"),
    ("印度", "🇮🇳"), ("india", "🇮🇳"), ("in", "🇮🇳"),
    ("巴西", "🇧🇷"), ("brazil", "🇧🇷"), ("br", "🇧🇷"),
    ("马来西亚", "🇲🇾"), ("malaysia", "🇲🇾"), ("my", "🇲🇾"),
    ("泰国", "🇹🇭"), ("thailand", "🇹🇭"), ("th", "🇹🇭"),
    ("越南", "🇻🇳"), ("vietnam", "🇻🇳"), ("vn", "🇻🇳"),
    ("菲律宾", "🇵🇭"), ("philippines", "🇵🇭"), ("ph", "🇵🇭"),
]

def resolve_node_flag(node, server_country_map=None) -> str:
    """根据服务器归属国籍或名称关键词智能解析国旗 Emoji"""
    name = node.get("name", "")
    # 若节点名已自带国旗 Emoji，则不重复补充
    for char in name[:4]:
        if 0x1F1E6 <= ord(char) <= 0x1F1FF:
            return ""

    sid = node.get("server_id")
    if server_country_map and sid in server_country_map:
        c_code = server_country_map[sid]
        flg = country_code_to_flag(c_code)
        if flg:
            return flg

    text = f"{node.get('server_name', '')} {name}".lower()
    for kw, flg in KEYWORD_FLAG_MAP:
        if kw in text:
            return flg

    return "🌐"

def format_node_display_name(node, server_country_map=None) -> str:
    """格式化带国旗标识的优雅节点名称"""
    raw_name = (node.get("name") or "").strip() or f"Node-{node.get('port', 0)}"
    flag = resolve_node_flag(node, server_country_map)
    if flag:
        return f"{flag} {raw_name}"
    return raw_name

def get_server_country_map():
    try:
        conn = get_db()
        server_rows = conn.execute("SELECT id, country FROM node").fetchall()
        conn.close()
        return {r["id"]: (r["country"] or "") for r in server_rows}
    except Exception:
        return {}

CURRENT_VERSION = "v2.5.0"

def get_local_version() -> str:
    ver_file = "/opt/monitor/VERSION"
    if os.path.exists(ver_file):
        try:
            with open(ver_file, "r", encoding="utf-8") as f:
                v = f.read().strip()
                if v:
                    return v
        except Exception:
            pass
    return CURRENT_VERSION

_update_cache = {
    "checked_at": 0,
    "data": None
}

def parse_semver(v_str: str):
    import re
    v_str = v_str.lstrip("vV").strip()
    parts = re.split(r'[-.]', v_str)
    nums = []
    for p in parts:
        try:
            nums.append(int(p))
        except ValueError:
            break
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums[:3])

def check_system_update(force=False):
    global _update_cache
    now = time.time()
    if not force and (now - _update_cache["checked_at"] < 300) and _update_cache["data"]:
        return _update_cache["data"]

    cur_ver = get_local_version()
    latest_ver = cur_ver
    changelog = []
    release_date = ""
    title = ""

    v_json_url = "https://raw.githubusercontent.com/2290145679/ProxyProbe-Release/main/version.json"
    req = urllib.request.Request(v_json_url, headers={"User-Agent": f"ProxyProbe/{cur_ver}"})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            v_data = json.loads(resp.read().decode("utf-8"))
            latest_ver = (v_data.get("version") or cur_ver).strip()
            changelog = v_data.get("changelog") or []
            release_date = v_data.get("release_date") or ""
            title = v_data.get("title") or ""
    except Exception:
        try:
            v_raw_url = "https://raw.githubusercontent.com/2290145679/ProxyProbe-Release/main/VERSION"
            req2 = urllib.request.Request(v_raw_url, headers={"User-Agent": f"ProxyProbe/{cur_ver}"})
            with urllib.request.urlopen(req2, timeout=5) as resp2:
                latest_ver = resp2.read().decode("utf-8").strip() or cur_ver
        except Exception:
            pass

    has_update = False
    try:
        has_update = parse_semver(latest_ver) > parse_semver(cur_ver)
    except Exception:
        has_update = (latest_ver != cur_ver and latest_ver != "")

    result = {
        "ok": True,
        "current_version": cur_ver,
        "latest_version": latest_ver,
        "has_update": has_update,
        "title": title or f"ProxyProbe {latest_ver} 最新版本",
        "changelog": changelog,
        "release_date": release_date,
        "release_url": "https://github.com/2290145679/ProxyProbe-Release"
    }

    _update_cache["checked_at"] = now
    _update_cache["data"] = result
    return result

def trigger_background_upgrade():
    def _run():
        time.sleep(1.0)
        hhub_bin = "/usr/local/bin/hhub"
        if os.path.exists(hhub_bin) and os.access(hhub_bin, os.X_OK):
            subprocess.Popen([hhub_bin, "upgrade"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            script_path = "/opt/monitor/scripts/hhub.sh"
            if os.path.exists(script_path):
                subprocess.Popen(["bash", script_path, "upgrade"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    t = threading.Thread(target=_run, daemon=True)
    t.start()

def get_node_latest_latencies():
    """Query the latest ping latency for all assigned probes across all nodes."""
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT
                pn.node_id,
                pt.id AS task_id,
                pt.name,
                pr.latency,
                pr.ts
            FROM ping_node pn
            JOIN ping_task pt ON pt.id = pn.task_id
            LEFT JOIN (
                SELECT node_id, task_id, latency, ts,
                       ROW_NUMBER() OVER (PARTITION BY node_id, task_id ORDER BY ts DESC) as rn
                FROM ping_record
            ) pr ON pr.node_id = pn.node_id AND pr.task_id = pt.id AND pr.rn = 1
            ORDER BY pn.node_id, pt.id
        """)
        rows = cur.fetchall()
        conn.close()
        result = {}
        for r in rows:
            nid = str(r["node_id"])
            if nid not in result:
                result[nid] = []
            result[nid].append({
                "task_id": r["task_id"],
                "name": r["name"],
                "latency": r["latency"],
                "ts": r["ts"]
            })
        return result
    except Exception as e:
        print(f"[Error] get_node_latest_latencies: {e}")
        return {}


DEFAULT_CLASH_SMART_RULES = """# --- 局域网与私有网络直连 ---
- GEOIP,LAN,DIRECT
- DOMAIN-SUFFIX,local,DIRECT
- DOMAIN-SUFFIX,localhost,DIRECT
- IP-CIDR,127.0.0.0/8,DIRECT
- IP-CIDR,172.16.0.0/12,DIRECT
- IP-CIDR,192.168.0.0/16,DIRECT
- IP-CIDR,10.0.0.0/8,DIRECT
- IP-CIDR,100.64.0.0/10,DIRECT
# --- 常用 AI 智能助手走代理 ---
- DOMAIN-SUFFIX,openai.com,节点选择
- DOMAIN-SUFFIX,chatgpt.com,节点选择
- DOMAIN-SUFFIX,anthropic.com,节点选择
- DOMAIN-SUFFIX,claude.ai,节点选择
- DOMAIN-SUFFIX,oaistatic.com,节点选择
- DOMAIN-SUFFIX,oaiusercontent.com,节点选择
- DOMAIN-KEYWORD,gemini,节点选择
- DOMAIN-KEYWORD,openai,节点选择
# --- 常用海外社交与影音走代理 ---
- DOMAIN-SUFFIX,google.com,节点选择
- DOMAIN-SUFFIX,youtube.com,节点选择
- DOMAIN-SUFFIX,github.com,节点选择
- DOMAIN-SUFFIX,githubusercontent.com,节点选择
- DOMAIN-SUFFIX,twitter.com,节点选择
- DOMAIN-SUFFIX,x.com,节点选择
- DOMAIN-SUFFIX,telegram.org,节点选择
- DOMAIN-SUFFIX,t.me,节点选择
- DOMAIN-SUFFIX,netflix.com,节点选择
- DOMAIN-SUFFIX,spotify.com,节点选择
# --- 国内常见服务与域名直连 ---
- DOMAIN-SUFFIX,cn,DIRECT
- DOMAIN-SUFFIX,baidu.com,DIRECT
- DOMAIN-SUFFIX,qq.com,DIRECT
- DOMAIN-SUFFIX,weixin.com,DIRECT
- DOMAIN-SUFFIX,alipay.com,DIRECT
- DOMAIN-SUFFIX,taobao.com,DIRECT
- DOMAIN-SUFFIX,jd.com,DIRECT
- DOMAIN-SUFFIX,bilibili.com,DIRECT
- DOMAIN-SUFFIX,163.com,DIRECT
- DOMAIN-SUFFIX,zhihu.com,DIRECT
- GEOIP,CN,DIRECT
# --- 最终兜底规则 ---
- MATCH,节点选择"""

DEFAULT_CLASH_MINIMAL_RULES = """- GEOIP,LAN,DIRECT
- GEOIP,CN,DIRECT
- MATCH,节点选择"""

DEFAULT_CLASH_GLOBAL_RULES = """- GEOIP,LAN,DIRECT
- MATCH,节点选择"""

DEFAULT_SINGBOX_SMART_RULES = json.dumps([
    {"protocol": "dns", "outbound": "dns-out"},
    {"ip_is_private": True, "outbound": "DIRECT"},
    {"clash_mode": "Direct", "outbound": "DIRECT"},
    {"clash_mode": "Global", "outbound": "PROXY"},
    {"domain_suffix": [".cn", "baidu.com", "qq.com", "weixin.com", "taobao.com", "bilibili.com", "jd.com", "163.com", "zhihu.com"], "outbound": "DIRECT"},
    {"geoip": ["cn", "private"], "outbound": "DIRECT"},
    {"domain_suffix": ["openai.com", "chatgpt.com", "anthropic.com", "claude.ai", "google.com", "youtube.com", "github.com", "twitter.com", "x.com", "telegram.org", "netflix.com"], "outbound": "PROXY"},
    {"outbound": "PROXY"}
], indent=2, ensure_ascii=False)

DEFAULT_SINGBOX_MINIMAL_RULES = json.dumps([
    {"protocol": "dns", "outbound": "dns-out"},
    {"ip_is_private": True, "outbound": "DIRECT"},
    {"clash_mode": "Direct", "outbound": "DIRECT"},
    {"clash_mode": "Global", "outbound": "PROXY"},
    {"geoip": ["cn", "private"], "outbound": "DIRECT"},
    {"outbound": "PROXY"}
], indent=2, ensure_ascii=False)

DEFAULT_SINGBOX_GLOBAL_RULES = json.dumps([
    {"protocol": "dns", "outbound": "dns-out"},
    {"ip_is_private": True, "outbound": "DIRECT"},
    {"clash_mode": "Direct", "outbound": "DIRECT"},
    {"outbound": "PROXY"}
], indent=2, ensure_ascii=False)

def get_rule_presets():
    return [
        {
            "id": "smart",
            "name": "国内外智能分流",
            "desc": "推荐日常使用。局域网与国内 IP/常见域名直连，常用国外站点、AI 矩阵及主流媒体走节点代理，自动兼顾速度与隐私。",
            "badge": "默认推荐",
            "clash_rules": DEFAULT_CLASH_SMART_RULES,
            "singbox_rules": DEFAULT_SINGBOX_SMART_RULES
        },
        {
            "id": "minimal",
            "name": "极简轻量分流",
            "desc": "仅局域网与中国大陆 IP (GEOIP,CN) 直连，其余全部流量无感走代理节点。",
            "badge": "轻量高速",
            "clash_rules": DEFAULT_CLASH_MINIMAL_RULES,
            "singbox_rules": DEFAULT_SINGBOX_MINIMAL_RULES
        },
        {
            "id": "global",
            "name": "全局代理模式",
            "desc": "除局域网私有地址外，全部网络请求统一通过代理节点转发。",
            "badge": "全部代理",
            "clash_rules": DEFAULT_CLASH_GLOBAL_RULES,
            "singbox_rules": DEFAULT_SINGBOX_GLOBAL_RULES
        },
        {
            "id": "custom",
            "name": "自定义专家规则",
            "desc": "自由编写定制 Clash Rules 及 Sing-box 路由规则，完全由管理员自主掌控分流逻辑。",
            "badge": "自由定制",
            "clash_rules": DEFAULT_CLASH_SMART_RULES,
            "singbox_rules": DEFAULT_SINGBOX_SMART_RULES
        }
    ]

def get_active_clash_rules():
    mode = get_setting("sub_rule_mode", "smart")
    if mode == "custom":
        raw = get_setting("sub_clash_rules", "").strip()
        if raw:
            rules = []
            for line in raw.splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if line.startswith("- "):
                    line = line[2:].strip()
                rules.append(line)
            if rules:
                return rules
    elif mode == "minimal":
        raw = DEFAULT_CLASH_MINIMAL_RULES
    elif mode == "global":
        raw = DEFAULT_CLASH_GLOBAL_RULES
    else:
        raw = DEFAULT_CLASH_SMART_RULES
    
    rules = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("- "):
            line = line[2:].strip()
        rules.append(line)
    return rules

def get_active_singbox_rules():
    mode = get_setting("sub_rule_mode", "smart")
    if mode == "custom":
        raw = get_setting("sub_singbox_rules", "").strip()
        if raw:
            try:
                parsed = json.loads(raw)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                pass
    elif mode == "minimal":
        return json.loads(DEFAULT_SINGBOX_MINIMAL_RULES)
    elif mode == "global":
        return json.loads(DEFAULT_SINGBOX_GLOBAL_RULES)
    
    return json.loads(DEFAULT_SINGBOX_SMART_RULES)

def generate_clash_yaml(nodes, user=None, warning_msg=None, server_country_map=None):
    if warning_msg:
        cfg = {
            "port": 7890,
            "socks-port": 7891,
            "allow-lan": False,
            "mode": "rule",
            "log-level": "info",
            "proxies": [
                {
                    "name": warning_msg,
                    "type": "socks5",
                    "server": "127.0.0.1",
                    "port": 1080
                }
            ],
            "proxy-groups": [
                {
                    "name": "PROXY",
                    "type": "select",
                    "proxies": [warning_msg]
                }
            ],
            "rules": [
                "MATCH,DIRECT"
            ]
        }
        try:
            import yaml
            return yaml.dump(cfg, allow_unicode=True, sort_keys=False)
        except Exception:
            return f"""port: 7890
socks-port: 7891
mode: rule
proxies:
  - name: "{warning_msg}"
    type: socks5
    server: 127.0.0.1
    port: 1080
proxy-groups:
  - name: PROXY
    type: select
    proxies:
      - "{warning_msg}"
rules:
  - MATCH,DIRECT
"""

    info_proxies = []
    info_names = []
    if user:
        for title in build_subscription_info_nodes(user):
            info_proxies.append({
                "name": title,
                "type": "socks5",
                "server": "127.0.0.1",
                "port": 0
            })
            info_names.append(title)

    proxies = []
    names = []
    for n in nodes:
        proto = n.get("protocol")
        host = n.get("server_host") or "189.24.108.25"
        port = int(n.get("port") or 20443)
        uuid_str = n.get("uuid") or ""
        pwd_str = n.get("password") or uuid_str
        if user:
            u_uuid, u_pwd = ensure_user_credentials(user)
            uuid_str = u_uuid
            pwd_str = u_pwd

        name = format_node_display_name(n, server_country_map)
        base_name = name
        counter = 2
        while name in names:
            name = f"{base_name} ({counter})"
            counter += 1

        proxy_item = None
        if proto == "vless_reality":
            pbk = n.get("public_key") or ""
            sid = n.get("short_id") or ""
            sni = n.get("sni") or "www.apple.com"
            flow = n.get("flow") or "xtls-rprx-vision"
            proxy_item = {
                "name": name,
                "type": "vless",
                "server": host,
                "port": port,
                "uuid": uuid_str,
                "network": "tcp",
                "tls": True,
                "udp": True,
                "flow": flow,
                "servername": sni,
                "reality-opts": {
                    "public-key": pbk,
                    "short-id": sid
                },
                "client-fingerprint": "chrome"
            }
        elif proto == "vless_reality_xhttp":
            pbk = n.get("public_key") or ""
            sid = n.get("short_id") or ""
            sni = n.get("sni") or "www.apple.com"
            xpath = n.get("ws_path") or "/xhttp"
            proxy_item = {
                "name": name,
                "type": "vless",
                "server": host,
                "port": port,
                "uuid": uuid_str,
                "network": "xhttp",
                "tls": True,
                "udp": True,
                "servername": sni,
                "reality-opts": {
                    "public-key": pbk,
                    "short-id": sid
                },
                "client-fingerprint": "chrome",
                "xhttp-opts": {
                    "path": xpath,
                    "mode": "auto"
                }
            }
        elif proto == "vless_ws":
            ws_path = n.get("ws_path") or "/ws-proxy"
            proxy_item = {
                "name": name,
                "type": "vless",
                "server": host,
                "port": port,
                "uuid": uuid_str,
                "network": "ws",
                "tls": False,
                "udp": True,
                "ws-opts": {
                    "path": ws_path
                }
            }
        elif proto == "vmess_ws":
            ws_path = n.get("ws_path") or "/vmess-ws"
            proxy_item = {
                "name": name,
                "type": "vmess",
                "server": host,
                "port": port,
                "uuid": uuid_str,
                "alterId": 0,
                "cipher": "auto",
                "network": "ws",
                "tls": False,
                "udp": True,
                "ws-opts": {
                    "path": ws_path
                }
            }
        elif proto == "hysteria2":
            sni = n.get("sni") or "bing.com"
            proxy_item = {
                "name": name,
                "type": "hysteria2",
                "server": host,
                "port": port,
                "password": pwd_str,
                "sni": sni,
                "skip-cert-verify": True
            }
        elif proto == "trojan":
            sni = n.get("sni") or host
            proxy_item = {
                "name": name,
                "type": "trojan",
                "server": host,
                "port": port,
                "password": pwd_str,
                "sni": sni,
                "skip-cert-verify": True,
                "udp": True
            }
        elif proto == "ss2022":
            method = n.get("method") or "2022-blake3-aes-128-gcm"
            proxy_item = {
                "name": name,
                "type": "ss",
                "server": host,
                "port": port,
                "cipher": method,
                "password": pwd_str,
                "udp": True
            }
        elif proto == "socks5":
            uname = (n.get("username") or "").strip()
            if user:
                uname = user.get("username", "")
            proxy_item = {
                "name": name,
                "type": "socks5",
                "server": host,
                "port": port
            }
            if uname:
                proxy_item["username"] = uname
                proxy_item["password"] = pwd_str

        if proxy_item:
            proxies.append(proxy_item)
            names.append(name)

    if not names:
        names = ["DIRECT"]

    clash_cfg = {
        "port": 7890,
        "socks-port": 7891,
        "allow-lan": False,
        "mode": "rule",
        "log-level": "info",
        "unified-delay": True,
        "proxies": info_proxies + proxies,
        "proxy-groups": [
            {
                "name": "节点选择",
                "type": "select",
                "proxies": ["自动选择"] + info_names + names
            },
            {
                "name": "自动选择",
                "type": "url-test",
                "url": "http://www.gstatic.com/generate_204",
                "interval": 300,
                "tolerance": 50,
                "proxies": list(names)
            }
        ],
        "rules": get_active_clash_rules()
    }

    try:
        import yaml
        return yaml.dump(clash_cfg, allow_unicode=True, sort_keys=False)
    except Exception:
        lines = [
            "port: 7890",
            "socks-port: 7891",
            "allow-lan: false",
            "mode: rule",
            "log-level: info",
            "unified-delay: true",
            "proxies:"
        ]
        for p in (info_proxies + proxies):
            lines.append(f"  - name: \"{p['name']}\"")
            lines.append(f"    type: {p['type']}")
            lines.append(f"    server: \"{p['server']}\"")
            lines.append(f"    port: {p['port']}")
            if "uuid" in p:
                lines.append(f"    uuid: \"{p['uuid']}\"")
            if "password" in p:
                lines.append(f"    password: \"{p['password']}\"")
            if "network" in p:
                lines.append(f"    network: {p['network']}")
            if "tls" in p:
                lines.append(f"    tls: {'true' if p['tls'] else 'false'}")
            if "udp" in p:
                lines.append(f"    udp: {'true' if p['udp'] else 'false'}")
            if "flow" in p and p['flow']:
                lines.append(f"    flow: {p['flow']}")
            if "servername" in p:
                lines.append(f"    servername: \"{p['servername']}\"")
            if "sni" in p:
                lines.append(f"    sni: \"{p['sni']}\"")
            if "skip-cert-verify" in p:
                lines.append("    skip-cert-verify: true")
            if "reality-opts" in p:
                lines.append("    reality-opts:")
                lines.append(f"      public-key: \"{p['reality-opts']['public-key']}\"")
                lines.append(f"      short-id: \"{p['reality-opts']['short-id']}\"")
            if "client-fingerprint" in p:
                lines.append(f"    client-fingerprint: {p['client-fingerprint']}")
        lines.append("proxy-groups:")
        lines.append("  - name: \"节点选择\"")
        lines.append("    type: select")
        lines.append("    proxies:")
        lines.append("      - \"自动选择\"")
        for iname in info_names:
            lines.append(f"      - \"{iname}\"")
        for n in names:
            lines.append(f"      - \"{n}\"")
        lines.append("  - name: \"自动选择\"")
        lines.append("    type: url-test")
        lines.append("    url: http://www.gstatic.com/generate_204")
        lines.append("    interval: 300")
        lines.append("    tolerance: 50")
        lines.append("    proxies:")
        for n in names:
            lines.append(f"      - \"{n}\"")
        lines.append("rules:")
        for r in clash_cfg["rules"]:
            lines.append(f"  - {r}")
        return "\n".join(lines)


def generate_singbox_client_config(nodes, user=None, warning_msg=None, server_country_map=None) -> str:
    """生成标准 Sing-box 客户端跨平台通用订阅 JSON 结构 (兼容 SFA / SFI / Sing-box Desktop)"""
    if warning_msg:
        cfg = {
            "version": 1,
            "outbounds": [
                {
                    "type": "socks",
                    "tag": warning_msg,
                    "server": "127.0.0.1",
                    "server_port": 1080
                }
            ]
        }
        return json.dumps(cfg, indent=2, ensure_ascii=False)

    outbounds = []
    node_tags = []

    if user:
        for title in build_subscription_info_nodes(user):
            outbounds.append({
                "type": "socks",
                "tag": title,
                "server": "127.0.0.1",
                "server_port": 1080
            })
            node_tags.append(title)

    for n in nodes:
        proto = n.get("protocol")
        host = n.get("server_host") or "189.24.108.25"
        port = int(n.get("port") or 20443)
        uuid_str = n.get("uuid") or ""
        pwd_str = n.get("password") or uuid_str
        if user:
            u_uuid, u_pwd = ensure_user_credentials(user)
            uuid_str = u_uuid
            pwd_str = u_pwd

        tag = format_node_display_name(n, server_country_map)
        base_tag = tag
        counter = 2
        while tag in node_tags:
            tag = f"{base_tag} ({counter})"
            counter += 1

        node_item = None
        if proto in ("vless_reality", "vless_reality_xhttp"):
            pbk = n.get("public_key") or ""
            sid = n.get("short_id") or ""
            sni = n.get("sni") or "www.apple.com"
            flow = n.get("flow") or "xtls-rprx-vision"
            node_item = {
                "type": "vless",
                "tag": tag,
                "server": host,
                "server_port": port,
                "uuid": uuid_str,
                "tls": {
                    "enabled": True,
                    "server_name": sni,
                    "reality": {
                        "enabled": True,
                        "public_key": pbk,
                        "short_id": sid
                    }
                }
            }
            if flow:
                node_item["flow"] = flow
            if proto == "vless_reality_xhttp":
                xpath = n.get("ws_path") or "/xhttp"
                node_item["transport"] = {
                    "type": "http",
                    "path": xpath
                }
        elif proto == "hysteria2":
            sni = n.get("sni") or "bing.com"
            node_item = {
                "type": "hysteria2",
                "tag": tag,
                "server": host,
                "server_port": port,
                "password": pwd_str,
                "tls": {
                    "enabled": True,
                    "server_name": sni,
                    "insecure": True
                }
            }
        elif proto == "tuic":
            sni = n.get("sni") or "bing.com"
            node_item = {
                "type": "tuic",
                "tag": tag,
                "server": host,
                "server_port": port,
                "uuid": uuid_str,
                "password": pwd_str,
                "congestion_controller": "bbr",
                "tls": {
                    "enabled": True,
                    "server_name": sni,
                    "insecure": True
                }
            }
        elif proto == "trojan":
            sni = n.get("sni") or host
            node_item = {
                "type": "trojan",
                "tag": tag,
                "server": host,
                "server_port": port,
                "password": pwd_str,
                "tls": {
                    "enabled": True,
                    "server_name": sni
                }
            }
        elif proto == "ss2022":
            method = n.get("method") or "2022-blake3-aes-128-gcm"
            node_item = {
                "type": "shadowsocks",
                "tag": tag,
                "server": host,
                "server_port": port,
                "method": method,
                "password": pwd_str
            }
        elif proto == "vless_ws":
            ws_path = n.get("ws_path") or "/ws-proxy"
            node_item = {
                "type": "vless",
                "tag": tag,
                "server": host,
                "server_port": port,
                "uuid": uuid_str,
                "transport": {
                    "type": "ws",
                    "path": ws_path
                }
            }
        elif proto == "vmess_ws":
            ws_path = n.get("ws_path") or "/ws-proxy"
            node_item = {
                "type": "vmess",
                "tag": tag,
                "server": host,
                "server_port": port,
                "uuid": uuid_str,
                "security": "auto",
                "transport": {
                    "type": "ws",
                    "path": ws_path
                }
            }

        if node_item:
            outbounds.append(node_item)
            node_tags.append(tag)

    valid_nodes = [t for t in node_tags if not t.startswith("📊") and not t.startswith("⏳")]
    selector_tags = (["AUTO"] + valid_nodes + ["DIRECT"]) if valid_nodes else ["DIRECT"]
    urltest_tags = valid_nodes if valid_nodes else ["DIRECT"]

    config = {
        "version": 1,
        "outbounds": [
            {
                "type": "selector",
                "tag": "PROXY",
                "outbounds": selector_tags,
                "default": selector_tags[0]
            },
            {
                "type": "urltest",
                "tag": "AUTO",
                "outbounds": urltest_tags,
                "url": "https://www.gstatic.com/generate_204",
                "interval": "3m",
                "tolerance": 50
            }
        ] + outbounds + [
            {
                "type": "direct",
                "tag": "DIRECT"
            },
            {
                "type": "block",
                "tag": "BLOCK"
            },
            {
                "type": "dns",
                "tag": "dns-out"
            }
        ],
        "route": {
            "rules": get_active_singbox_rules(),
            "auto_detect_interface": True
        }
    }
    return json.dumps(config, indent=2, ensure_ascii=False)

def is_local_node(node):
    s_id = node.get("server_id", 0)
    s_host = node.get("server_host", "")
    s_name = node.get("server_name", "")
    return s_id == 0 or (s_host in LOCAL_HOSTS) or (s_name == "本机")

def build_inbounds_for_nodes(nodes, active_users=None):
    if active_users is None:
        active_users = get_active_users()

    inbounds = []
    for n in nodes:
        proto = n["protocol"]
        port = n["port"]
        uid = n.get("uuid") or ""
        pwd = n.get("password") or uid
        tag = f"inbound-{n.get('id', port)}"

        if proto == "vless_reality":
            vless_clients = []
            seen_ids = set()
            if uid and uid not in seen_ids:
                seen_ids.add(uid)
                vless_clients.append({
                    "id": uid,
                    "email": "default@vless",
                    "flow": n.get("flow") or "xtls-rprx-vision"
                })
            for u in active_users:
                u_uuid, _ = ensure_user_credentials(u)
                if u_uuid not in seen_ids:
                    seen_ids.add(u_uuid)
                    vless_clients.append({
                        "id": u_uuid,
                        "email": f"user_{u['id']}",
                        "flow": n.get("flow") or "xtls-rprx-vision"
                    })

            inbounds.append({
                "tag": tag,
                "listen": "::",
                "port": port,
                "protocol": "vless",
                "settings": {
                    "clients": vless_clients,
                    "decryption": "none"
                },
                "streamSettings": {
                    "network": "tcp",
                    "security": "reality",
                    "realitySettings": {
                        "show": False,
                        "dest": n.get("dest") or "www.apple.com:443",
                        "xver": 0,
                        "serverNames": [n.get("sni") or "www.apple.com"],
                        "privateKey": n.get("private_key") or "",
                        "shortIds": [n.get("short_id") or ""]
                    }
                },
                "sniffing": { "enabled": True, "destOverride": ["http", "tls", "quic"] }
            })
        elif proto == "vless_reality_xhttp":
            xpath = n.get("ws_path") or "/xhttp"
            if not xpath.startswith("/"):
                xpath = "/" + xpath
            vless_clients = []
            seen_ids = set()
            if uid and uid not in seen_ids:
                seen_ids.add(uid)
                vless_clients.append({ "id": uid, "email": "default@vless" })
            for u in active_users:
                u_uuid, _ = ensure_user_credentials(u)
                if u_uuid not in seen_ids:
                    seen_ids.add(u_uuid)
                    vless_clients.append({ "id": u_uuid, "email": f"user_{u['id']}" })

            inbounds.append({
                "tag": tag,
                "listen": "::",
                "port": port,
                "protocol": "vless",
                "settings": {
                    "clients": vless_clients,
                    "decryption": "none"
                },
                "streamSettings": {
                    "network": "xhttp",
                    "security": "reality",
                    "realitySettings": {
                        "show": False,
                        "dest": n.get("dest") or "www.apple.com:443",
                        "xver": 0,
                        "serverNames": [n.get("sni") or "www.apple.com"],
                        "privateKey": n.get("private_key") or "",
                        "shortIds": [n.get("short_id") or ""]
                    },
                    "xhttpSettings": {
                        "path": xpath,
                        "mode": "auto"
                    }
                },
                "sniffing": { "enabled": True, "destOverride": ["http", "tls", "quic"] }
            })
        elif proto == "vless_ws":
            ws_path = n.get("ws_path") or "/ws-proxy"
            if not ws_path.startswith("/"):
                ws_path = "/" + ws_path
            vless_clients = []
            seen_ids = set()
            if uid and uid not in seen_ids:
                seen_ids.add(uid)
                vless_clients.append({ "id": uid, "email": "default@vless" })
            for u in active_users:
                u_uuid, _ = ensure_user_credentials(u)
                if u_uuid not in seen_ids:
                    seen_ids.add(u_uuid)
                    vless_clients.append({ "id": u_uuid, "email": f"user_{u['id']}" })

            inbounds.append({
                "tag": tag,
                "listen": "::",
                "port": port,
                "protocol": "vless",
                "settings": {
                    "clients": vless_clients,
                    "decryption": "none"
                },
                "streamSettings": {
                    "network": "ws",
                    "security": "none",
                    "wsSettings": { "path": ws_path }
                }
            })
        elif proto == "vmess_ws":
            ws_path = n.get("ws_path") or "/vmess-ws"
            if not ws_path.startswith("/"):
                ws_path = "/" + ws_path
            vmess_clients = []
            seen_ids = set()
            if uid and uid not in seen_ids:
                seen_ids.add(uid)
                vmess_clients.append({ "id": uid, "alterId": 0, "email": "default@vmess" })
            for u in active_users:
                u_uuid, _ = ensure_user_credentials(u)
                if u_uuid not in seen_ids:
                    seen_ids.add(u_uuid)
                    vmess_clients.append({ "id": u_uuid, "alterId": 0, "email": f"user_{u['id']}" })

            inbounds.append({
                "tag": tag,
                "listen": "::",
                "port": port,
                "protocol": "vmess",
                "settings": {
                    "clients": vmess_clients
                },
                "streamSettings": {
                    "network": "ws",
                    "security": "none",
                    "wsSettings": { "path": ws_path }
                },
                "sniffing": { "enabled": True, "destOverride": ["http", "tls", "quic"] }
            })
        elif proto == "trojan":
            trojan_clients = []
            seen_pwds = set()
            if pwd and pwd not in seen_pwds:
                seen_pwds.add(pwd)
                trojan_clients.append({ "password": pwd, "email": "default@trojan" })
            for u in active_users:
                _, u_pwd = ensure_user_credentials(u)
                if u_pwd not in seen_pwds:
                    seen_pwds.add(u_pwd)
                    trojan_clients.append({ "password": u_pwd, "email": f"user_{u['id']}" })

            inbounds.append({
                "tag": tag,
                "listen": "::",
                "port": port,
                "protocol": "trojan",
                "settings": {
                    "clients": trojan_clients
                },
                "streamSettings": { "network": "tcp", "security": "none" }
            })
        elif proto == "ss2022":
            method = n.get("method") or "2022-blake3-aes-128-gcm"
            inbounds.append({
                "tag": tag,
                "listen": "::",
                "port": port,
                "protocol": "shadowsocks",
                "settings": {
                    "method": method,
                    "password": pwd,
                    "network": "tcp,udp"
                }
            })
        elif proto == "socks5":
            uname = (n.get("username") or "").strip()
            settings = {
                "auth": "password" if uname else "noauth",
                "udp": True
            }
            if uname:
                settings["accounts"] = [{ "user": uname, "pass": pwd }]
            inbounds.append({
                "tag": tag,
                "listen": "::",
                "port": port,
                "protocol": "socks",
                "settings": settings
            })
    return inbounds

def build_singbox_inbounds_for_nodes(nodes, active_users=None):
    if active_users is None:
        active_users = get_active_users()

    inbounds = []
    for n in nodes:
        proto = n["protocol"]
        port = int(n["port"])
        pwd = n.get("password") or n.get("uuid") or "hy2password"
        sni = n.get("sni") or "bing.com"
        tag = f"hy2-in-{n.get('id', port)}"
        masq = n.get("dest") or "https://www.bing.com"
        if not masq.startswith("http://") and not masq.startswith("https://"):
            host_only = masq.split(":")[0]
            masq = f"https://{host_only}"

        if proto == "hysteria2":
            hy2_users = []
            seen_pwds = set()
            if pwd and pwd not in seen_pwds:
                seen_pwds.add(pwd)
                hy2_users.append({ "name": "default", "password": pwd })
            for u in active_users:
                _, u_pwd = ensure_user_credentials(u)
                if u_pwd not in seen_pwds:
                    seen_pwds.add(u_pwd)
                    hy2_users.append({ "name": f"user_{u['id']}", "password": u_pwd })

            inbounds.append({
                "type": "hysteria2",
                "tag": tag,
                "listen": "::",
                "listen_port": port,
                "users": hy2_users,
                "ignore_client_bandwidth": True,
                "tls": {
                    "enabled": True,
                    "server_name": sni,
                    "alpn": ["h3"],
                    "certificate_path": SINGBOX_CERT,
                    "key_path": SINGBOX_KEY
                },
                "masquerade": masq
            })
    return inbounds

def apply_singbox_config():
    if not os.path.exists(SINGBOX_BIN):
        return False, "未找到 sing-box 核心"
    os.makedirs(os.path.dirname(SINGBOX_CONFIG), exist_ok=True)
    conn = get_db()
    cur = conn.execute("SELECT * FROM proxy_node WHERE enabled = 1")
    all_nodes = [dict(r) for r in cur.fetchall()]
    conn.close()

    local_nodes = [n for n in all_nodes if is_local_node(n) and not n.get("is_relay") and n["protocol"] in ("hysteria2", "tuic")]
    inbounds = build_singbox_inbounds_for_nodes(local_nodes)

    os.makedirs("/var/log/sing-box", exist_ok=True)
    config = {
        "log": {
            "level": "warn",
            "timestamp": True,
            "output": "/var/log/sing-box/access.log"
        },
        "inbounds": inbounds,
        "outbounds": [
            { "type": "direct", "tag": "direct" },
            { "type": "block", "tag": "block" }
        ]
    }

    with open(SINGBOX_CONFIG, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    test_res = subprocess.run([SINGBOX_BIN, "check", "-c", SINGBOX_CONFIG], capture_output=True, text=True)
    if test_res.returncode == 0:
        subprocess.run(["systemctl", "restart", "sing-box"], capture_output=True)
        return True, "Sing-box 配置已生效并重启成功"
    else:
        return False, f"Sing-box 配置校验失败: {test_res.stderr or test_res.stdout}"

def install_local_xray():
    os.makedirs("/etc/xray", exist_ok=True)
    os.makedirs("/usr/local/share/xray", exist_ok=True)
    os.makedirs("/usr/local/etc/xray", exist_ok=True)
    
    local_zip = "/opt/monitor/scripts/Xray-linux-64.zip"
    tmp_dir = "/tmp/xray_inst"
    os.makedirs(tmp_dir, exist_ok=True)
    
    if os.path.exists(local_zip):
        subprocess.run(["unzip", "-o", local_zip, "-d", tmp_dir], capture_output=True)
    else:
        cmd = "curl -fsSL https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-64.zip -o /tmp/xray.zip && unzip -o /tmp/xray.zip -d /tmp/xray_inst"
        subprocess.run(cmd, shell=True, capture_output=True)

    bin_path = os.path.join(tmp_dir, "xray")
    if os.path.exists(bin_path):
        subprocess.run(["install", "-m", "0755", bin_path, XRAY_BIN], capture_output=True)
        for dat in ["geoip.dat", "geosite.dat"]:
            dp = os.path.join(tmp_dir, dat)
            if os.path.exists(dp):
                subprocess.run(["cp", "-f", dp, "/usr/local/share/xray/"], capture_output=True)
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
    else:
        return False, "解压 Xray 二进制失败"

    svc = (
        "[Unit]\n"
        "Description=Xray Service\n"
        "After=network.target nss-lookup.target\n\n"
        "[Service]\n"
        "Type=simple\n"
        "User=root\n"
        "ExecStart=/usr/local/bin/xray run -config /etc/xray/config.json\n"
        "Restart=always\n"
        "RestartSec=3\n"
        "LimitNPROC=10000\n"
        "LimitNOFILE=1000000\n\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    )
    with open("/etc/systemd/system/xray.service", "w") as f:
        f.write(svc)
    subprocess.run(["systemctl", "daemon-reload"], capture_output=True)
    subprocess.run(["systemctl", "enable", "xray"], capture_output=True)
    apply_xray_config()
    subprocess.run(["systemctl", "restart", "xray"], capture_output=True)
    return True, "Xray 核心已成功安装并启动"

def uninstall_local_xray():
    subprocess.run(["systemctl", "stop", "xray"], capture_output=True)
    subprocess.run(["systemctl", "disable", "xray"], capture_output=True)
    if os.path.exists(XRAY_BIN):
        try:
            os.remove(XRAY_BIN)
        except Exception:
            pass
    return True, "Xray 核心已卸载并停止服务"

def install_local_singbox():
    os.makedirs("/etc/sing-box", exist_ok=True)
    os.makedirs("/var/log/sing-box", exist_ok=True)
    
    local_tar = "/opt/monitor/scripts/sing-box-linux-amd64.tar.gz"
    tmp_dir = "/tmp/sb_inst"
    os.makedirs(tmp_dir, exist_ok=True)
    
    if os.path.exists(local_tar):
        subprocess.run(["tar", "-xzf", local_tar, "-C", tmp_dir], capture_output=True)
    else:
        cmd = "curl -fsSL https://github.com/SagerNet/sing-box/releases/download/v1.14.1/sing-box-1.14.1-linux-amd64.tar.gz -o /tmp/singbox.tar.gz && tar -xzf /tmp/singbox.tar.gz -C /tmp/sb_inst"
        subprocess.run(cmd, shell=True, capture_output=True)
        
    sb_bin = None
    for root, dirs, files in os.walk(tmp_dir):
        if "sing-box" in files:
            sb_bin = os.path.join(root, "sing-box")
            break
            
    if sb_bin:
        subprocess.run(["install", "-m", "0755", sb_bin, SINGBOX_BIN], capture_output=True)
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
    else:
        return False, "未找到 sing-box 二进制文件"

    if not os.path.exists(SINGBOX_CERT) or not os.path.exists(SINGBOX_KEY):
        subprocess.run([
            "openssl", "req", "-x509", "-nodes", "-newkey", "ec",
            "-pkeyopt", "ec_paramgen_curve:prime256v1",
            "-keyout", SINGBOX_KEY, "-out", SINGBOX_CERT,
            "-subj", "/CN=bing.com", "-days", "36500",
            "-addext", "subjectAltName=DNS:bing.com"
        ], capture_output=True)

    svc = (
        "[Unit]\n"
        "Description=sing-box Service\n"
        "Documentation=https://sing-box.sagernet.org/\n"
        "After=network.target nss-lookup.target\n\n"
        "[Service]\n"
        "Type=simple\n"
        "User=root\n"
        "WorkingDirectory=/etc/sing-box\n"
        "ExecStart=/usr/local/bin/sing-box run -c /etc/sing-box/config.json\n"
        "Restart=always\n"
        "RestartSec=3\n"
        "LimitNPROC=10000\n"
        "LimitNOFILE=1000000\n\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    )
    with open("/etc/systemd/system/sing-box.service", "w") as f:
        f.write(svc)
    subprocess.run(["systemctl", "daemon-reload"], capture_output=True)
    subprocess.run(["systemctl", "enable", "sing-box"], capture_output=True)
    apply_singbox_config()
    subprocess.run(["systemctl", "restart", "sing-box"], capture_output=True)
    return True, "Sing-box 核心已成功安装并启动"

def uninstall_local_singbox():
    subprocess.run(["systemctl", "stop", "sing-box"], capture_output=True)
    subprocess.run(["systemctl", "disable", "sing-box"], capture_output=True)
    if os.path.exists(SINGBOX_BIN):
        try:
            os.remove(SINGBOX_BIN)
        except Exception:
            pass
    return True, "Sing-box 核心已卸载并停止服务"

def install_local_realm():
    os.makedirs("/etc/realm", exist_ok=True)
    local_tar = "/opt/monitor/scripts/realm-x86_64-unknown-linux-musl.tar.gz"
    tmp_dir = "/tmp/realm_inst"
    os.makedirs(tmp_dir, exist_ok=True)

    if os.path.exists(local_tar):
        subprocess.run(["tar", "-xzf", local_tar, "-C", tmp_dir], capture_output=True)
    else:
        cmd = "curl -fsSL https://github.com/zhboner/realm/releases/latest/download/realm-x86_64-unknown-linux-musl.tar.gz -o /tmp/realm.tar.gz && tar -xzf /tmp/realm.tar.gz -C /tmp/realm_inst"
        subprocess.run(cmd, shell=True, capture_output=True)

    realm_bin = None
    for root, dirs, files in os.walk(tmp_dir):
        if "realm" in files:
            realm_bin = os.path.join(root, "realm")
            break

    if realm_bin:
        subprocess.run(["install", "-m", "0755", realm_bin, REALM_BIN], capture_output=True)
        import shutil
        shutil.rmtree(tmp_dir, ignore_errors=True)
    else:
        return False, "未找到 realm 二进制文件"

    if not os.path.exists(REALM_CONFIG):
        default_cfg = {
            "log": { "level": "warn" },
            "network": { "no_tcp": False, "use_udp": True },
            "endpoints": [
                {
                    "listen": "127.0.0.1:39998",
                    "remote": "127.0.0.1:39998"
                }
            ]
        }
        with open(REALM_CONFIG, "w", encoding="utf-8") as f:
            json.dump(default_cfg, f, indent=2)

    svc = (
        "[Unit]\n"
        "Description=Realm Port Forwarding Service\n"
        "After=network.target\n\n"
        "[Service]\n"
        "Type=simple\n"
        "User=root\n"
        "ExecStart=/usr/local/bin/realm -c /etc/realm/config.json\n"
        "Restart=always\n"
        "RestartSec=3\n"
        "LimitNOFILE=1000000\n\n"
        "[Install]\n"
        "WantedBy=multi-user.target\n"
    )
    with open("/etc/systemd/system/realm.service", "w") as f:
        f.write(svc)
    subprocess.run(["systemctl", "daemon-reload"], capture_output=True)
    subprocess.run(["systemctl", "enable", "realm"], capture_output=True)
    apply_realm_config()
    subprocess.run(["systemctl", "restart", "realm"], capture_output=True)
    return True, "Realm 端口转发核心已成功安装并启动"

def uninstall_local_realm():
    subprocess.run(["systemctl", "stop", "realm"], capture_output=True)
    subprocess.run(["systemctl", "disable", "realm"], capture_output=True)
    if os.path.exists(REALM_BIN):
        try:
            os.remove(REALM_BIN)
        except Exception:
            pass
    if os.path.exists("/etc/systemd/system/realm.service"):
        try:
            os.remove("/etc/systemd/system/realm.service")
            subprocess.run(["systemctl", "daemon-reload"], capture_output=True)
        except Exception:
            pass
    return True, "Realm 核心已卸载并停止服务"

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

def apply_realm_config():
    if not os.path.exists(REALM_BIN):
        return True, "未安装 realm 核心"

    os.makedirs(os.path.dirname(REALM_CONFIG), exist_ok=True)
    conn = get_db()
    cur = conn.execute("SELECT * FROM proxy_node WHERE enabled = 1")
    all_nodes = [dict(r) for r in cur.fetchall()]
    conn.close()

    local_relay_nodes = [n for n in all_nodes if is_local_node(n) and n.get("is_relay")]

    endpoints = []
    relay_ports = []
    for n in local_relay_nodes:
        l_port = int(n.get("port") or 0)
        r_host = (n.get("remote_host") or "").strip()
        r_port = int(n.get("remote_port") or 0)
        if l_port > 0 and r_host and r_port > 0:
            endpoints.append({
                "listen": f"0.0.0.0:{l_port}",
                "remote": f"{r_host}:{r_port}"
            })
            relay_ports.append(l_port)

    if not endpoints:
        endpoints.append({
            "listen": "127.0.0.1:39998",
            "remote": "127.0.0.1:39998"
        })

    config = {
        "log": {
            "level": "warn"
        },
        "network": {
            "no_tcp": False,
            "use_udp": True
        },
        "endpoints": endpoints
    }

    with open(REALM_CONFIG, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    if relay_ports:
        allow_ports(relay_ports)

    res = subprocess.run(["systemctl", "restart", "realm"], capture_output=True, text=True)
    if res.returncode == 0:
        return True, f"Realm 转发配置已生效 (共 {len(local_relay_nodes)} 条规则)"
    else:
        return False, f"Realm 服务重启失败: {res.stderr or res.stdout}"

def apply_all_configs():
    ok_x, msg_x = apply_xray_config()
    ok_s, msg_s = apply_singbox_config()
    ok_r, msg_r = apply_realm_config()
    return (ok_x and ok_s and ok_r), f"Xray: {msg_x} | Sing-box: {msg_s} | Realm: {msg_r}"

def apply_xray_config():
    os.makedirs(os.path.dirname(XRAY_CONFIG), exist_ok=True)
    conn = get_db()
    cur = conn.execute("SELECT * FROM proxy_node WHERE enabled = 1")
    all_nodes = [dict(r) for r in cur.fetchall()]
    conn.close()

    local_nodes = [n for n in all_nodes if is_local_node(n) and not n.get("is_relay")]
    inbounds = build_inbounds_for_nodes(local_nodes)

    if not inbounds:
        inbounds.append({
            "tag": "inbound-dummy",
            "listen": "127.0.0.1",
            "port": 39999,
            "protocol": "socks",
            "settings": { "auth": "noauth" }
        })

    api_inbound = {
        "tag": "api",
        "listen": "127.0.0.1",
        "port": 10085,
        "protocol": "dokodemo-door",
        "settings": { "address": "127.0.0.1" }
    }

    os.makedirs("/var/log/xray", exist_ok=True)
    config = {
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
        "inbounds": [api_inbound] + inbounds,
        "outbounds": [
            { "protocol": "freedom", "tag": "direct", "settings": { "domainStrategy": "UseIPv4" } },
            { "protocol": "blackhole", "tag": "block" },
            { "protocol": "freedom", "tag": "api" }
        ],
        "routing": {
            "rules": [
                {
                    "inboundTag": ["api"],
                    "outboundTag": "api",
                    "type": "field"
                }
            ]
        }
    }

    with open(XRAY_CONFIG, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    test_res = subprocess.run([XRAY_BIN, "run", "-test", "-config", XRAY_CONFIG], capture_output=True, text=True)
    if test_res.returncode == 0:
        subprocess.run(["systemctl", "restart", "xray"], capture_output=True)
        return True, "Xray 配置已生效并重启成功"
    else:
        return False, f"Xray 配置测试失败: {test_res.stderr}"

class ProxyHandler(BaseHTTPRequestHandler):
    def send_text(self, text, code=200, content_type="text/plain; charset=utf-8"):
        body = text.encode("utf-8") if isinstance(text, str) else text
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        # 0. One-click deploy script for remote agents
        if path == "/proxy-agent.sh":
            self.send_text(PROXY_AGENT_SH, 200, "text/x-shellscript; charset=utf-8")
            return
        elif path == "/api/proxy/agent-client-script":
            self.send_text(PROXY_AGENT_PY, 200, "text/x-python; charset=utf-8")
            return

        # License status API
        if path == "/api/proxy/license/status":
            # 若距离上次在线同步超过 20 秒，或带有 ?sync=1，立即进行一次快速在线心跳打卡与黑名单同步
            sync_param = qs.get("sync", ["0"])[0]
            conn_chk = get_db()
            cur = conn_chk.cursor()
            cur.execute("SELECT value FROM setting WHERE key='license_last_sync_ts'")
            row = cur.fetchone()
            last_sync_ts = int(row[0]) if row and row[0] and row[0].isdigit() else 0
            conn_chk.close()

            if sync_param == "1" or (time.time() - last_sync_ts) > 20:
                license_guard.ping_auth_server(DB_PATH)

            conn = get_db()
            lic_status = license_guard.get_current_license_status(conn)
            
            # 统计当前资源占用
            server_count = conn.execute("SELECT COUNT(*) FROM node").fetchone()[0]
            node_count = conn.execute("SELECT COUNT(*) FROM proxy_node").fetchone()[0]
            user_count = conn.execute("SELECT COUNT(*) FROM proxy_user WHERE is_admin = 0").fetchone()[0]
            conn.close()

            max_servers = lic_status.get("max_servers", 1)
            max_nodes = lic_status.get("max_nodes", 1)
            max_users = lic_status.get("max_users", 1)

            lic_status["limits"] = {
                "max_servers": max_servers,
                "max_nodes": max_nodes,
                "max_users": max_users
            }

            lic_status["usage"] = {
                "server_count": server_count,
                "node_count": node_count,
                "user_count": user_count,
                "free_limits": {
                    "max_servers": 1,
                    "max_nodes": 1,
                    "max_users": 1
                }
            }
            self.send_json(lic_status)
            return

        # 1. Client subscription endpoint (Authenticated via token)
        if path == "/api/proxy/sub":
            token = qs.get("token", [""])[0]
            if not token:
                self.send_response(403)
                self.end_headers()
                self.wfile.write(b"Missing token")
                return

            conn = get_db()
            u_cur = conn.execute("SELECT * FROM proxy_user WHERE sub_token = ?", (token,))
            user_row = u_cur.fetchone()
            if not user_row:
                legacy_token = get_sub_token()
                if token == legacy_token:
                    admin_cur = conn.execute("SELECT * FROM proxy_user WHERE is_admin = 1 LIMIT 1")
                    user_row = admin_cur.fetchone()

            if not user_row:
                conn.close()
                self.send_response(403)
                self.end_headers()
                self.wfile.write(b"Invalid subscription token")
                return

            user = dict(user_row)
            now = int(time.time())
            is_enabled = user.get("enabled", 1) == 1
            is_expired = user.get("expires_at", 0) > 0 and now > user.get("expires_at", 0)
            total_used = user.get("upload_bytes", 0) + user.get("download_bytes", 0)
            limit = user.get("traffic_limit_bytes", 0)
            is_over_quota = (limit > 0 and total_used >= limit)
            is_device_over = is_user_over_device_limit(user)

            u_bytes = user.get("upload_bytes", 0)
            d_bytes = user.get("download_bytes", 0)
            exp_time = user.get("expires_at", 0)
            sub_userinfo = f"upload={u_bytes}; download={d_bytes}; total={limit}; expire={exp_time}"

            ua = self.headers.get("User-Agent", "").lower()

            # 智能 UA 客户端检测引擎 (支持 Clash, Sing-box, Surge, Shadowrocket, v2rayN 等)
            force_clash = qs.get("clash", [""])[0] == "1"
            force_sb = qs.get("singbox", [""])[0] == "1" or qs.get("sb", [""])[0] == "1"
            force_b64 = qs.get("b64", [""])[0] == "1" or qs.get("v2ray", [""])[0] == "1"

            is_clash = force_clash or (not force_sb and not force_b64 and (
                "clash" in ua or "meta" in ua or "mihomo" in ua or "stash" in ua or "verge" in ua or "flclash" in ua
            ))
            is_singbox = force_sb or (not force_clash and not force_b64 and not is_clash and (
                "sing-box" in ua or "singbox" in ua or "sfa" in ua or "sfi" in ua
            ))

            if not is_enabled or is_expired or is_over_quota or is_device_over:
                conn.close()
                d_limit = user.get("device_limit", 0)
                status_reason = f"设备数超限(限制{d_limit}台)" if is_device_over else ("流量已超额" if is_over_quota else ("订阅已到期" if is_expired else "账户已停用"))
                if is_clash:
                    yaml_content = generate_clash_yaml([], user=user, warning_msg=f"⚠️ {status_reason}，请联系管理员")
                    encoded = yaml_content.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "text/yaml; charset=utf-8")
                    self.send_header("Subscription-Userinfo", sub_userinfo)
                    self.send_header("Content-Disposition", f'attachment; filename="{user.get("username", "sub")}.yaml"')
                    self.send_header("Content-Length", str(len(encoded)))
                    self.end_headers()
                    self.wfile.write(encoded)
                elif is_singbox:
                    sb_content = generate_singbox_client_config([], user=user, warning_msg=f"⚠️ {status_reason}，请联系管理员")
                    encoded = sb_content.encode("utf-8")
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Subscription-Userinfo", sub_userinfo)
                    self.send_header("Content-Disposition", f'attachment; filename="{user.get("username", "sub")}.json"')
                    self.send_header("Content-Length", str(len(encoded)))
                    self.end_headers()
                    self.wfile.write(encoded)
                else:
                    warning_link = f"vless://00000000-0000-0000-0000-000000000000@127.0.0.1:0?security=none#{quote('⚠️ ' + status_reason + '，请联系管理员')}"
                    import base64
                    encoded = base64.b64encode(warning_link.encode("utf-8"))
                    self.send_response(200)
                    self.send_header("Content-Type", "text/plain; charset=utf-8")
                    self.send_header("Subscription-Userinfo", sub_userinfo)
                    self.send_header("Content-Disposition", f'attachment; filename="{user.get("username", "sub")}.txt"')
                    self.send_header("Content-Length", str(len(encoded)))
                    self.end_headers()
                    self.wfile.write(encoded)
                return

            cur = conn.execute("SELECT * FROM proxy_node WHERE enabled = 1 ORDER BY id DESC")
            nodes = [dict(r) for r in cur.fetchall()]
            cur_nodes = conn.execute("SELECT id, ip, ipv4, country FROM node")
            server_rows = cur_nodes.fetchall()
            node_ip_map = {r["id"]: resolve_server_host(dict(r)) for r in server_rows}
            server_country_map = {r["id"]: (r["country"] or "") for r in server_rows}
            conn.close()

            for n in nodes:
                sid = n.get("server_id")
                if sid in node_ip_map and is_private_ip(n.get("server_host")):
                    n["server_host"] = node_ip_map[sid]

            if is_clash:
                yaml_content = generate_clash_yaml(nodes, user=user, server_country_map=server_country_map)
                encoded = yaml_content.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/yaml; charset=utf-8")
                self.send_header("Subscription-Userinfo", sub_userinfo)
                self.send_header("Content-Disposition", f'attachment; filename="{user.get("username", "sub")}.yaml"')
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
                return

            if is_singbox:
                sb_content = generate_singbox_client_config(nodes, user=user, server_country_map=server_country_map)
                encoded = sb_content.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Subscription-Userinfo", sub_userinfo)
                self.send_header("Content-Disposition", f'attachment; filename="{user.get("username", "sub")}.json"')
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
                return

            links = [format_node_link(n, user=user, server_country_map=server_country_map) for n in nodes if format_node_link(n, user=user, server_country_map=server_country_map)]
            info_links = []
            if user:
                for title in build_subscription_info_nodes(user):
                    info_links.append(f"vless://00000000-0000-0000-0000-000000000000@127.0.0.1:0?security=none#{quote(title)}")
            all_links = info_links + links
            import base64
            encoded = base64.b64encode("\n".join(all_links).encode("utf-8"))
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Subscription-Userinfo", sub_userinfo)
            self.send_header("Content-Disposition", f'attachment; filename="{user.get("username", "sub")}.txt"')
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return

            cur = conn.execute("SELECT * FROM proxy_node WHERE enabled = 1 ORDER BY id DESC")
            nodes = [dict(r) for r in cur.fetchall()]
            cur_nodes = conn.execute("SELECT id, ip, ipv4 FROM node")
            node_ip_map = {r["id"]: resolve_server_host(dict(r)) for r in cur_nodes.fetchall()}
            conn.close()

            for n in nodes:
                sid = n.get("server_id")
                if sid in node_ip_map and is_private_ip(n.get("server_host")):
                    n["server_host"] = node_ip_map[sid]

            if is_clash:
                yaml_content = generate_clash_yaml(nodes, user=user)
                encoded = yaml_content.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/yaml; charset=utf-8")
                self.send_header("Subscription-Userinfo", sub_userinfo)
                self.send_header("Content-Disposition", f'attachment; filename="{user.get("username", "sub")}.yaml"')
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
                return

            links = [format_node_link(n, user=user) for n in nodes if format_node_link(n, user=user)]
            info_links = []
            if user:
                for title in build_subscription_info_nodes(user):
                    info_links.append(f"vless://00000000-0000-0000-0000-000000000000@127.0.0.1:0?security=none#{quote(title)}")
            all_links = info_links + links
            import base64
            encoded = base64.b64encode("\n".join(all_links).encode("utf-8"))
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Subscription-Userinfo", sub_userinfo)
            self.send_header("Content-Disposition", f'attachment; filename="{user.get("username", "sub")}.txt"')
            self.send_header("Content-Length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
            return

        # 2. Remote agent configuration pull (Authenticated via node token)
        if path == "/api/proxy/agent-sync":
            token = qs.get("token", [""])[0]
            if not token:
                self.send_json({"ok": False, "error": "Missing token"}, 400)
                return

            conn = get_db()
            cur = conn.execute("SELECT id, name, ip, ipv4 FROM node WHERE token = ?", (token,))
            node_row = cur.fetchone()
            if not node_row:
                conn.close()
                self.send_json({"ok": False, "error": "Invalid node token"}, 403)
                return

            node_id = node_row["id"]
            cur_nodes = conn.execute("SELECT * FROM proxy_node WHERE server_id = ? AND enabled = 1", (node_id,))
            server_nodes = [dict(r) for r in cur_nodes.fetchall()]
            conn.close()

            xray_nodes = [n for n in server_nodes if n["protocol"] not in ("hysteria2", "tuic") and not n.get("is_relay")]
            singbox_nodes = [n for n in server_nodes if n["protocol"] in ("hysteria2", "tuic") and not n.get("is_relay")]
            inbounds = build_inbounds_for_nodes(xray_nodes)
            singbox_inbounds = build_singbox_inbounds_for_nodes(singbox_nodes)
            self.send_json({
                "ok": True,
                "node_id": node_id,
                "server_name": node_row["name"],
                "inbounds": inbounds,
                "xray_inbounds": inbounds,
                "singbox_inbounds": singbox_inbounds
            })
            return

        # Theme style endpoint
        if path == "/api/proxy/theme":
            user = get_current_user(self.headers)
            theme = "default"
            if user:
                theme = user.get("theme_style") or (get_setting("admin_theme_style", "default") if user.get("is_admin") else "default")
            else:
                theme = get_setting("admin_theme_style", "default")
            self.send_json({"ok": True, "theme_style": theme or "default"})
            return

        # 3. User authenticated endpoints (Regular user or Admin)
        if path == "/api/proxy/user/me":
            user = get_current_user(self.headers)
            if not user:
                self.send_json({"ok": False, "error": "未登录"}, 401)
                return
            limit = user.get("traffic_limit_bytes", 0)
            used = user.get("upload_bytes", 0) + user.get("download_bytes", 0)
            remaining = max(0, limit - used) if limit > 0 else -1
            now = int(time.time())
            is_expired = user.get("expires_at", 0) > 0 and now > user.get("expires_at", 0)
            is_over = limit > 0 and used >= limit
            is_dev_over = is_user_over_device_limit(user)
            online_devs = get_user_online_device_count(user["id"])
            device_limit = user.get("device_limit", 0)
            
            status_text = "disabled" if user.get("enabled", 1) == 0 else ("expired" if is_expired else ("over_quota" if is_over else ("over_device_limit" if is_dev_over else "active")))
            
            sub_token = user.get("sub_token") or get_sub_token()
            base_url = get_request_base_url(self.headers)
            user_theme = user.get("theme_style") or (get_setting("admin_theme_style", "default") if user.get("is_admin") else "default")
            self.send_json({
                "ok": True,
                "user": {
                    "id": user.get("id"),
                    "username": user.get("username"),
                    "is_admin": bool(user.get("is_admin", 0)),
                    "sub_token": sub_token,
                    "sub_url": f"{base_url}/api/proxy/sub?token={sub_token}",
                    "clash_url": f"{base_url}/api/proxy/sub?token={sub_token}&clash=1",
                    "singbox_url": f"{base_url}/api/proxy/sub?token={sub_token}&singbox=1",
                    "traffic_limit_bytes": limit,
                    "device_limit": device_limit,
                    "online_devices": online_devs,
                    "upload_bytes": user.get("upload_bytes", 0),
                    "download_bytes": user.get("download_bytes", 0),
                    "total_used_bytes": used,
                    "remaining_bytes": remaining,
                    "expires_at": user.get("expires_at", 0),
                    "enabled": user.get("enabled", 1),
                    "status": status_text,
                    "created_at": user.get("created_at", 0),
                    "theme_style": user_theme or "default"
                }
            })
            return

        if path == "/api/proxy/user/nodes":
            user = get_current_user(self.headers)
            if not user:
                self.send_json({"ok": False, "error": "未登录"}, 401)
                return
            conn = get_db()
            cur = conn.execute("SELECT id, server_id, name, protocol, server_name, server_host, port, enabled FROM proxy_node WHERE enabled = 1 ORDER BY id DESC")
            nodes = [dict(r) for r in cur.fetchall()]
            cur_nodes = conn.execute("SELECT id, ip, ipv4, country FROM node")
            server_rows = cur_nodes.fetchall()
            node_ip_map = {r["id"]: resolve_server_host(dict(r)) for r in server_rows}
            server_country_map = {r["id"]: (r["country"] or "") for r in server_rows}
            conn.close()
            for n in nodes:
                sid = n.get("server_id")
                if sid in node_ip_map and is_private_ip(n.get("server_host")):
                    n["server_host"] = node_ip_map[sid]
                n["flag"] = resolve_node_flag(n, server_country_map)
                n["display_name"] = format_node_display_name(n, server_country_map)
            self.send_json({"ok": True, "nodes": nodes})
            return

        if path.startswith("/api/proxy/nodes/") and path.endswith("/test"):
            user = get_current_user(self.headers)
            if not user:
                self.send_json({"ok": False, "error": "未登录"}, 401)
                return
            node_id = int(path.split("/")[-2])
            conn = get_db()
            cur = conn.execute("SELECT * FROM proxy_node WHERE id = ?", (node_id,))
            row = cur.fetchone()
            if not row:
                conn.close()
                self.send_json({"ok": False, "message": "节点不存在"}, 404)
                return
            node = dict(row)
            if is_private_ip(node.get("server_host")):
                cur_s = conn.execute("SELECT id, ip, ipv4 FROM node WHERE id = ?", (node.get("server_id"),))
                s_row = cur_s.fetchone()
                if s_row:
                    node["server_host"] = resolve_server_host(dict(s_row))
            conn.close()

            ok, msg, ms = test_node_connectivity(node)
            self.send_json({"ok": ok, "message": msg, "latency_ms": ms})
            return

        if path == "/api/proxy/unlock/config":
            enabled, custom = get_unlock_config()
            show_badges = get_setting("unlock_show_badges", "1") == "1"
            self.send_json({
                "ok": True,
                "enabled": enabled,
                "show_badges": show_badges,
                "presets": DEFAULT_UNLOCK_PRESETS,
                "custom": custom
            })
            return

        if path == "/api/proxy/unlock-status":
            conn = get_db()
            conn.row_factory = sqlite3.Row
            cur = conn.execute("SELECT * FROM node_unlock_status")
            status_map = {}
            for r in cur.fetchall():
                row = dict(r)
                nid = str(row.get("node_id"))
                raw_json = row.get("data_json")
                parsed = None
                if raw_json:
                    try:
                        parsed = json.loads(raw_json)
                    except Exception:
                        pass
                if parsed and isinstance(parsed, dict):
                    status_map[nid] = parsed
                else:
                    status_map[nid] = {
                        "netflix": {"ok": bool(row.get("netflix_ok")), "msg": row.get("netflix_msg", "")},
                        "chatgpt": {"ok": bool(row.get("chatgpt_ok")), "msg": row.get("chatgpt_msg", "")},
                        "youtube": {"ok": bool(row.get("youtube_ok")), "msg": row.get("youtube_msg", "")},
                        "disney":  {"ok": bool(row.get("disney_ok")), "msg": row.get("disney_msg", "")},
                        "region":  row.get("region", ""),
                        "updated_at": row.get("updated_at", 0)
                    }
            conn.close()
            enabled, custom = get_unlock_config()
            show_badges = get_setting("unlock_show_badges", "1") == "1"
            self.send_json({
                "ok": True,
                "status": status_map,
                "enabled": enabled,
                "show_badges": show_badges,
                "presets": DEFAULT_UNLOCK_PRESETS,
                "custom": custom
            })
            return

        if path.startswith("/api/proxy/nodes/") and path.endswith("/unlock-test"):
            try:
                node_id = int(path.split("/")[-2])
            except ValueError:
                self.send_json({"ok": False, "message": "无效的节点ID"}, 400)
                return
            conn = get_db()
            cur = conn.execute("SELECT * FROM proxy_node WHERE id = ?", (node_id,))
            row = cur.fetchone()
            if not row:
                conn.close()
                self.send_json({"ok": False, "message": "节点不存在"}, 404)
                return
            node = dict(row)
            conn.close()

            unlock_res = check_node_streaming_unlock(node)
            save_node_unlock_status(node_id, unlock_res)
            self.send_json({"ok": True, "result": unlock_res})
            return

        if path == "/api/proxy/notify/telegram/settings":
            token = get_setting("notify_telegram_token", "").strip()
            chat_id = (get_setting("notify_telegram_chat", "") or get_setting("backup_tg_chat", "")).strip()
            token_masked = (token[:6] + "••••" + token[-4:]) if len(token) > 12 else ("••••••••" if token else "")
            self.send_json({
                "ok": True,
                "configured": bool(token and chat_id),
                "token_masked": token_masked,
                "chat_id": chat_id
            })
            return

        if path in ("/api/proxy/system/update-check", "/api/proxy/system/update-check/", "/api/proxy/update-check", "/api/system/update-check"):
            force = qs.get("force", ["0"])[0] in ("1", "true")
            res = check_system_update(force=force)
            self.send_json(res)
            return

        if path in ("/api/proxy/system/upgrade", "/api/proxy/system/upgrade/", "/api/proxy/upgrade", "/api/proxy/upgrade/", "/api/system/upgrade", "/api/system/upgrade/"):
            if qs.get("action", [""])[0] in ("1", "run", "upgrade"):
                if not check_auth(self.headers):
                    self.send_json({"ok": False, "error": "Unauthorized: 请先登录管理员账号"}, 401)
                    return
                trigger_background_upgrade()
                self.send_json({"ok": True, "message": "升级指令已下发，系统正在后台无损热升级..."})
                return
            self.send_json({
                "ok": True,
                "message": "ProxyProbe 在线无损热升级接口就绪。请在控制面板点击【立即一键在线热升级】，或使用 POST 请求触发。"
            })
            return

        if path == "/api/proxy/probe/public-status":
            latencies = get_node_latest_latencies()
            self.send_json({
                "ok": True,
                "settings": {
                    "public_show_price": get_setting("public_show_price", "0") == "1",
                    "public_show_expiry": get_setting("public_show_expiry", "0") == "1",
                    "public_show_traffic_limit": get_setting("public_show_traffic_limit", "0") == "1"
                },
                "latencies": latencies
            })
            return

        if path == "/api/proxy/settings/display":
            if not check_auth(self.headers):
                self.send_json({"error": "Unauthorized"}, 401)
                return
            self.send_json({
                "ok": True,
                "public_show_price": get_setting("public_show_price", "0") == "1",
                "public_show_expiry": get_setting("public_show_expiry", "0") == "1",
                "public_show_traffic_limit": get_setting("public_show_traffic_limit", "0") == "1"
            })
            return

        if path == "/api/proxy/rules/config":
            if not check_auth(self.headers):
                self.send_json({"error": "Unauthorized"}, 401)
                return
            mode = get_setting("sub_rule_mode", "smart")
            clash_rules = get_setting("sub_clash_rules", "")
            singbox_rules = get_setting("sub_singbox_rules", "")
            presets = get_rule_presets()
            matched_preset = next((p for p in presets if p["id"] == mode), presets[0])
            effective_clash = clash_rules if clash_rules else matched_preset["clash_rules"]
            effective_singbox = singbox_rules if singbox_rules else matched_preset["singbox_rules"]
            self.send_json({
                "ok": True,
                "mode": mode,
                "clash_rules": effective_clash,
                "singbox_rules": effective_singbox,
                "presets": presets
            })
            return

        if path == "/api/proxy/rules/preview":
            if not check_auth(self.headers):
                self.send_json({"error": "Unauthorized"}, 401)
                return
            conn = get_db()
            cur = conn.execute("SELECT * FROM proxy_node WHERE enabled = 1")
            nodes = [dict(r) for r in cur.fetchall()]
            conn.close()
            sc_map = get_server_country_map()
            clash_yaml = generate_clash_yaml(nodes, None, None, sc_map)
            singbox_json = generate_singbox_client_config(nodes, None, None, sc_map)
            self.send_json({
                "ok": True,
                "clash_yaml": clash_yaml,
                "singbox_json": singbox_json
            })
            return

        # 4. Admin-only endpoints
        if not check_auth(self.headers):
            self.send_json({"error": "Unauthorized"}, 401)
            return

        if path == "/api/proxy/backup/telegram/config":
            enabled = get_setting("backup_tg_enabled", "0") == "1"
            try:
                interval_hours = int(get_setting("backup_tg_interval_hours", "24"))
            except ValueError:
                interval_hours = 24
            try:
                last_time = int(get_setting("backup_tg_last_time", "0"))
            except ValueError:
                last_time = 0
            token = get_setting("notify_telegram_token", "").strip()
            default_chat = get_setting("notify_telegram_chat", "").strip()
            custom_chat = get_setting("backup_tg_chat", "").strip()
            last_status = get_setting("backup_tg_last_status", "")
            self.send_json({
                "ok": True,
                "enabled": enabled,
                "interval_hours": interval_hours,
                "custom_chat": custom_chat,
                "default_chat": default_chat,
                "has_token": bool(token),
                "last_time": last_time,
                "last_status": last_status
            })
            return

        if path == "/api/proxy/backup/download":
            try:
                gz_data, raw_size, gz_size = generate_backup_gz()
                file_time_str = time.strftime("%Y%m%d_%H%M%S")
                filename = f"monitor_backup_{file_time_str}.db.gz"
                self.send_response(200)
                self.send_header("Content-Type", "application/gzip")
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
                self.send_header("Content-Length", str(len(gz_data)))
                self.end_headers()
                self.wfile.write(gz_data)
                return
            except Exception as e:
                self.send_json({"ok": False, "error": f"导出备份失败: {e}"}, 500)
                return

        if path == "/api/proxy/users":
            conn = get_db()
            cur = conn.execute("SELECT * FROM proxy_user ORDER BY id ASC")
            users = [dict(r) for r in cur.fetchall()]
            conn.close()
            now = int(time.time())
            for u in users:
                u.pop("password_hash", None)
                limit = u.get("traffic_limit_bytes", 0)
                used = u.get("upload_bytes", 0) + u.get("download_bytes", 0)
                remaining = max(0, limit - used) if limit > 0 else -1
                is_expired = u.get("expires_at", 0) > 0 and now > u.get("expires_at", 0)
                is_over = limit > 0 and used >= limit
                is_dev_over = is_user_over_device_limit(u)
                u["device_limit"] = u.get("device_limit", 0)
                u["online_devices"] = get_user_online_device_count(u["id"])
                u["total_used_bytes"] = used
                u["remaining_bytes"] = remaining
                u["status"] = "disabled" if u.get("enabled", 1) == 0 else ("expired" if is_expired else ("over_quota" if is_over else ("over_device_limit" if is_dev_over else "active")))
                base_url = get_request_base_url(self.headers)
                u["sub_url"] = f"{base_url}/api/proxy/sub?token={u['sub_token']}"
                u["clash_url"] = f"{base_url}/api/proxy/sub?token={u['sub_token']}&clash=1"
            self.send_json({"ok": True, "users": users})
            return

        if path.startswith("/api/proxy/core/"):
            parts = path.strip("/").split("/")
            if len(parts) >= 5:
                core_name = parts[3]
                action = parts[4]
                if core_name == "xray":
                    if action == "install":
                        ok, msg = install_local_xray()
                        self.send_json({"ok": ok, "message": msg})
                        return
                    elif action == "uninstall":
                        ok, msg = uninstall_local_xray()
                        self.send_json({"ok": ok, "message": msg})
                        return
                elif core_name == "singbox":
                    if action == "install":
                        ok, msg = install_local_singbox()
                        self.send_json({"ok": ok, "message": msg})
                        return
                    elif action == "uninstall":
                        ok, msg = uninstall_local_singbox()
                        self.send_json({"ok": ok, "message": msg})
                        return
                elif core_name == "realm":
                    if action == "install":
                        ok, msg = install_local_realm()
                        self.send_json({"ok": ok, "message": msg})
                        return
                    elif action == "uninstall":
                        ok, msg = uninstall_local_realm()
                        self.send_json({"ok": ok, "message": msg})
                        return
            self.send_json({"ok": False, "message": "未知核心操作"}, 400)
            return

        if path == "/api/proxy/nodes":
            conn = get_db()
            cur = conn.execute("SELECT * FROM proxy_node ORDER BY id DESC")
            nodes = [dict(r) for r in cur.fetchall()]
            cur_nodes = conn.execute("SELECT id, ip, ipv4, country FROM node")
            server_rows = cur_nodes.fetchall()
            node_ip_map = {r["id"]: resolve_server_host(dict(r)) for r in server_rows}
            server_country_map = {r["id"]: (r["country"] or "") for r in server_rows}
            for n in nodes:
                sid = n.get("server_id")
                if sid in node_ip_map:
                    resolved = node_ip_map[sid]
                    if is_private_ip(n.get("server_host")):
                        n["server_host"] = resolved
                        try:
                            with conn:
                                conn.execute("UPDATE proxy_node SET server_host = ? WHERE id = ?", (resolved, n["id"]))
                        except Exception:
                            pass
                n["flag"] = resolve_node_flag(n, server_country_map)
                n["display_name"] = format_node_display_name(n, server_country_map)
                n["link"] = format_node_link(n, server_country_map=server_country_map)
            conn.close()
            self.send_json({
                "nodes": nodes,
                "sub_token": get_sub_token(),
                "recommended_port": get_free_port()
            })
            return

        elif path == "/api/proxy/servers":
            conn = get_db()
            cur = conn.execute("SELECT id, name, ip, ipv4, ipv6, token FROM node ORDER BY sort ASC, id ASC")
            remote_nodes = [dict(r) for r in cur.fetchall()]
            
            cur_status = conn.execute("SELECT * FROM node_proxy_status")
            status_map = {r["node_id"]: dict(r) for r in cur_status.fetchall()}
            conn.close()

            now = int(time.time())
            local_xray_installed = os.path.exists(XRAY_BIN)
            local_xray_running = subprocess.run(["systemctl", "is-active", "--quiet", "xray"]).returncode == 0
            local_singbox_installed = os.path.exists(SINGBOX_BIN)
            local_singbox_running = subprocess.run(["systemctl", "is-active", "--quiet", "sing-box"]).returncode == 0
            local_realm_installed = os.path.exists(REALM_BIN)
            local_realm_running = subprocess.run(["systemctl", "is-active", "--quiet", "realm"]).returncode == 0

            local_ipv4 = get_local_ip(socket.AF_INET) or "189.24.108.25"
            local_ipv6 = get_local_ip(socket.AF_INET6)

            servers = []

            for r in remote_nodes:
                r_ipv4 = (r.get("ipv4") or r.get("ip") or "").strip()
                r_ipv6 = (r.get("ipv6") or "").strip()
                host = resolve_server_host(r)
                is_local = (host in LOCAL_HOSTS)
                st = status_map.get(r["id"], {})
                last_seen = st.get("last_seen", 0)
                is_online = (now - last_seen < 30)

                if is_local:
                    x_inst = local_xray_installed
                    x_run = local_xray_running
                    sb_inst = local_singbox_installed
                    sb_run = local_singbox_running
                    r_inst = local_realm_installed
                    r_run = local_realm_running
                else:
                    x_inst = bool(st.get("xray_installed") or st.get("version"))
                    x_run = is_online and bool(st.get("xray_running", st.get("status") == "running"))
                    sb_inst = bool(st.get("singbox_installed"))
                    sb_run = is_online and bool(st.get("singbox_running"))
                    r_inst = bool(st.get("realm_installed"))
                    r_run = is_online and bool(st.get("realm_running"))

                servers.append({
                    "id": r["id"],
                    "name": r["name"] or f"节点-{r['id']}",
                    "host": host,
                    "ipv4": r_ipv4,
                    "ipv6": r_ipv6,
                    "is_local": is_local,
                    "token": r.get("token", ""),
                    "xray_installed": x_inst,
                    "xray_running": x_run,
                    "xray_version": st.get("version", ""),
                    "singbox_installed": sb_inst,
                    "singbox_running": sb_run,
                    "singbox_version": st.get("singbox_version", ""),
                    "realm_installed": r_inst,
                    "realm_running": r_run,
                    "realm_version": st.get("realm_version", ""),
                    "last_seen": last_seen
                })
            self.send_json({"servers": servers})
            return

        elif path == "/api/proxy/status":
            xray_installed = os.path.exists(XRAY_BIN)
            xray_version = ""
            xray_running = False
            if xray_installed:
                v_res = subprocess.run([XRAY_BIN, "version"], capture_output=True, text=True)
                if v_res.stdout:
                    xray_version = v_res.stdout.splitlines()[0]
                s_res = subprocess.run(["systemctl", "is-active", "--quiet", "xray"])
                xray_running = (s_res.returncode == 0)

            singbox_installed = os.path.exists(SINGBOX_BIN)
            singbox_version = ""
            singbox_running = False
            if singbox_installed:
                v_res = subprocess.run([SINGBOX_BIN, "version"], capture_output=True, text=True)
                if v_res.stdout:
                    singbox_version = v_res.stdout.splitlines()[0]
                s_res = subprocess.run(["systemctl", "is-active", "--quiet", "sing-box"])
                singbox_running = (s_res.returncode == 0)

            realm_installed = os.path.exists(REALM_BIN)
            realm_version = ""
            realm_running = False
            if realm_installed:
                v_res = subprocess.run([REALM_BIN, "-v"], capture_output=True, text=True)
                if v_res.stdout:
                    realm_version = v_res.stdout.splitlines()[0]
                s_res = subprocess.run(["systemctl", "is-active", "--quiet", "realm"])
                realm_running = (s_res.returncode == 0)

            self.send_json({
                "installed": xray_installed,
                "version": xray_version,
                "running": xray_running,
                "xray": {
                    "installed": xray_installed,
                    "version": xray_version,
                    "running": xray_running
                },
                "singbox": {
                    "installed": singbox_installed,
                    "version": singbox_version,
                    "running": singbox_running
                },
                "realm": {
                    "installed": realm_installed,
                    "version": realm_version,
                    "running": realm_running
                }
            })
            return

        elif path == "/api/proxy/keygen":
            query = parse_qs(parsed.query)
            proto = query.get("protocol", ["vless_reality"])[0]
            method = query.get("method", ["2022-blake3-aes-128-gcm"])[0]
            port = get_free_port()
            
            res = {
                "port": port,
                "protocol": proto
            }
            if proto in ("vless_reality", "vless_reality_xhttp"):
                priv, pub, sid = gen_xray_keys()
                uid = gen_uuid()
                res.update({
                    "uuid": uid,
                    "private_key": priv,
                    "public_key": pub,
                    "short_id": sid,
                    "sni": "www.apple.com",
                    "dest": "www.apple.com:443",
                    "ws_path": "/xhttp" if proto == "vless_reality_xhttp" else "/ws-proxy"
                })
            elif proto == "hysteria2":
                pwd = gen_random_password(16)
                res.update({
                    "password": pwd,
                    "sni": "bing.com",
                    "dest": "https://www.bing.com"
                })
            elif proto == "vmess_ws":
                uid = gen_uuid()
                res.update({
                    "uuid": uid,
                    "ws_path": "/vmess-ws"
                })
            elif proto == "ss2022":
                key = gen_ss2022_key(method)
                res.update({
                    "method": method,
                    "password": key
                })
            elif proto == "socks5":
                uname = "user_" + secrets.token_hex(3)
                pwd = gen_random_password(12)
                res.update({
                    "username": uname,
                    "password": pwd
                })
            elif proto == "trojan":
                pwd = gen_random_password(16)
                res.update({
                    "password": pwd
                })
            elif proto in ("hysteria2", "tuic"):
                pwd = gen_random_password(16)
                uid = gen_uuid()
                res.update({
                    "uuid": uid,
                    "password": pwd,
                    "sni": "bing.com"
                })
            else:
                uid = gen_uuid()
                res.update({
                    "uuid": uid,
                    "password": uid
                })
            self.send_json(res)
            return

        self.send_json({"error": "Not Found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        body_data = self.rfile.read(length).decode("utf-8") if length > 0 else "{}"
        try:
            req = json.loads(body_data)
        except Exception:
            req = {}

        # 1. Remote agent heartbeat and status report (Authenticated via token)
        if path == "/api/proxy/agent-sync":
            token = req.get("token", "")
            if not token:
                self.send_json({"ok": False, "error": "Missing token"}, 400)
                return
            
            conn = get_db()
            cur = conn.execute("SELECT id FROM node WHERE token = ?", (token,))
            row = cur.fetchone()
            if not row:
                conn.close()
                self.send_json({"ok": False, "error": "Invalid token"}, 403)
                return
            
            node_id = row["id"]
            status = req.get("status", "unknown")
            version = req.get("version", "")
            ports_json = json.dumps(req.get("ports", []))
            listening_ports_json = json.dumps(req.get("listening_ports", []))
            xray_log = req.get("log", "")
            xray_installed = int(req.get("xray_installed", 1 if version else 0))
            xray_running = int(req.get("xray_running", 1 if status == "running" else 0))
            singbox_installed = int(req.get("singbox_installed", 0))
            singbox_running = int(req.get("singbox_running", 0))
            singbox_version = req.get("singbox_version", "")
            realm_installed = int(req.get("realm_installed", 0))
            realm_running = int(req.get("realm_running", 0))
            realm_version = req.get("realm_version", "")
            now = int(time.time())
            with conn:
                conn.execute("""
                INSERT OR REPLACE INTO node_proxy_status (
                    node_id, status, version, ports, listening_ports, log, last_seen,
                    xray_installed, xray_running, singbox_installed, singbox_running, singbox_version,
                    realm_installed, realm_running, realm_version
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    node_id, status, version, ports_json, listening_ports_json, xray_log, now,
                    xray_installed, xray_running, singbox_installed, singbox_running, singbox_version,
                    realm_installed, realm_running, realm_version
                ))
            user_stats = req.get("user_stats", [])
            if user_stats:
                with conn:
                    for st in user_stats:
                        uid = st.get("user_id")
                        up = int(st.get("upload") or 0)
                        down = int(st.get("download") or 0)
                        if uid and (up > 0 or down > 0):
                            conn.execute("""
                                UPDATE proxy_user
                                SET upload_bytes = upload_bytes + ?, download_bytes = download_bytes + ?
                                WHERE id = ?
                            """, (up, down, uid))
            conn.close()
            self.send_json({"ok": True})
            return

        # User authentication & self-service endpoints
        if path == "/api/proxy/auth/login":
            username = req.get("username", "").strip()
            password = req.get("password", "").strip()
            if not password:
                self.send_json({"ok": False, "message": "请输入密码"}, 400)
                return

            conn = get_db()
            user_row = None
            if username:
                cur = conn.execute("SELECT * FROM proxy_user WHERE username = ?", (username,))
                user_row = cur.fetchone()
            else:
                cur = conn.execute("SELECT * FROM proxy_user WHERE is_admin = 1 ORDER BY id ASC LIMIT 1")
                user_row = cur.fetchone()

            if not user_row:
                conn.close()
                self.send_json({"ok": False, "message": "用户名或密码错误"}, 401)
                return

            user = dict(user_row)
            if not verify_password(password, user.get("password_hash", "")):
                conn.close()
                self.send_json({"ok": False, "message": "用户名或密码错误"}, 401)
                return

            if user.get("enabled", 1) != 1:
                conn.close()
                self.send_json({"ok": False, "message": "该账户已被管理员禁用"}, 403)
                return

            # Issue session token
            raw_token = secrets.token_hex(32)
            token_hash = sha256(raw_token.encode()).hexdigest()
            session_days = 14
            expires_at = int(time.time()) + session_days * 86400

            with conn:
                conn.execute("INSERT OR REPLACE INTO session (token_hash, expires_at) VALUES (?, ?)", (token_hash, expires_at))
                conn.execute("INSERT OR REPLACE INTO proxy_session_user (token_hash, user_id, created_at) VALUES (?, ?, ?)", (token_hash, user["id"], int(time.time())))
            conn.close()

            # Set cookie
            cookie_header = f"monitor_session={raw_token}; Path=/; Max-Age={session_days*86400}; SameSite=Lax; HttpOnly"
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Set-Cookie", cookie_header)
            resp_body = json.dumps({
                "ok": True,
                "user": {
                    "id": user["id"],
                    "username": user["username"],
                    "is_admin": bool(user["is_admin"])
                }
            }).encode("utf-8")
            self.send_header("Content-Length", str(len(resp_body)))
            self.end_headers()
            self.wfile.write(resp_body)
            return

        if path == "/api/proxy/user/reset-token":
            user = get_current_user(self.headers)
            if not user:
                self.send_json({"ok": False, "error": "未登录"}, 401)
                return
            new_token = secrets.token_hex(16)
            conn = get_db()
            with conn:
                conn.execute("UPDATE proxy_user SET sub_token = ? WHERE id = ?", (new_token, user["id"]))
            conn.close()
            base_url = get_request_base_url(self.headers)
            self.send_json({"ok": True, "sub_token": new_token, "sub_url": f"{base_url}/api/proxy/sub?token={new_token}"})
            return

        # 切换并持久化保存主题风格 (跟随账号)
        if path == "/api/proxy/theme":
            user = get_current_user(self.headers)
            is_adm = check_auth(self.headers) or (user and user.get("is_admin") == 1)
            if not user and not is_adm:
                self.send_json({"ok": False, "error": "未登录"}, 401)
                return
            new_theme = req.get("theme_style", "default")
            if new_theme not in ("default", "sakura"):
                new_theme = "default"
            if user and user.get("id", 0) > 0:
                conn = get_db()
                with conn:
                    conn.execute("UPDATE proxy_user SET theme_style = ? WHERE id = ?", (new_theme, user["id"]))
                conn.close()
            if is_adm:
                set_setting("admin_theme_style", new_theme)
            self.send_json({"ok": True, "theme_style": new_theme})
            return

        # License activation API (允许已登录管理员，或本机 127.0.0.1 终端激活)
        if path == "/api/proxy/license/activate":
            if not check_auth(self.headers) and self.client_address[0] not in ("127.0.0.1", "::1"):
                self.send_json({"error": "Unauthorized"}, 401)
                return
            lic_key = req.get("license_key", "").strip()
            conn = get_db()
            ok, msg, lic_status = license_guard.save_license_key(conn, lic_key)
            conn.close()
            if ok:
                self.send_json({"ok": True, "message": msg, "status": lic_status})
            else:
                self.send_json({"ok": False, "message": msg}, 400)
            return

        # 2. Admin required for all other POST endpoints
        if not check_auth(self.headers):
            self.send_json({"error": "Unauthorized"}, 401)
            return

        if path == "/api/proxy/backup/telegram/config":
            enabled = "1" if req.get("enabled") else "0"
            interval_hours = str(max(1, int(req.get("interval_hours", 24))))
            custom_chat = str(req.get("custom_chat", "")).strip()

            set_setting("backup_tg_enabled", enabled)
            set_setting("backup_tg_interval_hours", interval_hours)
            set_setting("backup_tg_chat", custom_chat)
            self.send_json({"ok": True, "message": "定时备份配置已保存"})
            return

        if path == "/api/proxy/unlock/config":
            enabled = req.get("enabled")
            custom = req.get("custom")
            show_badges = req.get("show_badges")
            if enabled is not None:
                set_setting("unlock_enabled_items", json.dumps(enabled))
            if custom is not None:
                set_setting("unlock_custom_items", json.dumps(custom))
            if show_badges is not None:
                set_setting("unlock_show_badges", "1" if show_badges else "0")
            self.send_json({"ok": True, "message": "流媒体与 AI 检测配置已更新"})
            return

        if path.startswith("/api/proxy/nodes/") and path.endswith("/unlock-test"):
            try:
                node_id = int(path.split("/")[-2])
            except ValueError:
                self.send_json({"ok": False, "message": "无效的节点ID"}, 400)
                return
            conn = get_db()
            cur = conn.execute("SELECT * FROM proxy_node WHERE id = ?", (node_id,))
            row = cur.fetchone()
            if not row:
                conn.close()
                self.send_json({"ok": False, "message": "节点不存在"}, 404)
                return
            node = dict(row)
            conn.close()

            unlock_res = check_node_streaming_unlock(node)
            save_node_unlock_status(node_id, unlock_res)
            self.send_json({"ok": True, "result": unlock_res})
            return

        if path == "/api/proxy/notify/telegram/test":
            token = (req.get("token") or get_setting("notify_telegram_token", "")).strip()
            chat_id = (req.get("chat_id") or get_setting("notify_telegram_chat", "") or get_setting("backup_tg_chat", "")).strip()
            if not token:
                self.send_json({"ok": False, "error": "尚未配置 Telegram Bot Token"}, 400)
                return
            if not chat_id:
                self.send_json({"ok": False, "error": "尚未配置 Telegram Chat ID"}, 400)
                return
            site_name = get_setting("site_name", "HHUB")
            now_str = time.strftime("%Y-%m-%d %H:%M:%S")
            test_text = (
                f"🔔 <b>[HHUB 提醒] Telegram 告警机器人测试成功！</b>\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"🌐 <b>站点名称:</b> {site_name}\n"
                f"⏱️ <b>测试时间:</b> {now_str}\n"
                f"⚡ <b>监控模式:</b> 静默无扰实时守护\n"
                f"━━━━━━━━━━━━━━━━━━━━\n"
                f"📡 <i>当任意节点离线超过 75 秒或恢复在线时，系统将自动在此推送信令。</i>"
            )
            ok, err = send_telegram_msg(token, chat_id, test_text)
            if ok:
                self.send_json({"ok": True, "message": "测试通知已成功送达您的 Telegram！"})
            else:
                self.send_json({"ok": False, "error": f"Telegram API 报错: {err}"}, 500)
            return

        if path == "/api/proxy/notify/telegram/settings":
            token = req.get("token", "").strip()
            chat_id = req.get("chat_id", "").strip()
            if token and not token.startswith("••"):
                set_setting("notify_telegram_token", token)
            if chat_id:
                set_setting("notify_telegram_chat", chat_id)
                set_setting("backup_tg_chat", chat_id)
            self.send_json({"ok": True, "message": "Telegram 告警配置已保存"})
            return

        if path == "/api/proxy/backup/telegram/run":
            custom_chat = str(req.get("custom_chat", "")).strip() or None
            try:
                ok, msg, gz_size = perform_telegram_backup(custom_chat)
                self.send_json({
                    "ok": True,
                    "message": msg,
                    "size_kb": round(gz_size / 1024, 1)
                })
            except Exception as e:
                self.send_json({"ok": False, "error": str(e)}, 500)
        if path == "/api/proxy/rules/config":
            if not check_auth(self.headers):
                self.send_json({"error": "Unauthorized"}, 401)
                return
            mode = req.get("mode", "smart")
            clash_rules = req.get("clash_rules", "")
            singbox_rules = req.get("singbox_rules", "")
            set_setting("sub_rule_mode", mode)
            set_setting("sub_clash_rules", clash_rules)
            set_setting("sub_singbox_rules", singbox_rules)
            self.send_json({"ok": True, "message": "分流规则配置已成功保存"})
            return

        if path == "/api/proxy/users":
            # 商业许可证/套餐配额检查
            conn_chk = get_db()
            lic_status = license_guard.get_current_license_status(conn_chk)
            curr_user_count = conn_chk.execute("SELECT COUNT(*) FROM proxy_user WHERE is_admin = 0").fetchone()[0]
            conn_chk.close()

            if lic_status.get("type") == "revoked":
                self.send_json({
                    "ok": False,
                    "error": "license_revoked",
                    "message": "商业许可证已被授权中心吊销冻结，禁止创建或变更客户端用户！",
                    "machine_id": lic_status.get("machine_id")
                }, 403)
                return

            max_users = lic_status.get("max_users", 1)
            plan_name = lic_status.get("plan_name", "免费版")

            if curr_user_count >= max_users:
                self.send_json({
                    "ok": False,
                    "error": "license_quota_exceeded",
                    "message": f"当前【{plan_name}】配额已满（上限 {max_users} 个客户端用户，当前已建 {curr_user_count} 个），添加更多用户请升级商业许可证套餐！",
                    "machine_id": lic_status.get("machine_id"),
                    "current": curr_user_count,
                    "max": max_users
                }, 403)
                return

            username = req.get("username", "").strip()
            password = req.get("password", "").strip()
            limit_gb = float(req.get("traffic_limit_gb", 200))
            expires_days = int(req.get("expires_days", 0))
            device_limit = int(req.get("device_limit", 0))

            if not username:
                self.send_json({"ok": False, "message": "用户名不能为空"}, 400)
                return
            if not password:
                self.send_json({"ok": False, "message": "密码不能为空"}, 400)
                return

            limit_bytes = int(limit_gb * 1024 * 1024 * 1024) if limit_gb > 0 else 0
            expires_at = (int(time.time()) + expires_days * 86400) if expires_days > 0 else 0
            sub_token = secrets.token_hex(16)
            pwd_hash = hash_password(password)

            conn = get_db()
            try:
                with conn:
                    cur = conn.execute("""
                        INSERT INTO proxy_user (username, password_hash, sub_token, traffic_limit_bytes, upload_bytes, download_bytes, expires_at, enabled, is_admin, created_at, device_limit)
                        VALUES (?, ?, ?, ?, 0, 0, ?, 1, 0, ?, ?)
                    """, (username, pwd_hash, sub_token, limit_bytes, expires_at, int(time.time()), device_limit))
                    new_id = cur.lastrowid
                conn.close()
                apply_all_configs()
                self.send_json({"ok": True, "id": new_id, "sub_token": sub_token, "message": "用户创建成功"})
            except sqlite3.IntegrityError:
                conn.close()
                self.send_json({"ok": False, "message": "该用户名已存在"}, 400)
            return

        if path.startswith("/api/proxy/users/") and path.endswith("/reset-traffic"):
            user_id = int(path.split("/")[-2])
            conn = get_db()
            with conn:
                conn.execute("UPDATE proxy_user SET upload_bytes = 0, download_bytes = 0 WHERE id = ?", (user_id,))
            conn.close()
            apply_all_configs()
            self.send_json({"ok": True, "message": "流量已重置为 0"})
            return

        if path.startswith("/api/proxy/users/") and path.endswith("/reset-token"):
            user_id = int(path.split("/")[-2])
            new_token = secrets.token_hex(16)
            conn = get_db()
            with conn:
                conn.execute("UPDATE proxy_user SET sub_token = ? WHERE id = ?", (new_token, user_id))
            conn.close()
            apply_all_configs()
            self.send_json({"ok": True, "sub_token": new_token, "message": "订阅 Token 已重置"})
            return

        if path.startswith("/api/proxy/users/") and path.endswith("/toggle"):
            user_id = int(path.split("/")[-2])
            conn = get_db()
            with conn:
                conn.execute("UPDATE proxy_user SET enabled = 1 - enabled WHERE id = ?", (user_id,))
            conn.close()
            apply_all_configs()
            self.send_json({"ok": True, "message": "用户状态已变更"})
            return

        if path.startswith("/api/proxy/users/") and path.endswith("/edit"):
            user_id = int(path.split("/")[-2])
            limit_gb = req.get("traffic_limit_gb")
            expires_at = req.get("expires_at")
            new_pwd = req.get("password", "").strip()
            device_limit = req.get("device_limit")
            
            conn = get_db()
            with conn:
                if limit_gb is not None:
                    limit_bytes = int(float(limit_gb) * 1024 * 1024 * 1024) if float(limit_gb) > 0 else 0
                    conn.execute("UPDATE proxy_user SET traffic_limit_bytes = ? WHERE id = ?", (limit_bytes, user_id))
                if expires_at is not None:
                    conn.execute("UPDATE proxy_user SET expires_at = ? WHERE id = ?", (int(expires_at), user_id))
                if device_limit is not None:
                    conn.execute("UPDATE proxy_user SET device_limit = ? WHERE id = ?", (int(device_limit), user_id))
                if new_pwd:
                    conn.execute("UPDATE proxy_user SET password_hash = ? WHERE id = ?", (hash_password(new_pwd), user_id))
            conn.close()
            apply_all_configs()
            self.send_json({"ok": True, "message": "用户信息已更新"})
            return

        if path.startswith("/api/proxy/core/"):
            parts = path.strip("/").split("/")
            if len(parts) >= 5:
                core_name = parts[3]
                action = parts[4]
                if core_name == "xray":
                    if action == "install":
                        ok, msg = install_local_xray()
                        self.send_json({"ok": ok, "message": msg})
                        return
                    elif action == "uninstall":
                        ok, msg = uninstall_local_xray()
                        self.send_json({"ok": ok, "message": msg})
                        return
                elif core_name == "singbox":
                    if action == "install":
                        ok, msg = install_local_singbox()
                        self.send_json({"ok": ok, "message": msg})
                        return
                    elif action == "uninstall":
                        ok, msg = uninstall_local_singbox()
                        self.send_json({"ok": ok, "message": msg})
                        return
                elif core_name == "realm":
                    if action == "install":
                        ok, msg = install_local_realm()
                        self.send_json({"ok": ok, "message": msg})
                        return
                    elif action == "uninstall":
                        ok, msg = uninstall_local_realm()
                        self.send_json({"ok": ok, "message": msg})
                        return
            self.send_json({"ok": False, "message": "未知核心操作"}, 400)
            return

        if path.startswith("/api/proxy/nodes/") and path.endswith("/test"):
            try:
                node_id = int(path.split("/")[-2])
            except ValueError:
                self.send_json({"ok": False, "message": "无效的节点ID"}, 400)
                return
            conn = get_db()
            cur = conn.execute("SELECT * FROM proxy_node WHERE id = ?", (node_id,))
            row = cur.fetchone()
            if not row:
                conn.close()
                self.send_json({"ok": False, "message": "节点不存在"}, 404)
                return
            node = dict(row)
            if is_private_ip(node.get("server_host")):
                cur_s = conn.execute("SELECT id, ip, ipv4 FROM node WHERE id = ?", (node.get("server_id"),))
                s_row = cur_s.fetchone()
                if s_row:
                    node["server_host"] = resolve_server_host(dict(s_row))
            conn.close()

            ok, msg, ms = test_node_connectivity(node)
            self.send_json({"ok": ok, "message": msg, "latency_ms": ms})
            return

        if path == "/api/proxy/nodes":
            # 商业许可证/套餐配额检查
            conn_lic = get_db()
            lic_status = license_guard.get_current_license_status(conn_lic)
            curr_node_count = conn_lic.execute("SELECT COUNT(*) FROM proxy_node").fetchone()[0]
            conn_lic.close()

            if lic_status.get("type") == "revoked":
                self.send_json({
                    "ok": False,
                    "error": "license_revoked",
                    "message": "商业许可证已被授权中心吊销冻结，禁止创建或变更代理节点！",
                    "machine_id": lic_status.get("machine_id")
                }, 403)
                return

            max_nodes = lic_status.get("max_nodes", 1)
            plan_name = lic_status.get("plan_name", "免费版")

            if curr_node_count >= max_nodes:
                self.send_json({
                    "ok": False,
                    "error": "license_quota_exceeded",
                    "message": f"当前【{plan_name}】配额已满（上限 {max_nodes} 个代理节点，当前已建 {curr_node_count} 个），添加更多节点请升级商业许可证套餐！",
                    "machine_id": lic_status.get("machine_id"),
                    "current": curr_node_count,
                    "max": max_nodes
                }, 403)
                return

            server_id = int(req.get("server_id", 0))
            if server_id == 0:
                self.send_json({"ok": False, "message": "无法使用未纳管的本机创建节点，请先在「探针节点」页面添加服务器！"}, 400)
                return

            server_name = req.get("server_name", "")
            server_host = req.get("server_host", "")
            
            # Resolve private IP to public IP
            if (is_private_ip(server_host) or server_host == "127.0.0.1") and server_id != 0:
                conn_tmp = get_db()
                s_cur = conn_tmp.execute("SELECT id, ip, ipv4 FROM node WHERE id = ?", (server_id,))
                s_row = s_cur.fetchone()
                conn_tmp.close()
                if s_row:
                    server_host = resolve_server_host(dict(s_row))

            name = req.get("name", "").strip() or server_name or f"节点-{int(time.time())}"
            protocol = req.get("protocol", "vless_reality")
            
            is_relay = int(req.get("is_relay", 0))
            relay_server_id = int(req.get("relay_server_id", 0))
            relay_port = int(req.get("relay_port", 0))
            remote_host = (req.get("remote_host") or "").strip()
            remote_port = int(req.get("remote_port", 0))
            target_node_id = int(req.get("target_node_id", 0))

            port = int(req.get("port") or relay_port or get_free_port())
            is_local = is_local_node({"server_id": server_id, "server_host": server_host, "server_name": server_name})

            if is_relay == 1:
                if is_local:
                    if not os.path.exists(REALM_BIN):
                        self.send_json({"ok": False, "message": "本机尚未安装 Realm 端口转发核心，无法创建中转落地节点，请先在核心状态卡片中安装 Realm！"}, 400)
                        return
                else:
                    conn_chk = get_db()
                    cur_st = conn_chk.execute("SELECT realm_installed FROM node_proxy_status WHERE node_id = ?", (server_id,))
                    s_stat = cur_st.fetchone()
                    conn_chk.close()
                    if not s_stat or not s_stat["realm_installed"]:
                        self.send_json({"ok": False, "message": f"服务器 [{server_name}] 尚未安装 Realm 端口转发核心！"}, 400)
                        return
            else:
                # 校验所选服务器是否已安装对应协议所需的核心
                needs_singbox = protocol in ("hysteria2", "tuic")
                if is_local:
                    if needs_singbox and not os.path.exists(SINGBOX_BIN):
                        self.send_json({"ok": False, "message": "本机尚未安装 Sing-box 核心，无法创建此类协议节点，请先在核心状态卡片中安装核心！"}, 400)
                        return
                    if not needs_singbox and not os.path.exists(XRAY_BIN):
                        self.send_json({"ok": False, "message": "本机尚未安装 Xray-Core 核心，无法创建此类协议节点，请先在核心状态卡片中安装核心！"}, 400)
                        return
                else:
                    conn_chk = get_db()
                    cur_st = conn_chk.execute("SELECT xray_installed, singbox_installed FROM node_proxy_status WHERE node_id = ?", (server_id,))
                    s_stat = cur_st.fetchone()
                    conn_chk.close()
                    if needs_singbox and (not s_stat or not s_stat["singbox_installed"]):
                        self.send_json({"ok": False, "message": f"服务器 [{server_name}] 尚未安装 Sing-box 核心，无法创建此类协议节点！"}, 400)
                        return
                    if not needs_singbox and (not s_stat or not s_stat["xray_installed"]):
                        self.send_json({"ok": False, "message": f"服务器 [{server_name}] 尚未安装 Xray-Core 核心，无法创建此类协议节点！"}, 400)
                        return
            
            uuid = req.get("uuid") or gen_uuid()
            flow = req.get("flow", "xtls-rprx-vision")
            sni = req.get("sni", "www.apple.com")
            dest = req.get("dest", f"{sni}:443")
            priv_key = req.get("private_key", "")
            pub_key = req.get("public_key", "")
            short_id = req.get("short_id", "")
            ws_path = req.get("ws_path", "/ws-proxy" if protocol != "vmess_ws" else "/vmess-ws")
            method = req.get("method", "2022-blake3-aes-128-gcm")
            password = req.get("password", "")
            username = req.get("username", "")
            extra_json = req.get("extra_json", "")

            if protocol in ("vless_reality", "vless_reality_xhttp") and (not priv_key or not pub_key):
                gen_priv, gen_pub, gen_sid = gen_xray_keys()
                priv_key = priv_key or gen_priv
                pub_key = pub_key or gen_pub
                short_id = short_id or gen_sid
            elif protocol == "ss2022" and not password:
                password = gen_ss2022_key(method)
            elif protocol == "socks5" and not password:
                password = gen_random_password(12)
            elif protocol == "trojan" and not password:
                password = gen_random_password(16)

            now = int(time.time())
            conn = get_db()
            with conn:
                cur = conn.execute("""
                INSERT INTO proxy_node (
                    server_id, server_name, server_host, name, protocol, port,
                    uuid, flow, sni, dest, public_key, private_key, short_id,
                    ws_path, method, password, username, extra_json,
                    is_relay, relay_server_id, relay_port, remote_host, remote_port, target_node_id,
                    enabled, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                """, (
                    server_id, server_name, server_host, name, protocol, port,
                    uuid, flow, sni, dest, pub_key, priv_key, short_id,
                    ws_path, method, password, username, extra_json,
                    is_relay, relay_server_id, port, remote_host, remote_port, target_node_id,
                    now
                ))
                new_id = cur.lastrowid
            conn.close()

            # Apply locally if it belongs to local server, else remote agent will pull on next tick (within 5s)
            if is_local_node({"server_id": server_id, "server_host": server_host, "server_name": server_name}):
                ok, msg = apply_all_configs()
            else:
                ok, msg = True, f"远端节点已保存，将被控服务器 [{server_name}] 实时同步"

            # Auto-test connectivity
            test_ok, test_msg, test_ms = test_node_connectivity({
                "id": new_id,
                "protocol": protocol,
                "server_host": server_host,
                "port": port,
                "uuid": uuid,
                "flow": flow,
                "sni": sni,
                "public_key": pub_key,
                "short_id": short_id,
                "is_relay": is_relay,
                "remote_host": remote_host,
                "remote_port": remote_port
            })

            self.send_json({
                "ok": ok,
                "id": new_id,
                "node_id": new_id,
                "message": msg,
                "test_result": {
                    "ok": test_ok,
                    "message": test_msg,
                    "latency_ms": test_ms
                }
            })
            return

        elif path.startswith("/api/proxy/nodes/") and path.endswith("/toggle"):

            try:
                node_id = int(path.split("/")[-2])
            except ValueError:
                self.send_json({"ok": False, "message": "无效的节点ID"}, 400)
                return
            conn = get_db()
            with conn:
                cur = conn.execute("SELECT enabled, server_id, server_host, server_name FROM proxy_node WHERE id = ?", (node_id,))
                row = cur.fetchone()
                if row:
                    new_val = 0 if row[0] == 1 else 1
                    conn.execute("UPDATE proxy_node SET enabled = ? WHERE id = ?", (new_val, node_id))
                    if is_local_node(dict(row)):
                        apply_all_configs()
            conn.close()
            self.send_json({"ok": True})
            return

        elif path == "/api/proxy/reset-sub-token":
            new_token = secrets.token_hex(16)
            conn = get_db()
            with conn:
                conn.execute("INSERT OR REPLACE INTO setting (key, value) VALUES ('proxy_sub_token', ?)", (new_token,))
            conn.close()
            self.send_json({"ok": True, "sub_token": new_token})
            return

        elif path == "/api/proxy/install-xray":
            subprocess.run(["mkdir", "-p", "/etc/xray", "/var/log/xray"])
            cmd = "curl -fsSL https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-64.zip -o /tmp/xray.zip && unzip -o /tmp/xray.zip xray -d /tmp/ && install -m 0755 /tmp/xray/xray /usr/local/bin/xray && rm -rf /tmp/xray*"
            res = subprocess.run(cmd, shell=True, capture_output=True, text=True)
            apply_xray_config()
            self.send_json({"ok": res.returncode == 0, "output": res.stdout or res.stderr})
        elif path in ("/api/proxy/system/update-check", "/api/proxy/system/update-check/", "/api/proxy/update-check", "/api/system/update-check"):
            force = req.get("force", False)
            res = check_system_update(force=bool(force))
            self.send_json(res)
            return

        elif path in ("/api/proxy/system/upgrade", "/api/proxy/system/upgrade/", "/api/proxy/upgrade", "/api/proxy/upgrade/", "/api/system/upgrade", "/api/system/upgrade/"):
            if not check_auth(self.headers):
                self.send_json({"ok": False, "error": "Unauthorized: 请先登录管理员账号"}, 401)
                return
            trigger_background_upgrade()
            self.send_json({"ok": True, "message": "升级指令已下发，系统正在后台无损热升级..."})
            return

        elif path == "/api/proxy/settings/display":
            if not check_auth(self.headers):
                self.send_json({"error": "Unauthorized"}, 401)
                return
            show_price = "1" if req.get("public_show_price") else "0"
            show_expiry = "1" if req.get("public_show_expiry") else "0"
            show_traffic = "1" if req.get("public_show_traffic_limit") else "0"
            set_setting("public_show_price", show_price)
            set_setting("public_show_expiry", show_expiry)
            set_setting("public_show_traffic_limit", show_traffic)
            self.send_json({"ok": True, "message": "服务器公开信息展示权限已更新"})
            return

        self.send_json({"error": "Not Found"}, 404)

    def do_DELETE(self):
        if not check_auth(self.headers):
            self.send_json({"error": "Unauthorized"}, 401)
            return

        parsed = urlparse(self.path)
        path = parsed.path
        m = re.match(r"^/api/proxy/nodes/(\d+)$", path)
        if m:
            node_id = int(m.group(1))
            conn = get_db()
            with conn:
                cur = conn.execute("SELECT server_id, server_host, server_name FROM proxy_node WHERE id = ?", (node_id,))
                row = cur.fetchone()
                conn.execute("DELETE FROM proxy_node WHERE id = ?", (node_id,))
                if row and is_local_node(dict(row)):
                    apply_all_configs()
            conn.close()
            self.send_json({"ok": True})
            return

        m_user = re.match(r"^/api/proxy/users/(\d+)$", path)
        if m_user:
            user_id = int(m_user.group(1))
            if user_id == 1:
                self.send_json({"ok": False, "message": "不能删除初始管理员账号"}, 400)
                return
            conn = get_db()
            with conn:
                conn.execute("DELETE FROM proxy_user WHERE id = ?", (user_id,))
                conn.execute("DELETE FROM proxy_session_user WHERE user_id = ?", (user_id,))
            conn.close()
            apply_all_configs()
            self.send_json({"ok": True, "message": "用户已删除"})
            return

        self.send_json({"error": "Not Found"}, 404)

if __name__ == "__main__":
    init_db()
    license_guard.start_heartbeat_thread(DB_PATH, "http://156.226.173.102:18888")
    t = threading.Thread(target=traffic_collector_loop, daemon=True)
    t.start()
    t_backup = threading.Thread(target=telegram_backup_loop, daemon=True)
    t_backup.start()
    t_alert = threading.Thread(target=telegram_node_alert_loop, daemon=True)
    t_alert.start()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), ProxyHandler)
    print(f"ProxyManager daemon listening on 127.0.0.1:{PORT}")
    server.serve_forever()
