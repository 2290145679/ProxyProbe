# -*- coding: utf-8 -*-
"""
ProxyProbe Telegram 机器人与运维告警中枢 (Telegram Engine)
支持功能:
- TG 双向交互式控制台指令 (/status, /test, /backup, /nodes, /help)
- 定时全库异地备份压缩推送
- 节点离线 (>75s) 与恢复实时报警推送
- 纳管服务器到期前 N 天续费提醒
"""

import os
import json
import time
import uuid
import gzip
import sqlite3
import urllib.request
import urllib.parse
import urllib.error
import tempfile
import datetime

_ENV_GET_DB = None
_ENV_GET_SETTING = None
_ENV_SET_SETTING = None
_ENV_GEN_BACKUP_GZ = None
_ENV_CHECK_NODES_HEALTH = None

def init_telegram_context(get_db_fn=None, get_setting_fn=None, set_setting_fn=None, gen_backup_gz_fn=None, check_nodes_health_fn=None):
    global _ENV_GET_DB, _ENV_GET_SETTING, _ENV_SET_SETTING, _ENV_GEN_BACKUP_GZ, _ENV_CHECK_NODES_HEALTH
    if get_db_fn: _ENV_GET_DB = get_db_fn
    if get_setting_fn: _ENV_GET_SETTING = get_setting_fn
    if set_setting_fn: _ENV_SET_SETTING = set_setting_fn
    if gen_backup_gz_fn: _ENV_GEN_BACKUP_GZ = gen_backup_gz_fn
    if check_nodes_health_fn: _ENV_CHECK_NODES_HEALTH = check_nodes_health_fn

def get_db():
    if _ENV_GET_DB:
        return _ENV_GET_DB()
    conn = sqlite3.connect("/opt/proxyprobe/data/monitor.db")
    conn.row_factory = sqlite3.Row
    return conn

def get_setting(key, default=""):
    if _ENV_GET_SETTING:
        return _ENV_GET_SETTING(key, default)
    try:
        conn = get_db()
        row = conn.execute("SELECT val FROM proxy_settings WHERE key = ?", (key,)).fetchone()
        conn.close()
        if row and row["val"] is not None:
            return row["val"]
    except Exception:
        pass
    return default

def set_setting(key, val):
    if _ENV_SET_SETTING:
        return _ENV_SET_SETTING(key, val)
    try:
        conn = get_db()
        with conn:
            conn.execute("INSERT INTO proxy_settings (key, val) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET val = excluded.val", (key, str(val)))
        conn.close()
    except Exception:
        pass

def generate_backup_gz():
    if _ENV_GEN_BACKUP_GZ:
        return _ENV_GEN_BACKUP_GZ()
    return b"", 0, 0

