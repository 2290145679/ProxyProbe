import json
import os
import random
import re
import secrets
import socket
import sqlite3
import subprocess
import threading
import time
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
        proto = headers.get("X-Forwarded-Proto") or "https"
        proto = proto.split(",")[0].strip()
        if host:
            return f"{proto}://{host}"
    return "https://test.yohoo.xyz"

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
  echo "    curl -fsSL https://test.yohoo.xyz/proxy-agent.sh | bash -s -- --server https://test.yohoo.xyz --token <TOKEN>" >&2
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

        # Migration: ensure admin user exists in proxy_user
        cur_adm = conn.execute("SELECT id FROM proxy_user WHERE username = 'admin'")
        if not cur_adm.fetchone():
            adm_hash = hash_password("admin123")
            conn.execute("""
                INSERT INTO proxy_user (username, password_hash, sub_token, traffic_limit_bytes, upload_bytes, download_bytes, expires_at, enabled, is_admin, created_at, device_limit)
                VALUES ('admin', ?, ?, 0, 0, 0, 0, 1, 1, ?, 0)
            """, (adm_hash, sub_tok, int(time.time())))
    conn.close()

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

def format_node_link(node, user=None):
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
    if node.get("is_relay"):
        name_raw = f"[{node.get('server_name', '中转')}] ➔ {node.get('name', '落地')}"
    else:
        name_raw = f"[{node.get('server_name', '本机')}] {node.get('name', 'node')}"
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

def generate_clash_yaml(nodes, user=None, warning_msg=None):
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

        if n.get("is_relay"):
            name = f"[{n.get('server_name', '中转')}] ➔ {n.get('name', '落地')}"
        else:
            name = f"[{n.get('server_name', '本机')}] {n.get('name', 'node')}"

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
        "proxies": proxies,
        "proxy-groups": [
            {
                "name": "节点选择",
                "type": "select",
                "proxies": ["自动选择"] + names
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
        "rules": [
            "GEOIP,LAN,DIRECT",
            "MATCH,节点选择"
        ]
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
        for p in proxies:
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
        lines.append("  - GEOIP,LAN,DIRECT")
        lines.append("  - MATCH,节点选择")
        return "\n".join(lines)

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
            is_clash = ("clash" in ua or "meta" in ua or "mihomo" in ua or qs.get("clash", [""])[0] == "1")

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
            import base64
            encoded = base64.b64encode("\n".join(links).encode("utf-8"))
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
            self.send_json({
                "ok": True,
                "user": {
                    "id": user.get("id"),
                    "username": user.get("username"),
                    "is_admin": bool(user.get("is_admin", 0)),
                    "sub_token": sub_token,
                    "sub_url": f"{base_url}/api/proxy/sub?token={sub_token}",
                    "clash_url": f"{base_url}/api/proxy/sub?token={sub_token}&clash=1",
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
                    "created_at": user.get("created_at", 0)
                }
            })
            return

        if path == "/api/proxy/user/nodes":
            user = get_current_user(self.headers)
            if not user:
                self.send_json({"ok": False, "error": "未登录"}, 401)
                return
            conn = get_db()
            cur = conn.execute("SELECT id, name, protocol, server_name, server_host, port, enabled FROM proxy_node WHERE enabled = 1 ORDER BY id DESC")
            nodes = [dict(r) for r in cur.fetchall()]
            cur_nodes = conn.execute("SELECT id, ip, ipv4 FROM node")
            node_ip_map = {r["id"]: resolve_server_host(dict(r)) for r in cur_nodes.fetchall()}
            conn.close()
            for n in nodes:
                sid = n.get("server_id")
                if sid in node_ip_map and is_private_ip(n.get("server_host")):
                    n["server_host"] = node_ip_map[sid]
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

        # 4. Admin-only endpoints
        if not check_auth(self.headers):
            self.send_json({"error": "Unauthorized"}, 401)
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
            cur_nodes = conn.execute("SELECT id, ip, ipv4 FROM node")
            node_ip_map = {r["id"]: resolve_server_host(dict(r)) for r in cur_nodes.fetchall()}
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
                n["link"] = format_node_link(n)
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

            servers = [{
                "id": 0,
                "name": "本机 (当前服务器)",
                "host": local_ipv4,
                "ipv4": local_ipv4,
                "ipv6": local_ipv6,
                "is_local": True,
                "token": "",
                "xray_installed": local_xray_installed,
                "xray_running": local_xray_running,
                "xray_version": "Xray 26.3.27" if local_xray_installed else "",
                "singbox_installed": local_singbox_installed,
                "singbox_running": local_singbox_running,
                "singbox_version": "sing-box 1.14.1" if local_singbox_installed else "",
                "realm_installed": local_realm_installed,
                "realm_running": local_realm_running,
                "realm_version": "Realm 2.9.6" if local_realm_installed else "",
                "last_seen": now
            }]

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
            server_name = req.get("server_name", "本机")
            server_host = req.get("server_host", "189.24.108.25")
            
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
    server = ThreadingHTTPServer(("127.0.0.1", PORT), ProxyHandler)
    print(f"ProxyManager daemon listening on 127.0.0.1:{PORT}")
    server.serve_forever()
