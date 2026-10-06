# -*- coding: utf-8 -*-
"""
ProxyProbe 用户在线状态感知与并发设备限额控制引擎 (User Engine)
核心功能:
- 180 秒滑动窗口多协议在线设备感知与 IP 去重 (_user_active_ips)
- 用户并发设备数上限自动熔断封禁 (is_user_over_device_limit)
- Linux TC (Traffic Control) HTB 端口/IP 级别实时限速 (TCManager)
- 周期性流量统计与配额轮询收集 (traffic_collector_loop)
"""

import os
import re
import time
import json
import sqlite3
import subprocess
import socket
import struct
import urllib.request

XRAY_BIN = "/usr/local/bin/xray"
SINGBOX_BIN = "/usr/local/bin/sing-box"

_ENV_GET_DB = None
_ENV_APPLY_ALL_CONFIGS = None

def init_user_context(get_db_fn=None, apply_all_configs_fn=None):
    global _ENV_GET_DB, _ENV_APPLY_ALL_CONFIGS
    if get_db_fn: _ENV_GET_DB = get_db_fn
    if apply_all_configs_fn: _ENV_APPLY_ALL_CONFIGS = apply_all_configs_fn

def get_db():
    if _ENV_GET_DB:
        return _ENV_GET_DB()
    conn = sqlite3.connect("/opt/proxyprobe/data/monitor.db")
    conn.row_factory = sqlite3.Row
    return conn

def apply_all_configs():
    if _ENV_APPLY_ALL_CONFIGS:
        return _ENV_APPLY_ALL_CONFIGS()
    return True, "No-op"

_user_active_ips = {}  # { user_id: { ip_str: last_seen_epoch } }
_user_last_seen = {}   # { user_id: last_seen_epoch }
_sb_ip_to_user = {}    # { ip_str: user_id }
_sb_ipport_to_user = {} # { "ip:port": user_id }
_sb_ip_to_node = {}    # { ip_str: node_id }
_sb_ipport_to_node = {} # { "ip:port": node_id }
_sb_pending_sessions = {} # { conn_id: { "ip": ..., "port": ..., "nid": ..., "uid": ..., "time": ... } }
_last_active_sb_user = 1
_last_active_sb_node = None
_last_xray_log_offset = 0
_last_singbox_log_offset = 0

def format_time_ago(ts, now=None):
    if not ts or ts <= 0:
        return "从未在线"
    if now is None:
        now = int(time.time())
    diff = max(0, now - int(ts))
    if diff < 60:
        return "刚刚"
    elif diff < 3600:
        return f"{diff // 60} 分钟前"
    elif diff < 86400:
        return f"{diff // 3600} 小时前"
    elif diff < 86400 * 30:
        return f"{diff // 86400} 天前"
    else:
        return f"{diff // (86400 * 30)} 个月前"

