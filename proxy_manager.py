import base64
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
import gzip
import ipaddress
import json
import os
import random
import re
import secrets
import shutil
import socket
import sqlite3
import ssl
import smtplib
import struct
import subprocess
import sys
import tempfile
from email.header import Header
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
import threading
import time
import urllib.error
import urllib.request
import uuid
from hashlib import sha256
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, unquote, urlparse
try:
    import license_guard
except ImportError:
    license_guard = None

# 修复 PyInstaller 环境变量污染子进程问题 (杜绝 LD_LIBRARY_PATH 干扰 systemctl / xray / sing-box)
if getattr(sys, 'frozen', False):
    if 'LD_LIBRARY_PATH_ORIG' in os.environ:
        os.environ['LD_LIBRARY_PATH'] = os.environ['LD_LIBRARY_PATH_ORIG']
    else:
        os.environ.pop('LD_LIBRARY_PATH', None)

BASE_DIR = "/opt/proxyprobe" if os.path.exists("/opt/proxyprobe") else "/opt/monitor"
DATA_DIR = os.path.join(BASE_DIR, "data")
DB_PATH = os.path.join(DATA_DIR, "proxyprobe.db") if os.path.exists(os.path.join(DATA_DIR, "proxyprobe.db")) else os.path.join(DATA_DIR, "monitor.db")
XRAY_BIN = "/usr/local/bin/xray"
XRAY_CONFIG = "/etc/xray/config.json"
SINGBOX_BIN = "/usr/local/bin/sing-box"
SINGBOX_CONFIG = "/etc/sing-box/config.json"
SINGBOX_CERT = "/etc/sing-box/cert.pem"
SINGBOX_KEY = "/etc/sing-box/key.pem"
REALM_BIN = "/usr/local/bin/realm"
REALM_CONFIG = "/etc/realm/config.json"
_LAST_AUTO_RECOVER_ATTEMPT_TS = 0

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

PORT = int(os.environ.get("PROXY_MANAGER_PORT", 28090))
for _i, _arg in enumerate(sys.argv):
    if _arg == "--port" and _i + 1 < len(sys.argv):
        try:
            PORT = int(sys.argv[_i + 1])
        except ValueError:
            pass
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", ""}

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

def is_private_ip(addr):
    if not addr:
        return True
    try:
        import ipaddress
        ip = ipaddress.ip_address(str(addr).strip())
        return ip.is_private or ip.is_loopback or ip.is_reserved or ip.is_link_local
    except Exception:
        return False

_SERVER_PUBLIC_IP_CACHE = {"ip": "", "ts": 0}

def get_server_public_ip():
    now = time.time()
    if _SERVER_PUBLIC_IP_CACHE["ip"] and (now - _SERVER_PUBLIC_IP_CACHE["ts"] < 300):
        return _SERVER_PUBLIC_IP_CACHE["ip"]
    
    # 1. 优先尝试本地出站套接字探测 (最快且不消耗网络请求)
    ip = get_local_ip(socket.AF_INET)
    if ip and not is_private_ip(ip):
        _SERVER_PUBLIC_IP_CACHE["ip"] = ip
        _SERVER_PUBLIC_IP_CACHE["ts"] = now
        LOCAL_HOSTS.add(ip)
        return ip
        
    # 2. 多源公网 IP 接口快速获取 (超时 2 秒防阻塞)
    for url in ("https://api.ipify.org", "https://icanhazip.com", "https://ip.sb"):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/7.68.0"})
            with urllib.request.urlopen(req, timeout=2) as resp:
                text = resp.read().decode("utf-8").strip()
                if text and not is_private_ip(text):
                    _SERVER_PUBLIC_IP_CACHE["ip"] = text
                    _SERVER_PUBLIC_IP_CACHE["ts"] = now
                    LOCAL_HOSTS.add(text)
                    return text
        except Exception:
            continue

    return ip or ""

def get_request_base_url(headers=None):
    if headers:
        host = headers.get("X-Forwarded-Host") or headers.get("Host") or ""
        host = host.split(",")[0].strip()
        proto = headers.get("X-Forwarded-Proto") or ("https" if headers.get("X-Forwarded-Ssl") == "on" else "http")
        proto = proto.split(",")[0].strip()
        if host:
            return f"{proto}://{host}"
    local_ip = get_server_public_ip() or get_local_ip() or "127.0.0.1"
    return f"http://{local_ip}"

def format_host_for_uri(host):
    if not host:
        return "127.0.0.1"
    host_str = str(host).strip()
    if ":" in host_str and not host_str.startswith("["):
        return f"[{host_str}]"
    return host_str


