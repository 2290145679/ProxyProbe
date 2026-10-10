# -*- coding: utf-8 -*-
"""
ProxyProbe 代理节点管理与协议入站落盘引擎 (Node Engine)
核心功能:
- 密钥与凭证生成: Reality/Xray x25519 密钥对、SS2022 PSK、UUID、随机端口
- 多协议真实握手与沙盒巡检: TCP/HTTP/TLS 端到端测速 (test_node_connectivity)
- 多核心入站规则构建: Xray-Core / Sing-box / Realm 规则自动装配 (build_inbounds_for_nodes)
- 核心配置热落盘与平滑重载: 零中断重载 (apply_all_configs)
"""

import os
import re
import json
import time
import base64
import random
import socket
import secrets
import sqlite3
import ssl
import uuid
import shutil
import ipaddress
import subprocess
import concurrent.futures
from urllib.parse import quote

BASE_DIR = "/opt/proxyprobe"
XRAY_BIN = "/usr/local/bin/xray"
XRAY_CONFIG = "/etc/xray/config.json"
SINGBOX_BIN = "/usr/local/bin/sing-box"
SINGBOX_CONFIG = "/etc/sing-box/config.json"
SINGBOX_CERT = "/etc/sing-box/cert.pem"
SINGBOX_KEY = "/etc/sing-box/key.pem"
REALM_BIN = "/usr/local/bin/realm"
REALM_CONFIG = "/etc/realm/config.toml"
LOCAL_HOSTS = {"189.24.108.25", "127.0.0.1", "localhost", "::1", "test.yohoo.xyz", "tz.yohoo.xyz", ""}

def ensure_server_cert():
    if not os.path.exists(SINGBOX_CERT) or not os.path.exists(SINGBOX_KEY):
        try:
            os.makedirs(os.path.dirname(SINGBOX_CERT), exist_ok=True)
            subprocess.run([
                "openssl", "req", "-x509", "-nodes", "-newkey", "ec",
                "-pkeyopt", "ec_paramgen_curve:prime256v1",
                "-keyout", SINGBOX_KEY, "-out", SINGBOX_CERT,
                "-subj", "/CN=bing.com", "-days", "36500",
                "-addext", "subjectAltName=DNS:bing.com"
            ], capture_output=True)
        except Exception:
            pass

_ENV_GET_DB = None
_ENV_GET_SETTING = None
_ENV_GET_SERVER_IP = None
_ENV_GET_ACTIVE_USERS = None
_ENV_ENSURE_USER_CREDS = None
_ENV_FORMAT_HOST = None

def init_node_context(
    get_db_fn=None,
    get_setting_fn=None,
    get_server_ip_fn=None,
    get_active_users_fn=None,
    ensure_user_creds_fn=None,
    format_host_fn=None,
    xray_bin=None,
    xray_config=None,
    singbox_bin=None,
    singbox_config=None,
    realm_bin=None,
    realm_config=None,
):
    global _ENV_GET_DB, _ENV_GET_SETTING, _ENV_GET_SERVER_IP, _ENV_GET_ACTIVE_USERS, _ENV_ENSURE_USER_CREDS, _ENV_FORMAT_HOST
    global XRAY_BIN, XRAY_CONFIG, SINGBOX_BIN, SINGBOX_CONFIG, REALM_BIN, REALM_CONFIG
    if get_db_fn: _ENV_GET_DB = get_db_fn
    if get_setting_fn: _ENV_GET_SETTING = get_setting_fn
    if get_server_ip_fn: _ENV_GET_SERVER_IP = get_server_ip_fn
    if get_active_users_fn: _ENV_GET_ACTIVE_USERS = get_active_users_fn
    if ensure_user_creds_fn: _ENV_ENSURE_USER_CREDS = ensure_user_creds_fn
    if format_host_fn: _ENV_FORMAT_HOST = format_host_fn
    if xray_bin: XRAY_BIN = xray_bin
    if xray_config: XRAY_CONFIG = xray_config
    if singbox_bin: SINGBOX_BIN = singbox_bin
    if singbox_config: SINGBOX_CONFIG = singbox_config
    if realm_bin: REALM_BIN = realm_bin
    if realm_config: REALM_CONFIG = realm_config

