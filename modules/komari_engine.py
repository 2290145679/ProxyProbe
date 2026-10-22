# -*- coding: utf-8 -*-
"""
Komari Probe Integration Engine
负责 Komari 探针核心服务的配置读写、节点打通、服务守护与 API 桥接。
"""

import os
import re
import json
import sqlite3
import subprocess
import time

KOMARI_DEFAULT_DB = "/opt/proxyprobe/data/komari.db"

def get_komari_db_path():
    """获取 Komari 数据库路径"""
    if os.path.exists(KOMARI_DEFAULT_DB):
        return KOMARI_DEFAULT_DB
    
    # 兼容本地开发或自定义目录
    local_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "komari.db")
    if os.path.exists(local_path):
        return local_path
    
    # 回退到默认路径（即便文件尚在创建中）
    return KOMARI_DEFAULT_DB

def get_komari_db():
    """连接 Komari 数据库"""
    db_path = get_komari_db_path()
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    conn = sqlite3.connect(db_path, timeout=10)
    conn.execute("PRAGMA journal_mode=WAL")
    return conn

def parse_db_val(val_str):
    """解析 Komari configs 表中存储的 JSON/字符串值"""
    if val_str is None:
        return ""
    val_str = str(val_str).strip()
    if val_str == "true":
        return True
    if val_str == "false":
        return False
    try:
        return json.loads(val_str)
    except Exception:
        if val_str.startswith('"') and val_str.endswith('"'):
            return val_str[1:-1]
        return val_str

def format_db_val(val):
    """序列化为 Komari configs 表标准格式"""
    if isinstance(val, bool):
        return "true" if val else "false"
    if isinstance(val, (int, float)):
        return str(val)
    if isinstance(val, (dict, list)):
        return json.dumps(val, ensure_ascii=False)
    # 字符串用 JSON 格式括起来
    return json.dumps(str(val), ensure_ascii=False)

def get_probe_settings():
    """读取 Komari 探针全量设置"""
    defaults = {
        "sitename": "ProxyProbe",
        "description": "现代化极简服务器监控与代理管理平台",
        "theme": "default",
        "private_site": False,
        "send_ip_addr_to_guest": False,
        "cors_origin_check_enabled": True,
        "ws_origin_check_enabled": True,
        "geo_ip_enabled": True,
        "notification_enabled": True,
        "expire_notification_enabled": True,
        "expire_notification_lead_days": 7,
        "traffic_limit_percentage": 80,
        "custom_head": "",
        "custom_body": "",
    }
    
    db_path = get_komari_db_path()
    if not os.path.exists(db_path):
        return defaults

    try:
        conn = get_komari_db()
        cur = conn.execute("SELECT key, value FROM configs")
        rows = cur.fetchall()
        conn.close()
        
        res = dict(defaults)
        for k, v in rows:
            parsed = parse_db_val(v)
            res[k] = parsed
        return res
    except Exception as e:
        print(f"[!] 读取 Komari 配置异常: {e}")
        return defaults

def update_probe_settings(patch: dict):
    """更新 Komari 探针设置"""
    db_path = get_komari_db_path()
    try:
        conn = get_komari_db()
        # 确保 configs 表存在
        conn.execute("CREATE TABLE IF NOT EXISTS configs (key TEXT PRIMARY KEY, value TEXT)")
        
        for k, v in patch.items():
            db_val = format_db_val(v)
            conn.execute("INSERT OR REPLACE INTO configs (key, value) VALUES (?, ?)", (k, db_val))
        
        conn.commit()
        conn.close()
        remove_probe_nav_widget()
        return True, "配置更新成功"
    except Exception as e:
        return False, f"写入 Komari 数据库失败: {e}"