# =============================================================================
# 探针被控节点一键安装与守护进程模板 (Proxy Agent Templates)
# 已解耦至 modules/agent_templates.py
# =============================================================================
from modules.agent_templates import PROXY_AGENT_SH, PROXY_AGENT_PY

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
            server_host TEXT DEFAULT '',
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
            ("target_node_id", "INTEGER DEFAULT 0"),
            ("upload_bytes", "INTEGER DEFAULT 0"),
            ("download_bytes", "INTEGER DEFAULT 0"),
            ("last_check_status", "TEXT DEFAULT ''"),
            ("last_check_latency", "INTEGER DEFAULT 0"),
            ("last_check_time", "INTEGER DEFAULT 0"),
            ("last_check_error", "TEXT DEFAULT ''"),
            ("bandwidth_limit_mbps", "INTEGER DEFAULT 0"),
            ("vip_levels", "TEXT DEFAULT ''")
        ]:
            try:
                conn.execute(f"ALTER TABLE proxy_node ADD COLUMN {col_name} {col_type}")
            except Exception:
                pass

        try:
            conn.execute("ALTER TABLE proxy_user ADD COLUMN email TEXT DEFAULT ''")
        except Exception:
            pass

        try:
            conn.execute("ALTER TABLE proxy_user ADD COLUMN bandwidth_limit_mbps INTEGER DEFAULT 0")
        except Exception:
            pass

        try:
            conn.execute("ALTER TABLE proxy_user ADD COLUMN vip_level TEXT DEFAULT 'vip1'")
        except Exception:
            pass

        # VIP 套餐等级表
        conn.execute("""
        CREATE TABLE IF NOT EXISTS proxy_tier (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tier_key TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            speed_limit_mbps INTEGER DEFAULT 0,
            device_limit INTEGER DEFAULT 0,
            sort_order INTEGER DEFAULT 0,
            created_at INTEGER NOT NULL
        )
        """)
        try:
            cur_t = conn.execute("SELECT COUNT(*) FROM proxy_tier")
            if cur_t.fetchone()[0] == 0:
                now_init = int(time.time())
                conn.execute("INSERT INTO proxy_tier (tier_key, name, description, speed_limit_mbps, device_limit, sort_order, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                             ("vip1", "VIP1 基础会员", "标准高速节点接入", 100, 3, 1, now_init))
                conn.execute("INSERT INTO proxy_tier (tier_key, name, description, speed_limit_mbps, device_limit, sort_order, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                             ("vip2", "VIP2 进阶专线", "专线低延迟高速节点", 300, 5, 2, now_init))
                conn.execute("INSERT INTO proxy_tier (tier_key, name, description, speed_limit_mbps, device_limit, sort_order, created_at) VALUES (?, ?, ?, ?, ?, ?, ?)",
                             ("vip3", "VIP3 旗舰尊享", "顶级全协议极速专线", 1000, 10, 3, now_init))
        except Exception:
            pass

        # VIP 套餐扩展字段与默认价格
        for col_name, col_def in [
            ("tier_id", "TEXT DEFAULT ''"),
            ("price_monthly", "REAL DEFAULT 0"),
            ("price_quarterly", "REAL DEFAULT 0"),
            ("price_yearly", "REAL DEFAULT 0"),
            ("traffic_gb", "REAL DEFAULT 0"),
        ]:
            try:
                conn.execute(f"ALTER TABLE proxy_tier ADD COLUMN {col_name} {col_def}")
            except Exception:
                pass

        try:
            conn.execute("UPDATE proxy_tier SET tier_id = tier_key WHERE tier_id = '' OR tier_id IS NULL")
            conn.execute("UPDATE proxy_tier SET price_monthly = 15.0, price_quarterly = 40.0, price_yearly = 150.0 WHERE tier_key = 'vip1' AND (price_monthly = 0 OR price_monthly IS NULL)")
            conn.execute("UPDATE proxy_tier SET price_monthly = 30.0, price_quarterly = 80.0, price_yearly = 300.0 WHERE tier_key = 'vip2' AND (price_monthly = 0 OR price_monthly IS NULL)")
            conn.execute("UPDATE proxy_tier SET price_monthly = 60.0, price_quarterly = 160.0, price_yearly = 600.0 WHERE tier_key = 'vip3' AND (price_monthly = 0 OR price_monthly IS NULL)")
        except Exception:
            pass

        # 用户表扩展余额字段
        try:
            conn.execute("ALTER TABLE proxy_user ADD COLUMN balance REAL DEFAULT 0.0")
        except Exception:
            pass

        # 订单与支付记录表
        conn.execute("""
        CREATE TABLE IF NOT EXISTS proxy_order (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_no TEXT UNIQUE NOT NULL,
            user_id INTEGER NOT NULL,
            username TEXT NOT NULL,
            tier_id INTEGER DEFAULT 0,
            tier_key TEXT DEFAULT '',
            tier_name TEXT NOT NULL,
            period TEXT NOT NULL,
            amount REAL NOT NULL,
            pay_method TEXT DEFAULT 'balance',
            status TEXT DEFAULT 'pending',
            note TEXT DEFAULT '',
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """)

        # 系统公告表
        conn.execute("""
        CREATE TABLE IF NOT EXISTS proxy_announcement (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            summary TEXT DEFAULT '',
            content TEXT NOT NULL,
            is_pinned INTEGER DEFAULT 0,
            enabled INTEGER DEFAULT 1,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL
        )
        """)

        # 客户端下载专区表
        conn.execute("""
        CREATE TABLE IF NOT EXISTS proxy_app_download (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            platform TEXT DEFAULT 'all',
            version TEXT DEFAULT '',
            description TEXT DEFAULT '',
            file_path TEXT DEFAULT '',
            file_name TEXT DEFAULT '',
            file_size INTEGER DEFAULT 0,
            external_url TEXT DEFAULT '',
            sort_order INTEGER DEFAULT 0,
            enabled INTEGER DEFAULT 1,
            created_at INTEGER NOT NULL
        )
        """)
        try:
            cur_a = conn.execute("SELECT COUNT(*) FROM proxy_app_download")
            if cur_a.fetchone()[0] == 0:
                now_init = int(time.time())
                presets = [
                    ("Clash Verge Rev", "windows", "v1.7.5", "支持分流规则与全协议的现代跨平台客户端 (Windows 推荐)", "", "", 0, "https://github.com/clash-verge-rev/clash-verge-rev/releases", 1, 1, now_init),
                    ("NekoBox for Android", "android", "v1.3.1", "Android 平台强大通用的轻量级代理核心客户端", "", "", 0, "https://github.com/MatsuriDayo/NekoBoxForAndroid/releases", 2, 1, now_init),
                    ("FLClash", "all", "v0.8.69", "颜值极高、功能现代的全平台 Clash 客户端 (Win/Mac/Android)", "", "", 0, "https://github.com/chen08209/FlClash/releases", 3, 1, now_init),
                    ("Hiddify", "all", "v2.5.7", "全协议自适应、极致防识别的全平台通用客户端", "", "", 0, "https://github.com/hiddify/hiddify-app/releases", 4, 1, now_init),
                    ("Shadowrocket (小火箭)", "ios", "最新版", "iOS / iPadOS 经典翻墙网络调试利器 (需非国区 AppStore 下载)", "", "", 0, "https://apps.apple.com/app/shadowrocket/id932747118", 5, 1, now_init),
                    ("v2rayN", "windows", "v6.42", "Windows 经典全协议支持核心客户端 (内置 Xray / Sing-box)", "", "", 0, "https://github.com/2dust/v2rayN/releases", 6, 1, now_init)
                ]
                for p in presets:
                    conn.execute("""
                        INSERT INTO proxy_app_download (name, platform, version, description, file_path, file_name, file_size, external_url, sort_order, enabled, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, p)
        except Exception:
            pass

        try:
            os.makedirs(os.path.join(BASE_DIR, "uploads", "apps"), exist_ok=True)
        except Exception:
            pass

        conn.execute("""
        CREATE TABLE IF NOT EXISTS email_verify_code (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT NOT NULL,
            code TEXT NOT NULL,
            action_type TEXT NOT NULL,
            expires_at INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            ip TEXT DEFAULT ''
        )
        """)

        conn.execute("""
        CREATE TABLE IF NOT EXISTS proxy_traffic_hourly (
            time_bucket INTEGER NOT NULL PRIMARY KEY,
            upload_bytes INTEGER DEFAULT 0,
            download_bytes INTEGER DEFAULT 0
        )
        """)

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

        # Migration: ensure theme_style exists
        try:
            conn.execute("ALTER TABLE proxy_user ADD COLUMN theme_style TEXT DEFAULT 'default'")
        except sqlite3.OperationalError:
            pass

        # Migration: ensure last_active_at exists
        try:
            conn.execute("ALTER TABLE proxy_user ADD COLUMN last_active_at INTEGER DEFAULT 0")
        except sqlite3.OperationalError:
            pass

        # Initialize in-memory last seen cache
        try:
            cur_seen = conn.execute("SELECT id, last_active_at FROM proxy_user WHERE last_active_at > 0")
            for r in cur_seen.fetchall():
                _user_last_seen[r["id"]] = r["last_active_at"]
        except Exception:
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

def get_sub_token():
    return get_setting("proxy_sub_token", "default-token")

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

# =============================================================================
# Telegram 机器人交互与定时异地备份推送引擎 (Telegram Engine)
# 已解耦至 modules/telegram_engine.py
# =============================================================================
from modules.telegram_engine import (
    send_telegram_msg,
    send_telegram_document,
    perform_telegram_backup,
    telegram_backup_loop,
    check_server_expirations,
    telegram_node_alert_loop,
    telegram_bot_command_loop,
    server_expiry_check_loop,
    init_telegram_context,
)

init_telegram_context(
    get_db_fn=get_db,
    get_setting_fn=get_setting,
    set_setting_fn=set_setting,
    gen_backup_gz_fn=generate_backup_gz,
    check_nodes_health_fn=lambda: check_all_nodes_health_parallel()
)

# =============================================================================
# 一键平滑换机与数据迁移体系 (Zero-Touch Server Migration System)
# 已解耦至 modules/migration_engine.py
# =============================================================================
from modules.migration_engine import (
    _MIGRATION_TOKENS,
    _MIGRATION_LOCK,
    clean_expired_migration_tokens,
    is_ip_address,
    update_caddy_domain_alias,
    apply_restored_database as _raw_apply_restored_db,
    generate_clone_script
)

def apply_restored_database(raw_db_bytes, source_domain="", source_ip="", target_domain=""):
    return _raw_apply_restored_db(
        raw_db_bytes,
        source_domain=source_domain,
        source_ip=source_ip,
        target_domain=target_domain,
        db_path=DB_PATH,
        get_db_fn=get_db,
        get_ip_fn=get_server_public_ip
    )


def send_smtp_email(to_email, subject, html_content):
    host = get_setting("smtp_host", "").strip()
    port = int(get_setting("smtp_port", "465"))
    user = get_setting("smtp_user", "").strip()
    password = get_setting("smtp_pass", "").strip()
    from_name = get_setting("smtp_from_name", "HHUB").strip()
    use_ssl = get_setting("smtp_ssl", "1") == "1"

    if not host or not user or not password:
        return False, "发信邮箱尚未配置，请管理员在后台「设置」中配置 SMTP 参数"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = Header(subject, "utf-8")
    msg["From"] = f"{Header(from_name, 'utf-8').encode()} <{user}>"
    msg["To"] = to_email

    part = MIMEText(html_content, "html", "utf-8")
    msg.attach(part)

    try:
        if use_ssl or port == 465:
            server = smtplib.SMTP_SSL(host, port, timeout=15)
        else:
            server = smtplib.SMTP(host, port, timeout=15)
            server.starttls()
        server.login(user, password)
        server.sendmail(user, [to_email], msg.as_string())
        server.quit()
        return True, "邮件发送成功"
    except Exception as e:
        return False, f"发信失败: {e}"

def generate_verification_email_html(site_name, code, purpose_text):
    return f"""
    <div style="max-width: 520px; margin: 0 auto; padding: 32px 24px; font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background: #ffffff; border: 1px solid #e5e7eb; border-radius: 16px; box-shadow: 0 10px 15px -3px rgba(0,0,0,0.05);">
        <div style="text-align: center; margin-bottom: 24px;">
            <h2 style="color: #111827; font-size: 22px; font-weight: 800; margin: 0; letter-spacing: -0.5px;">{site_name}</h2>
            <p style="color: #6b7280; font-size: 13px; margin: 6px 0 0;">安全中心 · {purpose_text}</p>
        </div>
        <div style="background: #f8fafc; border: 1px solid #e2e8f0; border-radius: 12px; padding: 22px; text-align: center; margin-bottom: 24px;">
            <div style="font-size: 12px; color: #64748b; margin-bottom: 8px; font-weight: 500;">您的 6 位数字验证码</div>
            <span style="font-size: 36px; font-weight: 900; letter-spacing: 8px; color: #4f46e5; font-family: monospace;">{code}</span>
        </div>
        <p style="color: #334155; font-size: 13px; line-height: 1.6; margin: 0 0 12px;">
            您正在进行 <strong>{purpose_text}</strong> 操作，请在 <strong>10 分钟</strong> 内输入上方验证码完成验证。
        </p>
        <p style="color: #94a3b8; font-size: 12px; line-height: 1.5; margin: 0;">
            提示：如果这不是您本人的操作，请忽略此邮件，切勿将验证码泄露给任何人。
        </p>
        <div style="border-top: 1px solid #f1f5f9; margin-top: 28px; padding-top: 16px; text-align: center; color: #94a3b8; font-size: 11px;">
            © {site_name} · 本邮件由系统安全引擎自动发送，请勿直接回复
        </div>
    </div>
    """

def batch_create_nodes_for_server(server_id, protocols, bandwidth_limit_mbps=0, vip_levels=""):
    conn = get_db()
    try:
        # 1. Get server info
        if server_id == 0:
            cur_first = conn.execute("SELECT id, name, ip, ipv4, country FROM node ORDER BY id ASC LIMIT 1")
            first_row = cur_first.fetchone()
            if first_row:
                s_dict = dict(first_row)
                server_id = s_dict["id"]
                s_name = s_dict.get("name") or f"Server-{server_id}"
                s_host = resolve_server_host(s_dict)
            else:
                s_name = "本机"
                s_host = get_setting("server_host", "") or get_server_public_ip() or get_local_ip() or "127.0.0.1"
        else:
            cur = conn.execute("SELECT id, name, ip, ipv4, country FROM node WHERE id = ?", (server_id,))
            s_row = cur.fetchone()
            if not s_row:
                raise ValueError(f"未找到目标服务器 (ID: {server_id})")
            s_dict = dict(s_row)
            s_name = s_dict.get("name") or f"Server-{server_id}"
            s_host = resolve_server_host(s_dict)

        # 2. Find allocated ports
        cur_ports = conn.execute("SELECT port FROM proxy_node")
        used_ports = {r[0] for r in cur_ports.fetchall()}

        needed = len(protocols)
        allocated_ports = []
        candidate = 20000 + random.randint(100, 3000)
        while len(allocated_ports) < needed:
            if candidate not in used_ports:
                allocated_ports.append(candidate)
                used_ports.add(candidate)
            candidate += 1
            if candidate > 65000:
                candidate = 15000

        now = int(time.time())
        created = []
        with conn:
            for proto, port in zip(protocols, allocated_ports):
                uuid_val = str(uuid.uuid4())
                pwd_val = gen_random_password(16)

                if proto == "vless_reality":
                    priv, pub, sid = gen_xray_keys()
                    name = f"[{s_name}] VLESS Reality"
                    cur = conn.execute("""
                        INSERT INTO proxy_node (
                            server_id, server_name, server_host, name, protocol, port,
                            uuid, flow, sni, dest, public_key, private_key, short_id,
                            bandwidth_limit_mbps, vip_levels, enabled, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                    """, (server_id, s_name, s_host, name, proto, port,
                          uuid_val, "xtls-rprx-vision", "www.apple.com", "www.apple.com:443", pub, priv, sid,
                          bandwidth_limit_mbps, vip_levels, now))
                    created.append({"id": cur.lastrowid, "name": name, "protocol": proto, "port": port})

                elif proto == "vless_reality_xhttp":
                    priv, pub, sid = gen_xray_keys()
                    name = f"[{s_name}] VLESS XHTTP"
                    cur = conn.execute("""
                        INSERT INTO proxy_node (
                            server_id, server_name, server_host, name, protocol, port,
                            uuid, flow, sni, dest, public_key, private_key, short_id, ws_path,
                            bandwidth_limit_mbps, vip_levels, enabled, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                    """, (server_id, s_name, s_host, name, proto, port,
                          uuid_val, "", "www.apple.com", "www.apple.com:443", pub, priv, sid, "/xhttp",
                          bandwidth_limit_mbps, vip_levels, now))
                    created.append({"id": cur.lastrowid, "name": name, "protocol": proto, "port": port})

                elif proto == "hysteria2":
                    name = f"[{s_name}] Hysteria 2"
                    cur = conn.execute("""
                        INSERT INTO proxy_node (
                            server_id, server_name, server_host, name, protocol, port,
                            uuid, password, sni,
                            bandwidth_limit_mbps, vip_levels, enabled, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                    """, (server_id, s_name, s_host, name, proto, port,
                          uuid_val, pwd_val, "bing.com",
                          bandwidth_limit_mbps, vip_levels, now))
                    created.append({"id": cur.lastrowid, "name": name, "protocol": proto, "port": port})

                elif proto == "anytls":
                    name = f"[{s_name}] AnyTLS"
                    cur = conn.execute("""
                        INSERT INTO proxy_node (
                            server_id, server_name, server_host, name, protocol, port,
                            uuid, password, sni,
                            bandwidth_limit_mbps, vip_levels, enabled, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                    """, (server_id, s_name, s_host, name, proto, port,
                          uuid_val, pwd_val, "www.bing.com",
                          bandwidth_limit_mbps, vip_levels, now))
                    created.append({"id": cur.lastrowid, "name": name, "protocol": proto, "port": port})

                elif proto == "trojan":
                    name = f"[{s_name}] Trojan"
                    cur = conn.execute("""
                        INSERT INTO proxy_node (
                            server_id, server_name, server_host, name, protocol, port,
                            uuid, password, sni,
                            bandwidth_limit_mbps, vip_levels, enabled, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                    """, (server_id, s_name, s_host, name, proto, port,
                          uuid_val, pwd_val, "bing.com",
                          bandwidth_limit_mbps, vip_levels, now))
                    created.append({"id": cur.lastrowid, "name": name, "protocol": proto, "port": port})

                elif proto == "ss2022":
                    name = f"[{s_name}] Shadowsocks 2022"
                    psk = base64.b64encode(secrets.token_bytes(16)).decode("utf-8")
                    cur = conn.execute("""
                        INSERT INTO proxy_node (
                            server_id, server_name, server_host, name, protocol, port,
                            uuid, password, method,
                            bandwidth_limit_mbps, vip_levels, enabled, created_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                    """, (server_id, s_name, s_host, name, proto, port,
                          uuid_val, psk, "2022-blake3-aes-128-gcm",
                          bandwidth_limit_mbps, vip_levels, now))
                    created.append({"id": cur.lastrowid, "name": name, "protocol": proto, "port": port})
    finally:
        conn.close()

    threading.Thread(target=apply_all_configs, daemon=True).start()
    return created

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
                    u_row = conn.execute("SELECT * FROM proxy_user WHERE sub_token = ?", (b_tok,)).fetchone()
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

# =============================================================================
# 用户在线状态感知、设备限额与流量控制引擎 (User Engine)
# 已解耦至 modules/user_engine.py
# =============================================================================
from modules.user_engine import (
    _user_active_ips,
    _user_last_seen,
    _sb_ip_to_user,
    _sb_ipport_to_user,
    _sb_ip_to_node,
    _sb_ipport_to_node,
    _sb_pending_sessions,
    format_time_ago,
    update_device_tracker,
    is_user_over_device_limit,
    get_active_users,
    TCManager,
    sync_traffic_control,
    traffic_collector_loop,
    get_user_online_device_count,
    init_user_context,
)

init_user_context(get_db_fn=get_db, apply_all_configs_fn=lambda: apply_all_configs())

# =============================================================================
# 节点密钥生成、沙盒握手连通性与巡检引擎 (Node Engine - Part 1)
# 已解耦至 modules/node_engine.py
# =============================================================================
from modules.node_engine import (
    gen_ss2022_key,
    gen_random_password,
    gen_xray_keys,
    gen_uuid,
    get_free_port,
    is_private_ip,
    resolve_server_host,
    is_local_node,
    test_node_connectivity,
    check_all_nodes_health_parallel,
    node_health_checker_loop,
    init_node_context,
)

init_node_context(
    get_db_fn=get_db,
    get_setting_fn=get_setting,
    get_server_ip_fn=get_server_public_ip,
    get_active_users_fn=get_active_users,
    ensure_user_creds_fn=ensure_user_credentials,
    format_host_fn=format_host_for_uri,
    xray_bin=XRAY_BIN,
    xray_config=XRAY_CONFIG,
    singbox_bin=SINGBOX_BIN,
    singbox_config=SINGBOX_CONFIG,
    realm_bin=REALM_BIN,
    realm_config=REALM_CONFIG,
)

# =============================================================================
# 客户端订阅生成与多协议节点格式化引擎 (Subscription Engine - Part 1)
# 已解耦至 modules/subscription_engine.py
# =============================================================================
from modules.subscription_engine import (
    format_node_link,
    build_subscription_info_nodes,
    country_code_to_flag,
    KEYWORD_FLAG_MAP,
    resolve_node_flag,
    format_node_display_name,
    get_server_country_map,
    init_subscription_context,
)

init_subscription_context(get_db_fn=get_db, get_setting_fn=get_setting)


CURRENT_VERSION = "v2.5.34"

def is_legacy_migration_needed() -> bool:
    """
    判断当前系统是否仍运行在旧版目录 /opt/monitor 中。
    旧版目录停止直接 Web 在线覆盖升级，需引导管理员在 SSH 终端执行一键迁移指令 hhub migrate。
    """
    try:
        cur_file = os.path.abspath(__file__)
        if "/opt/monitor" in cur_file:
            return True
        if not os.path.exists("/opt/proxyprobe") and os.path.exists("/opt/monitor"):
            return True
    except Exception:
        pass
    return False

def get_local_version() -> str:
    for ver_file in (os.path.join(BASE_DIR, "VERSION"), "/opt/proxyprobe/VERSION", "/opt/monitor/VERSION"):
        if os.path.exists(ver_file):
            try:
                with open(ver_file, "r", encoding="utf-8") as f:
                    v = f.read().strip()
                    if v:
                        return v
            except Exception:
                pass
    # 若 VERSION 文件缺失，自动在运行目录写入缺省版本号，杜绝版本恒定误判为有更新
    try:
        ver_path = os.path.join(BASE_DIR, "VERSION")
        os.makedirs(os.path.dirname(ver_path), exist_ok=True)
        with open(ver_path, "w", encoding="utf-8") as f:
            f.write(CURRENT_VERSION + "\n")
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

    v_json_url = "https://raw.githubusercontent.com/2290145679/ProxyProbe/main/version.json"
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
            v_raw_url = "https://raw.githubusercontent.com/2290145679/ProxyProbe/main/VERSION"
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

    need_migration = is_legacy_migration_needed()

    result = {
        "ok": True,
        "current_version": cur_ver,
        "latest_version": latest_ver,
        "has_update": has_update,
        "need_migration": need_migration,
        "migration_cmd": "hhub migrate",
        "migration_reason": "ProxyProbe 现已全面升级为独立安装目录 (/opt/proxyprobe)，与原版极简探针 100% 独立共存、配置完全隔离。为保障生产数据库与配置安全，旧目录已停止直接在线覆盖，请在 SSH 终端执行一键迁移指令平滑切换至新架构！",
        "title": title or f"ProxyProbe {latest_ver} 最新版本",
        "changelog": changelog,
        "release_date": release_date,
        "release_url": "https://github.com/2290145679/ProxyProbe"
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
            for sp in (os.path.join(BASE_DIR, "scripts", "hhub.sh"), "/opt/proxyprobe/scripts/hhub.sh", "/opt/monitor/scripts/hhub.sh"):
                if os.path.exists(sp):
                    subprocess.Popen(["bash", sp, "upgrade"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    break
    t = threading.Thread(target=_run, daemon=True)
    t.start()

def get_node_latest_latencies():
    """Query the latest ping latency and recent history for all assigned probes across all nodes."""
    try:
        conn = get_db()
        cur = conn.cursor()

        # 1. 查询每个节点已绑定的 Ping 任务
        cur.execute("""
            SELECT pn.node_id, pt.id AS task_id, pt.name
            FROM ping_node pn
            JOIN ping_task pt ON pt.id = pn.task_id
            ORDER BY pn.node_id, pt.id
        """)
        assigned = cur.fetchall()

        # 2. 查询每个节点每个任务最近 20 次检测记录（按时间正序排列，用于卡片 20 格走势条）
        cur.execute("""
            SELECT node_id, task_id, latency, ts
            FROM (
                SELECT node_id, task_id, latency, ts,
                       ROW_NUMBER() OVER (PARTITION BY node_id, task_id ORDER BY ts DESC) as rn
                FROM ping_record
            )
            WHERE rn <= 20
            ORDER BY node_id, task_id, ts ASC
        """)
        history_rows = cur.fetchall()

        # 3. 统计 1h / 6h / 24h 多时间窗口维度的采样总数、丢包数与均值延迟 (单次复合查询，极简探针原生标准)
        now_ts = int(time.time())
        t_1h = now_ts - 3600
        t_6h = now_ts - 21600
        t_24h = now_ts - 86400
        cur.execute("""
            SELECT node_id, task_id,
                   -- 1 小时
                   COUNT(CASE WHEN ts >= ? THEN 1 END) as total_1h,
                   SUM(CASE WHEN ts >= ? AND (latency IS NULL OR latency < 0) THEN 1 ELSE 0 END) as lost_1h,
                   AVG(CASE WHEN ts >= ? AND latency >= 0 THEN latency ELSE NULL END) as avg_1h,
                   MIN(CASE WHEN ts >= ? AND latency >= 0 THEN latency ELSE NULL END) as min_1h,
                   MAX(CASE WHEN ts >= ? AND latency >= 0 THEN latency ELSE NULL END) as max_1h,
                   -- 6 小时
                   COUNT(CASE WHEN ts >= ? THEN 1 END) as total_6h,
                   SUM(CASE WHEN ts >= ? AND (latency IS NULL OR latency < 0) THEN 1 ELSE 0 END) as lost_6h,
                   AVG(CASE WHEN ts >= ? AND latency >= 0 THEN latency ELSE NULL END) as avg_6h,
                   MIN(CASE WHEN ts >= ? AND latency >= 0 THEN latency ELSE NULL END) as min_6h,
                   MAX(CASE WHEN ts >= ? AND latency >= 0 THEN latency ELSE NULL END) as max_6h,
                   -- 24 小时
                   COUNT(*) as total_24h,
                   SUM(CASE WHEN latency IS NULL OR latency < 0 THEN 1 ELSE 0 END) as lost_24h,
                   AVG(CASE WHEN latency >= 0 THEN latency ELSE NULL END) as avg_24h,
                   MIN(CASE WHEN latency >= 0 THEN latency ELSE NULL END) as min_24h,
                   MAX(CASE WHEN latency >= 0 THEN latency ELSE NULL END) as max_24h
            FROM ping_record
            WHERE ts >= ?
            GROUP BY node_id, task_id
        """, (t_1h, t_1h, t_1h, t_1h, t_1h, t_6h, t_6h, t_6h, t_6h, t_6h, t_24h))
        stats_rows = cur.fetchall()

        WINDOW_CONFIGS = {
            "1h": {"duration": 3600, "step": 120, "slots": 30},
            "6h": {"duration": 21600, "step": 720, "slots": 30},
            "24h": {"duration": 86400, "step": 3600, "slots": 24},
        }

        from collections import defaultdict
        bars_by_window = {}
        for w_key, cfg in WINDOW_CONFIGS.items():
            step = cfg["step"]
            slots = cfg["slots"]
            since = now_ts - cfg["duration"]
            cur.execute("""
                SELECT node_id, task_id, ts / ? as b,
                       AVG(CASE WHEN latency >= 0 THEN latency END) as avg_lat,
                       SUM(CASE WHEN latency < 0 OR latency IS NULL THEN 1 ELSE 0 END) as lost,
                       COUNT(*) as tot
                FROM ping_record
                WHERE ts >= ?
                GROUP BY node_id, task_id, b
            """, (step, since))

            b_dict = defaultdict(dict)
            for r in cur.fetchall():
                b_dict[(r["node_id"], r["task_id"])][r["b"]] = r

            curr_b = now_ts // step
            w_history_map = {}
            for a in assigned:
                key = (a["node_id"], a["task_id"])
                node_b_map = b_dict.get(key, {})
                h_list = []
                for i in range(slots):
                    b_idx = curr_b - (slots - 1 - i)
                    slot_ts = b_idx * step
                    r = node_b_map.get(b_idx)
                    if r:
                        lat = round(r["avg_lat"]) if r["avg_lat"] is not None else -1
                        h_list.append({
                            "ts": slot_ts,
                            "latency": lat,
                            "lost": r["lost"],
                            "total": r["tot"]
                        })
                    else:
                        h_list.append(None)
                w_history_map[key] = h_list
            bars_by_window[w_key] = w_history_map

        conn.close()

        history_map = defaultdict(list)
        for r in history_rows:
            history_map[(r["node_id"], r["task_id"])].append({
                "latency": r["latency"],
                "ts": r["ts"]
            })

        stats_map = {}
        for r in stats_rows:
            stats_map[(r["node_id"], r["task_id"])] = r

        def _build_win(tot, lost, avg_val, min_val, max_val, bars_list):
            tot = tot or 0
            lost = lost or 0
            return {
                "total": tot,
                "lost": lost,
                "avg": round(avg_val) if avg_val is not None else None,
                "min": round(min_val) if min_val is not None else None,
                "max": round(max_val) if max_val is not None else None,
                "loss_rate": round((lost / tot) * 100, 1) if tot > 0 else 0.0,
                "bars": bars_list or []
            }

        result = defaultdict(list)
        for a in assigned:
            nid = str(a["node_id"])
            tid = a["task_id"]
            key = (a["node_id"], tid)
            hist = history_map.get(key, [])
            latest_lat = hist[-1]["latency"] if hist else None
            latest_ts = hist[-1]["ts"] if hist else None

            bars_1h = bars_by_window.get("1h", {}).get(key, [])
            bars_6h = bars_by_window.get("6h", {}).get(key, [])
            bars_24h = bars_by_window.get("24h", {}).get(key, [])

            st = stats_map.get(key)
            if st:
                w1 = _build_win(st["total_1h"], st["lost_1h"], st["avg_1h"], st["min_1h"], st["max_1h"], bars_1h)
                w6 = _build_win(st["total_6h"], st["lost_6h"], st["avg_6h"], st["min_6h"], st["max_6h"], bars_6h)
                w24 = _build_win(st["total_24h"], st["lost_24h"], st["avg_24h"], st["min_24h"], st["max_24h"], bars_24h)
            else:
                valid_lats = [h["latency"] for h in hist if h["latency"] is not None and h["latency"] >= 0]
                avg_lat = round(sum(valid_lats) / len(valid_lats)) if valid_lats else None
                min_lat = min(valid_lats) if valid_lats else None
                max_lat = max(valid_lats) if valid_lats else None
                tot = len(hist)
                lost = sum(1 for h in hist if h.get("latency") is None or h["latency"] < 0)
                fallback_w = _build_win(tot, lost, avg_lat, min_lat, max_lat, hist)
                w1, w6, w24 = fallback_w, fallback_w, fallback_w

            windows = {
                "1h": w1,
                "6h": w6,
                "24h": w24
            }

            result[nid].append({
                "task_id": tid,
                "name": a["name"],
                "latency": latest_lat,
                "ts": latest_ts,
                "history": hist,
                "avg": w1["avg"],
                "min": w1["min"],
                "max": w1["max"],
                "loss_rate": w1["loss_rate"],
                "total_samples": w1["total"],
                "lost_samples": w1["lost"],
                "windows": windows
            })

        return dict(result)
    except Exception as e:
        print(f"[Error] get_node_latest_latencies: {e}")
        return {}


# =============================================================================
# 客户端分流规则、策略组与 Clash/Singbox 订阅生成引擎 (Subscription Engine - Part 2)
# 已解耦至 modules/subscription_engine.py
# =============================================================================
from modules.subscription_engine import (
    DEFAULT_CLASH_SMART_RULES,
    DEFAULT_CLASH_MINIMAL_RULES,
    DEFAULT_CLASH_GLOBAL_RULES,
    DEFAULT_SINGBOX_SMART_RULES,
    DEFAULT_SINGBOX_MINIMAL_RULES,
    DEFAULT_SINGBOX_GLOBAL_RULES,
    get_rule_presets,
    get_active_clash_rules,
    get_active_singbox_rules,
    REGION_MAP,
    KEYWORD_RULES,
    detect_node_region,
    generate_clash_yaml,
    generate_singbox_client_config,
)

# =============================================================================
# 节点入站规则构建与 Xray/Singbox/Realm 平滑重载引擎 (Node Engine - Part 2)
# 已解耦至 modules/node_engine.py
# =============================================================================
from modules.node_engine import (
    build_inbounds_for_nodes,
    build_singbox_inbounds_for_nodes,
    apply_singbox_config,
    apply_realm_config,
    apply_all_configs,
    apply_xray_config,
    install_local_xray,
    uninstall_local_xray,
    install_local_singbox,
    uninstall_local_singbox,
    install_local_realm,
    uninstall_local_realm,
)

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

        # License status API (开源社区版全功能开放，消除任何商业限制)
        if path == "/api/proxy/license/status":
            conn = get_db()
            server_count = conn.execute("SELECT COUNT(*) FROM node").fetchone()[0]
            node_count = conn.execute("SELECT COUNT(*) FROM proxy_node").fetchone()[0]
            user_count = conn.execute("SELECT COUNT(*) FROM proxy_user WHERE is_admin = 0").fetchone()[0]
            conn.close()
            self.send_json({
                "ok": True,
                "active": True,
                "type": "open_source",
                "plan_name": "开源社区版",
                "unlimited": True,
                "max_servers": -1,
                "max_nodes": 999999,
                "max_users": 999999,
                "limits": {
                    "max_servers": -1,
                    "max_nodes": 999999,
                    "max_users": 999999
                },
                "usage": {
                    "server_count": server_count,
                    "node_count": node_count,
                    "user_count": user_count
                }
            })
            return

        # 1. Client subscription endpoint (Authenticated via token)
        if path in ("/api/proxy/sub", "/sub"):
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

            # VIP 等级隔离：非管理员用户只能订阅其对应 VIP 等级的节点
            if user.get("is_admin") != 1:
                u_vip = str(user.get("vip_level") or "vip1").strip().lower()
                filtered = []
                for n in nodes:
                    raw_vips = str(n.get("vip_levels") or "").strip().lower()
                    if not raw_vips or raw_vips == "all":
                        filtered.append(n)
                    else:
                        vips = [v.strip() for v in raw_vips.split(",") if v.strip()]
                        if u_vip in vips:
                            filtered.append(n)
                nodes = filtered

            hub_ip = get_server_public_ip()
            for n in nodes:
                sid = n.get("server_id")
                cur_host = str(n.get("server_host", "")).strip()
                if sid in node_ip_map and not is_private_ip(node_ip_map[sid]) and node_ip_map[sid] not in ('127.0.0.1', 'localhost'):
                    n["server_host"] = node_ip_map[sid]
                elif is_private_ip(cur_host) or cur_host in ('127.0.0.1', 'localhost', ''):
                    if hub_ip and not is_private_ip(hub_ip):
                        n["server_host"] = hub_ip

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

            # Fetch tier speed limits
            cur_t = conn.execute("SELECT tier_key, speed_limit_mbps FROM proxy_tier")
            tier_speed_map = {r[0]: int(r[1] or 0) for r in cur_t.fetchall()}

            # Fetch active users speed limits
            cur_u = conn.execute("SELECT id, vip_level, bandwidth_limit_mbps FROM proxy_user WHERE enabled = 1")
            users_rows = cur_u.fetchall()
            conn.close()

            user_speed_limits = {}
            for r in users_rows:
                uid = int(r["id"])
                custom_mbps = int(r["bandwidth_limit_mbps"] or 0)
                vip = r["vip_level"] or "vip1"
                tier_mbps = tier_speed_map.get(vip, 0)
                eff_mbps = custom_mbps if custom_mbps > 0 else tier_mbps
                if eff_mbps > 0:
                    user_speed_limits[str(uid)] = eff_mbps

            node_speed_limits = {}
            for n in server_nodes:
                nid = int(n["id"])
                port = int(n.get("port") or 0)
                mbps = int(n.get("bandwidth_limit_mbps") or 0)
                if mbps > 0 and port > 0:
                    node_speed_limits[str(nid)] = { "port": port, "mbps": mbps }

            xray_nodes = [n for n in server_nodes if n["protocol"] not in ("hysteria2", "tuic", "anytls") and not n.get("is_relay")]
            singbox_nodes = [n for n in server_nodes if n["protocol"] in ("hysteria2", "tuic", "anytls") and not n.get("is_relay")]
            relay_nodes = [n for n in server_nodes if n.get("is_relay")]

            inbounds = build_inbounds_for_nodes(xray_nodes)
            singbox_inbounds = build_singbox_inbounds_for_nodes(singbox_nodes)

            realm_endpoints = []
            for n in relay_nodes:
                l_port = int(n.get("port") or 0)
                r_host = (n.get("remote_host") or "").strip()
                r_port = int(n.get("remote_port") or 0)
                if l_port > 0 and r_host and r_port > 0:
                    realm_endpoints.append({
                        "listen": f"0.0.0.0:{l_port}",
                        "remote": f"{r_host}:{r_port}"
                    })

            self.send_json({
                "ok": True,
                "node_id": node_id,
                "server_name": node_row["name"],
                "inbounds": inbounds,
                "xray_inbounds": inbounds,
                "singbox_inbounds": singbox_inbounds,
                "realm_endpoints": realm_endpoints,
                "user_speed_limits": user_speed_limits,
                "node_speed_limits": node_speed_limits
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
            uid = user.get("id")
            last_active = _user_last_seen.get(uid) or user.get("last_active_at") or 0
            is_online = ((last_active > 0 and (now - last_active) < 180) or (online_devs > 0)) and (user.get("enabled", 1) == 1)
            
            status_text = "disabled" if user.get("enabled", 1) == 0 else ("expired" if is_expired else ("over_quota" if is_over else ("over_device_limit" if is_dev_over else "active")))
            
            sub_token = user.get("sub_token") or get_sub_token()
            base_url = get_request_base_url(self.headers)
            user_theme = user.get("theme_style") or (get_setting("admin_theme_style", "default") if user.get("is_admin") else "default")
            
            # 速率限制指标计算 (独享限速优先于套餐限速)
            custom_limit = int(user.get("bandwidth_limit_mbps") or 0)
            u_vip = user.get("vip_level") or "vip1"
            tier_limit = 0
            try:
                conn_t = get_db()
                row_t = conn_t.execute("SELECT speed_limit_mbps FROM proxy_tier WHERE tier_key = ? OR tier_id = ?", (u_vip, u_vip)).fetchone()
                conn_t.close()
                if row_t:
                    tier_limit = int(row_t[0] or 0)
            except Exception:
                pass
            eff_limit = custom_limit if custom_limit > 0 else tier_limit

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
                    "last_active_at": last_active,
                    "is_online": bool(is_online),
                    "last_active_desc": format_time_ago(last_active, now),
                    "upload_bytes": user.get("upload_bytes", 0),
                    "download_bytes": user.get("download_bytes", 0),
                    "total_used_bytes": used,
                    "remaining_bytes": remaining,
                    "expires_at": user.get("expires_at", 0),
                    "enabled": user.get("enabled", 1),
                    "status": status_text,
                    "created_at": user.get("created_at", 0),
                    "theme_style": user_theme or "default",
                    "vip_level": user.get("vip_level", "vip1"),
                    "bandwidth_limit_mbps": custom_limit,
                    "tier_speed_limit_mbps": tier_limit,
                    "effective_speed_limit_mbps": eff_limit,
                    "balance": round(float(user.get("balance") or 0.0), 2)
                }
            })
            return

        if path == "/api/proxy/user/nodes":
            user = get_current_user(self.headers)
            if not user:
                self.send_json({"ok": False, "error": "未登录"}, 401)
                return
            conn = get_db()
            cur = conn.execute("SELECT id, server_id, name, protocol, server_name, server_host, port, enabled, bandwidth_limit_mbps, vip_levels FROM proxy_node WHERE enabled = 1 ORDER BY id DESC")
            nodes = [dict(r) for r in cur.fetchall()]
            cur_nodes = conn.execute("SELECT id, ip, ipv4, country FROM node")
            server_rows = cur_nodes.fetchall()
            node_ip_map = {r["id"]: resolve_server_host(dict(r)) for r in server_rows}
            server_country_map = {r["id"]: (r["country"] or "") for r in server_rows}
            conn.close()

            # VIP 等级隔离：非管理员用户只能看到对应 VIP 等级的节点
            if user.get("is_admin") != 1:
                u_vip = str(user.get("vip_level") or "vip1").strip().lower()
                filtered = []
                for n in nodes:
                    raw_vips = str(n.get("vip_levels") or "").strip().lower()
                    if not raw_vips or raw_vips == "all":
                        filtered.append(n)
                    else:
                        vips = [v.strip() for v in raw_vips.split(",") if v.strip()]
                        if u_vip in vips:
                            filtered.append(n)
                nodes = filtered

            for n in nodes:
                sid = n.get("server_id")
                if sid in node_ip_map and is_private_ip(n.get("server_host")):
                    n["server_host"] = node_ip_map[sid]
                n["flag"] = resolve_node_flag(n, server_country_map)
                n["display_name"] = format_node_display_name(n, server_country_map)
            self.send_json({"ok": True, "nodes": nodes, "user_vip_level": user.get("vip_level", "vip1")})
            return

        # VIP 套餐列表接口 (公开/用户端与管理端通用)
        if path == "/api/proxy/tiers":
            conn = get_db()
            cur = conn.execute("SELECT id, tier_key, name, description, speed_limit_mbps, device_limit, sort_order, created_at, tier_id, price_monthly, price_quarterly, price_yearly, traffic_gb FROM proxy_tier ORDER BY sort_order ASC, id ASC")
            tiers = []
            for r in cur.fetchall():
                d = dict(r)
                if not d.get("tier_id"):
                    d["tier_id"] = d.get("tier_key", "")
                d["price_monthly"] = round(float(d.get("price_monthly") or 0.0), 2)
                d["price_quarterly"] = round(float(d.get("price_quarterly") or 0.0), 2)
                d["price_yearly"] = round(float(d.get("price_yearly") or 0.0), 2)
                d["traffic_gb"] = round(float(d.get("traffic_gb") or 0.0), 2)
                d["bandwidth_limit_mbps"] = int(d.get("speed_limit_mbps") or 0)
                tiers.append(d)
            conn.close()
            self.send_json({"ok": True, "tiers": tiers})
            return

        # =====================================================================
        # 换机迁移公开读取接口 (基于凭据 Token 或状态读取，免 Cookie 鉴权)
        # =====================================================================
        if path == "/api/proxy/migration/clone.sh":
            clean_expired_migration_tokens()
            tok = qs.get("token", [""])[0]
            with _MIGRATION_LOCK:
                info = _MIGRATION_TOKENS.get(tok)
            if not info or info.get("type") != "clone":
                self.send_text("#!/bin/bash\necho '[-] 错误: 克隆凭据无效或已过期，请重新在源主控后台生成！' >&2\nexit 1\n", 403, "text/x-shellscript; charset=utf-8")
                return
            host = self.headers.get("Host", "").strip() or "127.0.0.1:28080"
            source_domain = host.split(":")[0] if ":" in host else host
            target_domain = (info.get("target_domain") or "").strip() or source_domain
            script_text = generate_clone_script(host, source_domain, tok, target_domain=target_domain)
            self.send_text(script_text, 200, "text/x-shellscript; charset=utf-8")
            return

        if path == "/api/proxy/migration/clone-db":
            clean_expired_migration_tokens()
            tok = qs.get("token", [""])[0]
            with _MIGRATION_LOCK:
                info = _MIGRATION_TOKENS.get(tok)
            if not info or info.get("type") != "clone":
                self.send_json({"ok": False, "error": "克隆凭据无效或已过期"}, 403)
                return
            try:
                gz_data, _, _ = generate_backup_gz()
                self.send_response(200)
                self.send_header("Content-Type", "application/gzip")
                self.send_header("Content-Length", str(len(gz_data)))
                self.end_headers()
                self.wfile.write(gz_data)
                return
            except Exception as e:
                self.send_json({"ok": False, "error": f"导出克隆快照失败: {e}"}, 500)
                return

        if path == "/api/proxy/migration/status":
            conn = get_db()
            node_cnt = 0
            user_cnt = 0
            rule_cnt = 0
            try:
                node_cnt = conn.execute("SELECT COUNT(*) FROM node").fetchone()[0]
                user_cnt = conn.execute("SELECT COUNT(*) FROM proxy_user").fetchone()[0]
                rule_cnt = conn.execute("SELECT COUNT(*) FROM proxy_node").fetchone()[0]
            except Exception:
                pass
            conn.close()

            just_completed = get_setting("migration_just_completed", "0") == "1"
            source_domain = get_setting("migration_source_domain", "")
            target_domain = get_setting("migration_target_domain", "")
            source_ip = get_setting("migration_source_ip", "")
            completed_at = int(get_setting("migration_completed_at", "0") or 0)
            cur_ip = get_server_public_ip()

            self.send_json({
                "ok": True,
                "just_completed": just_completed,
                "source_domain": source_domain,
                "target_domain": target_domain or source_domain,
                "source_ip": source_ip,
                "completed_at": completed_at,
                "current_ip": cur_ip,
                "node_count": node_cnt,
                "user_count": user_cnt,
                "rule_count": rule_cnt
            })
            return

        # 支付网关配置接口 (管理端)
        if path == "/api/proxy/settings/payment":
            if not check_auth(self.headers):
                self.send_json({"error": "Unauthorized"}, 401)
                return
            pay_on = get_setting("pay_enabled", "1") == "1"
            usdt = get_setting("pay_usdt_trc20", "")
            ali = get_setting("pay_alipay_qr", "")
            wx = get_setting("pay_wechat_qr", "")
            tg = get_setting("pay_tg_contact", "")
            notes = get_setting("pay_notes", "转账付款后请备注您的登录用户名或将交易单号发送给在线客服完成开通。")
            self.send_json({
                "ok": True,
                "enabled": pay_on,
                "pay_enabled": pay_on,
                "usdt_trc20": usdt,
                "pay_usdt_trc20": usdt,
                "alipay_qr": ali,
                "pay_alipay_qr": ali,
                "wechat_qr": wx,
                "pay_wechat_qr": wx,
                "tg_support": tg,
                "pay_tg_contact": tg,
                "pay_notes": notes,
            })
            return

        # 支付网关配置 (用户端公开)
        if path == "/api/proxy/user/payment-config":
            pay_on = get_setting("pay_enabled", "1") == "1"
            usdt = get_setting("pay_usdt_trc20", "")
            ali = get_setting("pay_alipay_qr", "")
            wx = get_setting("pay_wechat_qr", "")
            tg = get_setting("pay_tg_contact", "")
            notes = get_setting("pay_notes", "转账付款后请备注您的登录用户名或将交易单号发送给在线客服完成开通。")
            self.send_json({
                "ok": True,
                "enabled": pay_on,
                "pay_enabled": pay_on,
                "usdt_trc20": usdt,
                "pay_usdt_trc20": usdt,
                "alipay_qr": ali,
                "pay_alipay_qr": ali,
                "wechat_qr": wx,
                "pay_wechat_qr": wx,
                "tg_support": tg,
                "pay_tg_contact": tg,
                "pay_notes": notes,
            })
            return

        # 订单记录列表接口 (管理端)
        if path == "/api/proxy/orders":
            if not check_auth(self.headers):
                self.send_json({"error": "Unauthorized"}, 401)
                return
            conn = get_db()
            cur = conn.execute("SELECT * FROM proxy_order ORDER BY id DESC LIMIT 500")
            orders = [dict(r) for r in cur.fetchall()]
            conn.close()
            self.send_json({"ok": True, "orders": orders})
            return

        # 用户个人订单记录列表 (用户端)
        if path == "/api/proxy/user/orders":
            user = get_current_user(self.headers)
            if not user:
                self.send_json({"ok": False, "error": "未登录"}, 401)
                return
            conn = get_db()
            cur = conn.execute("SELECT * FROM proxy_order WHERE user_id = ? ORDER BY id DESC LIMIT 50", (user["id"],))
            orders = [dict(r) for r in cur.fetchall()]
            conn.close()
            self.send_json({"ok": True, "orders": orders})
            return

        # 系统公告接口 (管理端)
        if path == "/api/proxy/announcements":
            if not check_auth(self.headers):
                self.send_json({"error": "Unauthorized"}, 401)
                return
            conn = get_db()
            cur = conn.execute("SELECT id, title, summary, content, is_pinned, enabled, created_at, updated_at FROM proxy_announcement ORDER BY is_pinned DESC, id DESC")
            announcements = [dict(r) for r in cur.fetchall()]
            conn.close()
            self.send_json({"ok": True, "announcements": announcements})
            return

        # 系统公告列表 (用户端/公开)
        if path == "/api/proxy/user/announcements":
            conn = get_db()
            cur = conn.execute("SELECT id, title, summary, is_pinned, created_at, updated_at FROM proxy_announcement WHERE enabled = 1 ORDER BY is_pinned DESC, id DESC")
            announcements = [dict(r) for r in cur.fetchall()]
            conn.close()
            self.send_json({"ok": True, "announcements": announcements})
            return

        # 系统公告详情 (用户端/公开)
        m_user_anno = re.match(r"^/api/proxy/user/announcements/(\d+)$", path)
        if m_user_anno:
            anno_id = int(m_user_anno.group(1))
            conn = get_db()
            cur = conn.execute("SELECT id, title, summary, content, is_pinned, created_at, updated_at FROM proxy_announcement WHERE id = ? AND enabled = 1", (anno_id,))
            row = cur.fetchone()
            conn.close()
            if not row:
                self.send_json({"ok": False, "message": "公告不存在或已下架"}, 404)
                return
            self.send_json({"ok": True, "announcement": dict(row)})
            return

        # 全局登录弹窗通知 (管理端配置)
        if path == "/api/proxy/settings/notification":
            if not check_auth(self.headers):
                self.send_json({"error": "Unauthorized"}, 401)
                return
            self.send_json({
                "ok": True,
                "enabled": get_setting("global_notification_enabled", "0") == "1",
                "title": get_setting("global_notification_title", "系统重要通知"),
                "content": get_setting("global_notification_content", ""),
                "updated_at": int(get_setting("global_notification_updated_at", "0"))
            })
            return

        # 全局登录弹窗通知 (用户端读取)
        if path == "/api/proxy/user/notification":
            enabled = get_setting("global_notification_enabled", "0") == "1"
            self.send_json({
                "ok": True,
                "enabled": enabled,
                "title": get_setting("global_notification_title", "系统重要通知") if enabled else "",
                "content": get_setting("global_notification_content", "") if enabled else "",
                "updated_at": int(get_setting("global_notification_updated_at", "0")) if enabled else 0
            })
            return

        # 客户端下载专区 (管理端)
        if path == "/api/proxy/apps":
            if not check_auth(self.headers):
                self.send_json({"error": "Unauthorized"}, 401)
                return
            conn = get_db()
            cur = conn.execute("SELECT id, name, platform, version, description, file_path, file_name, file_size, external_url, sort_order, enabled, created_at FROM proxy_app_download ORDER BY sort_order ASC, id ASC")
            apps = [dict(r) for r in cur.fetchall()]
            conn.close()
            for a in apps:
                a["has_local_file"] = 1 if (a.get("file_path") and os.path.exists(a["file_path"])) else 0
            self.send_json({"ok": True, "apps": apps})
            return

        # 客户端下载专区 (用户端)
        if path == "/api/proxy/user/apps":
            conn = get_db()
            cur = conn.execute("SELECT id, name, platform, version, description, file_name, file_size, external_url, sort_order, created_at, file_path FROM proxy_app_download WHERE enabled = 1 ORDER BY sort_order ASC, id ASC")
            apps = [dict(r) for r in cur.fetchall()]
            conn.close()
            for a in apps:
                a["has_local_file"] = 1 if (a.get("file_path") and os.path.exists(a["file_path"])) else 0
                a.pop("file_path", None)
            self.send_json({"ok": True, "apps": apps})
            return

        # 客户端软件包直接流式下载
        m_app_dl = re.match(r"^/api/proxy/apps/download/(\d+)$", path)
        if m_app_dl:
            app_id = int(m_app_dl.group(1))
            conn = get_db()
            cur = conn.execute("SELECT file_path, file_name FROM proxy_app_download WHERE id = ? AND enabled = 1", (app_id,))
            row = cur.fetchone()
            conn.close()
            if not row or not row[0] or not os.path.exists(row[0]):
                self.send_response(404)
                self.send_header("Content-Type", "text/plain; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"File not found on server")
                return
            f_path = row[0]
            f_name = row[1] or os.path.basename(f_path)
            f_size = os.path.getsize(f_path)
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Disposition", f"attachment; filename*=UTF-8''{quote(f_name)}")
            self.send_header("Content-Length", str(f_size))
            self.end_headers()
            with open(f_path, "rb") as f_in:
                shutil.copyfileobj(f_in, self.wfile)
            return

        # 服务器到期提醒设置 (管理端)
        if path == "/api/proxy/settings/server-expiry":
            if not check_auth(self.headers):
                self.send_json({"error": "Unauthorized"}, 401)
                return
            self.send_json({
                "ok": True,
                "enabled": get_setting("server_expire_remind_enabled", "1") == "1",
                "days": int(get_setting("server_expire_remind_days", "7")),
                "last_notify_date": get_setting("server_expire_last_notify_date", "")
            })
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

        if path == "/api/proxy/dashboard/check-interval":
            if not check_auth(self.headers):
                self.send_json({"ok": False, "error": "Unauthorized"}, 401)
                return
            try:
                interval_min = int(get_setting("node_check_interval_minutes", "10") or 10)
            except Exception:
                interval_min = 10
            self.send_json({"ok": True, "interval_minutes": interval_min})
            return

        if path == "/api/proxy/dashboard/overview":
            if not check_auth(self.headers):
                self.send_json({"ok": False, "error": "Unauthorized"}, 401)
                return
            conn = get_db()
            conn.row_factory = sqlite3.Row
            # 1. Server counts
            cur_srv = conn.execute("SELECT id, name, ip, last_seen FROM node")
            servers = [dict(r) for r in cur_srv.fetchall()]
            now = int(time.time())
            online_servers = sum(1 for s in servers if s.get("last_seen", 0) > (now - 75))
            
            # 2. Nodes
            cur_node = conn.execute("""
                SELECT id, server_id, server_name, name, protocol, port, enabled,
                       upload_bytes, download_bytes, last_check_status, last_check_latency,
                       last_check_time, last_check_error
                FROM proxy_node
            """)
            nodes = [dict(r) for r in cur_node.fetchall()]
            active_nodes = [n for n in nodes if n.get("enabled", 1) == 1]
            healthy_nodes = sum(1 for n in active_nodes if n.get("last_check_status") == "ok")
            unhealthy_nodes = sum(1 for n in active_nodes if n.get("last_check_status") == "fail")
            
            # Calculate node ranking
            node_ranking = []
            total_node_traffic = 0
            for n in active_nodes:
                up = n.get("upload_bytes") or 0
                down = n.get("download_bytes") or 0
                tot = up + down
                total_node_traffic += tot
                node_ranking.append({
                    "id": n["id"],
                    "name": n["name"],
                    "server_name": n.get("server_name") or "本机",
                    "protocol": n["protocol"],
                    "port": n["port"],
                    "upload_bytes": up,
                    "download_bytes": down,
                    "total_bytes": tot,
                    "last_check_status": n.get("last_check_status") or "",
                    "last_check_latency": n.get("last_check_latency") or 0,
                    "last_check_time": n.get("last_check_time") or 0,
                    "last_check_error": n.get("last_check_error") or ""
                })
            node_ranking.sort(key=lambda x: x["total_bytes"], reverse=True)
            for nr in node_ranking:
                nr["percentage"] = round((nr["total_bytes"] / total_node_traffic * 100), 1) if total_node_traffic > 0 else 0.0

            # Calculate server ranking (服务器消耗排行)
            server_map = {}
            for s in servers:
                sid = s["id"]
                sname = s.get("name") or f"服务器-{sid}"
                sip = s.get("ip") or s.get("ipv4") or ""
                server_map[sid] = {
                    "id": sid,
                    "name": sname,
                    "ip": sip,
                    "upload_bytes": 0,
                    "download_bytes": 0,
                    "total_bytes": 0,
                    "node_count": 0,
                    "is_online": (s.get("last_seen", 0) > (now - 75))
                }

            has_local_nodes = any((n.get("server_id") or 0) == 0 for n in active_nodes)
            if has_local_nodes or (0 not in server_map and not servers):
                server_map[0] = {
                    "id": 0,
                    "name": "本机",
                    "ip": get_server_public_ip() or "127.0.0.1",
                    "upload_bytes": 0,
                    "download_bytes": 0,
                    "total_bytes": 0,
                    "node_count": 0,
                    "is_online": True
                }

            for n in active_nodes:
                sid = n.get("server_id") or 0
                if sid not in server_map:
                    server_map[sid] = {
                        "id": sid,
                        "name": n.get("server_name") or f"服务器-{sid}",
                        "ip": n.get("server_host") or "",
                        "upload_bytes": 0,
                        "download_bytes": 0,
                        "total_bytes": 0,
                        "node_count": 0,
                        "is_online": True
                    }
                up = n.get("upload_bytes") or 0
                down = n.get("download_bytes") or 0
                server_map[sid]["upload_bytes"] += up
                server_map[sid]["download_bytes"] += down
                server_map[sid]["total_bytes"] += (up + down)
                server_map[sid]["node_count"] += 1

            try:
                cur_tr = conn.execute("SELECT node_id, total_rx, total_tx FROM traffic")
                for tr in cur_tr.fetchall():
                    nid = tr["node_id"]
                    if nid in server_map and server_map[nid]["total_bytes"] == 0:
                        rx = tr["total_rx"] or 0
                        tx = tr["total_tx"] or 0
                        if (rx + tx) > 0:
                            server_map[nid]["download_bytes"] = rx
                            server_map[nid]["upload_bytes"] = tx
                            server_map[nid]["total_bytes"] = rx + tx
            except Exception:
                pass

            total_srv_traffic = sum(s["total_bytes"] for s in server_map.values())
            server_ranking = list(server_map.values())
            server_ranking.sort(key=lambda x: x["total_bytes"], reverse=True)
            for sr in server_ranking:
                sr["percentage"] = round((sr["total_bytes"] / total_srv_traffic * 100), 1) if total_srv_traffic > 0 else 0.0

            # 3. Protocol distribution
            proto_map = {}
            for n in active_nodes:
                p = n.get("protocol") or "other"
                proto_map[p] = proto_map.get(p, 0) + 1
            proto_dist = []
            for p, cnt in proto_map.items():
                proto_dist.append({
                    "protocol": p,
                    "count": cnt,
                    "percentage": round(cnt / len(active_nodes) * 100, 1) if active_nodes else 0.0
                })
            proto_dist.sort(key=lambda x: x["count"], reverse=True)

            # 4. User ranking
            cur_users = conn.execute("""
                SELECT id, username, upload_bytes, download_bytes, traffic_limit_bytes, expires_at, enabled
                FROM proxy_user
            """)
            users = [dict(r) for r in cur_users.fetchall()]
            user_ranking = []
            total_user_traffic = 0
            for u in users:
                up = u.get("upload_bytes") or 0
                down = u.get("download_bytes") or 0
                tot = up + down
                total_user_traffic += tot
                limit = u.get("traffic_limit_bytes") or 0
                pct = round(tot / limit * 100, 1) if limit > 0 else 0.0
                user_ranking.append({
                    "id": u["id"],
                    "username": u["username"],
                    "upload_bytes": up,
                    "download_bytes": down,
                    "total_bytes": tot,
                    "traffic_limit_bytes": limit,
                    "percentage": pct,
                    "expires_at": u.get("expires_at") or 0,
                    "enabled": u.get("enabled", 1)
                })
            user_ranking.sort(key=lambda x: x["total_bytes"], reverse=True)

            # 5. Average latency
            tested = [n for n in active_nodes if n.get("last_check_status") == "ok" and (n.get("last_check_latency") or 0) > 0]
            avg_lat = round(sum(n["last_check_latency"] for n in tested) / len(tested), 1) if tested else 0
            best_node = min(tested, key=lambda x: x["last_check_latency"]) if tested else None

            # 6. Hourly traffic for last 24h
            cur_hourly = conn.execute("""
                SELECT time_bucket, upload_bytes, download_bytes
                FROM proxy_traffic_hourly
                WHERE time_bucket >= ?
                ORDER BY time_bucket ASC
            """, (now - 86400,))
            hourly_map = {r["time_bucket"]: (r["upload_bytes"], r["download_bytes"]) for r in cur_hourly.fetchall()}
            
            hourly_traffic = []
            cur_slot = (now // 3600) * 3600
            for i in range(23, -1, -1):
                slot_time = cur_slot - i * 3600
                up, down = hourly_map.get(slot_time, (0, 0))
                time_label = time.strftime("%H:00", time.localtime(slot_time))
                hourly_traffic.append({
                    "timestamp": slot_time,
                    "time": time_label,
                    "upload": up,
                    "download": down,
                    "total": up + down
                })

            tg_token = get_setting("notify_telegram_token", "").strip()
            tg_chat = (get_setting("notify_telegram_chat", "") or get_setting("backup_tg_chat", "")).strip()
            tg_ready = bool(tg_token and tg_chat)

            conn.close()

            self.send_json({
                "ok": True,
                "summary": {
                    "total_servers": len(servers),
                    "online_servers": online_servers,
                    "total_nodes": len(active_nodes),
                    "healthy_nodes": healthy_nodes,
                    "unhealthy_nodes": unhealthy_nodes,
                    "total_users": len(users),
                    "active_users": sum(1 for u in users if u.get("enabled", 1) == 1),
                    "online_users": sum(1 for u in users if (_user_last_seen.get(u["id"], 0) > (now - 180) or get_user_online_device_count(u["id"]) > 0) and u.get("enabled", 1) == 1),
                    "total_upload_bytes": sum(n.get("upload_bytes") or 0 for n in active_nodes),
                    "total_download_bytes": sum(n.get("download_bytes") or 0 for n in active_nodes),
                    "total_traffic_bytes": total_node_traffic,
                    "avg_latency_ms": avg_lat,
                    "best_node": best_node["name"] if best_node else None,
                    "best_latency_ms": best_node["last_check_latency"] if best_node else 0,
                    "tg_bot_active": tg_ready,
                    "inspection_interval_minutes": int(get_setting("node_check_interval_minutes", "10") or 10)
                },
                "server_ranking": server_ranking,
                "node_ranking": node_ranking,
                "user_ranking": user_ranking[:8],
                "protocol_distribution": proto_dist,
                "hourly_traffic": hourly_traffic
            })
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

        if path in ("/api/version", "/api/proxy/version", "/api/proxy/system/update-check", "/api/proxy/system/update-check/", "/api/proxy/update-check", "/api/system/update-check"):
            force = qs.get("force", ["0"])[0] in ("1", "true")
            res = check_system_update(force=force)
            res["version"] = res.get("current_version", CURRENT_VERSION)
            self.send_json(res)
            return

        if path in ("/api/proxy/system/upgrade", "/api/proxy/system/upgrade/", "/api/proxy/upgrade", "/api/proxy/upgrade/", "/api/system/upgrade", "/api/system/upgrade/"):
            if qs.get("action", [""])[0] in ("1", "run", "upgrade"):
                if not check_auth(self.headers):
                    self.send_json({"ok": False, "error": "Unauthorized: 请先登录管理员账号"}, 401)
                    return
                if is_legacy_migration_needed():
                    self.send_json({
                        "ok": False,
                        "need_migration": True,
                        "migration_cmd": "hhub migrate",
                        "error": "系统检测到当前面板仍运行在旧版目录 /opt/monitor。为保护您的数据库与配置安全，并平滑切换至全新独立架构 /opt/proxyprobe，请在 SSH 终端执行一次【hhub migrate】完成一键迁移！"
                    }, 400)
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
            is_adm = check_auth(self.headers)
            self.send_json({
                "ok": True,
                "is_admin": is_adm,
                "settings": {
                    "public_show_price": get_setting("public_show_price", "0") == "1",
                    "public_show_expiry": get_setting("public_show_expiry", "0") == "1",
                    "public_show_traffic_limit": get_setting("public_show_traffic_limit", "0") == "1",
                    "total_cost_currency": get_setting("total_cost_currency", "CNY").strip().upper() or "CNY"
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
                "public_show_traffic_limit": get_setting("public_show_traffic_limit", "0") == "1",
                "total_cost_currency": get_setting("total_cost_currency", "CNY").strip().upper() or "CNY"
            })
            return

        if path == "/api/proxy/settings/support":
            tg_enabled = get_setting("support_tg_enabled", "0") == "1"
            tg_url = get_setting("support_tg_url", "")
            self.send_json({
                "ok": True,
                "enabled": tg_enabled,
                "telegram_url": tg_url
            })
            return

        if path == "/api/proxy/settings/smtp":
            if not check_auth(self.headers):
                self.send_json({"error": "Unauthorized"}, 401)
                return
            self.send_json({
                "ok": True,
                "smtp_enabled": get_setting("smtp_enabled", "0") == "1",
                "smtp_host": get_setting("smtp_host", "smtp.gmail.com"),
                "smtp_port": int(get_setting("smtp_port", "465")),
                "smtp_ssl": get_setting("smtp_ssl", "1") == "1",
                "smtp_user": get_setting("smtp_user", ""),
                "smtp_pass": get_setting("smtp_pass", ""),
                "smtp_from_name": get_setting("smtp_from_name", "HHUB"),
                "site_name": get_setting("site_name", "HHUB-加速中心"),
                "register_enabled": get_setting("register_enabled", "1") == "1"
            })
            return

        if path == "/api/proxy/auth/config":
            self.send_json({
                "ok": True,
                "register_enabled": get_setting("register_enabled", "1") == "1",
                "smtp_enabled": get_setting("smtp_enabled", "0") == "1",
                "site_name": get_setting("site_name", "HHUB-加速中心"),
                "support_tg_enabled": get_setting("support_tg_enabled", "0") == "1",
                "support_tg_url": get_setting("support_tg_url", "") if get_setting("support_tg_enabled", "0") == "1" else ""
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

        # =====================================================================
        # 换机迁移与克隆 GET 接口
        # =====================================================================
        if path == "/api/proxy/migration/clone-token":
            if not check_auth(self.headers):
                self.send_json({"error": "Unauthorized"}, 401)
                return
            clean_expired_migration_tokens()
            target_domain = qs.get("target_domain", [""])[0].strip()
            tok = "mig_" + secrets.token_hex(16)
            expires_at = time.time() + 1800
            with _MIGRATION_LOCK:
                _MIGRATION_TOKENS[tok] = {
                    "type": "clone",
                    "target_domain": target_domain,
                    "expires_at": expires_at
                }
            host = self.headers.get("Host", "").strip() or get_setting("site_url", "").replace("https://", "").replace("http://", "").strip() or "127.0.0.1:28080"
            source_domain = host.split(":")[0] if ":" in host else host
            is_https = self.headers.get("X-Forwarded-Proto") == "https" or get_setting("site_url", "").startswith("https://")
            if is_ip_address(source_domain):
                proto = "https" if is_https else "http"
            else:
                proto = "https" if (is_https or (":28090" not in host and ":28080" not in host)) else "http"

            clone_cmd = f"curl -fsSLk '{proto}://{host}/api/proxy/migration/clone.sh?token={tok}' | bash"
            self.send_json({
                "ok": True,
                "token": tok,
                "clone_cmd": clone_cmd,
                "source_domain": source_domain,
                "target_domain": target_domain or source_domain,
                "is_source_ip": is_ip_address(source_domain),
                "expires_in": 1800
            })
            return

        if path == "/api/proxy/users":
            conn = get_db()
            cur = conn.execute("SELECT * FROM proxy_user ORDER BY id ASC")
            users = [dict(r) for r in cur.fetchall()]
            tier_speed_map = {}
            try:
                t_cur = conn.execute("SELECT tier_key, speed_limit_mbps FROM proxy_tier")
                tier_speed_map = {r[0]: int(r[1] or 0) for r in t_cur.fetchall()}
            except Exception:
                pass
            conn.close()
            now = int(time.time())
            ONLINE_WINDOW = 180
            for u in users:
                u.pop("password_hash", None)
                limit = u.get("traffic_limit_bytes", 0)
                used = u.get("upload_bytes", 0) + u.get("download_bytes", 0)
                remaining = max(0, limit - used) if limit > 0 else -1
                is_expired = u.get("expires_at", 0) > 0 and now > u.get("expires_at", 0)
                is_over = limit > 0 and used >= limit
                is_dev_over = is_user_over_device_limit(u)
                uid = u["id"]
                last_active = _user_last_seen.get(uid) or u.get("last_active_at") or 0
                online_devs = get_user_online_device_count(uid)
                is_online = ((last_active > 0 and (now - last_active) < ONLINE_WINDOW) or (online_devs > 0)) and (u.get("enabled", 1) == 1)
                u["device_limit"] = u.get("device_limit", 0)
                u["online_devices"] = online_devs
                u["last_active_at"] = last_active
                u["is_online"] = bool(is_online)
                u["last_active_desc"] = format_time_ago(last_active, now)
                u["total_used_bytes"] = used
                u["remaining_bytes"] = remaining
                u["status"] = "disabled" if u.get("enabled", 1) == 0 else ("expired" if is_expired else ("over_quota" if is_over else ("over_device_limit" if is_dev_over else "active")))
                
                # 速率限制指标计算 (独享限速优先于套餐限速)
                custom_limit = int(u.get("bandwidth_limit_mbps") or 0)
                u_vip = u.get("vip_level") or "vip1"
                tier_limit = tier_speed_map.get(u_vip, 0)
                eff_limit = custom_limit if custom_limit > 0 else tier_limit
                u["bandwidth_limit_mbps"] = custom_limit
                u["tier_speed_limit_mbps"] = tier_limit
                u["effective_speed_limit_mbps"] = eff_limit

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
                try:
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
                except Exception as e:
                    print(f"[Error] Failed processing node {n.get('id')}: {e}")
                    n["flag"] = "🌐"
                    n["display_name"] = n.get("name") or "Node"
                    n["link"] = ""
            conn.close()
            self.send_json({
                "nodes": nodes,
                "sub_token": get_sub_token(),
                "recommended_port": get_free_port()
            })
            return

        elif path == "/api/proxy/servers":
            conn = get_db()
            hub_pub_ip = get_server_public_ip()
            # 自动级联自愈：彻底清除在 node 表中已被删除的服务器残留的节点与旧状态，杜绝重加服务器时的数据冲突
            existing_node_ids = {r[0] for r in conn.execute("SELECT id FROM node").fetchall()}
            with conn:
                orphaned_nodes = conn.execute("SELECT id, server_id FROM proxy_node WHERE server_id != 0").fetchall()
                del_node_ids = [on["id"] for on in orphaned_nodes if on["server_id"] not in existing_node_ids]
                if del_node_ids:
                    conn.execute(f"DELETE FROM proxy_node WHERE id IN ({','.join('?' for _ in del_node_ids)})", del_node_ids)
                    conn.execute(f"DELETE FROM proxy_node_latency WHERE node_id IN ({','.join('?' for _ in del_node_ids)})", del_node_ids)

                orphaned_statuses = conn.execute("SELECT node_id FROM node_proxy_status WHERE node_id != 0").fetchall()
                del_status_ids = [st["node_id"] for st in orphaned_statuses if st["node_id"] not in existing_node_ids]
                if del_status_ids:
                    conn.execute(f"DELETE FROM node_proxy_status WHERE node_id IN ({','.join('?' for _ in del_status_ids)})", del_status_ids)

                # 自动级联自愈：若 node 表或 proxy_node 表中有 127.0.0.1 或空 IP，自动修复为本机公网 IP
                if hub_pub_ip and not is_private_ip(hub_pub_ip):
                    conn.execute("""
                        UPDATE node 
                        SET ip = CASE WHEN (ip IN ('', '127.0.0.1') OR ip LIKE '127.%') THEN ? ELSE ip END,
                            ipv4 = CASE WHEN (ipv4 IN ('', '127.0.0.1') OR ipv4 LIKE '127.%') THEN ? ELSE ipv4 END
                        WHERE (ip IN ('', '127.0.0.1') OR ipv4 IN ('', '127.0.0.1') OR ip LIKE '127.%' OR ipv4 LIKE '127.%')
                    """, (hub_pub_ip, hub_pub_ip))
                    conn.execute("""
                        UPDATE proxy_node
                        SET server_host = ?
                        WHERE server_host IN ('127.0.0.1', 'localhost', '') OR server_host LIKE '127.%'
                    """, (hub_pub_ip,))

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

            local_ipv4 = hub_pub_ip or get_local_ip(socket.AF_INET) or "127.0.0.1"
            local_ipv6 = get_local_ip(socket.AF_INET6)

            servers = []

            for r in remote_nodes:
                raw_ipv4 = (r.get("ipv4") or "").strip()
                pub_ip = (r.get("ip") or r.get("country_ip") or "").strip()
                host = resolve_server_host(r)
                if host in ("127.0.0.1", "localhost", "") or is_private_ip(host):
                    if hub_pub_ip and not is_private_ip(hub_pub_ip):
                        host = hub_pub_ip
                if raw_ipv4 and not is_private_ip(raw_ipv4):
                    r_ipv4 = raw_ipv4
                elif pub_ip and not is_private_ip(pub_ip):
                    r_ipv4 = pub_ip
                else:
                    r_ipv4 = host or hub_pub_ip or raw_ipv4 or pub_ip
                r_ipv6 = (r.get("ipv6") or "").strip()
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
                    x_inst = bool(st.get("xray_installed") or (is_online and st.get("version")))
                    x_run = is_online and bool(st.get("xray_running", st.get("status") == "running"))
                    sb_inst = bool(st.get("singbox_installed") or (is_online and st.get("singbox_version")))
                    sb_run = is_online and bool(st.get("singbox_running"))
                    r_inst = bool(st.get("realm_installed") or (is_online and st.get("realm_version")))
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
                    "proxy_online": True if is_local else bool(now - last_seen < 90),
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
            elif proto == "anytls":
                pwd = gen_random_password(16)
                res.update({
                    "password": pwd,
                    "sni": "www.bing.com"
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
                    "password": pwd,
                    "sni": "bing.com"
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

        # 客户端二进制包上传直接流式写入磁盘，避免解析 JSON 或内存溢出
        if path == "/api/proxy/apps/upload":
            if not check_auth(self.headers):
                self.send_json({"error": "Unauthorized"}, 401)
                return
            app_id = int(self.headers.get("X-App-Id", 0))
            raw_filename = unquote(self.headers.get("X-Filename", "client_package.zip"))
            safe_name = re.sub(r'[^a-zA-Z0-9_\-\.\u4e00-\u9fa5]', '_', raw_filename)
            if not safe_name:
                safe_name = f"app_{app_id}_{int(time.time())}.bin"
            upload_dir = "/opt/monitor/uploads/apps"
            os.makedirs(upload_dir, exist_ok=True)
            target_path = os.path.join(upload_dir, f"{app_id}_{safe_name}")
            
            remaining = length
            with open(target_path, "wb") as f_out:
                chunk_size = 65536
                while remaining > 0:
                    chunk = self.rfile.read(min(remaining, chunk_size))
                    if not chunk:
                        break
                    f_out.write(chunk)
                    remaining -= len(chunk)
            
            file_size = os.path.getsize(target_path)
            conn = get_db()
            with conn:
                conn.execute("UPDATE proxy_app_download SET file_path = ?, file_name = ?, file_size = ? WHERE id = ?", (target_path, safe_name, file_size, app_id))
            conn.close()
            self.send_json({"ok": True, "file_name": safe_name, "file_size": file_size, "message": "客户端安装包上传成功"})
            return

        body_data = self.rfile.read(length).decode("utf-8", errors="replace") if length > 0 else "{}"
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

            # 自动提取并持久化有效公网 IP，更新 node 表并自愈 proxy_node 表中残留的 127.0.0.1
            client_ip = ""
            xff = self.headers.get("X-Forwarded-For")
            if xff:
                client_ip = xff.split(",")[0].strip()
            elif self.headers.get("CF-Connecting-IP"):
                client_ip = self.headers.get("CF-Connecting-IP").strip()
            elif self.client_address:
                client_ip = str(self.client_address[0]).strip()

            reported_ip = str(req.get("ipv4") or req.get("ip") or "").strip()
            valid_ip = ""
            if reported_ip and not is_private_ip(reported_ip):
                valid_ip = reported_ip
            elif client_ip and not is_private_ip(client_ip):
                valid_ip = client_ip
            else:
                hub_ip = get_server_public_ip()
                if hub_ip and not is_private_ip(hub_ip):
                    valid_ip = hub_ip

            if valid_ip and not is_private_ip(valid_ip):
                with conn:
                    conn.execute("""
                        UPDATE node 
                        SET ip = CASE WHEN (ip IN ('', '127.0.0.1') OR ip LIKE '127.%' OR ip LIKE '10.%' OR ip LIKE '192.168.%') THEN ? ELSE ip END,
                            ipv4 = CASE WHEN (ipv4 IN ('', '127.0.0.1') OR ipv4 LIKE '127.%' OR ipv4 LIKE '10.%' OR ipv4 LIKE '192.168.%') THEN ? ELSE ipv4 END
                        WHERE id = ?
                    """, (valid_ip, valid_ip, node_id))
                    conn.execute("""
                        UPDATE proxy_node
                        SET server_host = ?
                        WHERE server_id = ? AND (server_host IN ('127.0.0.1', 'localhost', '') OR server_host LIKE '127.%')
                    """, (valid_ip, node_id))

            status = req.get("status", "unknown")
            version = req.get("version", "")
            ports_json = json.dumps(req.get("ports", []))
            listening_ports_json = json.dumps(req.get("listening_ports", []))
            xray_log = req.get("log", "")
            xray_installed = int(req.get("xray_installed", 1 if version else 0))
            xray_running = int(req.get("xray_running", 1 if status == "running" else 0))
            singbox_version = req.get("singbox_version", "")
            singbox_installed = int(req.get("singbox_installed", 1 if singbox_version else 0))
            singbox_running = int(req.get("singbox_running", 0))
            realm_version = req.get("realm_version", "")
            realm_installed = int(req.get("realm_installed", 1 if realm_version else 0))
            realm_running = int(req.get("realm_running", 0))
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
                            _user_last_seen[uid] = now
                            conn.execute("""
                                UPDATE proxy_user
                                SET upload_bytes = upload_bytes + ?, download_bytes = download_bytes + ?, last_active_at = ?
                                WHERE id = ?
                            """, (up, down, now, uid))
            active_users = req.get("active_users", [])
            if active_users:
                for uid in active_users:
                    if uid:
                        _user_last_seen[uid] = now
                        if uid not in _user_active_ips:
                            _user_active_ips[uid] = {}
                        _user_active_ips[uid][f"remote_{node_id}"] = now
            node_stats = req.get("node_stats", [])
            if node_stats:
                with conn:
                    tb = (int(time.time()) // 3600) * 3600
                    tot_up = 0
                    tot_down = 0
                    for st in node_stats:
                        nid = st.get("node_id")
                        up = int(st.get("upload") or 0)
                        down = int(st.get("download") or 0)
                        if nid and (up > 0 or down > 0):
                            conn.execute("""
                                UPDATE proxy_node
                                SET upload_bytes = upload_bytes + ?, download_bytes = download_bytes + ?
                                WHERE id = ?
                            """, (up, down, nid))
                            conn.execute("""
                                UPDATE proxy_node
                                SET upload_bytes = upload_bytes + ?, download_bytes = download_bytes + ?
                                WHERE target_node_id = ?
                            """, (up, down, nid))
                            tot_up += up
                            tot_down += down
                    if tot_up > 0 or tot_down > 0:
                        conn.execute("""
                            INSERT INTO proxy_traffic_hourly (time_bucket, upload_bytes, download_bytes)
                            VALUES (?, ?, ?)
                            ON CONFLICT(time_bucket) DO UPDATE SET
                                upload_bytes = upload_bytes + excluded.upload_bytes,
                                download_bytes = download_bytes + excluded.download_bytes
                        """, (tb, tot_up, tot_down))
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
                cur = conn.execute("SELECT * FROM proxy_user WHERE username = ? OR email = ?", (username, username))
                user_row = cur.fetchone()
            else:
                cur = conn.execute("SELECT * FROM proxy_user WHERE is_admin = 1 ORDER BY id ASC LIMIT 1")
                user_row = cur.fetchone()

            if not user_row:
                conn.close()
                self.send_json({"ok": False, "message": "用户名或密码错误"}, 401)
                return

            user = dict(user_row)
            pw_ok = verify_password(password, user.get("password_hash", ""))
            if not pw_ok and user.get("is_admin") == 1:
                # 兼容平滑过渡：若当前为管理员且 proxy_user 密码不匹配，自动尝试校验底层 setting 的 admin_password_hash (Argon2)
                adm_argon_h = get_setting("admin_password_hash", "")
                if adm_argon_h:
                    try:
                        from argon2 import PasswordHasher
                        ph = PasswordHasher()
                        if ph.verify(adm_argon_h, password):
                            pw_ok = True
                            # 自动将该密码同步回 proxy_user 表，实现双端永久自愈与密码统一
                            new_h = hash_password(password)
                            with conn:
                                conn.execute("UPDATE proxy_user SET password_hash = ? WHERE id = ?", (new_h, user["id"]))
                    except Exception:
                        pass

            if not pw_ok:
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

        # License activation / recover API (开源版直接返回成功)
        if path in ("/api/proxy/license/activate", "/api/proxy/license/recover"):
            self.send_json({
                "ok": True,
                "message": "系统已全面开源，所有功能不受限制",
                "status": {
                    "ok": True,
                    "active": True,
                    "type": "open_source",
                    "plan_name": "开源社区版",
                    "unlimited": True
                }
            })
            return

        if path == "/api/proxy/auth/send-code":
            email = (req.get("email") or "").strip().lower()
            action_type = (req.get("action_type") or req.get("purpose") or "register").strip()
            
            if not email or not re.match(r"^[\w\.\+\-]+@[\w\.\-]+\.[a-zA-Z]{2,}$", email):
                self.send_json({"ok": False, "message": "请输入有效的电子邮箱地址"}, 400)
                return

            if get_setting("smtp_enabled", "0") != "1":
                self.send_json({"ok": False, "message": "系统尚未启用或未配置邮箱发信服务，请联系管理员配置 SMTP！"}, 400)
                return

            now = int(time.time())
            conn = get_db()
            
            # Check 60-second cooldown
            cur_cd = conn.execute("SELECT created_at FROM email_verify_code WHERE email = ? AND action_type = ? ORDER BY id DESC LIMIT 1", (email, action_type))
            row_cd = cur_cd.fetchone()
            if row_cd and (now - row_cd[0]) < 60:
                conn.close()
                left_sec = 60 - (now - row_cd[0])
                self.send_json({"ok": False, "message": f"验证码发送过于频繁，请等待 {left_sec} 秒后再试"}, 429)
                return

            if action_type == "register":
                if get_setting("register_enabled", "1") != "1":
                    conn.close()
                    self.send_json({"ok": False, "message": "系统当前未开放用户自主注册，请联系管理员"}, 403)
                    return
                cur_u = conn.execute("SELECT id FROM proxy_user WHERE email = ? OR username = ?", (email, email))
                if cur_u.fetchone():
                    conn.close()
                    self.send_json({"ok": False, "message": "该邮箱已被注册，请直接登录或使用忘记密码"}, 400)
                    return
                purpose_text = "注册新账户"
            elif action_type == "reset_password":
                cur_u = conn.execute("SELECT id FROM proxy_user WHERE email = ? OR username = ?", (email, email))
                if not cur_u.fetchone():
                    conn.close()
                    self.send_json({"ok": False, "message": "该邮箱尚未注册任何账户"}, 404)
                    return
                purpose_text = "重置登录密码"
            else:
                conn.close()
                self.send_json({"ok": False, "message": "未知的业务类型"}, 400)
                return

            code = f"{random.randint(100000, 999999)}"
            site_name = get_setting("site_name", "HHUB-加速中心")
            html_content = generate_verification_email_html(site_name, code, purpose_text)

            ok, err = send_smtp_email(email, f"[{site_name}] {code} 是您的{purpose_text}验证码", html_content)
            if not ok:
                conn.close()
                self.send_json({"ok": False, "message": f"邮件发送失败: {err}"}, 500)
                return

            with conn:
                conn.execute("""
                    INSERT INTO email_verify_code (email, code, action_type, expires_at, created_at)
                    VALUES (?, ?, ?, ?, ?)
                """, (email, code, action_type, now + 600, now))
            conn.close()
            self.send_json({"ok": True, "message": "验证码已成功发送至您的邮箱，10 分钟内有效"})
            return

        if path == "/api/proxy/auth/register":
            if get_setting("register_enabled", "1") != "1":
                self.send_json({"ok": False, "message": "系统当前未开放用户自主注册"}, 403)
                return
            email = (req.get("email") or "").strip().lower()
            code = (req.get("code") or "").strip()
            password = (req.get("password") or "").strip()

            if not email or not re.match(r"^[\w\.\+\-]+@[\w\.\-]+\.[a-zA-Z]{2,}$", email):
                self.send_json({"ok": False, "message": "请输入有效的电子邮箱"}, 400)
                return
            if not code or len(code) != 6:
                self.send_json({"ok": False, "message": "请输入 6 位邮箱验证码"}, 400)
                return
            if not password or len(password) < 6:
                self.send_json({"ok": False, "message": "密码长度至少 6 位"}, 400)
                return

            now = int(time.time())
            conn = get_db()

            lic_status = license_guard.get_current_license_status(conn)
            curr_user_count = conn.execute("SELECT COUNT(*) FROM proxy_user WHERE is_admin = 0").fetchone()[0]
            max_users = lic_status.get("max_users", 1)
            plan_name = lic_status.get("plan_name", "免费版")
            if curr_user_count >= max_users:
                conn.close()
                self.send_json({
                    "ok": False,
                    "error": "license_quota_exceeded",
                    "message": f"系统用户配额已满（上限 {max_users} 个客户端用户），请联系管理员升级许可证套餐！"
                }, 403)
                return

            cur_vc = conn.execute("""
                SELECT id, code, expires_at FROM email_verify_code
                WHERE email = ? AND action_type = 'register'
                ORDER BY id DESC LIMIT 1
            """, (email,))
            row_vc = cur_vc.fetchone()
            if not row_vc or row_vc["code"] != code:
                conn.close()
                self.send_json({"ok": False, "message": "验证码不正确，请重新核对或重新获取"}, 400)
                return
            if row_vc["expires_at"] < now:
                conn.close()
                self.send_json({"ok": False, "message": "验证码已过期，请重新获取"}, 400)
                return

            cur_exist = conn.execute("SELECT id FROM proxy_user WHERE email = ? OR username = ?", (email, email))
            if cur_exist.fetchone():
                conn.close()
                self.send_json({"ok": False, "message": "该邮箱已注册，请直接登录"}, 400)
                return

            sub_token = secrets.token_hex(16)
            pwd_hash = hash_password(password)
            default_traffic = int(float(get_setting("register_default_traffic_gb", "200")) * 1024 * 1024 * 1024)

            with conn:
                cur_ins = conn.execute("""
                    INSERT INTO proxy_user (
                        username, email, password_hash, sub_token,
                        traffic_limit_bytes, upload_bytes, download_bytes,
                        expires_at, enabled, is_admin, created_at, device_limit, bandwidth_limit_mbps
                    ) VALUES (?, ?, ?, ?, ?, 0, 0, 0, 1, 0, ?, 0, 0)
                """, (email, email, pwd_hash, sub_token, default_traffic, now))
                new_user_id = cur_ins.lastrowid
                conn.execute("DELETE FROM email_verify_code WHERE email = ?", (email,))

            raw_token = secrets.token_hex(32)
            token_hash = sha256(raw_token.encode()).hexdigest()
            session_days = 14
            expires_at = now + session_days * 86400
            with conn:
                conn.execute("INSERT OR REPLACE INTO session (token_hash, expires_at) VALUES (?, ?)", (token_hash, expires_at))
                conn.execute("INSERT OR REPLACE INTO proxy_session_user (token_hash, user_id, created_at) VALUES (?, ?, ?)", (token_hash, new_user_id, now))
            conn.close()

            threading.Thread(target=apply_all_configs, daemon=True).start()

            cookie_header = f"monitor_session={raw_token}; Path=/; Max-Age={session_days*86400}; SameSite=Lax; HttpOnly"
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Set-Cookie", cookie_header)
            resp_body = json.dumps({
                "ok": True,
                "message": "注册成功并已自动登录",
                "user": {
                    "id": new_user_id,
                    "username": email,
                    "email": email,
                    "is_admin": False
                }
            }, ensure_ascii=False).encode("utf-8")
            self.send_header("Content-Length", str(len(resp_body)))
            self.end_headers()
            self.wfile.write(resp_body)
            return

        if path == "/api/proxy/auth/reset-password":
            email = (req.get("email") or "").strip().lower()
            code = (req.get("code") or "").strip()
            new_password = (req.get("new_password") or "").strip()

            if not email or not code:
                self.send_json({"ok": False, "message": "邮箱与验证码不能为空"}, 400)
                return
            if not new_password or len(new_password) < 6:
                self.send_json({"ok": False, "message": "新密码长度至少 6 位"}, 400)
                return

            now = int(time.time())
            conn = get_db()
            cur_vc = conn.execute("""
                SELECT id, code, expires_at FROM email_verify_code
                WHERE email = ? AND action_type = 'reset_password'
                ORDER BY id DESC LIMIT 1
            """, (email,))
            row_vc = cur_vc.fetchone()
            if not row_vc or row_vc["code"] != code:
                conn.close()
                self.send_json({"ok": False, "message": "验证码不正确，请重新核对"}, 400)
                return
            if row_vc["expires_at"] < now:
                conn.close()
                self.send_json({"ok": False, "message": "验证码已过期，请重新获取"}, 400)
                return

            cur_u = conn.execute("SELECT id FROM proxy_user WHERE email = ? OR username = ?", (email, email))
            u_row = cur_u.fetchone()
            if not u_row:
                conn.close()
                self.send_json({"ok": False, "message": "未找到对应的用户账户"}, 404)
                return

            with conn:
                conn.execute("UPDATE proxy_user SET password_hash = ? WHERE id = ?", (hash_password(new_password), u_row[0]))
                try:
                    cur_adm_chk = conn.execute("SELECT is_admin FROM proxy_user WHERE id = ?", (u_row[0],))
                    adm_chk_r = cur_adm_chk.fetchone()
                    if adm_chk_r and adm_chk_r[0] == 1:
                        from argon2 import PasswordHasher
                        ph = PasswordHasher()
                        argon_h = ph.hash(new_password)
                        conn.execute("INSERT OR REPLACE INTO setting (key, value) VALUES ('admin_password_hash', ?)", (argon_h,))
                except Exception:
                    pass
                conn.execute("DELETE FROM email_verify_code WHERE email = ?", (email,))
            conn.close()

            self.send_json({"ok": True, "message": "密码重置成功，请使用新密码登录"})
            return

        if path == "/api/proxy/orders":
            user = get_current_user(self.headers)
            if not user:
                if not check_auth(self.headers):
                    self.send_json({"ok": False, "message": "未登录"}, 401)
                    return
                target_user_id = req.get("user_id")
                if not target_user_id:
                    self.send_json({"ok": False, "message": "请指定目标用户 ID"}, 400)
                    return
                conn = get_db()
                cur = conn.execute("SELECT * FROM proxy_user WHERE id = ?", (target_user_id,))
                row = cur.fetchone()
                conn.close()
                if not row:
                    self.send_json({"ok": False, "message": "指定用户不存在"}, 404)
                    return
                user = dict(row)
            
            user_id = user["id"]
            username = user["username"]
            tier_key = str(req.get("tier_key") or req.get("tier_id") or "").strip().lower()
            period = str(req.get("period") or "monthly").strip().lower()
            pay_method = str(req.get("pay_method") or "balance").strip().lower()
            user_note = str(req.get("note") or "").strip()

            conn = get_db()
            cur = conn.execute("SELECT * FROM proxy_tier WHERE tier_key = ? OR tier_id = ?", (tier_key, tier_key))
            tier_row = cur.fetchone()
            if not tier_row:
                conn.close()
                self.send_json({"ok": False, "message": "所选 VIP 套餐不存在"}, 400)
                return
            tier = dict(tier_row)

            if period == "yearly":
                amount = float(tier.get("price_yearly") or 0.0)
                days_add = 365
            elif period == "quarterly":
                amount = float(tier.get("price_quarterly") or 0.0)
                days_add = 90
            else:
                period = "monthly"
                amount = float(tier.get("price_monthly") or 0.0)
                days_add = 30

            order_no = f"ORD{int(time.time())}{secrets.token_hex(3).upper()}"
            now_ts = int(time.time())

            if pay_method == "balance":
                cur_u = conn.execute("SELECT balance, expires_at FROM proxy_user WHERE id = ?", (user_id,))
                u_row = cur_u.fetchone()
                curr_balance = float(u_row[0] or 0.0) if u_row else 0.0
                curr_expires_at = int(u_row[1] or 0) if u_row else 0

                if curr_balance < amount:
                    conn.close()
                    self.send_json({
                        "ok": False,
                        "message": f"账户余额不足（当前: ￥{curr_balance:.2f}，需要: ￥{amount:.2f}），请联系管理员充值或选择其他支付方式"
                    }, 400)
                    return

                new_balance = round(curr_balance - amount, 2)
                new_expires_at = (curr_expires_at + days_add * 86400) if curr_expires_at > now_ts else (now_ts + days_add * 86400)

                with conn:
                    conn.execute("UPDATE proxy_user SET balance = ?, expires_at = ?, vip_level = ? WHERE id = ?",
                                 (new_balance, new_expires_at, tier["tier_key"], user_id))
                    if tier.get("speed_limit_mbps", 0) > 0:
                        conn.execute("UPDATE proxy_user SET bandwidth_limit_mbps = ? WHERE id = ?", (tier["speed_limit_mbps"], user_id))
                    if tier.get("device_limit", 0) > 0:
                        conn.execute("UPDATE proxy_user SET device_limit = ? WHERE id = ?", (tier["device_limit"], user_id))
                    
                    conn.execute("""
                        INSERT INTO proxy_order (order_no, user_id, username, tier_id, tier_key, tier_name, period, amount, pay_method, status, note, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'completed', ?, ?, ?)
                    """, (order_no, user_id, username, tier["id"], tier["tier_key"], tier["name"], period, amount, pay_method, user_note, now_ts, now_ts))
                conn.close()
                threading.Thread(target=apply_all_configs, daemon=True).start()
                self.send_json({
                    "ok": True,
                    "order_no": order_no,
                    "status": "completed",
                    "balance": new_balance,
                    "expires_at": new_expires_at,
                    "message": f"购买成功！已扣除 ￥{amount:.2f}，套餐【{tier['name']}】与有效期已即刻生效。"
                })
                return
            else:
                with conn:
                    conn.execute("""
                        INSERT INTO proxy_order (order_no, user_id, username, tier_id, tier_key, tier_name, period, amount, pay_method, status, note, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?)
                    """, (order_no, user_id, username, tier["id"], tier["tier_key"], tier["name"], period, amount, pay_method, user_note, now_ts, now_ts))
                conn.close()
                self.send_json({
                    "ok": True,
                    "order_no": order_no,
                    "status": "pending",
                    "amount": amount,
                    "message": "订单已提交！请按照转账指引完成支付，客服确认后将立即为您开通。"
                })
                return

        # =====================================================================
        # 换机搬家数据接收接口 (点对点安全传输，凭 6 位连接码鉴权，免 Cookie)
        # =====================================================================
        if path == "/api/proxy/migration/receive":
            clean_expired_migration_tokens()
            code = str(req.get("code", "")).strip().upper()
            with _MIGRATION_LOCK:
                info = _MIGRATION_TOKENS.get(code)
            if not info or info.get("type") != "receive":
                self.send_json({"ok": False, "message": "连接码无效或已过期，请在目标机重新生成！"}, 403)
                return

            db_b64 = req.get("db_gz_base64", "")
            source_domain = str(req.get("source_domain", "")).strip()
            source_ip = str(req.get("source_ip", "")).strip()
            target_domain = str(req.get("target_domain", "")).strip()

            if not db_b64:
                self.send_json({"ok": False, "message": "未收到有效数据库负载数据"}, 400)
                return

            try:
                gz_bytes = base64.b64decode(db_b64)
                raw_db = gzip.decompress(gz_bytes)
                ok, res = apply_restored_database(raw_db, source_domain=source_domain, source_ip=source_ip, target_domain=target_domain)
                if not ok:
                    self.send_json({"ok": False, "message": f"装载数据库失败: {res}"}, 500)
                    return

                with _MIGRATION_LOCK:
                    _MIGRATION_TOKENS.pop(code, None)

                self.send_json({
                    "ok": True,
                    "message": "迁移数据已成功接收并应用生效！",
                    "stats": res
                })
            except Exception as e:
                self.send_json({"ok": False, "message": f"解析处理数据包异常: {e}"}, 500)
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
            return

        # =====================================================================
        # 换机迁移与跨机搬家 POST 接口
        # =====================================================================
        if path == "/api/proxy/migration/prepare-receive":
            if not check_auth(self.headers):
                self.send_json({"error": "Unauthorized"}, 401)
                return
            clean_expired_migration_tokens()
            rand_hex = secrets.token_hex(2).upper()
            code = f"MIG-{rand_hex}"
            expires_at = time.time() + 900
            with _MIGRATION_LOCK:
                _MIGRATION_TOKENS[code] = {
                    "type": "receive",
                    "expires_at": expires_at
                }
            pub_ip = get_server_public_ip()
            self.send_json({
                "ok": True,
                "receive_code": code,
                "public_ip": pub_ip,
                "expires_in": 900
            })
            return

        if path == "/api/proxy/migration/push":
            if not check_auth(self.headers):
                self.send_json({"error": "Unauthorized"}, 401)
                return
            target_url_raw = str(req.get("target_url", "")).strip()
            receive_code = str(req.get("receive_code", "")).strip().upper()
            if not target_url_raw or not receive_code:
                self.send_json({"ok": False, "message": "目标服务器地址与 6 位连接码不能为空"}, 400)
                return

            try:
                gz_data, _, _ = generate_backup_gz()
                db_b64 = base64.b64encode(gz_data).decode("utf-8")
            except Exception as e:
                self.send_json({"ok": False, "message": f"打包本地数据失败: {e}"}, 500)
                return

            host_header = self.headers.get("Host", "").strip() or get_setting("site_url", "").replace("https://", "").replace("http://", "").strip() or "127.0.0.1"
            source_domain = host_header.split(":")[0] if ":" in host_header else host_header
            source_ip = get_server_public_ip()

            candidate_endpoints = []
            clean_target = target_url_raw.rstrip("/")
            if clean_target.startswith("http://") or clean_target.startswith("https://"):
                candidate_endpoints.append(f"{clean_target}/api/proxy/migration/receive")
            else:
                candidate_endpoints.append(f"http://{clean_target}:28090/api/proxy/migration/receive")
                candidate_endpoints.append(f"https://{clean_target}/api/proxy/migration/receive")
                candidate_endpoints.append(f"http://{clean_target}:28080/api/proxy/migration/receive")
                candidate_endpoints.append(f"http://{clean_target}/api/proxy/migration/receive")

            target_domain = str(req.get("target_domain", "")).strip()

            push_payload = json.dumps({
                "code": receive_code,
                "source_domain": source_domain,
                "target_domain": target_domain,
                "source_ip": source_ip,
                "db_gz_base64": db_b64
            }).encode("utf-8")

            success = False
            last_err = ""
            resp_data = {}

            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE

            for ep in candidate_endpoints:
                try:
                    post_req = urllib.request.Request(
                        ep,
                        data=push_payload,
                        headers={"Content-Type": "application/json", "User-Agent": "ProxyProbe-Migrate/1.0"}
                    )
                    with urllib.request.urlopen(post_req, timeout=12, context=ctx) as resp:
                        if resp.status == 200:
                            resp_data = json.loads(resp.read().decode("utf-8"))
                            if resp_data.get("ok"):
                                success = True
                                break
                            else:
                                last_err = resp_data.get("message") or "目标服务器拒绝接收"
                except urllib.error.HTTPError as he:
                    try:
                        err_json = json.loads(he.read().decode("utf-8"))
                        last_err = err_json.get("message") or f"HTTP {he.code}"
                    except Exception:
                        last_err = f"HTTP {he.code}"
                except Exception as ex:
                    last_err = str(ex)

            if success:
                self.send_json({
                    "ok": True,
                    "message": "数据已成功传输至新服务器并应用生效！",
                    "source_domain": source_domain,
                    "target_domain": target_domain or source_domain,
                    "stats": resp_data.get("stats") or {}
                })
            else:
                self.send_json({
                    "ok": False,
                    "message": f"连接或推送到目标服务器失败: {last_err}"
                }, 400)
            return

        if path == "/api/proxy/migration/dismiss":
            if not check_auth(self.headers):
                self.send_json({"error": "Unauthorized"}, 401)
                return
            set_setting("migration_just_completed", "0")
            self.send_json({"ok": True})
            return

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

            username = req.get("username", "").strip()
            email = req.get("email", "").strip() or (username if "@" in username else "")
            password = req.get("password", "").strip()
            limit_gb = float(req.get("traffic_limit_gb", 200))
            bandwidth_limit_mbps = int(req.get("bandwidth_limit_mbps", 0))
            expires_days = int(req.get("expires_days", 0))
            device_limit = int(req.get("device_limit", 0))
            vip_level = (req.get("vip_level") or "vip1").strip()
            balance = float(req.get("balance", 0.0) or 0.0)

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
                        INSERT INTO proxy_user (username, email, password_hash, sub_token, traffic_limit_bytes, upload_bytes, download_bytes, expires_at, enabled, is_admin, created_at, device_limit, bandwidth_limit_mbps, vip_level, balance)
                        VALUES (?, ?, ?, ?, ?, 0, 0, ?, 1, 0, ?, ?, ?, ?, ?)
                    """, (username, email, pwd_hash, sub_token, limit_bytes, expires_at, int(time.time()), device_limit, bandwidth_limit_mbps, vip_level, balance))
                    new_id = cur.lastrowid
                conn.close()
                threading.Thread(target=apply_all_configs, daemon=True).start()
                self.send_json({"ok": True, "id": new_id, "user_id": new_id, "sub_token": sub_token, "message": "用户创建成功"})
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

        if path.startswith("/api/proxy/users/") and path.endswith("/balance"):
            if not check_auth(self.headers):
                self.send_json({"error": "Unauthorized"}, 401)
                return
            user_id = int(path.split("/")[-2])
            delta_val = req.get("delta") if req.get("delta") is not None else req.get("adjust")
            adjust = float(delta_val) if delta_val is not None else 0.0
            set_balance = req.get("balance")
            conn = get_db()
            with conn:
                if set_balance is not None:
                    conn.execute("UPDATE proxy_user SET balance = ? WHERE id = ?", (max(0.0, float(set_balance)), user_id))
                elif adjust != 0.0:
                    conn.execute("UPDATE proxy_user SET balance = MAX(0.0, balance + ?) WHERE id = ?", (adjust, user_id))
            cur = conn.execute("SELECT balance FROM proxy_user WHERE id = ?", (user_id,))
            row = cur.fetchone()
            conn.close()
            new_bal = round(row[0] if row else 0.0, 2)
            self.send_json({"ok": True, "balance": new_bal, "message": f"用户余额已更新为 ￥{new_bal:.2f}"})
            return

        if path.startswith("/api/proxy/users/") and path.endswith("/edit"):
            user_id = int(path.split("/")[-2])
            limit_gb = req.get("traffic_limit_gb")
            expires_at = req.get("expires_at")
            new_pwd = req.get("password", "").strip()
            device_limit = req.get("device_limit")
            bw_mbps = req.get("bandwidth_limit_mbps")
            email = req.get("email")
            vip_level = req.get("vip_level")
            balance = req.get("balance")
            
            conn = get_db()
            with conn:
                if limit_gb is not None:
                    limit_bytes = int(float(limit_gb) * 1024 * 1024 * 1024) if float(limit_gb) > 0 else 0
                    conn.execute("UPDATE proxy_user SET traffic_limit_bytes = ? WHERE id = ?", (limit_bytes, user_id))
                if expires_at is not None:
                    conn.execute("UPDATE proxy_user SET expires_at = ? WHERE id = ?", (int(expires_at), user_id))
                if device_limit is not None:
                    conn.execute("UPDATE proxy_user SET device_limit = ? WHERE id = ?", (int(device_limit), user_id))
                if bw_mbps is not None:
                    conn.execute("UPDATE proxy_user SET bandwidth_limit_mbps = ? WHERE id = ?", (int(bw_mbps), user_id))
                if email is not None:
                    conn.execute("UPDATE proxy_user SET email = ? WHERE id = ?", (str(email).strip(), user_id))
                if vip_level is not None:
                    conn.execute("UPDATE proxy_user SET vip_level = ? WHERE id = ?", (str(vip_level).strip() or "vip1", user_id))
                if balance is not None:
                    conn.execute("UPDATE proxy_user SET balance = ? WHERE id = ?", (max(0.0, float(balance)), user_id))
                if new_pwd:
                    conn.execute("UPDATE proxy_user SET password_hash = ? WHERE id = ?", (hash_password(new_pwd), user_id))
                    try:
                        cur_chk = conn.execute("SELECT is_admin FROM proxy_user WHERE id = ?", (user_id,))
                        chk_r = cur_chk.fetchone()
                        if chk_r and chk_r[0] == 1:
                            from argon2 import PasswordHasher
                            ph = PasswordHasher()
                            argon_h = ph.hash(new_pwd)
                            conn.execute("INSERT OR REPLACE INTO setting (key, value) VALUES ('admin_password_hash', ?)", (argon_h,))
                    except Exception:
                        pass
            conn.close()
            threading.Thread(target=apply_all_configs, daemon=True).start()
            self.send_json({"ok": True, "message": "用户信息已更新"})
            return

        if path == "/api/proxy/dashboard/check-health":
            if not check_auth(self.headers):
                self.send_json({"ok": False, "error": "Unauthorized"}, 401)
                return
            results = check_all_nodes_health_parallel()
            self.send_json({"ok": True, "results": results})
            return

        if path == "/api/proxy/dashboard/check-interval":
            if not check_auth(self.headers):
                self.send_json({"ok": False, "error": "Unauthorized"}, 401)
                return
            interval_min = int(req.get("interval_minutes", 10) or 10)
            if interval_min < 1:
                interval_min = 1
            if interval_min > 1440:
                interval_min = 1440
            set_setting("node_check_interval_minutes", str(interval_min))
            self.send_json({"ok": True, "interval_minutes": interval_min, "message": f"自动巡检周期已更新为 {interval_min} 分钟"})
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
                    cur_st = conn_chk.execute("SELECT realm_installed, realm_version FROM node_proxy_status WHERE node_id = ?", (server_id,))
                    s_stat = cur_st.fetchone()
                    conn_chk.close()
                    r_ok = bool(s_stat and (s_stat["realm_installed"] or s_stat["realm_version"]))
                    if not r_ok:
                        self.send_json({"ok": False, "message": f"服务器 [{server_name}] 尚未安装 Realm 端口转发核心！"}, 400)
                        return
            else:
                # 校验所选服务器是否已安装对应协议所需的核心
                needs_singbox = protocol in ("hysteria2", "tuic", "anytls")
                if is_local:
                    if needs_singbox and not os.path.exists(SINGBOX_BIN):
                        self.send_json({"ok": False, "message": "本机尚未安装 Sing-box 核心，无法创建此类协议节点，请先在核心状态卡片中安装核心！"}, 400)
                        return
                    if not needs_singbox and not os.path.exists(XRAY_BIN):
                        self.send_json({"ok": False, "message": "本机尚未安装 Xray-Core 核心，无法创建此类协议节点，请先在核心状态卡片中安装核心！"}, 400)
                        return
                else:
                    conn_chk = get_db()
                    cur_st = conn_chk.execute("SELECT xray_installed, singbox_installed, version, singbox_version FROM node_proxy_status WHERE node_id = ?", (server_id,))
                    s_stat = cur_st.fetchone()
                    conn_chk.close()
                    x_ok = bool(s_stat and (s_stat["xray_installed"] or s_stat["version"]))
                    sb_ok = bool(s_stat and (s_stat["singbox_installed"] or s_stat["singbox_version"]))
                    if needs_singbox and not sb_ok:
                        self.send_json({"ok": False, "message": f"服务器 [{server_name}] 尚未安装 Sing-box 核心，无法创建此类协议节点！"}, 400)
                        return
                    if not needs_singbox and not x_ok:
                        self.send_json({"ok": False, "message": f"服务器 [{server_name}] 尚未安装 Xray-Core 核心，无法创建此类协议节点！"}, 400)
                        return
            
            uuid = req.get("uuid") or gen_uuid()
            flow = req.get("flow", "xtls-rprx-vision")
            sni = req.get("sni") or ("www.bing.com" if protocol in ("trojan", "hysteria2", "tuic", "anytls") else "www.apple.com")
            dest = req.get("dest", f"{sni}:443")
            priv_key = req.get("private_key", "")
            pub_key = req.get("public_key", "")
            short_id = req.get("short_id", "")
            ws_path = req.get("ws_path", "/ws-proxy" if protocol != "vmess_ws" else "/vmess-ws")
            method = req.get("method", "2022-blake3-aes-128-gcm")
            password = req.get("password", "")
            username = req.get("username", "")
            extra_json = req.get("extra_json", "")
            bandwidth_limit_mbps = int(req.get("bandwidth_limit_mbps", 0))

            if protocol in ("vless_reality", "vless_reality_xhttp") and (not priv_key or not pub_key):
                gen_priv, gen_pub, gen_sid = gen_xray_keys()
                priv_key = priv_key or gen_priv
                pub_key = pub_key or gen_pub
                short_id = short_id or gen_sid
            elif protocol == "ss2022" and not password:
                password = gen_ss2022_key(method)
            elif protocol == "socks5" and not password:
                password = gen_random_password(12)
            elif protocol in ("trojan", "anytls") and not password:
                password = gen_random_password(16)

            now = int(time.time())
            vip_levels = (req.get("vip_levels") or req.get("vip_level") or "").strip()
            if not vip_levels:
                self.send_json({"ok": False, "message": "请选择节点可见 VIP 权限等级（例如：所有用户可见 或 指定 VIP 等级）"}, 400)
                return
            conn = get_db()
            with conn:
                cur = conn.execute("""
                INSERT INTO proxy_node (
                    server_id, server_name, server_host, name, protocol, port,
                    uuid, flow, sni, dest, public_key, private_key, short_id,
                    ws_path, method, password, username, extra_json,
                    is_relay, relay_server_id, relay_port, remote_host, remote_port, target_node_id,
                    bandwidth_limit_mbps, vip_levels, enabled, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
                """, (
                    server_id, server_name, server_host, name, protocol, port,
                    uuid, flow, sni, dest, pub_key, priv_key, short_id,
                    ws_path, method, password, username, extra_json,
                    is_relay, relay_server_id, port, remote_host, remote_port, target_node_id,
                    bandwidth_limit_mbps, vip_levels, now
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
                "ws_path": ws_path,
                "method": method,
                "password": password,
                "username": username,
                "is_relay": is_relay,
                "remote_host": remote_host,
                "remote_port": remote_port
            })

            self.send_json({
                "ok": ok,
                "id": new_id,
                "node_id": new_id,
                "node": {"id": new_id, "name": name, "protocol": protocol, "port": port},
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
            if is_legacy_migration_needed():
                self.send_json({
                    "ok": False,
                    "need_migration": True,
                    "migration_cmd": "hhub migrate",
                    "error": "系统检测到当前面板仍运行在旧版目录 /opt/monitor。为保护您的数据库与配置安全，并平滑切换至全新独立架构 /opt/proxyprobe，请在 SSH 终端执行一次【hhub migrate】完成一键迁移！"
                }, 400)
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
            total_cur = (req.get("total_cost_currency") or "CNY").strip().upper()
            set_setting("public_show_price", show_price)
            set_setting("public_show_expiry", show_expiry)
            set_setting("public_show_traffic_limit", show_traffic)
            set_setting("total_cost_currency", total_cur)
            self.send_json({"ok": True, "message": "服务器公开信息展示权限已更新"})
            return

        elif path.startswith("/api/proxy/nodes/") and path.endswith("/edit"):
            if not check_auth(self.headers):
                self.send_json({"error": "Unauthorized"}, 401)
                return
            try:
                node_id = int(path.split("/")[-2])
            except ValueError:
                self.send_json({"ok": False, "message": "无效的节点 ID"}, 400)
                return

            name = (req.get("name") or "").strip()
            port = req.get("port")
            uuid_val = req.get("uuid")
            pwd_val = req.get("password")
            sni = req.get("sni")
            bw = req.get("bandwidth_limit_mbps")
            vip_levels = req.get("vip_levels") if req.get("vip_levels") is not None else req.get("vip_level")
            enabled = req.get("enabled")

            conn = get_db()
            with conn:
                if port is not None:
                    port_num = int(port)
                    chk = conn.execute("SELECT id FROM proxy_node WHERE port = ? AND id != ?", (port_num, node_id)).fetchone()
                    if chk:
                        conn.close()
                        self.send_json({"ok": False, "message": f"端口 {port_num} 已被其他节点占用，请更换端口！"}, 400)
                        return
                    conn.execute("UPDATE proxy_node SET port = ? WHERE id = ?", (port_num, node_id))
                if name:
                    conn.execute("UPDATE proxy_node SET name = ? WHERE id = ?", (name, node_id))
                if uuid_val is not None:
                    conn.execute("UPDATE proxy_node SET uuid = ? WHERE id = ?", (str(uuid_val).strip(), node_id))
                if pwd_val is not None:
                    conn.execute("UPDATE proxy_node SET password = ? WHERE id = ?", (str(pwd_val).strip(), node_id))
                if sni is not None:
                    conn.execute("UPDATE proxy_node SET sni = ? WHERE id = ?", (str(sni).strip(), node_id))
                if bw is not None:
                    conn.execute("UPDATE proxy_node SET bandwidth_limit_mbps = ? WHERE id = ?", (int(bw), node_id))
                if vip_levels is not None:
                    conn.execute("UPDATE proxy_node SET vip_levels = ? WHERE id = ?", (str(vip_levels).strip(), node_id))
                if enabled is not None:
                    conn.execute("UPDATE proxy_node SET enabled = ? WHERE id = ?", (int(enabled), node_id))
            conn.close()
            threading.Thread(target=apply_all_configs, daemon=True).start()
            self.send_json({"ok": True, "message": "节点配置已更新并已生效"})
            return

        elif path == "/api/proxy/nodes/batch-create":
            if not check_auth(self.headers):
                self.send_json({"error": "Unauthorized"}, 401)
                return
            server_id = int(req.get("server_id", 0))
            protocols = req.get("protocols") or ["vless_reality", "hysteria2", "anytls", "trojan", "ss2022"]
            bandwidth_limit_mbps = int(req.get("bandwidth_limit_mbps", 0))
            vip_levels = (req.get("vip_levels") or "").strip()
            try:
                created = batch_create_nodes_for_server(server_id, protocols, bandwidth_limit_mbps, vip_levels=vip_levels)
                self.send_json({
                    "ok": True,
                    "created": created,
                    "message": f"成功一键生成全家桶 {len(created)} 个协议节点！"
                })
            except Exception as e:
                self.send_json({"ok": False, "message": str(e)}, 400)
            return

        elif path == "/api/proxy/settings/support":
            if not check_auth(self.headers):
                self.send_json({"error": "Unauthorized"}, 401)
                return
            enabled = "1" if req.get("enabled") else "0"
            tg_url = (req.get("telegram_url") or "").strip()
            set_setting("support_tg_enabled", enabled)
            set_setting("support_tg_url", tg_url)
            self.send_json({"ok": True, "message": "客服设置已成功保存"})
            return

        elif path == "/api/proxy/settings/smtp":
            if not check_auth(self.headers):
                self.send_json({"error": "Unauthorized"}, 401)
                return
            set_setting("smtp_enabled", "1" if req.get("smtp_enabled") else "0")
            set_setting("smtp_host", (req.get("smtp_host") or "").strip())
            set_setting("smtp_port", str(int(req.get("smtp_port", 465))))
            set_setting("smtp_ssl", "1" if req.get("smtp_ssl") else "0")
            set_setting("smtp_user", (req.get("smtp_user") or "").strip())
            if "smtp_pass" in req and req["smtp_pass"]:
                set_setting("smtp_pass", str(req["smtp_pass"]).strip())
            set_setting("smtp_from_name", (req.get("smtp_from_name") or "HHUB").strip())
            set_setting("site_name", (req.get("site_name") or "HHUB-加速中心").strip())
            set_setting("register_enabled", "1" if req.get("register_enabled") else "0")
            self.send_json({"ok": True, "message": "SMTP 邮件发信配置已成功保存"})
            return

        elif path == "/api/proxy/smtp/test":
            if not check_auth(self.headers):
                self.send_json({"error": "Unauthorized"}, 401)
                return
            to_email = (req.get("to_email") or get_setting("smtp_user", "")).strip()
            if not to_email:
                self.send_json({"ok": False, "message": "请填写测试接收邮箱或在配置中填写发信账号"}, 400)
                return
            site_name = get_setting("site_name", "HHUB-加速中心")
            test_html = f"""
            <div style="max-width: 520px; margin: 0 auto; padding: 28px; font-family: sans-serif; background: #fff; border: 1px solid #e2e8f0; border-radius: 12px;">
                <h3 style="color: #4f46e5; margin-top: 0;">🎉 SMTP 测试邮件发送成功！</h3>
                <p style="color: #334155; line-height: 1.6;">您好！这是一封来自 <strong>{site_name}</strong> 的系统发信测试邮件。</p>
                <p style="color: #64748b; font-size: 13px;">这证明您的 SMTP 邮件服务器配置（包括主机、端口、SSL/TLS 握手及授权凭据）完全正确，用户注册与重置密码邮件功能已可正常运作！</p>
                <div style="margin-top: 20px; font-size: 12px; color: #94a3b8;">发送时间: {time.strftime('%Y-%m-%d %H:%M:%S')}</div>
            </div>
            """
            ok, err = send_smtp_email(to_email, f"[{site_name}] SMTP 发信配置测试通知", test_html)
            if ok:
                self.send_json({"ok": True, "message": f"测试邮件已成功发送至 {to_email}，请查收邮箱！"})
            else:
                self.send_json({"ok": False, "message": f"测试发信失败: {err}"}, 500)
            return

        elif path == "/api/proxy/tiers":
            if not check_auth(self.headers):
                self.send_json({"error": "Unauthorized"}, 401)
                return
            t_id = req.get("id")
            tier_key = (req.get("tier_key") or req.get("tier_id") or "").strip().lower()
            tier_id_val = (req.get("tier_id") or tier_key).strip().lower()
            name = (req.get("name") or "").strip()
            description = (req.get("description") or "").strip()
            speed_limit = int(req.get("speed_limit_mbps", 0) or req.get("bandwidth_limit_mbps", 0) or 0)
            device_limit = int(req.get("device_limit", 0) or 0)
            sort_order = int(req.get("sort_order", 0) or 0)
            price_monthly = float(req.get("price_monthly", 0.0) or 0.0)
            price_quarterly = float(req.get("price_quarterly", 0.0) or 0.0)
            price_yearly = float(req.get("price_yearly", 0.0) or 0.0)
            traffic_gb = float(req.get("traffic_gb", 0.0) or 0.0)

            if not tier_key:
                self.send_json({"ok": False, "message": "套餐标识（tier_key / tier_id）不能为空"}, 400)
                return
            if not name:
                self.send_json({"ok": False, "message": "套餐名称不能为空"}, 400)
                return

            conn = get_db()
            with conn:
                if t_id:
                    conn.execute("""
                        UPDATE proxy_tier
                        SET tier_key = ?, tier_id = ?, name = ?, description = ?, speed_limit_mbps = ?, device_limit = ?, sort_order = ?,
                            price_monthly = ?, price_quarterly = ?, price_yearly = ?, traffic_gb = ?
                        WHERE id = ?
                    """, (tier_key, tier_id_val, name, description, speed_limit, device_limit, sort_order, price_monthly, price_quarterly, price_yearly, traffic_gb, int(t_id)))
                    saved_id = int(t_id)
                else:
                    cur = conn.execute("""
                        INSERT INTO proxy_tier (tier_key, tier_id, name, description, speed_limit_mbps, device_limit, sort_order, price_monthly, price_quarterly, price_yearly, traffic_gb, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (tier_key, tier_id_val, name, description, speed_limit, device_limit, sort_order, price_monthly, price_quarterly, price_yearly, traffic_gb, int(time.time())))
                    saved_id = cur.lastrowid
            conn.close()
            self.send_json({"ok": True, "id": saved_id, "tier_id": saved_id, "message": "VIP 套餐已成功保存"})
            return

        elif path == "/api/proxy/settings/payment":
            if not check_auth(self.headers):
                self.send_json({"error": "Unauthorized"}, 401)
                return
            set_setting("pay_enabled", "1" if (req.get("pay_enabled") or req.get("enabled", True)) else "0")
            set_setting("pay_usdt_trc20", str(req.get("pay_usdt_trc20") or req.get("usdt_trc20", "")).strip())
            set_setting("pay_alipay_qr", str(req.get("pay_alipay_qr") or req.get("alipay_qr", "")).strip())
            set_setting("pay_wechat_qr", str(req.get("pay_wechat_qr") or req.get("wechat_qr", "")).strip())
            set_setting("pay_tg_contact", str(req.get("pay_tg_contact") or req.get("tg_support", "")).strip())
            set_setting("pay_notes", str(req.get("pay_notes", "")).strip())
            self.send_json({"ok": True, "message": "支付网关配置已成功保存"})
            return

        elif re.match(r"^/api/proxy/orders/(\d+)/complete$", path):
            if not check_auth(self.headers):
                self.send_json({"error": "Unauthorized"}, 401)
                return
            order_id = int(path.split("/")[-2])
            conn = get_db()
            cur = conn.execute("SELECT * FROM proxy_order WHERE id = ?", (order_id,))
            order = cur.fetchone()
            if not order:
                conn.close()
                self.send_json({"ok": False, "message": "订单不存在"}, 404)
                return
            order = dict(order)
            if order["status"] == "completed":
                conn.close()
                self.send_json({"ok": True, "message": "订单早已是完成状态"})
                return

            user_id = order["user_id"]
            tier_key = order["tier_key"]
            period = order["period"]
            days_add = 365 if period == "yearly" else (90 if period == "quarterly" else 30)
            now_ts = int(time.time())

            cur_u = conn.execute("SELECT expires_at FROM proxy_user WHERE id = ?", (user_id,))
            u_row = cur_u.fetchone()
            curr_exp = int(u_row[0] or 0) if u_row else 0
            new_expires_at = (curr_exp + days_add * 86400) if curr_exp > now_ts else (now_ts + days_add * 86400)

            cur_t = conn.execute("SELECT speed_limit_mbps, device_limit FROM proxy_tier WHERE tier_key = ?", (tier_key,))
            t_row = cur_t.fetchone()

            with conn:
                conn.execute("UPDATE proxy_user SET expires_at = ?, vip_level = ? WHERE id = ?", (new_expires_at, tier_key, user_id))
                if t_row and t_row[0] > 0:
                    conn.execute("UPDATE proxy_user SET bandwidth_limit_mbps = ? WHERE id = ?", (t_row[0], user_id))
                if t_row and t_row[1] > 0:
                    conn.execute("UPDATE proxy_user SET device_limit = ? WHERE id = ?", (t_row[1], user_id))
                conn.execute("UPDATE proxy_order SET status = 'completed', updated_at = ? WHERE id = ?", (now_ts, order_id))
            conn.close()
            threading.Thread(target=apply_all_configs, daemon=True).start()
            self.send_json({"ok": True, "message": f"订单已审核通过并生效，用户会员期限已延长至 {time.strftime('%Y-%m-%d', time.localtime(new_expires_at))}"})
            return

        elif re.match(r"^/api/proxy/orders/(\d+)/reject$", path):
            if not check_auth(self.headers):
                self.send_json({"error": "Unauthorized"}, 401)
                return
            order_id = int(path.split("/")[-2])
            now_ts = int(time.time())
            conn = get_db()
            with conn:
                conn.execute("UPDATE proxy_order SET status = 'rejected', updated_at = ? WHERE id = ?", (now_ts, order_id))
            conn.close()
            self.send_json({"ok": True, "message": "订单已驳回/取消"})
            return

        elif path == "/api/proxy/announcements":
            if not check_auth(self.headers):
                self.send_json({"error": "Unauthorized"}, 401)
                return
            a_id = req.get("id")
            title = (req.get("title") or "").strip()
            summary = (req.get("summary") or "").strip()
            content = (req.get("content") or "").strip()
            is_pinned = 1 if req.get("is_pinned") else 0
            enabled = 1 if req.get("enabled", True) else 0
            now = int(time.time())

            if not title:
                self.send_json({"ok": False, "message": "公告标题不能为空"}, 400)
                return

            conn = get_db()
            with conn:
                if a_id:
                    conn.execute("""
                        UPDATE proxy_announcement
                        SET title = ?, summary = ?, content = ?, is_pinned = ?, enabled = ?, updated_at = ?
                        WHERE id = ?
                    """, (title, summary, content, is_pinned, enabled, now, int(a_id)))
                    saved_id = int(a_id)
                else:
                    cur = conn.execute("""
                        INSERT INTO proxy_announcement (title, summary, content, is_pinned, enabled, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """, (title, summary, content, is_pinned, enabled, now, now))
                    saved_id = cur.lastrowid
            conn.close()
            self.send_json({"ok": True, "id": saved_id, "announcement_id": saved_id, "message": "系统公告已成功保存"})
            return

        elif path == "/api/proxy/settings/notification":
            if not check_auth(self.headers):
                self.send_json({"error": "Unauthorized"}, 401)
                return
            enabled = "1" if req.get("enabled") else "0"
            title = (req.get("title") or "").strip()
            content = (req.get("content") or "").strip()
            set_setting("global_notification_enabled", enabled)
            set_setting("global_notification_title", title)
            set_setting("global_notification_content", content)
            set_setting("global_notification_updated_at", str(int(time.time())))
            self.send_json({"ok": True, "message": "全局登录通知已成功保存"})
            return

        elif path == "/api/proxy/apps":
            if not check_auth(self.headers):
                self.send_json({"error": "Unauthorized"}, 401)
                return
            app_id = req.get("id")
            name = (req.get("name") or "").strip()
            platform = (req.get("platform") or "all").strip()
            version = (req.get("version") or "").strip()
            description = (req.get("description") or "").strip()
            external_url = (req.get("external_url") or req.get("mirror_url") or "").strip()
            sort_order = int(req.get("sort_order", 0))
            enabled = 1 if req.get("enabled", True) else 0

            if not name:
                self.send_json({"ok": False, "message": "客户端软件名称不能为空"}, 400)
                return

            conn = get_db()
            with conn:
                if app_id:
                    conn.execute("""
                        UPDATE proxy_app_download
                        SET name = ?, platform = ?, version = ?, description = ?, external_url = ?, sort_order = ?, enabled = ?
                        WHERE id = ?
                    """, (name, platform, version, description, external_url, sort_order, enabled, int(app_id)))
                    saved_id = int(app_id)
                else:
                    cur = conn.execute("""
                        INSERT INTO proxy_app_download (name, platform, version, description, external_url, sort_order, enabled, created_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (name, platform, version, description, external_url, sort_order, enabled, int(time.time())))
                    saved_id = cur.lastrowid
            conn.close()
            self.send_json({"ok": True, "id": saved_id, "app_id": saved_id, "message": "软件配置已成功保存"})
            return

        elif path == "/api/proxy/settings/server-expiry":
            if not check_auth(self.headers):
                self.send_json({"error": "Unauthorized"}, 401)
                return
            enabled = "1" if req.get("enabled") else "0"
            days = str(int(req.get("days") or req.get("remind_days_before") or 7))
            set_setting("server_expire_remind_enabled", enabled)
            set_setting("server_expire_remind_days", days)
            self.send_json({"ok": True, "message": "服务器到期提醒设置已成功保存"})
            return

        elif path == "/api/proxy/server-expiry/test-notify":
            if not check_auth(self.headers):
                self.send_json({"error": "Unauthorized"}, 401)
                return
            ok, msg = check_server_expirations(force=True)
            self.send_json({"ok": ok, "message": msg})
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
                try:
                    conn.execute("DELETE FROM proxy_node_latency WHERE node_id = ?", (node_id,))
                except Exception:
                    pass
            conn.close()
            if row and is_local_node(dict(row)):
                threading.Thread(target=apply_all_configs, daemon=True).start()
            self.send_json({"ok": True, "message": "节点已成功删除"})
            return

        m_tier = re.match(r"^/api/proxy/tiers/(\d+)$", path)
        if m_tier:
            t_id = int(m_tier.group(1))
            conn = get_db()
            with conn:
                conn.execute("DELETE FROM proxy_tier WHERE id = ?", (t_id,))
            conn.close()
            self.send_json({"ok": True, "message": "套餐已删除"})
            return

        m_order = re.match(r"^/api/proxy/orders/(\d+)$", path)
        if m_order:
            order_id = int(m_order.group(1))
            conn = get_db()
            with conn:
                conn.execute("DELETE FROM proxy_order WHERE id = ?", (order_id,))
            conn.close()
            self.send_json({"ok": True, "message": "订单记录已删除"})
            return

        m_anno = re.match(r"^/api/proxy/announcements/(\d+)$", path)
        if m_anno:
            a_id = int(m_anno.group(1))
            conn = get_db()
            with conn:
                conn.execute("DELETE FROM proxy_announcement WHERE id = ?", (a_id,))
            conn.close()
            self.send_json({"ok": True, "message": "公告已删除"})
            return

        m_app = re.match(r"^/api/proxy/apps/(\d+)$", path)
        if m_app:
            app_id = int(m_app.group(1))
            conn = get_db()
            with conn:
                cur = conn.execute("SELECT file_path FROM proxy_app_download WHERE id = ?", (app_id,))
                row = cur.fetchone()
                if row and row[0] and os.path.exists(row[0]):
                    try:
                        os.remove(row[0])
                    except Exception:
                        pass
                conn.execute("DELETE FROM proxy_app_download WHERE id = ?", (app_id,))
            conn.close()
            self.send_json({"ok": True, "message": "客户端软件已删除"})
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
            threading.Thread(target=apply_all_configs, daemon=True).start()
            self.send_json({"ok": True, "message": "用户已删除"})
            return

        m_server = re.match(r"^/api/proxy/servers/(\d+)$", path)
        if m_server:
            server_id = int(m_server.group(1))
            conn = get_db()
            with conn:
                cur_nodes = conn.execute("SELECT id FROM proxy_node WHERE server_id = ?", (server_id,))
                del_node_ids = [r[0] for r in cur_nodes.fetchall()]
                if del_node_ids:
                    conn.execute(f"DELETE FROM proxy_node WHERE id IN ({','.join('?' for _ in del_node_ids)})", del_node_ids)
                    try:
                        conn.execute(f"DELETE FROM proxy_node_latency WHERE node_id IN ({','.join('?' for _ in del_node_ids)})", del_node_ids)
                    except Exception:
                        pass
                conn.execute("DELETE FROM node_proxy_status WHERE node_id = ?", (server_id,))
                conn.execute("DELETE FROM node WHERE id = ?", (server_id,))
            conn.close()
            threading.Thread(target=apply_all_configs, daemon=True).start()
            self.send_json({"ok": True, "message": f"服务器及关联的 {len(del_node_ids)} 个节点已彻底清除"})
            return

        self.send_json({"error": "Not Found"}, 404)

if __name__ == "__main__":
    init_db()

    def _initial_ip_heal():
        time.sleep(1)
        try:
            pub_ip = get_server_public_ip()
            if pub_ip and not is_private_ip(pub_ip):
                c = sqlite3.connect(DB_PATH)
                with c:
                    c.execute("""
                        UPDATE node 
                        SET ip = CASE WHEN (ip IN ('', '127.0.0.1') OR ip LIKE '127.%') THEN ? ELSE ip END,
                            ipv4 = CASE WHEN (ipv4 IN ('', '127.0.0.1') OR ipv4 LIKE '127.%') THEN ? ELSE ipv4 END
                        WHERE (ip IN ('', '127.0.0.1') OR ipv4 IN ('', '127.0.0.1') OR ip LIKE '127.%' OR ipv4 LIKE '127.%')
                    """, (pub_ip, pub_ip))
                    c.execute("""
                        UPDATE proxy_node
                        SET server_host = ?
                        WHERE server_host IN ('127.0.0.1', 'localhost', '') OR server_host LIKE '127.%'
                    """, (pub_ip,))
                c.close()
        except Exception:
            pass
    threading.Thread(target=_initial_ip_heal, daemon=True, name="init_ip_heal").start()
    t = threading.Thread(target=traffic_collector_loop, daemon=True)
    t.start()
    t_backup = threading.Thread(target=telegram_backup_loop, daemon=True)
    t_backup.start()
    t_alert = threading.Thread(target=telegram_node_alert_loop, daemon=True)
    t_alert.start()
    t_health = threading.Thread(target=node_health_checker_loop, daemon=True)
    t_health.start()
    t_tg_cmd = threading.Thread(target=telegram_bot_command_loop, daemon=True)
    t_tg_cmd.start()
    t_expiry = threading.Thread(target=server_expiry_check_loop, daemon=True)
    t_expiry.start()
    server = ThreadingHTTPServer(("127.0.0.1", PORT), ProxyHandler)
    print(f"ProxyManager daemon listening on 127.0.0.1:{PORT}")
    server.serve_forever()