def update_device_tracker():
    global _user_active_ips, _user_last_seen, _sb_ip_to_user, _sb_ipport_to_user, _sb_ip_to_node, _sb_ipport_to_node, _sb_pending_sessions
    global _last_active_sb_user, _last_active_sb_node, _last_xray_log_offset, _last_singbox_log_offset
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
                                _user_last_seen[uid] = now
                                if uid not in _user_active_ips:
                                    _user_active_ips[uid] = {}
                                _user_active_ips[uid][ip] = now
        except Exception:
            pass

    # 2. Parse Sing-box access log if present (correlates session ID to user and node)
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
                    m_cid = re.search(r'\[(\d+)\s+[^\]]+\]', line)
                    m_tag = re.search(r'inbound/\w+\[([^\]]+)\]', line)
                    m_conn_from = re.search(r'inbound connection from ([\d\.:a-fA-F]+):(\d+)', line)
                    m_user = re.search(r'\[(user_\d+|default)\]', line)

                    cid = m_cid.group(1) if m_cid else None
                    inb_tag = m_tag.group(1) if m_tag else ""
                    m_nid = re.search(r'in-(\d+)', inb_tag)
                    nid = int(m_nid.group(1)) if m_nid else None

                    if cid:
                        if m_conn_from:
                            ip = m_conn_from.group(1).strip()
                            port = m_conn_from.group(2).strip()
                            if cid in _sb_pending_sessions and "uid" in _sb_pending_sessions[cid]:
                                uid = _sb_pending_sessions.pop(cid)["uid"]
                                _sb_ip_to_user[ip] = uid
                                _sb_ipport_to_user[f"{ip}:{port}"] = uid
                                _last_active_sb_user = uid
                                if nid:
                                    _last_active_sb_node = nid
                                    _sb_ip_to_node[ip] = nid
                                    _sb_ipport_to_node[f"{ip}:{port}"] = nid
                                if ip not in ("127.0.0.1", "::1"):
                                    _user_last_seen[uid] = now
                                    if uid not in _user_active_ips:
                                        _user_active_ips[uid] = {}
                                    _user_active_ips[uid][ip] = now
                            else:
                                _sb_pending_sessions[cid] = {"ip": ip, "port": port, "nid": nid, "time": now}
                        elif m_user:
                            u_str = m_user.group(1)
                            uid = 1 if u_str == "default" else int(u_str.split("_")[1])
                            if cid in _sb_pending_sessions and "ip" in _sb_pending_sessions[cid]:
                                sess = _sb_pending_sessions.pop(cid)
                                ip = sess["ip"]
                                port = sess["port"]
                                if not nid:
                                    nid = sess.get("nid")
                                _sb_ip_to_user[ip] = uid
                                _sb_ipport_to_user[f"{ip}:{port}"] = uid
                                _last_active_sb_user = uid
                                if nid:
                                    _last_active_sb_node = nid
                                    _sb_ip_to_node[ip] = nid
                                    _sb_ipport_to_node[f"{ip}:{port}"] = nid
                                if ip not in ("127.0.0.1", "::1"):
                                    _user_last_seen[uid] = now
                                    if uid not in _user_active_ips:
                                        _user_active_ips[uid] = {}
                                    _user_active_ips[uid][ip] = now
                            else:
                                _sb_pending_sessions[cid] = {"uid": uid, "nid": nid, "time": now}
                                _last_active_sb_user = uid
                                if nid:
                                    _last_active_sb_node = nid
                    else:
                        m_ip = re.search(r'\[([\d\.:a-fA-F]+):(\d+)\s*->', line)
                        m_u = re.search(r'user:\s*([^\s\)]+)', line)
                        if m_ip and m_u:
                            ip = m_ip.group(1).strip()
                            port = m_ip.group(2).strip()
                            u_str = m_u.group(1).strip()
                            uid = 1 if u_str == "default" else (int(u_str.split("_")[1]) if u_str.startswith("user_") else 1)
                            _sb_ip_to_user[ip] = uid
                            _sb_ipport_to_user[f"{ip}:{port}"] = uid
                            _last_active_sb_user = uid
                            if ip not in ("127.0.0.1", "::1"):
                                _user_last_seen[uid] = now
                                if uid not in _user_active_ips:
                                    _user_active_ips[uid] = {}
                                _user_active_ips[uid][ip] = now

            for c_k in list(_sb_pending_sessions.keys()):
                if now - _sb_pending_sessions[c_k].get("time", now) > 60:
                    _sb_pending_sessions.pop(c_k, None)
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
_last_sb_global_up = 0
_last_sb_global_down = 0
_last_sb_global_initialized = False
_last_sb_conns = {}  # { conn_id: (up, down, user_id, node_id) }
_last_active_sb_user = 1
_last_active_sb_node = None

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
                    m = re.search(r'dev\s+([^\s]+)', res.stdout)
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
        except Exception as e:
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

_tc_manager = None

def sync_traffic_control():
    global _tc_manager, _user_active_ips
    if _tc_manager is None:
        _tc_manager = TCManager()

    try:
        conn = get_db()
        # 1. Fetch local nodes with bandwidth limit > 0
        cur_n = conn.execute("SELECT id, port, bandwidth_limit_mbps FROM proxy_node WHERE enabled = 1 AND is_relay = 0 AND bandwidth_limit_mbps > 0")
        desired_nodes = {}
        for r in cur_n.fetchall():
            nid = int(r["id"])
            port = int(r["port"])
            mbps = int(r["bandwidth_limit_mbps"] or 0)
            if mbps > 0 and port > 0:
                desired_nodes[nid] = { "port": port, "mbps": mbps }

        # 2. Fetch tier speed limits
        cur_t = conn.execute("SELECT tier_key, speed_limit_mbps FROM proxy_tier")
        tier_speed_map = {r[0]: int(r[1] or 0) for r in cur_t.fetchall()}

        # 3. Fetch active users
        cur_u = conn.execute("SELECT id, vip_level, bandwidth_limit_mbps FROM proxy_user WHERE enabled = 1")
        users_rows = cur_u.fetchall()
        conn.close()

        desired_users = {}
        now = int(time.time())
        for r in users_rows:
            uid = int(r["id"])
            custom_mbps = int(r["bandwidth_limit_mbps"] or 0)
            vip = r["vip_level"] or "vip1"
            tier_mbps = tier_speed_map.get(vip, 0)
            eff_mbps = custom_mbps if custom_mbps > 0 else tier_mbps

            if eff_mbps > 0:
                user_ips = _user_active_ips.get(uid, {})
                active_ips = set()
                for ip_str, last_t in user_ips.items():
                    if now - last_t < 180 and ip_str not in ("127.0.0.1", "::1") and not ip_str.startswith("remote_"):
                        active_ips.add(ip_str)
                if active_ips:
                    desired_users[uid] = { "mbps": eff_mbps, "ips": active_ips }

        _tc_manager.sync(desired_nodes, desired_users)
    except Exception:
        pass