def remove_probe_nav_widget():
    """彻底从 Komari custom_body 中清理悬浮导航组件"""
    db_path = get_komari_db_path()
    if not os.path.exists(db_path):
        return False
    try:
        conn = get_komari_db()
        cur = conn.execute("SELECT value FROM configs WHERE key='custom_body'")
        row = cur.fetchone()
        existing_body = parse_db_val(row[0]) if row and row[0] else ""
        
        cleaned_body = re.sub(r"<!-- PROXYPROBE_NAV_START -->.*?<!-- PROXYPROBE_NAV_END -->", "", existing_body, flags=re.DOTALL).strip()
        cleaned_body = re.sub(r"<div id=\"proxyprobe-nav-bar\".*?<!-- PROXYPROBE_NAV_END -->", "", cleaned_body, flags=re.DOTALL).strip()
        
        db_val = format_db_val(cleaned_body)
        conn.execute("INSERT OR REPLACE INTO configs (key, value) VALUES ('custom_body', ?)", (db_val,))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[!] 清理探针悬浮导航条失败: {e}")
        return False

def get_probe_status():
    """检测 Komari 探针服务与端口运行状态"""
    status = {
        "service": "komari.service",
        "running": False,
        "port": 28080,
        "db_exists": os.path.exists(get_komari_db_path()),
        "uptime": 0
    }
    
    # 检查进程
    try:
        out = subprocess.check_output(["pgrep", "-f", "komari server"], stderr=subprocess.DEVNULL)
        if out.strip():
            status["running"] = True
    except Exception:
        status["running"] = False
        
    return status

def restart_komari_service():
    """重启 Komari 探针服务"""
    try:
        subprocess.run(["systemctl", "restart", "komari.service"], check=True)
        return True, "Komari 服务重启成功"
    except Exception as e:
        return False, f"服务重启失败: {e}"

# =============================================================================
# Komari 账户与认证会话互通打通模块 (Account & Session Bridge)
# =============================================================================
KOMARI_SALT = "06Wm4Jv1Hkxx"

def hash_komari_password(passwd: str) -> str:
    """按 Komari 官方规范生成密码哈希 (SHA256 + 固定加盐 + Base64)"""
    import hashlib
    import base64
    h = hashlib.sha256((passwd + KOMARI_SALT).encode("utf-8")).digest()
    return base64.b64encode(h).decode("utf-8")