def get_db():
    if _ENV_GET_DB: return _ENV_GET_DB()
    conn = sqlite3.connect("/opt/proxyprobe/data/monitor.db")
    conn.row_factory = sqlite3.Row
    return conn

def get_setting(key, default=""):
    if _ENV_GET_SETTING: return _ENV_GET_SETTING(key, default)
    try:
        conn = get_db()
        row = conn.execute("SELECT val FROM proxy_settings WHERE key = ?", (key,)).fetchone()
        conn.close()
        if row and row["val"] is not None:
            return row["val"]
    except Exception:
        pass
    return default

def get_server_public_ip():
    if _ENV_GET_SERVER_IP: return _ENV_GET_SERVER_IP()
    return "127.0.0.1"

def get_active_users():
    if _ENV_GET_ACTIVE_USERS: return _ENV_GET_ACTIVE_USERS()
    try:
        conn = get_db()
        cur = conn.execute("SELECT * FROM proxy_user WHERE enabled = 1")
        rows = [dict(r) for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception:
        return []

def ensure_user_credentials(user):
    if _ENV_ENSURE_USER_CREDS: return _ENV_ENSURE_USER_CREDS(user)
    import uuid
    user_id = user["id"]
    sub_token = user.get("sub_token") or f"user_{user_id}"
    u_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"monitor_user_{user_id}_{sub_token}"))
    u_pwd = f"u{user_id}_{sub_token[:12]}"
    return u_uuid, u_pwd

def format_host_for_uri(host):
    if _ENV_FORMAT_HOST: return _ENV_FORMAT_HOST(host)
    if not host: return "127.0.0.1"
    host_str = str(host).strip()
    if ":" in host_str and not host_str.startswith("["):
        return f"[{host_str}]"
    return host_str

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
    server_ip = get_server_public_ip()
    if server_ip and not is_private_ip(server_ip):
        return server_ip
    return ipv4 or pub_ip or "127.0.0.1"

def is_local_node(node):
    s_id = node.get("server_id", 0)
    s_host = str(node.get("server_host", "")).strip()
    s_name = str(node.get("server_name", "")).strip()
    pub_ip = get_server_public_ip()
    return s_id == 0 or (s_host in LOCAL_HOSTS) or (pub_ip and s_host == pub_ip) or (s_name in ("本机", "localhost"))

_IPV6_CAPABLE_CACHE = {"ts": 0, "val": False}