def traffic_collector_loop():
    global _last_active_user_ids, _last_sb_global_up, _last_sb_global_down, _last_sb_conns, _last_active_sb_user, _last_active_sb_node
    time.sleep(3)
    try:
        _last_active_user_ids = {u["id"] for u in get_active_users()}
    except Exception:
        pass

    while True:
        try:
            time.sleep(3)
            now = int(time.time())
            # 0. Update device tracker from logs
            update_device_tracker()

            # 0.1 Sync traffic control (per-node and per-user/tier rate limits)
            sync_traffic_control()

            user_traffic = {}
            node_traffic = {}
            tot_up = 0
            tot_down = 0

            # 1. Query Xray StatsService via local API
            if os.path.exists(XRAY_BIN):
                try:
                    res = subprocess.run(
                        [XRAY_BIN, "api", "statsquery", "--server=127.0.0.1:10085", "-reset=true"],
                        capture_output=True, text=True, timeout=5
                    )
                    if res.returncode == 0 and res.stdout:
                        data = json.loads(res.stdout)
                        stats = data.get("stat") or []
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
                                        tot_up += val
                                    elif direction == "downlink":
                                        user_traffic[uid]["down"] += val
                                        tot_down += val
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
                                        node_traffic[nid] = {"up": 0, "down": 0}
                                    if direction == "uplink":
                                        node_traffic[nid]["up"] += val
                                    elif direction == "downlink":
                                        node_traffic[nid]["down"] += val
                except Exception:
                    pass

            # 2. Query Sing-box Clash API for Hysteria 2 / AnyTLS / TUIC
            if os.path.exists(SINGBOX_BIN):
                try:
                    req_sb = urllib.request.Request("http://127.0.0.1:9095/connections")
                    with urllib.request.urlopen(req_sb, timeout=3) as resp_sb:
                        sb_data = json.loads(resp_sb.read().decode("utf-8"))
                        curr_sb_up = int(sb_data.get("uploadTotal", 0))
                        curr_sb_down = int(sb_data.get("downloadTotal", 0))

                        global _last_sb_global_initialized
                        if not _last_sb_global_initialized:
                            _last_sb_global_initialized = True
                            _last_sb_global_up = curr_sb_up
                            _last_sb_global_down = curr_sb_down
                            delta_sb_up = 0
                            delta_sb_down = 0
                        else:
                            if curr_sb_up < _last_sb_global_up or curr_sb_down < _last_sb_global_down:
                                delta_sb_up = curr_sb_up
                                delta_sb_down = curr_sb_down
                                _last_sb_conns.clear()
                            else:
                                delta_sb_up = max(0, curr_sb_up - _last_sb_global_up)
                                delta_sb_down = max(0, curr_sb_down - _last_sb_global_down)
                            _last_sb_global_up = curr_sb_up
                            _last_sb_global_down = curr_sb_down

                        conns = sb_data.get("connections", [])
                        curr_conn_ids = set()
                        sum_active_up = 0
                        sum_active_down = 0

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
                            
                            m_nid = re.search(r'in-(\d+)', inb_type)
                            nid = int(m_nid.group(1)) if m_nid else (_sb_ipport_to_node.get(f"{src_ip}:{src_port}") or _sb_ip_to_node.get(src_ip) or _last_active_sb_node)
                            if nid:
                                _last_active_sb_node = nid

                            uid = _sb_ipport_to_user.get(f"{src_ip}:{src_port}") or _sb_ip_to_user.get(src_ip)
                            if not uid and src_ip:
                                for u_k, ips in _user_active_ips.items():
                                    if src_ip in ips:
                                        uid = u_k
                                        break
                            if not uid:
                                uid = _last_active_sb_user or 1
                            else:
                                _last_active_sb_user = uid

                            prev_up, prev_down, _, _ = _last_sb_conns.get(cid, (0, 0, uid, nid))
                            d_up = max(0, c_up - prev_up)
                            d_down = max(0, c_down - prev_down)
                            _last_sb_conns[cid] = (c_up, c_down, uid, nid)

                            if d_up > 0 or d_down > 0:
                                _user_last_seen[uid] = now
                                sum_active_up += d_up
                                sum_active_down += d_down
                                if uid not in user_traffic:
                                    user_traffic[uid] = {"up": 0, "down": 0}
                                user_traffic[uid]["up"] += d_up
                                user_traffic[uid]["down"] += d_down
                                if nid:
                                    if nid not in node_traffic:
                                        node_traffic[nid] = {"up": 0, "down": 0}
                                    node_traffic[nid]["up"] += d_up
                                    node_traffic[nid]["down"] += d_down

                        for closed_id in set(_last_sb_conns.keys()) - curr_conn_ids:
                            _last_sb_conns.pop(closed_id, None)

                        rem_up = max(0, delta_sb_up - sum_active_up)
                        rem_down = max(0, delta_sb_down - sum_active_down)
                        if rem_up > 0 or rem_down > 0:
                            fallback_uid = _last_active_sb_user or 1
                            _user_last_seen[fallback_uid] = now
                            fallback_nid = _last_active_sb_node
                            if not fallback_nid:
                                try:
                                    conn_sb = get_db()
                                    r_sb = conn_sb.execute("SELECT id FROM proxy_node WHERE protocol IN ('hysteria2', 'anytls', 'tuic') AND enabled = 1 AND is_relay = 0 ORDER BY id ASC LIMIT 1").fetchone()
                                    conn_sb.close()
                                    if r_sb:
                                        fallback_nid = r_sb[0]
                                        _last_active_sb_node = fallback_nid
                                except Exception:
                                    pass
                            if fallback_uid not in user_traffic:
                                user_traffic[fallback_uid] = {"up": 0, "down": 0}
                            user_traffic[fallback_uid]["up"] += rem_up
                            user_traffic[fallback_uid]["down"] += rem_down
                            if fallback_nid:
                                if fallback_nid not in node_traffic:
                                    node_traffic[fallback_nid] = {"up": 0, "down": 0}
                                node_traffic[fallback_nid]["up"] += rem_up
                                node_traffic[fallback_nid]["down"] += rem_down

                        tot_up += delta_sb_up
                        tot_down += delta_sb_down
                except Exception:
                    pass

            if user_traffic or node_traffic:
                conn = get_db()
                with conn:
                    for uid, tf in user_traffic.items():
                        conn.execute("""
                            UPDATE proxy_user
                            SET upload_bytes = upload_bytes + ?, download_bytes = download_bytes + ?, last_active_at = ?
                            WHERE id = ?
                        """, (tf["up"], tf["down"], now, uid))
                    for nid, tf in node_traffic.items():
                        conn.execute("""
                            UPDATE proxy_node
                            SET upload_bytes = upload_bytes + ?, download_bytes = download_bytes + ?
                            WHERE id = ?
                        """, (tf["up"], tf["down"], nid))
                        conn.execute("""
                            UPDATE proxy_node
                            SET upload_bytes = upload_bytes + ?, download_bytes = download_bytes + ?
                            WHERE target_node_id = ?
                        """, (tf["up"], tf["down"], nid))
                    if tot_up > 0 or tot_down > 0:
                        tb = (int(time.time()) // 3600) * 3600
                        conn.execute("""
                            INSERT INTO proxy_traffic_hourly (time_bucket, upload_bytes, download_bytes)
                            VALUES (?, ?, ?)
                            ON CONFLICT(time_bucket) DO UPDATE SET
                                upload_bytes = upload_bytes + excluded.upload_bytes,
                                download_bytes = download_bytes + excluded.download_bytes
                        """, (tb, tot_up, tot_down))
                conn.close()

            # 2. Check if active user set changed (e.g. user reached quota or renewed/restored)
            curr_active_users = get_active_users()
            curr_active_ids = {u["id"] for u in curr_active_users}
            if curr_active_ids != _last_active_user_ids:
                print(f"[*] User active set changed from {_last_active_user_ids} to {curr_active_ids}. Re-applying configs...")
                _last_active_user_ids = curr_active_ids
                apply_all_configs()

        except Exception as e:
            time.sleep(3)