def verify_komari_password(username: str, passwd: str):
    """
    比对 Komari 数据库中的用户密码。
    返回 (is_valid, user_uuid)
    """
    db_path = get_komari_db_path()
    if not os.path.exists(db_path):
        return False, None
    try:
        expected_hash = hash_komari_password(passwd)
        conn = get_komari_db()
        cur = conn.execute("SELECT uuid, passwd FROM users WHERE username = ? LIMIT 1", (username,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return False, None
        uuid_val, stored_hash = row[0], row[1]
        if stored_hash == expected_hash:
            return True, uuid_val
        return False, None
    except Exception as e:
        print(f"[!] verify_komari_password error: {e}")
        return False, None

def sync_komari_admin_password(passwd: str, username: str = "admin") -> bool:
    """
    双向密码同步：将管理员密码写入 Komari 数据库 users 表
    """
    db_path = get_komari_db_path()
    if not os.path.exists(db_path):
        return False
    try:
        hashed = hash_komari_password(passwd)
        import datetime
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        conn = get_komari_db()
        # 查找是否存在 admin 用户
        cur = conn.execute("SELECT uuid FROM users WHERE username = ? LIMIT 1", (username,))
        row = cur.fetchone()
        if row:
            conn.execute("UPDATE users SET passwd = ?, updated_at = ? WHERE username = ?", (hashed, now_iso, username))
        else:
            import uuid
            new_uuid = str(uuid.uuid4())
            conn.execute("""
                INSERT INTO users (uuid, username, passwd, sso_type, sso_id, two_factor, created_at, updated_at)
                VALUES (?, ?, ?, '', '', '', ?, ?)
            """, (new_uuid, username, hashed, now_iso, now_iso))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[!] sync_komari_admin_password error: {e}")
        return False

def get_komari_admin_uuid(username: str = "admin") -> str:
    """获取 Komari 管理员的 UUID"""
    db_path = get_komari_db_path()
    if not os.path.exists(db_path):
        return ""
    try:
        conn = get_komari_db()
        cur = conn.execute("SELECT uuid FROM users WHERE username = ? LIMIT 1", (username,))
        row = cur.fetchone()
        conn.close()
        return row[0] if row else ""
    except Exception:
        return ""

def create_komari_session(uuid: str, expires_sec: int = 2592000, user_agent: str = "", ip: str = "") -> str:
    """
    在 Komari 数据库中创建有效会话记录并返回 session_token (32 位随机字串)
    """
    db_path = get_komari_db_path()
    if not os.path.exists(db_path):
        return ""
    try:
        import secrets
        import datetime
        alphabet = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        session_token = "".join(secrets.choice(alphabet) for _ in range(32))
        
        now = datetime.datetime.now(datetime.timezone.utc)
        expires = now + datetime.timedelta(seconds=expires_sec)
        
        conn = get_komari_db()
        conn.execute("""
            INSERT INTO sessions (uuid, session, user_agent, ip, login_method, latest_online, latest_user_agent, latest_ip, expires, created_at)
            VALUES (?, ?, ?, ?, 'password', ?, ?, ?, ?, ?)
        """, (
            uuid,
            session_token,
            user_agent,
            ip,
            now.strftime("%Y-%m-%d %H:%M:%S"),
            user_agent,
            ip,
            expires.strftime("%Y-%m-%d %H:%M:%S"),
            now.strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.commit()
        conn.close()
        return session_token
    except Exception as e:
        print(f"[!] create_komari_session error: {e}")
        return ""

def verify_komari_session(session_token: str):
    """
    校验 Komari session_token 是否有效，若有效返回对应的用户名或 None
    """
    if not session_token:
        return None
    db_path = get_komari_db_path()
    if not os.path.exists(db_path):
        return None
    try:
        import datetime
        conn = get_komari_db()
        cur = conn.execute("""
            SELECT s.uuid, s.expires, u.username
            FROM sessions s
            LEFT JOIN users u ON s.uuid = u.uuid
            WHERE s.session = ?
            LIMIT 1
        """, (session_token,))
        row = cur.fetchone()
        conn.close()
        if not row:
            return None
        uuid_val, expires_str, uname = row[0], row[1], row[2]
        
        # 兼容日期时间字符串比对
        try:
            exp_dt = datetime.datetime.fromisoformat(str(expires_str).replace("Z", "+00:00"))
            if exp_dt.tzinfo is None:
                exp_dt = exp_dt.replace(tzinfo=datetime.timezone.utc)
            if datetime.datetime.now(datetime.timezone.utc) > exp_dt:
                return None
        except Exception:
            pass # 格式不规范时宽容处理
            
        return uname or "admin"
    except Exception as e:
        print(f"[!] verify_komari_session error: {e}")
        return None

# =============================================================================
# Komari 节点与被控端双向打通模块 (Client & Node Sync)
# =============================================================================

def sync_client_to_komari(token: str, name: str, ip: str = None) -> bool:
    """确保该节点在 Komari clients 表中存在，以允许 komari-agent 正常连接上报"""
    if not token:
        return False
    db_path = get_komari_db_path()
    try:
        import uuid
        import datetime
        conn = get_komari_db()
        cur = conn.execute("SELECT uuid FROM clients WHERE token = ? LIMIT 1", (token,))
        row = cur.fetchone()
        now_iso = datetime.datetime.now(datetime.timezone.utc).isoformat()
        if row:
            if name:
                conn.execute("UPDATE clients SET name = ?, updated_at = ? WHERE token = ?", (name, now_iso, token))
        else:
            new_u = str(uuid.uuid4())
            conn.execute("""
                INSERT INTO clients (uuid, token, name, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
            """, (new_u, token, name or "Server", now_iso, now_iso))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[!] sync_client_to_komari error: {e}")
        return False

def delete_komari_client_by_token(token: str) -> bool:
    """从 Komari 探针数据库删除节点"""
    if not token:
        return False
    try:
        conn = get_komari_db()
        conn.execute("DELETE FROM clients WHERE token = ?", (token,))
        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"[!] delete_komari_client error: {e}")
        return False

def sync_all_nodes_to_komari(nodes: list = None) -> int:
    """批量对齐 ProxyProbe node 表与 Komari clients 表"""
    try:
        if nodes is None:
            db_candidates = [
                "/opt/proxyprobe/data/monitor.db",
                "/opt/monitor/data/monitor.db",
                "/opt/proxyprobe/data/proxyprobe.db"
            ]
            for p in db_candidates:
                if os.path.exists(p):
                    try:
                        c = sqlite3.connect(p)
                        chk = c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='node'").fetchone()
                        if chk:
                            cur = c.execute("SELECT id, name, token, ip, ipv4 FROM node")
                            nodes = [dict(zip([col[0] for col in cur.description], r)) for r in cur.fetchall()]
                            c.close()
                            break
                        c.close()
                    except Exception:
                        pass
        if not nodes:
            return 0

        synced = 0
        for n in nodes:
            tok = n.get("token")
            nm = n.get("name")
            if tok and sync_client_to_komari(tok, nm):
                synced += 1
        return synced
    except Exception as e:
        print(f"[!] sync_all_nodes_to_komari error: {e}")
        return 0

# =============================================================================
# 延迟检测 Ping 任务管理模块 (Ping Tasks Management)
# =============================================================================

def get_ping_tasks():
    """获取所有 Komari Ping 延迟检测任务"""
    db_path = get_komari_db_path()
    if not os.path.exists(db_path):
        return []
    try:
        conn = get_komari_db()
        cur = conn.execute("SELECT id, weight, name, clients, all_clients, type, target, interval FROM ping_tasks ORDER BY weight ASC, id DESC")
        rows = cur.fetchall()
        conn.close()
        res = []
        for r in rows:
            clients_val = r[3]
            try:
                clients_list = json.loads(clients_val) if clients_val else []
            except Exception:
                clients_list = [c.strip() for c in str(clients_val).split(",") if c.strip()]
            res.append({
                "id": r[0],
                "weight": r[1],
                "name": r[2],
                "clients": clients_list,
                "all_clients": bool(r[4]),
                "type": r[5] or "icmp",
                "target": r[6],
                "interval": r[7] or 60
            })
        return res
    except Exception as e:
        print(f"[!] get_ping_tasks error: {e}")
        return []

def save_ping_task(data: dict):
    """创建或更新 Ping 延迟检测任务"""
    try:
        task_id = data.get("id")
        weight = int(data.get("weight", 0))
        name = str(data.get("name", "")).strip()
        task_type = str(data.get("type", "icmp")).strip().lower()
        target = str(data.get("target", "")).strip()
        interval = int(data.get("interval", 60))
        all_clients = 1 if data.get("all_clients", True) else 0
        clients = json.dumps(data.get("clients", []))

        if not name or not target:
            return False, "任务名称和测速目标不能为空"

        conn = get_komari_db()
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ping_tasks (
                id integer PRIMARY KEY AUTOINCREMENT,
                weight integer NOT NULL DEFAULT 0,
                name varchar(255) NOT NULL,
                clients longtext,
                all_clients numeric NOT NULL DEFAULT false,
                type varchar(12) NOT NULL DEFAULT "icmp",
                target varchar(255) NOT NULL,
                interval integer NOT NULL DEFAULT 60
            )
        """)
        if task_id:
            conn.execute("""
                UPDATE ping_tasks 
                SET weight = ?, name = ?, clients = ?, all_clients = ?, type = ?, target = ?, interval = ?
                WHERE id = ?
            """, (weight, name, clients, all_clients, task_type, target, interval, task_id))
        else:
            conn.execute("""
                INSERT INTO ping_tasks (weight, name, clients, all_clients, type, target, interval)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (weight, name, clients, all_clients, task_type, target, interval))
        conn.commit()
        conn.close()
        return True, "Ping 延迟检测任务已成功保存"
    except Exception as e:
        return False, f"保存失败: {e}"

def delete_ping_task(task_id: int):
    """删除 Ping 延迟检测任务"""
    try:
        conn = get_komari_db()
        conn.execute("DELETE FROM ping_tasks WHERE id = ?", (task_id,))
        conn.commit()
        conn.close()
        return True, "任务已删除"
    except Exception as e:
        return False, f"删除失败: {e}"

# =============================================================================
# 实时探针遥测与在线状态打通模块 (Telemetry & Real-time Metrics Bridge)
# =============================================================================

def get_komari_clients_telemetry() -> dict:
    """
    通过 Komari 探针核心 RPC 接口与 SQLite 实时拉取所有上报节点的遥测数据，
    返回按 token 索引的实时节点指标字典。
    """
    import urllib.request
    import datetime
    
    result = {}
    try:
        # 1. 查询 komari.db 中的客户端映射 (token <-> uuid)
        conn = get_komari_db()
        cur = conn.execute("SELECT uuid, token, name, ipv4, ipv6, cpu_name, os, kernel_version, arch, mem_total, disk_total FROM clients")
        client_rows = cur.fetchall()
        conn.close()
        
        uuid_to_client = {}
        for r in client_rows:
            uuid_to_client[r[0]] = {
                "uuid": r[0],
                "token": r[1],
                "name": r[2],
                "ipv4": r[3] or "",
                "ipv6": r[4] or "",
                "cpu_name": r[5] or "",
                "os": r[6] or "",
                "kernel": r[7] or "",
                "arch": r[8] or "",
                "mem_total": r[9] or 0,
                "disk_total": r[10] or 0,
            }

        # 2. 调用 Komari 本地 RPC public:getNodesInformation
        nodes_info = []
        try:
            req = urllib.request.Request(
                "http://127.0.0.1:28080/api/rpc2",
                data=json.dumps({"jsonrpc": "2.0", "method": "public:getNodesInformation", "params": {}, "id": 1}).encode("utf-8"),
                headers={"Content-Type": "application/json"}
            )
            with urllib.request.urlopen(req, timeout=2) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                nodes_info = data.get("result", [])
        except Exception:
            pass

        now_dt = datetime.datetime.now(datetime.timezone.utc)
        now_ts = int(time.time())

        # 3. 对每个节点获取最新一条实时 metrics
        for n in nodes_info:
            u = n.get("uuid")
            c_meta = uuid_to_client.get(u, {})
            token = c_meta.get("token") or n.get("token")
            if not token:
                continue

            # 获取 recent records
            recent = []
            try:
                rec_req = urllib.request.Request(
                    "http://127.0.0.1:28080/api/rpc2",
                    data=json.dumps({"jsonrpc": "2.0", "method": "public:getClientRecentRecords", "params": {"uuid": u}, "id": 1}).encode("utf-8"),
                    headers={"Content-Type": "application/json"}
                )
                with urllib.request.urlopen(rec_req, timeout=2) as resp:
                    r_data = json.loads(resp.read().decode("utf-8"))
                    recent = r_data.get("result", [])
            except Exception:
                pass

            is_online = False
            last_seen_ts = 0
            metrics_obj = None

            if recent and len(recent) > 0:
                rec = recent[-1]
                up_str = rec.get("updated_at") or n.get("updated_at")
                if up_str:
                    try:
                        up_dt = datetime.datetime.fromisoformat(str(up_str).replace("Z", "+00:00"))
                        diff = (now_dt - up_dt).total_seconds()
                        last_seen_ts = int(now_ts - diff)
                        # Komari-agent 默认 1 秒或 5 秒推送，如果在 30 秒内有上报即为强实时在线
                        if diff < 30:
                            is_online = True
                    except Exception:
                        pass

                cpu_info = rec.get("cpu", {})
                ram_info = rec.get("ram", {})
                disk_info = rec.get("disk", {})
                load_info = rec.get("load", {})
                swap_info = rec.get("swap", {})
                net_info = rec.get("network", {})
                conn_info = rec.get("connections", {})

                mem_tot = ram_info.get("total") or n.get("mem_total") or c_meta.get("mem_total") or 0
                disk_tot = disk_info.get("total") or n.get("disk_total") or c_meta.get("disk_total") or 0

                metrics_obj = {
                    "cpu": round(cpu_info.get("usage", 0.0), 1),
                    "load": [load_info.get("load1", 0.0), load_info.get("load5", 0.0), load_info.get("load15", 0.0)],
                    "mem_total": mem_tot,
                    "mem_used": ram_info.get("used", 0),
                    "swap_total": swap_info.get("total", 0),
                    "swap_used": swap_info.get("used", 0),
                    "disk_total": disk_tot,
                    "disk_used": disk_info.get("used", 0),
                    "uptime": rec.get("uptime", 0),
                    "net_rx": net_info.get("down", 0),
                    "net_tx": net_info.get("up", 0),
                    "total_rx": net_info.get("totalDown", 0),
                    "total_tx": net_info.get("totalUp", 0),
                    "month_rx": 0,
                    "month_tx": 0,
                    "tcp": conn_info.get("tcp", 0),
                    "udp": conn_info.get("udp", 0),
                    "procs": rec.get("process", 0)
                }

            result[token] = {
                "uuid": u,
                "online": is_online,
                "last_seen": last_seen_ts,
                "os": n.get("os") or c_meta.get("os") or "",
                "kernel": n.get("kernel_version") or c_meta.get("kernel") or "",
                "arch": n.get("arch") or c_meta.get("arch") or "",
                "cpu_name": n.get("cpu_name") or c_meta.get("cpu_name") or "",
                "cpu_cores": n.get("cpu_cores") or 1,
                "mem_total": n.get("mem_total") or c_meta.get("mem_total") or 0,
                "disk_total": n.get("disk_total") or c_meta.get("disk_total") or 0,
                "ipv4": c_meta.get("ipv4") or "",
                "ipv6": c_meta.get("ipv6") or "",
                "region": n.get("region") or "",
                "metrics": metrics_obj
            }

        return result
    except Exception as e:
        print(f"[!] get_komari_clients_telemetry error: {e}")
        return result

# =============================================================================
# 主题与外观管理模块 (Themes Management & Market & Import)
# =============================================================================

THEMES_DIR = "/opt/proxyprobe/data/themes"

# 精选官方与社区主题市场列表
COMMUNITY_THEMES_MARKET = [
    {
        "id": "mochi",
        "name": "Mochi (抹茶日系极简)",
        "author": "Akizon77",
        "version": "v1.2.0",
        "description": "极简日系轻奢卡片流，精美水墨动效与响应式布局，支持多维度图表",
        "preview_url": "https://raw.githubusercontent.com/komari-monitor/theme-market/master/previews/mochi.jpg",
        "download_url": "https://github.com/komari-monitor/theme-market/releases/download/v1.0.0/theme-mochi.zip"
    },
    {
        "id": "naive",
        "name": "Komari Naive (清爽运维看板)",
        "author": "NaiveUI Dev",
        "version": "v1.0.5",
        "description": "基于 Vue 3 + Naive UI 的高对比度清爽监控面板，支持全屏 NOC 运维大屏",
        "preview_url": "https://raw.githubusercontent.com/komari-monitor/theme-market/master/previews/naive.jpg",
        "download_url": "https://github.com/komari-monitor/theme-market/releases/download/v1.0.0/theme-naive.zip"
    },
    {
        "id": "tasogare",
        "name": "Tasogare (黄昏二次元毛玻璃)",
        "author": "Tasogare Team",
        "version": "v2.0.1",
        "description": "二次元动漫黄昏毛玻璃主题，支持自定义动态壁纸、光斑滤镜与粒子特效",
        "preview_url": "https://raw.githubusercontent.com/komari-monitor/theme-market/master/previews/tasogare.jpg",
        "download_url": "https://github.com/komari-monitor/theme-market/releases/download/v1.0.0/theme-tasogare.zip"
    },
    {
        "id": "leonet",
        "name": "LeonetLab (天文台 3D 全景)",
        "author": "LeonetLab",
        "version": "v1.1.2",
        "description": "全球节点 3D 旋转地球仪与深空星轨大屏，适合多国家分布式节点监控",
        "preview_url": "https://raw.githubusercontent.com/komari-monitor/theme-market/master/previews/leonet.jpg",
        "download_url": "https://github.com/komari-monitor/theme-market/releases/download/v1.0.0/theme-leonet.zip"
    },
    {
        "id": "adhesive-note",
        "name": "Adhesive Note (彩色便利贴)",
        "author": "Memo Studio",
        "version": "v1.0.3",
        "description": "创意便签贴纸风格，色彩丰富自由拖拽，适合展示多服务器负载轻重",
        "preview_url": "https://raw.githubusercontent.com/komari-monitor/theme-market/master/previews/note.jpg",
        "download_url": "https://github.com/komari-monitor/theme-market/releases/download/v1.0.0/theme-note.zip"
    }
]

def get_themes_config():
    """获取当前主题、已安装主题列表以及市场精选"""
    try:
        settings = get_probe_settings()
        curr_theme = settings.get("theme", "default")
        
        # 扫描已安装主题目录
        installed = [
            {"id": "default", "name": "官方默认 (Default)", "description": "现代化极简卡片流，信息层级分明", "builtin": True},
            {"id": "classic", "name": "经典复古 (Classic)", "description": "紧凑型表格与多服务器实时曲线", "builtin": True},
            {"id": "minimal", "name": "极致紧凑 (Minimal)", "description": "轻量快速无干扰，适配低性能终端", "builtin": True}
        ]

        if os.path.exists(THEMES_DIR):
            for entry in os.listdir(THEMES_DIR):
                theme_path = os.path.join(THEMES_DIR, entry)
                if os.path.isdir(theme_path) and entry not in ["default", "classic", "minimal"]:
                    info_file = os.path.join(theme_path, "komari-theme.json")
                    theme_info = {
                        "id": entry,
                        "name": entry.capitalize(),
                        "description": "自定义导入主题",
                        "builtin": False,
                        "path": theme_path
                    }
                    if os.path.exists(info_file):
                        try:
                            with open(info_file, "r", encoding="utf-8") as f:
                                meta = json.load(f)
                                theme_info["name"] = meta.get("name", entry)
                                theme_info["description"] = meta.get("description", "自定义导入主题")
                                theme_info["version"] = meta.get("version", "")
                                theme_info["author"] = meta.get("author", "")
                        except Exception:
                            pass
                    installed.append(theme_info)

        return {
            "current_theme": curr_theme,
            "themes": installed,
            "market": COMMUNITY_THEMES_MARKET
        }
    except Exception as e:
        print(f"[!] get_themes_config error: {e}")
        return {"current_theme": "default", "themes": [], "market": COMMUNITY_THEMES_MARKET}

def import_theme_from_zip(zip_data: bytes, filename: str = "theme.zip"):
    """解压上传的主题包 (.zip / .tar.gz) 至 themes 目录"""
    import zipfile
    import tarfile
    import io

    try:
        os.makedirs(THEMES_DIR, exist_ok=True)
        # 确定主题目录名
        base_name = os.path.splitext(filename)[0]
        if base_name.endswith(".tar"):
            base_name = os.path.splitext(base_name)[0]
        # 过滤非法字符
        safe_id = "".join(c for c in base_name if c.isalnum() or c in "-_").strip().lower() or "custom-theme"
        target_dir = os.path.join(THEMES_DIR, safe_id)
        os.makedirs(target_dir, exist_ok=True)

        # 解压
        if filename.endswith(".zip") or zipfile.is_zipfile(io.BytesIO(zip_data)):
            with zipfile.ZipFile(io.BytesIO(zip_data)) as zf:
                # 检查是否存在顶层单目录包裹
                names = zf.namelist()
                has_sub = all("/" in n for n in names if not n.endswith("/"))
                zf.extractall(target_dir)
        elif filename.endswith((".tar.gz", ".tgz", ".tar")):
            with tarfile.open(fileobj=io.BytesIO(zip_data)) as tf:
                tf.extractall(target_dir)
        else:
            return False, "不支持的主题文件格式，请上传 .zip 或 .tar.gz 压缩包"

        # 如果解压后内部嵌套了一层同名子目录，做平铺规范化
        subdirs = [os.path.join(target_dir, d) for d in os.listdir(target_dir) if os.path.isdir(os.path.join(target_dir, d))]
        if len(subdirs) == 1 and not any(os.path.isfile(os.path.join(target_dir, f)) for f in os.listdir(target_dir)):
            nested = subdirs[0]
            for item in os.listdir(nested):
                import shutil
                shutil.move(os.path.join(nested, item), target_dir)
            os.rmdir(nested)

        return True, safe_id
    except Exception as e:
        return False, f"主题解压安装失败: {e}"

def import_theme_from_url(url: str, custom_id: str = None):
    """从网络直接下载并安装主题包"""
    import urllib.request
    try:
        url = url.strip()
        if not url.startswith("http://") and not url.startswith("https://"):
            return False, "请输入合法的 HTTP/HTTPS 下载链接"

        filename = os.path.basename(url.split("?")[0]) or "theme.zip"
        if custom_id:
            filename = f"{custom_id}.zip"

        req = urllib.request.Request(url, headers={"User-Agent": "ProxyProbe-ThemeInstaller/2.5"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read()

        ok, msg = import_theme_from_zip(data, filename)
        if ok:
            return True, f"主题安装成功: {msg}"
        return False, msg
    except Exception as e:
        return False, f"下载主题失败: {e}"

def delete_theme(theme_id: str):
    """删除已安装的主题"""
    import shutil
    try:
        if theme_id in ["default", "classic", "minimal"]:
            return False, "系统内建默认主题不可删除"
        theme_path = os.path.join(THEMES_DIR, theme_id)
        if os.path.exists(theme_path):
            shutil.rmtree(theme_path)
            # 如果当前应用的是被删除主题，重置回 default
            settings = get_probe_settings()
            if settings.get("theme") == theme_id:
                update_probe_settings({"theme": "default"})
            return True, "主题已成功删除"
        return False, "未找到该主题"
    except Exception as e:
        return False, f"删除主题失败: {e}"

def save_theme_config(theme_name: str, config_data: dict = None):
    """切换或保存主题配置"""
    try:
        if theme_name:
            update_probe_settings({"theme": theme_name})
        if config_data and theme_name:
            conn = get_komari_db()
            conn.execute("CREATE TABLE IF NOT EXISTS theme_configurations (short text NOT NULL PRIMARY KEY, data longtext)")
            data_str = json.dumps(config_data, ensure_ascii=False)
            conn.execute("INSERT OR REPLACE INTO theme_configurations (short, data) VALUES (?, ?)", (theme_name, data_str))
            conn.commit()
            conn.close()
        return True, "主题配置已更新"
    except Exception as e:
        return False, f"保存主题失败: {e}"