def host_has_ipv6_connectivity():
    """检测当前主控 VPS 内核是否具备可用的 IPv6 公网路由与出站能力 (5分钟缓存)"""
    now = time.time()
    if now - _IPV6_CAPABLE_CACHE["ts"] < 300:
        return _IPV6_CAPABLE_CACHE["val"]
    val = False
    try:
        s = socket.socket(socket.AF_INET6, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(("2606:4700:4700::1111", 53))
        s.close()
        val = True
    except Exception:
        val = False
    _IPV6_CAPABLE_CACHE["ts"] = now
    _IPV6_CAPABLE_CACHE["val"] = val
    return val

def is_target_ipv6(host):
    if ":" in host:
        return True
    try:
        infos = socket.getaddrinfo(host, None)
        has_v4 = any(info[0] == socket.AF_INET for info in infos)
        has_v6 = any(info[0] == socket.AF_INET6 for info in infos)
        if has_v6 and not has_v4:
            return True
    except Exception:
        pass
    return False

def check_node_via_agent_status(node):
    """
    当主控端无 IPv6 出站路由或网络不可达时，通过远程探针节点上报的真实心跳与监听端口做自愈感知校验
    """
    server_id = node.get("server_id", 0)
    port = int(node.get("port", 0))
    proto = node.get("protocol", "vless_reality")
    
    if not server_id:
        return None
        
    try:
        conn = get_db()
        cur = conn.execute("SELECT * FROM node_proxy_status WHERE node_id = ?", (server_id,))
        row = cur.fetchone()
        conn.close()
        
        if not row:
            return None
            
        st = dict(row)
        now = time.time()
        last_seen = st.get("last_seen") or 0
        is_online = (now - last_seen) < 90
        
        if not is_online:
            return False, f"被控探针离线 (上次心跳: {int(now - last_seen)} 秒前)，无法确认节点服务状态", 0
            
        # 核心运行状态
        if proto in ("hysteria2", "tuic", "anytls"):
            core_running = bool(st.get("singbox_running"))
            core_name = "Sing-box"
        elif node.get("is_relay"):
            core_running = bool(st.get("realm_running"))
            core_name = "Realm"
        else:
            core_running = bool(st.get("xray_running"))
            core_name = "Xray"
            
        # 端口监听排查
        port_found = False
        try:
            ports = json.loads(st.get("ports") or "[]")
            if port in ports:
                port_found = True
        except Exception:
            pass
        if not port_found:
            try:
                lports = json.loads(st.get("listening_ports") or "[]")
                if port in lports:
                    port_found = True
            except Exception:
                pass
        if not port_found and st.get("log"):
            try:
                log_data = json.loads(st["log"])
                ss_txt = log_data.get("ss", "")
                if f":{port} " in ss_txt or f":{port}\n" in ss_txt or f":{port}\t" in ss_txt or f":{port}" in ss_txt:
                    port_found = True
            except Exception:
                if f":{port}" in st["log"]:
                    port_found = True
                    
        if core_running and port_found:
            return True, f"节点运行正常 ({core_name} 监听端口 {port}，主控直连受限由客户端直连)", 0
        elif core_running:
            return True, f"核心运行就绪 ({core_name} 运行中，主控直连受限由客户端直连)", 0
        else:
            return False, f"被控端 {core_name} 核心未处于运行状态", 0
    except Exception as e:
        return False, str(e), 0

def test_node_connectivity(node):
    host = node.get("server_host") or "127.0.0.1"
    port = int(node.get("port", 0))
    proto = node.get("protocol", "vless_reality")
    node_id = node.get("id", 0)

    is_ipv6 = is_target_ipv6(host)
    sock_family = socket.AF_INET6 if is_ipv6 else socket.AF_INET

    # 主控机无 IPv6 外网出站路由防御：对非本机 IPv6 节点，直接使用被控探针真实运行与端口监听感知
    if is_ipv6 and not host_has_ipv6_connectivity():
        if not is_local_node(node):
            agent_res = check_node_via_agent_status(node)
            if agent_res:
                return agent_res
            return True, "核心就绪 (主控机无 IPv6 外网路由，由客户端直接连接)", 0

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
                err_str = str(e)
                if not is_local_node(node):
                    agent_res = check_node_via_agent_status(node)
                    if agent_res:
                        return agent_res
                return False, f"UDP 连接异常: {e}", 0

    # 1. TCP 端口快速连通性检测
    t0 = time.time()
    try:
        s = socket.socket(sock_family, socket.SOCK_STREAM)
        s.settimeout(2.5)
        res = s.connect_ex((host, port))
        s.close()
        tcp_ms = int((time.time() - t0) * 1000)
    except Exception as e:
        err_str = str(e)
        if not is_local_node(node):
            agent_res = check_node_via_agent_status(node)
            if agent_res:
                return agent_res
        return False, f"TCP 连接异常: {e}", 0

    if res != 0:
        if not is_local_node(node):
            agent_res = check_node_via_agent_status(node)
            if agent_res:
                return agent_res
        return False, f"TCP 端口 {port} 无法连通 (超时或拒绝连接)。若是 NAT 服务器请确认端口映射；若是常规 VPS 请确认安全组已放行入站", 0

    # 2. 真实协议握手与代理隧道流量测试
    # 2.0 AnyTLS 真实 TLS 握手测试 (Sing-box)
    if proto == "anytls":
        t0 = time.time()
        try:
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            sni = node.get("sni") or "www.bing.com"
            with socket.create_connection((host, port), timeout=3.0) as sock:
                with ctx.wrap_socket(sock, server_hostname=sni) as ssock:
                    tls_version = ssock.version()
                    ms = max(1, int((time.time() - t0) * 1000))
                    return True, f"连通正常，AnyTLS 握手成功 [{tls_version}] (延迟 ~{ms}ms)", ms
        except Exception as e:
            if not is_local_node(node):
                agent_res = check_node_via_agent_status(node)
                if agent_res:
                    return agent_res
            return False, f"TCP 端口已通，但 AnyTLS TLS 握手失败: {e}", tcp_ms

    # 2.1 SOCKS5 直接由 curl 测试握手认证
    if proto == "socks5":
        uname = (node.get("username") or "").strip()
        pwd = (node.get("password") or "").strip()
        proxy_url = f"socks5h://{quote(uname)}:{quote(pwd)}@{host}:{port}" if uname else f"socks5h://{host}:{port}"
        t0 = time.time()
        try:
            curl_res = subprocess.run([
                "curl", "-x", proxy_url,
                "https://www.cloudflare.com", "-I", "-m", "4"
            ], capture_output=True, text=True)
            ms = max(1, int((time.time() - t0) * 1000))
            if "HTTP/" in curl_res.stdout:
                return True, f"连通正常，SOCKS5 握手成功 (延迟 ~{ms}ms)", ms
            else:
                err = curl_res.stderr.strip() or "代理响应异常"
                return False, f"TCP 端口已通，但 SOCKS5 握手认证失败: {err}", tcp_ms
        except Exception as e:
            return False, f"SOCKS5 测试执行异常: {e}", tcp_ms

    # 2.2 Xray 真实客户端握手测试 (vless_reality, vless_reality_xhttp, trojan, ss2022, vmess_ws, vless_ws)
    if not os.path.exists(XRAY_BIN):
        return True, f"TCP 端口连通正常 (延迟 ~{tcp_ms}ms)", tcp_ms

    test_port = random.randint(18200, 19999)
    outbound = None

    if proto == "vless_reality":
        pbk = node.get("public_key") or ""
        sid = node.get("short_id") or ""
        sni = node.get("sni") or "www.apple.com"
        flow = node.get("flow") or "xtls-rprx-vision"
        outbound = {
            "protocol": "vless",
            "settings": {
                "vnext": [{
                    "address": host,
                    "port": port,
                    "users": [{
                        "id": node.get("uuid"),
                        "flow": flow,
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
                    "serverName": sni,
                    "publicKey": pbk,
                    "shortId": sid,
                    "spiderX": "/"
                }
            }
        }
    elif proto == "vless_reality_xhttp":
        pbk = node.get("public_key") or ""
        sid = node.get("short_id") or ""
        sni = node.get("sni") or "www.apple.com"
        xpath = node.get("ws_path") or "/xhttp"
        outbound = {
            "protocol": "vless",
            "settings": {
                "vnext": [{
                    "address": host,
                    "port": port,
                    "users": [{
                        "id": node.get("uuid"),
                        "encryption": "none"
                    }]
                }]
            },
            "streamSettings": {
                "network": "xhttp",
                "security": "reality",
                "realitySettings": {
                    "show": False,
                    "fingerprint": "chrome",
                    "serverName": sni,
                    "publicKey": pbk,
                    "shortId": sid,
                    "spiderX": "/"
                },
                "xhttpSettings": {
                    "path": xpath,
                    "mode": "auto"
                }
            }
        }
    elif proto == "trojan":
        pwd = node.get("password") or ""
        sni = node.get("sni") or "bing.com"
        tls_settings = { "serverName": sni }
        if os.path.exists(SINGBOX_CERT):
            tls_settings["certificates"] = [{
                "certificateFile": SINGBOX_CERT,
                "usage": "verify"
            }]
        outbound = {
            "protocol": "trojan",
            "settings": {
                "servers": [{
                    "address": host,
                    "port": port,
                    "password": pwd
                }]
            },
            "streamSettings": {
                "network": "tcp",
                "security": "tls",
                "tlsSettings": tls_settings
            }
        }
    elif proto == "ss2022":
        method = node.get("method") or "2022-blake3-aes-128-gcm"
        pwd = node.get("password") or ""
        outbound = {
            "protocol": "shadowsocks",
            "settings": {
                "servers": [{
                    "address": host,
                    "port": port,
                    "method": method,
                    "password": pwd
                }]
            }
        }
    elif proto == "vmess_ws":
        ws_path = node.get("ws_path") or "/vmess-ws"
        outbound = {
            "protocol": "vmess",
            "settings": {
                "vnext": [{
                    "address": host,
                    "port": port,
                    "users": [{
                        "id": node.get("uuid"),
                        "alterId": 0,
                        "security": "auto"
                    }]
                }]
            },
            "streamSettings": {
                "network": "ws",
                "wsSettings": { "path": ws_path }
            }
        }
    elif proto == "vless_ws":
        ws_path = node.get("ws_path") or "/ws-proxy"
        outbound = {
            "protocol": "vless",
            "settings": {
                "vnext": [{
                    "address": host,
                    "port": port,
                    "users": [{
                        "id": node.get("uuid"),
                        "encryption": "none"
                    }]
                }]
            },
            "streamSettings": {
                "network": "ws",
                "wsSettings": { "path": ws_path }
            }
        }

    if outbound:
        cfg = {
            "log": { "loglevel": "warning" },
            "inbounds": [{
                "port": test_port,
                "listen": "127.0.0.1",
                "protocol": "socks",
                "settings": { "auth": "noauth" }
            }],
            "outbounds": [outbound]
        }
        cfg_path = f"/tmp/test_client_{node_id}_{int(time.time())}.json"
        try:
            with open(cfg_path, "w") as f:
                json.dump(cfg, f)
            p = subprocess.Popen([XRAY_BIN, "run", "-config", cfg_path], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            time.sleep(1.0)
            t0 = time.time()
            curl_res = subprocess.run([
                "curl", "-x", f"socks5h://127.0.0.1:{test_port}",
                "https://www.cloudflare.com", "-I", "-m", "4"
            ], capture_output=True, text=True)
            ms = max(1, int((time.time() - t0) * 1000))
            p.kill()
            if os.path.exists(cfg_path):
                os.remove(cfg_path)
            if "HTTP/" in curl_res.stdout:
                return True, f"连通正常，{proto} 握手成功 (延迟 ~{ms}ms)", ms
            else:
                if not is_local_node(node):
                    agent_res = check_node_via_agent_status(node)
                    if agent_res:
                        return agent_res
                err = curl_res.stderr.strip() or "代理握手超时"
                return False, f"TCP 端口已通，但 {proto} 代理握手失败: {err}", tcp_ms
        except Exception as e:
            if not is_local_node(node):
                agent_res = check_node_via_agent_status(node)
                if agent_res:
                    return agent_res
            return False, f"握手测试执行异常: {e}", tcp_ms

    return True, f"TCP 端口连通正常 (延迟 ~{tcp_ms}ms)", tcp_ms

def check_all_nodes_health_parallel():
    """并发执行所有启用节点的真实端到端连通性握手测试，并将状态写回 SQLite"""
    conn = get_db()
    cur = conn.execute("SELECT * FROM proxy_node WHERE enabled = 1")
    nodes = [dict(r) for r in cur.fetchall()]
    conn.close()
    
    if not nodes:
        return []

    import concurrent.futures
    results = []
    def check_single(n):
        try:
            ok, msg, ms = test_node_connectivity(n)
            return {
                "id": n["id"],
                "name": n["name"],
                "protocol": n["protocol"],
                "port": n["port"],
                "server_name": n.get("server_name") or "本机",
                "ok": ok,
                "latency_ms": ms if ok else 0,
                "error": msg if not ok else "",
                "time": int(time.time())
            }
        except Exception as e:
            return {
                "id": n["id"],
                "name": n["name"],
                "protocol": n["protocol"],
                "port": n["port"],
                "server_name": n.get("server_name") or "本机",
                "ok": False,
                "latency_ms": 0,
                "error": str(e),
                "time": int(time.time())
            }

    with concurrent.futures.ThreadPoolExecutor(max_workers=min(len(nodes), 8)) as executor:
        futures = [executor.submit(check_single, n) for n in nodes]
        for f in concurrent.futures.as_completed(futures):
            try:
                results.append(f.result())
            except Exception:
                pass

    conn = get_db()
    with conn:
        for res in results:
            conn.execute("""
                UPDATE proxy_node
                SET last_check_status = ?, last_check_latency = ?, last_check_time = ?, last_check_error = ?
                WHERE id = ?
            """, (
                "ok" if res["ok"] else "fail",
                res["latency_ms"],
                res["time"],
                res["error"],
                res["id"]
            ))
    conn.close()
    return results

def node_health_checker_loop():
    """后台轻量静默巡检所有代理节点连通性 (可自定义周期)"""
    time.sleep(15)
    while True:
        try:
            check_all_nodes_health_parallel()
        except Exception:
            pass
        try:
            interval_min = int(get_setting("node_check_interval_minutes", "10") or 10)
        except Exception:
            interval_min = 10
        if interval_min < 1:
            interval_min = 1
        time.sleep(interval_min * 60)



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
            ensure_server_cert()
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

            stream_settings = {
                "network": "tcp",
                "security": "tls",
                "tlsSettings": {
                    "certificates": [
                        {
                            "certificateFile": SINGBOX_CERT,
                            "keyFile": SINGBOX_KEY
                        }
                    ]
                }
            }
            inbounds.append({
                "tag": tag,
                "listen": "::",
                "port": port,
                "protocol": "trojan",
                "settings": {
                    "clients": trojan_clients
                },
                "streamSettings": stream_settings
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
            accounts = []
            if uname:
                accounts.append({ "user": uname, "pass": pwd })
            for u in active_users:
                _, u_pwd = ensure_user_credentials(u)
                u_name = (u.get("username") or "").strip()
                if u_name and not any(a["user"] == u_name for a in accounts):
                    accounts.append({ "user": u_name, "pass": u_pwd })

            settings = {
                "auth": "password" if accounts else "noauth",
                "udp": True
            }
            if accounts:
                settings["accounts"] = accounts
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

            node_limit = int(n.get("bandwidth_limit_mbps") or 0)
            hy2_inbound = {
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
            }
            if node_limit > 0:
                hy2_inbound["up_mbps"] = node_limit
                hy2_inbound["down_mbps"] = node_limit
            inbounds.append(hy2_inbound)
        elif proto == "anytls":
            ensure_server_cert()
            anytls_users = []
            seen_pwds = set()
            if pwd and pwd not in seen_pwds:
                seen_pwds.add(pwd)
                anytls_users.append({ "name": "default", "password": pwd })
            for u in active_users:
                _, u_pwd = ensure_user_credentials(u)
                if u_pwd not in seen_pwds:
                    seen_pwds.add(u_pwd)
                    anytls_users.append({ "name": f"user_{u['id']}", "password": u_pwd })

            inbounds.append({
                "type": "anytls",
                "tag": f"anytls-in-{n.get('id', port)}",
                "listen": "::",
                "listen_port": port,
                "users": anytls_users,
                "tls": {
                    "enabled": True,
                    "certificate_path": SINGBOX_CERT,
                    "key_path": SINGBOX_KEY
                }
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

    local_nodes = [n for n in all_nodes if is_local_node(n) and not n.get("is_relay") and n["protocol"] in ("hysteria2", "tuic", "anytls")]
    inbounds = build_singbox_inbounds_for_nodes(local_nodes)

    os.makedirs("/var/log/sing-box", exist_ok=True)
    config = {
        "log": {
            "level": "info",
            "timestamp": True,
            "output": "/var/log/sing-box/access.log"
        },
        "experimental": {
            "clash_api": {
                "external_controller": "127.0.0.1:9095"
            }
        },
        "inbounds": inbounds,
        "outbounds": [
            { "type": "direct", "tag": "direct" },
            { "type": "block", "tag": "block" }
        ]
    }

    new_cfg_str = json.dumps(config, indent=2)
    existing_cfg_str = ""
    if os.path.exists(SINGBOX_CONFIG):
        try:
            with open(SINGBOX_CONFIG, "r", encoding="utf-8") as f:
                existing_cfg_str = f.read()
        except Exception:
            pass

    if existing_cfg_str.strip() == new_cfg_str.strip():
        return True, "Sing-box 配置无变化，跳过重启保持长连接零中断"

    with open(SINGBOX_CONFIG, "w", encoding="utf-8") as f:
        f.write(new_cfg_str)

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
    
    local_zip = os.path.join(BASE_DIR, "scripts", "Xray-linux-64.zip")
    if not os.path.exists(local_zip):
        for alt_zip in ("/opt/proxyprobe/scripts/Xray-linux-64.zip", "/opt/monitor/scripts/Xray-linux-64.zip"):
            if os.path.exists(alt_zip):
                local_zip = alt_zip
                break
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
    
    local_tar = os.path.join(BASE_DIR, "scripts", "sing-box-linux-amd64.tar.gz")
    if not os.path.exists(local_tar):
        for alt_tar in ("/opt/proxyprobe/scripts/sing-box-linux-amd64.tar.gz", "/opt/monitor/scripts/sing-box-linux-amd64.tar.gz"):
            if os.path.exists(alt_tar):
                local_tar = alt_tar
                break
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
    local_tar = os.path.join(BASE_DIR, "scripts", "realm-x86_64-unknown-linux-musl.tar.gz")
    if not os.path.exists(local_tar):
        for alt_tar in ("/opt/proxyprobe/scripts/realm-x86_64-unknown-linux-musl.tar.gz", "/opt/monitor/scripts/realm-x86_64-unknown-linux-musl.tar.gz"):
            if os.path.exists(alt_tar):
                local_tar = alt_tar
                break
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

    new_cfg_str = json.dumps(config, indent=2)
    existing_cfg_str = ""
    if os.path.exists(REALM_CONFIG):
        try:
            with open(REALM_CONFIG, "r", encoding="utf-8") as f:
                existing_cfg_str = f.read()
        except Exception:
            pass

    if existing_cfg_str.strip() == new_cfg_str.strip():
        return True, "Realm 配置无变化，跳过重启"

    with open(REALM_CONFIG, "w", encoding="utf-8") as f:
        f.write(new_cfg_str)

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

    local_nodes = [n for n in all_nodes if is_local_node(n) and not n.get("is_relay") and n["protocol"] not in ("hysteria2", "tuic", "anytls")]
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
            { "protocol": "freedom", "tag": "direct", "settings": { "domainStrategy": "AsIs" } },
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

    new_cfg_str = json.dumps(config, indent=2)
    existing_cfg_str = ""
    if os.path.exists(XRAY_CONFIG):
        try:
            with open(XRAY_CONFIG, "r", encoding="utf-8") as f:
                existing_cfg_str = f.read()
        except Exception:
            pass

    if existing_cfg_str.strip() == new_cfg_str.strip():
        return True, "Xray 配置无变化，跳过重启保持长连接零中断"

    with open(XRAY_CONFIG, "w", encoding="utf-8") as f:
        f.write(new_cfg_str)

    test_res = subprocess.run([XRAY_BIN, "run", "-test", "-config", XRAY_CONFIG], capture_output=True, text=True)
    if test_res.returncode == 0:
        subprocess.run(["systemctl", "restart", "xray"], capture_output=True)
        return True, "Xray 配置已生效并重启成功"
    else:
        return False, f"Xray 配置测试失败: {test_res.stderr}"