def check_all_nodes_health_parallel():
    if _ENV_CHECK_NODES_HEALTH:
        return _ENV_CHECK_NODES_HEALTH()
    return []

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
    tier_count = 0
    anno_count = 0
    app_count = 0
    try:
        conn = get_db()
        cur = conn.execute("SELECT COUNT(*) FROM node")
        server_count = cur.fetchone()[0]
        cur = conn.execute("SELECT COUNT(*) FROM proxy_node")
        node_count = cur.fetchone()[0]
        cur = conn.execute("SELECT COUNT(*) FROM proxy_user")
        user_count = cur.fetchone()[0]
        try:
            tier_count = conn.execute("SELECT COUNT(*) FROM proxy_tier").fetchone()[0]
            anno_count = conn.execute("SELECT COUNT(*) FROM proxy_announcement").fetchone()[0]
            app_count = conn.execute("SELECT COUNT(*) FROM proxy_app_download").fetchone()[0]
        except Exception:
            pass
        conn.close()
    except Exception:
        pass

    site_name = get_setting("site_name", "ProxyProbe")
    ts_now = int(time.time())
    time_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(ts_now))
    file_time_str = time.strftime("%Y%m%d_%H%M%S", time.localtime(ts_now))
    filename = f"monitor_backup_{file_time_str}.db.gz"

    caption = (
        f"📦 ProxyProbe 数据库自动备份快照\n"
        f"━━━━━━━━━━━━━━━━━━━━\n"
        f"🌐 站点: {site_name}\n"
        f"📅 时间: {time_str}\n"
        f"💾 大小: {gz_size / 1024:.1f} KB (原始: {raw_size / 1024:.1f} KB)\n"
        f"📊 资产: {server_count} 台服务器 · {node_count} 个节点 · {user_count} 位用户\n"
        f"🏷 扩展: {tier_count} 个VIP套餐 · {anno_count} 条系统公告 · {app_count} 款下载软件\n"
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

def check_server_expirations(force=False):
    """
    检查所有纳管服务器的到期时间并在到期前 N 天向 Telegram 推送续费提醒
    """
    enabled = get_setting("server_expire_remind_enabled", "1") == "1"
    if not enabled and not force:
        return False, "服务器到期提醒功能未启用"

    token = get_setting("notify_telegram_token", "").strip()
    chat_id = (get_setting("backup_tg_chat", "") or get_setting("notify_telegram_chat", "")).strip()
    if not token or not chat_id:
        return False, "尚未配置 Telegram Bot Token 或 Chat ID"

    try:
        remind_days = int(get_setting("server_expire_remind_days", "7"))
    except ValueError:
        remind_days = 7

    today_str = time.strftime("%Y-%m-%d")
    last_check_date = get_setting("server_expire_last_notify_date", "")
    if not force and last_check_date == today_str:
        return True, "今日已发送过到期提醒"

    conn = get_db()
    cur = conn.execute("SELECT id, name, ip, ipv4, expires_at FROM node WHERE expires_at IS NOT NULL AND expires_at != ''")
    servers = [dict(r) for r in cur.fetchall()]
    conn.close()

    expiring_servers = []
    now = int(time.time())

    for s in servers:
        exp_raw = str(s.get("expires_at") or "").strip()
        if not exp_raw:
            continue
        exp_ts = 0
        try:
            if len(exp_raw) == 10 and exp_raw.count("-") == 2:
                import datetime
                p = [int(x) for x in exp_raw.split("-")]
                dt = datetime.datetime(p[0], p[1], p[2], 23, 59, 59)
                exp_ts = int(dt.timestamp())
            elif exp_raw.isdigit():
                exp_ts = int(exp_raw)
        except Exception:
            continue

        if exp_ts > 0:
            diff_sec = exp_ts - now
            days_left = int(diff_sec / 86400)
            if days_left <= remind_days:
                s["days_left"] = days_left
                expiring_servers.append(s)

    if not expiring_servers:
        if force:
            return True, f"检测完成：当前没有在 {remind_days} 天内即将到期的服务器"
        return True, "无到期服务器"

    # 构造通知消息
    site_name = get_setting("site_name", "HHUB-加速中心")
    msg_lines = [
        f"🚨 <b>【{site_name} 服务器到期续费提醒】</b>",
        f"<i>系统检测到有 {len(expiring_servers)} 台探针服务器即将到期或已到期，请尽快前往对应服务商续费，防止服务中断！</i>\n"
    ]
    for s in expiring_servers:
        dl = s["days_left"]
        status_tag = f"⚠️ <b>仅剩 {dl} 天</b>" if dl > 0 else (f"🚨 <b>今天到期！</b>" if dl == 0 else f"❌ <b>已逾期 {abs(dl)} 天！</b>")
        host = s.get("ipv4") or s.get("ip") or "未知IP"
        msg_lines.append(f"• <b>{s['name']}</b> ({host})\n   📅 到期时间: <code>{s['expires_at']}</code> | 状态: {status_tag}")

    msg_lines.append(f"\n💡 <i>提醒规则：提前 {remind_days} 天预警 | 发送时间: {time.strftime('%Y-%m-%d %H:%M:%S')}</i>")
    text_content = "\n".join(msg_lines)

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = json.dumps({
        "chat_id": chat_id,
        "text": text_content,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json", "User-Agent": "ProxyProbe-ServerExpiry/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            set_setting("server_expire_last_notify_date", today_str)
            return True, f"成功推送 {len(expiring_servers)} 台服务器到期提醒至 Telegram"
    except Exception as e:
        return False, f"Telegram 发送异常: {e}"

def server_expiry_check_loop():
    while True:
        try:
            time.sleep(300)
            check_server_expirations(force=False)
        except Exception:
            pass





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



def telegram_bot_command_loop():
    """Telegram Bot 双向交互式运维指令处理器 (长轮询 getUpdates)"""
    time.sleep(10)
    last_update_id = 0
    while True:
        try:
            token = get_setting("notify_telegram_token", "").strip()
            admin_chat_id = (get_setting("notify_telegram_chat", "") or get_setting("backup_tg_chat", "")).strip()
            if not token or not admin_chat_id:
                time.sleep(30)
                continue

            url = f"https://api.telegram.org/bot{token}/getUpdates"
            params = {"timeout": 20, "offset": last_update_id + 1}
            req = urllib.request.Request(
                f"{url}?{urllib.parse.urlencode(params)}",
                headers={"User-Agent": "ProxyProbe-Bot/2.5"}
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            
            if not data.get("ok"):
                time.sleep(10)
                continue

            updates = data.get("result", [])
            for upd in updates:
                uid = upd.get("update_id", 0)
                if uid > last_update_id:
                    last_update_id = uid

                msg = upd.get("message") or upd.get("edited_message")
                if not msg:
                    continue

                chat = msg.get("chat", {})
                chat_id = str(chat.get("id", ""))
                text = (msg.get("text") or "").strip()
                if not text:
                    continue

                # 鉴权：严格校验发送者必须是后台配置的管理员 Chat ID
                if str(chat_id) != str(admin_chat_id):
                    continue

                # 指令路由解析
                cmd = text.split()[0].lower()
                if cmd in ("/start", "/help", "帮助", "menu"):
                    reply = (
                        "🤖 <b>ProxyProbe 智能运维机器人已就绪</b>\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        "💡 <b>支持的交互式运维指令：</b>\n"
                        "• <code>/status</code> 或 <code>状态</code> - 全网大盘与服务器概览\n"
                        "• <code>/test</code> 或 <code>测试</code> - 触发全节点真实握手巡检\n"
                        "• <code>/backup</code> 或 <code>备份</code> - 立即备份数据库并发回文件\n"
                        "• <code>/nodes</code> 或 <code>节点</code> - 查看当前所有节点延迟\n"
                        "• <code>/help</code> 或 <code>帮助</code> - 查看本指令菜单\n"
                        "━━━━━━━━━━━━━━━━━━━━\n"
                        "🔒 <i>管理员权限已验证，随时听候调度。</i>"
                    )
                    send_telegram_msg(token, chat_id, reply)

                elif cmd in ("/status", "状态", "/info"):
                    conn = get_db()
                    cur_srv = conn.execute("SELECT COUNT(*) FROM node")
                    total_srv = cur_srv.fetchone()[0]
                    cur_online_srv = conn.execute("SELECT COUNT(*) FROM node WHERE last_seen > ?", (int(time.time()) - 75,))
                    online_srv = cur_online_srv.fetchone()[0]
                    cur_node = conn.execute("SELECT COUNT(*), SUM(upload_bytes), SUM(download_bytes) FROM proxy_node WHERE enabled = 1")
                    row_node = cur_node.fetchone()
                    total_nodes = row_node[0] or 0
                    total_up = row_node[1] or 0
                    total_down = row_node[2] or 0
                    cur_healthy = conn.execute("SELECT COUNT(*) FROM proxy_node WHERE enabled = 1 AND last_check_status = 'ok'")
                    healthy_nodes = cur_healthy.fetchone()[0]
                    cur_users = conn.execute("SELECT COUNT(*) FROM proxy_user WHERE enabled = 1")
                    active_users = cur_users.fetchone()[0]
                    conn.close()

                    def fmt(b):
                        if b >= 1073741824: return f"{b/1073741824:.2f} GB"
                        if b >= 1048576: return f"{b/1048576:.2f} MB"
                        return f"{b/1024:.1f} KB"

                    health_rate = (healthy_nodes / total_nodes * 100) if total_nodes > 0 else 100
                    now_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
                    reply = (
                        f"📊 <b>[ProxyProbe 实时全网大盘]</b>\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"🖥️ <b>服务器在线:</b> <code>{online_srv} / {total_srv}</code> 台\n"
                        f"🌐 <b>节点连通率:</b> <code>{healthy_nodes} / {total_nodes}</code> ({health_rate:.1f}%)\n"
                        f"👥 <b>有效用户数:</b> <code>{active_users}</code> 人\n"
                        f"📈 <b>全网总上行:</b> <code>{fmt(total_up)}</code>\n"
                        f"📉 <b>全网总下行:</b> <code>{fmt(total_down)}</code>\n"
                        f"📦 <b>总消耗吞吐:</b> <code>{fmt(total_up + total_down)}</code>\n"
                        f"📅 <b>报送时间:</b> {now_str}\n"
                        f"━━━━━━━━━━━━━━━━━━━━\n"
                        f"💡 <i>发送 <code>/test</code> 可立即复测所有节点连通性</i>"
                    )
                    send_telegram_msg(token, chat_id, reply)

                elif cmd in ("/test", "测试", "/check"):
                    send_telegram_msg(token, chat_id, "⚡ <b>正在对全网代理节点发起端到端真实握手巡检，请稍候...</b>")
                    results = check_all_nodes_health_parallel()
                    passed = [r for r in results if r["ok"]]
                    failed = [r for r in results if not r["ok"]]
                    avg_lat = int(sum(r["latency_ms"] for r in passed) / len(passed)) if passed else 0
                    
                    rep_lines = [
                        f"🏁 <b>[全网巡检完成] 连通率: {len(passed)}/{len(results)} (均延: {avg_lat}ms)</b>",
                        "━━━━━━━━━━━━━━━━━━━━"
                    ]
                    if failed:
                        rep_lines.append("🔴 <b>异常节点列表:</b>")
                        for f in failed:
                            rep_lines.append(f"• <b>{f['name']}</b> ({f['protocol']}:{f['port']}) ➜ <i>{f['error']}</i>")
                        rep_lines.append("")
                    if passed:
                        rep_lines.append("🟢 <b>正常节点排布 (RTT):</b>")
                        for p in passed[:10]:
                            rep_lines.append(f"• {p['name']} ➜ <code>{p['latency_ms']} ms</code>")
                        if len(passed) > 10:
                            rep_lines.append(f"• <i>...等其余 {len(passed) - 10} 个节点均正常</i>")
                    rep_lines.append("━━━━━━━━━━━━━━━━━━━━")
                    send_telegram_msg(token, chat_id, "\n".join(rep_lines))

                elif cmd in ("/backup", "备份"):
                    send_telegram_msg(token, chat_id, "📦 <b>正在打包当前 SQLite 核心数据库快照并上传...</b>")
                    try:
                        ok, msg, sz = perform_telegram_backup(custom_chat_id=chat_id)
                        if not ok:
                            send_telegram_msg(token, chat_id, f"❌ 备份执行失败: {msg}")
                    except Exception as e:
                        send_telegram_msg(token, chat_id, f"❌ 备份异常: {str(e)}")

                elif cmd in ("/nodes", "节点"):
                    conn = get_db()
                    cur = conn.execute("SELECT name, protocol, port, server_name, last_check_status, last_check_latency FROM proxy_node WHERE enabled = 1")
                    rows = cur.fetchall()
                    conn.close()
                    if not rows:
                        send_telegram_msg(token, chat_id, "暂无活跃代理节点。")
                    else:
                        lines = ["📋 <b>全网活跃节点清单与感知状态:</b>", "━━━━━━━━━━━━━━━━━━━━"]
                        for r in rows:
                            st_icon = "🟢" if r[4] == "ok" else ("🔴" if r[4] == "fail" else "⚪")
                            lat = f"<code>{r[5]}ms</code>" if r[4] == "ok" else "异常/未测"
                            lines.append(f"{st_icon} <b>{r[0]}</b> [{r[1]}] 端口:<code>{r[2]}</code> ({r[3]}) ➜ {lat}")
                        lines.append("━━━━━━━━━━━━━━━━━━━━")
                        send_telegram_msg(token, chat_id, "\n".join(lines))

        except Exception:
            time.sleep(5)

