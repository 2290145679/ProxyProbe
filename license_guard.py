"""
ProxyProbe 商业许可证双轨混合系统 (License Guard)
Copyright (c) 2026 ProxyProbe Contributors
"""

import os
import sys
import json
import time
import base64
import hashlib
import uuid
import sqlite3
import threading
import hmac
import secrets
import urllib.request
import urllib.error

# 内置公钥 (Ed25519 32-byte raw hex)
MASTER_PUBLIC_KEY_HEX = "6637fdfd836e83fd31aa7c02698ab615d882bdb7533aaf2f83359480a1a5a4c3"

# 官方预留固定授权中心域名与多重容灾候选列表 (在线优先，域名解析与备用 IP 双轨保障)
DEFAULT_AUTH_DOMAIN = "auth.yohoo.xyz"
DEFAULT_AUTH_SERVER = os.environ.get("PROXYPROBE_AUTH_SERVER", f"http://{DEFAULT_AUTH_DOMAIN}")
AUTH_SERVER_CANDIDATES = [
    f"http://{DEFAULT_AUTH_DOMAIN}:18888",
    f"http://{DEFAULT_AUTH_DOMAIN}",
    f"https://{DEFAULT_AUTH_DOMAIN}",
    "http://156.226.173.102:18888",
    "http://127.0.0.1:18888"
]

# 80-bit 紧凑自包含防伪短卡密系统参数 (Base32 无歧义大写)
BASE32_CHARS = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
BASE32_MAP = {c: i for i, c in enumerate(BASE32_CHARS)}
SHORT_CODE_SECRET = b"ProxyProbe-SelfContained-License-Key-2026-Secret"

PLAN_INT_MAP = {
    1: "stardust",
    2: "planet",
    3: "star",
    4: "galaxy",
    5: "universe"
}
PLAN_STR_TO_INT = {v: k for k, v in PLAN_INT_MAP.items()}

# 套餐规格标准定义
PLAN_MAP = {
    "free": {"name": "免费体验版", "max_servers": 1, "max_nodes": 1, "max_users": 1},
    "stardust": {"name": "星尘套餐", "max_servers": 3, "max_nodes": 6, "max_users": 6},
    "planet": {"name": "行星套餐", "max_servers": 5, "max_nodes": 12, "max_users": 12},
    "star": {"name": "恒星套餐", "max_servers": 8, "max_nodes": 18, "max_users": 18},
    "galaxy": {"name": "星系套餐", "max_servers": 12, "max_nodes": 30, "max_users": 30},
    "universe": {"name": "宇宙套餐", "max_servers": 20, "max_nodes": 50, "max_users": 50},
}

# 尝试加载 cryptography 库，若无则使用纯 Python Ed25519 校验器
try:
    from cryptography.hazmat.primitives.asymmetric import ed25519
    _HAS_CRYPTOGRAPHY = True
except ImportError:
    _HAS_CRYPTOGRAPHY = False


# =============================================================================
# 纯 Python RFC 8032 Ed25519 验签器 (零外部依赖保底)
# =============================================================================
_q = 2**255 - 19
_l = 2**252 + 27742317777372353535851937790883648493

def _inv(x):
    return pow(x, _q - 2, _q)

_d = -121665 * _inv(121666) % _q
_I = pow(2, (_q - 1) // 4, _q)

def _xrecover(y):
    xx = (y * y - 1) * _inv(_d * y * y + 1)
    x = pow(xx, (_q + 3) // 8, _q)
    if (x * x - xx) % _q != 0:
        x = (x * _I) % _q
    if x % 2 != 0:
        x = _q - x
    return x

_By = 4 * _inv(5) % _q
_Bx = _xrecover(_By)
_B = [_Bx % _q, _By % _q]

def _edwards(P, Q):
    x1, y1 = P[0], P[1]
    x2, y2 = Q[0], Q[1]
    denom_x = (1 + _d * x1 * x2 * y1 * y2) % _q
    denom_y = (1 - _d * x1 * x2 * y1 * y2) % _q
    x3 = (x1 * y2 + x2 * y1) * _inv(denom_x) % _q
    y3 = (y1 * y2 + x1 * x2) * _inv(denom_y) % _q
    return [x3, y3]

def _scalarmult(P, e):
    if e == 0:
        return [0, 1]
    Q = _scalarmult(P, e // 2)
    Q = _edwards(Q, Q)
    if e & 1:
        Q = _edwards(Q, P)
    return Q

def _decodepoint(s):
    clamp = int.from_bytes(s, "little")
    y = clamp & ((1 << 255) - 1)
    x = _xrecover(y)
    if bool(x & 1) != bool((s[31] >> 7) & 1):
        x = _q - x
    return [x, y]

def _pure_python_verify(pubkey_bytes: bytes, sig_bytes: bytes, msg_bytes: bytes) -> bool:
    """纯 Python RFC 8032 签名验证"""
    if len(sig_bytes) != 64 or len(pubkey_bytes) != 32:
        return False
    try:
        Rraw = sig_bytes[:32]
        S = int.from_bytes(sig_bytes[32:], "little")
        if S >= _l:
            return False
        R = _decodepoint(Rraw)
        A = _decodepoint(pubkey_bytes)
        h = hashlib.sha512(Rraw + pubkey_bytes + msg_bytes).digest()
        k = int.from_bytes(h, "little")
        v1 = _scalarmult(_B, S)
        v2 = _edwards(R, _scalarmult(A, k))
        return v1 == v2
    except Exception:
        return False


def verify_ed25519_signature(pubkey_bytes: bytes, sig_bytes: bytes, data_bytes: bytes) -> bool:
    """统一 Ed25519 验签入口"""
    if _HAS_CRYPTOGRAPHY:
        try:
            pub = ed25519.Ed25519PublicKey.from_public_bytes(pubkey_bytes)
            pub.verify(sig_bytes, data_bytes)
            return True
        except Exception:
            return False
    else:
        return _pure_python_verify(pubkey_bytes, sig_bytes, data_bytes)


# =============================================================================
# 机器指纹生成 (Machine ID)
# =============================================================================
def get_machine_id() -> str:
    """
    生成稳定的 Linux/系统硬件指纹，形如 PP-8A3F-9B12-4C67
    """
    raw_pieces = []
    
    # 1. Linux machine-id
    for path in ["/etc/machine-id", "/var/lib/dbus/machine-id"]:
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    content = f.read().strip()
                    if content:
                        raw_pieces.append(f"mid:{content}")
                        break
            except Exception:
                pass

    # 2. DMI UUID
    for dmi in ["/sys/class/dmi/id/product_uuid", "/sys/devices/virtual/dmi/id/product_uuid"]:
        if os.path.exists(dmi):
            try:
                with open(dmi, "r", encoding="utf-8") as f:
                    u = f.read().strip()
                    if u:
                        raw_pieces.append(f"dmi:{u}")
                        break
            except Exception:
                pass

    # 3. 网卡 MAC 地址
    try:
        node = uuid.getnode()
        raw_pieces.append(f"mac:{node:012x}")
    except Exception:
        pass

    # 4. Windows 兼容降级
    if sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography")
            guid, _ = winreg.QueryValueEx(key, "MachineGuid")
            raw_pieces.append(f"wguid:{guid}")
        except Exception:
            pass

    if not raw_pieces:
        raw_pieces.append("default-fallback-id")

    combined = "|".join(raw_pieces)
    digest = hashlib.sha256(f"PP-SALT-MACHINE-2026:{combined}".encode("utf-8")).hexdigest().upper()
    
    # 格式化为 PP-XXXX-XXXX-XXXX
    return f"PP-{digest[0:4]}-{digest[4:8]}-{digest[8:12]}"


# =============================================================================
# 许可证解析与验签
# =============================================================================
def parse_and_verify_license(license_key: str, public_key_hex: str = MASTER_PUBLIC_KEY_HEX) -> dict:
    """
    解析并验证许可证字符串
    格式: PPLIC-<base64_payload>.<base64_signature>
    返回 (payload_dict, error_msg)
    """
    if not license_key or not isinstance(license_key, str):
        return None, "许可证为空"

    license_key = license_key.strip()
    if not license_key.startswith("PPLIC-"):
        return None, "许可证格式错误（必须以 PPLIC- 开头）"

    content = license_key[6:]
    parts = content.split(".")
    if len(parts) != 2:
        return None, "许可证数据结构损坏"

    payload_b64, sig_b64 = parts[0], parts[1]

    try:
        # 兼容 URL-safe base64 与标准 base64
        payload_bytes = base64.urlsafe_b64decode(payload_b64 + "==")
        sig_bytes = base64.urlsafe_b64decode(sig_b64 + "==")
    except Exception:
        return None, "许可证 Base64 解码失败"

    if len(sig_bytes) != 64:
        return None, f"数字签名长度非法 ({len(sig_bytes)} != 64)"

    pubkey_bytes = bytes.fromhex(public_key_hex)
    is_valid = verify_ed25519_signature(pubkey_bytes, sig_bytes, payload_bytes)
    if not is_valid:
        return None, "数字签名校验失败（许可证已被篡改或非官方签发）"

    try:
        payload = json.loads(payload_bytes.decode("utf-8"))
    except Exception:
        return None, "许可证载荷 JSON 解析失败"

    # 校验机器码
    curr_mid = get_machine_id()
    lic_mid = payload.get("machine_id", "").strip().upper()
    if lic_mid != "ANY" and lic_mid != curr_mid:
        return None, f"机器码不匹配（该许可证绑定: {lic_mid}，本机机器码: {curr_mid}）"

    # 校验过期时间
    expire_at = payload.get("expire_at", 0)
    now = int(time.time())
    if expire_at and expire_at > 0:
        if now > expire_at:
            exp_date = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(expire_at))
            return None, f"许可证已过期（到期时间: {exp_date}）"

    return payload, ""


# =============================================================================
# 80-bit 紧凑自包含短卡密编码与解码引擎 (在线优先，离线兜底核心)
# =============================================================================
def encode_short_code(plan_type_int: int, days: int, machine_id_str: str = "ANY") -> str:
    """生成 80-bit 紧凑自包含防伪短卡密: PP-XXXX-XXXX-XXXX-XXXX"""
    ver = 0  # 2 bits
    plan = plan_type_int & 0x7  # 3 bits
    d = days & 0x7FF  # 11 bits (0..2047, 0 = 永久)

    mid_clean = (machine_id_str or "").strip().upper()
    if mid_clean in ("", "ANY"):
        mid_hash = 0xFFFF
    else:
        mid_hash = int(hashlib.md5(mid_clean.encode("utf-8")).hexdigest()[:4], 16)

    nonce = secrets.randbelow(65536)  # 16 bits

    # 48 bits 核心负载数据
    data_int = (ver << 46) | (plan << 43) | (d << 32) | (mid_hash << 16) | nonce
    data_bytes = data_int.to_bytes(6, byteorder="big")

    mac_bytes = hmac.new(SHORT_CODE_SECRET, data_bytes, hashlib.sha256).digest()[:4]
    mac_int = int.from_bytes(mac_bytes, byteorder="big")

    total_int = (data_int << 32) | mac_int

    out = []
    val = total_int
    for _ in range(16):
        out.append(BASE32_CHARS[val & 0x1F])
        val >>= 5
    out.reverse()
    s = "".join(out)
    return f"PP-{s[:4]}-{s[4:8]}-{s[8:12]}-{s[12:16]}"


def decode_short_code(code_str: str, current_mid: str = "") -> tuple:
    """
    解析并离线校验 80-bit 紧凑防伪短卡密
    返回 (dict, err_msg)
    """
    clean_code = code_str.replace("PP-", "").replace("-", "").upper().strip()
    if len(clean_code) != 16 or any(c not in BASE32_MAP for c in clean_code):
        return None, "无效的短卡密格式 (应为 PP-XXXX-XXXX-XXXX-XXXX)"

    val = 0
    for c in clean_code:
        val = (val << 5) | BASE32_MAP[c]

    mac_int = val & 0xFFFFFFFF
    data_int = val >> 32
    data_bytes = data_int.to_bytes(6, byteorder="big")

    expected_mac = int.from_bytes(hmac.new(SHORT_CODE_SECRET, data_bytes, hashlib.sha256).digest()[:4], byteorder="big")
    if mac_int != expected_mac:
        return None, "卡密防伪校验未通过（非法伪造或卡密输入有误）"

    ver = (data_int >> 46) & 0x3
    plan_int = (data_int >> 43) & 0x7
    days = (data_int >> 32) & 0x7FF
    mid_hash = (data_int >> 16) & 0xFFFF

    plan_type = PLAN_INT_MAP.get(plan_int)
    if not plan_type:
        return None, f"未知套餐标识 ({plan_int})"

    if mid_hash != 0xFFFF:
        curr_clean = (current_mid or "").strip().upper()
        curr_hash = int(hashlib.md5(curr_clean.encode("utf-8")).hexdigest()[:4], 16)
        if mid_hash != curr_hash:
            return None, "该卡密已锁定绑定至特定机器，与当前服务器机器码不匹配"

    return {
        "plan_type": plan_type,
        "days": days,
        "bound_any": mid_hash == 0xFFFF
    }, ""


# =============================================================================
# 数据库存储与时钟水印防篡改
# =============================================================================
def init_license_tables(db_conn):
    """确保 setting 表和 license_log 表存在"""
    db_conn.execute("CREATE TABLE IF NOT EXISTS setting (key TEXT PRIMARY KEY, value TEXT)")
    db_conn.execute("""
    CREATE TABLE IF NOT EXISTS license_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp INTEGER,
        action TEXT,
        status TEXT,
        detail TEXT
    )
    """)
    db_conn.commit()


def check_and_update_watermark(db_conn) -> bool:
    """
    时钟水印防倒流防作弊检查
    若检测到当前时间比数据库记录的最新运行时间回退超过 300 秒，判定系统时间被篡改。
    """
    now = int(time.time())
    cur = db_conn.cursor()
    cur.execute("SELECT value FROM setting WHERE key='license_watermark_ts'")
    row = cur.fetchone()
    last_ts = int(row[0]) if row and row[0] and row[0].isdigit() else 0

    if last_ts > 0 and now < (last_ts - 300):
        # 异常时间倒流
        return False

    # 推进水印
    new_ts = max(now, last_ts)
    db_conn.execute("INSERT OR REPLACE INTO setting (key, value) VALUES ('license_watermark_ts', ?)", (str(new_ts),))
    db_conn.commit()
    return True


def get_current_license_status(db_conn) -> dict:
    """
    综合评估当前许可证状态（供 API 与路由守卫调用）
    """
    init_license_tables(db_conn)
    mid = get_machine_id()

    # 1. 时钟防作弊校验
    if not check_and_update_watermark(db_conn):
        return {
            "active": False,
            "type": "tampered",
            "message": "检测到系统时间被异常倒拨，安全防护已锁定！请恢复标准网络时间。",
            "machine_id": mid,
            "days_left": 0
        }

    # 2. 读取存储的 License
    cur = db_conn.cursor()
    cur.execute("SELECT value FROM setting WHERE key='license_key'")
    row = cur.fetchone()
    lic_key = row[0].strip() if row and row[0] else ""

    # 套餐规格标准定义
    PLAN_MAP = {
        "free": {"name": "免费体验版", "max_servers": 1, "max_nodes": 1, "max_users": 1},
        "stardust": {"name": "星尘套餐", "max_servers": 3, "max_nodes": 6, "max_users": 6},
        "planet": {"name": "行星套餐", "max_servers": 5, "max_nodes": 12, "max_users": 12},
        "star": {"name": "恒星套餐", "max_servers": 8, "max_nodes": 18, "max_users": 18},
        "galaxy": {"name": "星系套餐", "max_servers": 12, "max_nodes": 30, "max_users": 30},
        "universe": {"name": "宇宙套餐", "max_servers": 20, "max_nodes": 50, "max_users": 50},
    }

    if not lic_key:
        free_spec = PLAN_MAP["free"]
        return {
            "active": False,
            "type": "free",
            "plan_name": free_spec["name"],
            "max_servers": free_spec["max_servers"],
            "max_nodes": free_spec["max_nodes"],
            "max_users": free_spec["max_users"],
            "message": "当前为免费体验模式（配额：1服务器/1节点/1用户）",
            "machine_id": mid,
            "days_left": 0
        }

    # 3. 检查是否已被在线吊销
    cur.execute("SELECT value FROM setting WHERE key='license_revoked'")
    rev_row = cur.fetchone()
    if rev_row and rev_row[0] == "1":
        return {
            "active": False,
            "type": "revoked",
            "plan_name": "已吊销许可证",
            "max_servers": 0,
            "max_nodes": 0,
            "max_users": 0,
            "message": "此许可证已被中心授权服务器吊销或冻结！所有商业与节点功能已停用。",
            "machine_id": mid,
            "days_left": 0
        }

    # 4. 离线公钥验签 (支持完整非对称凭据或 80-bit 自包含紧凑短卡密)
    payload = None
    err = ""
    now = int(time.time())

    if lic_key.startswith("PP-") and "." not in lic_key:
        # 优先读取在线打卡缓存的 raw_token 非对称凭证
        cur.execute("SELECT value FROM setting WHERE key='license_raw_token'")
        t_row = cur.fetchone()
        cached_token = t_row[0].strip() if t_row and t_row[0] else ""
        if cached_token:
            payload, err = parse_and_verify_license(cached_token)

        # 若无 raw_token 或验证异常，则启用 80-bit 紧凑防伪短码离线解算兜底
        if not payload:
            decoded, dec_err = decode_short_code(lic_key, mid)
            if decoded:
                cur.execute("SELECT value FROM setting WHERE key='license_activated_ts'")
                act_row = cur.fetchone()
                act_ts = int(act_row[0]) if act_row and act_row[0] and act_row[0].isdigit() else now

                days = decoded["days"]
                expire_at = (act_ts + days * 86400) if days > 0 else 0

                if expire_at > 0 and now > expire_at:
                    err = f"短卡密许可证已过期（到期时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(expire_at))}）"
                else:
                    plan_info = PLAN_MAP.get(decoded["plan_type"], PLAN_MAP["planet"])
                    payload = {
                        "id": lic_key,
                        "type": decoded["plan_type"],
                        "customer": "商业授权 (双轨离线模式)",
                        "machine_id": mid,
                        "max_servers": plan_info["max_servers"],
                        "max_nodes": plan_info["max_nodes"],
                        "max_users": plan_info["max_users"],
                        "issued_at": act_ts,
                        "expire_at": expire_at
                    }
                    err = ""
            else:
                err = dec_err or err or "短卡密离线验证失败"
    else:
        payload, err = parse_and_verify_license(lic_key)

    if err or not payload:
        return {
            "active": False,
            "type": "invalid",
            "plan_name": "无效许可证",
            "max_servers": 0,
            "max_nodes": 0,
            "max_users": 0,
            "message": err or "许可证解析异常",
            "machine_id": mid,
            "days_left": 0
        }

    # 5. 计算剩余天数
    expire_at = payload.get("expire_at", 0)
    now = int(time.time())
    if expire_at and expire_at > 0:
        days_left = max(0, int((expire_at - now) / 86400))
        expire_date = time.strftime("%Y-%m-%d", time.localtime(expire_at))
    else:
        days_left = 99999
        expire_date = "永久买断 (Lifetime)"

    # 读取上次在线打卡时间
    cur.execute("SELECT value FROM setting WHERE key='license_last_sync_ts'")
    sync_row = cur.fetchone()
    last_sync = int(sync_row[0]) if sync_row and sync_row[0] and sync_row[0].isdigit() else 0

    plan_type = payload.get("type", "planet")
    plan_info = PLAN_MAP.get(plan_type, {
        "name": "商业定制版",
        "max_servers": payload.get("max_servers", 5),
        "max_nodes": payload.get("max_nodes", 12),
        "max_users": payload.get("max_users", 12)
    })

    # 优先使用签发时注入的硬配额，若无则使用标准套餐配额
    max_servers = payload.get("max_servers") or plan_info["max_servers"]
    max_nodes = payload.get("max_nodes") or plan_info["max_nodes"]
    max_users = payload.get("max_users") or plan_info["max_users"]

    return {
        "active": True,
        "type": plan_type,
        "plan_name": plan_info["name"],
        "customer": payload.get("customer", "商业授权"),
        "license_id": lic_key if (lic_key.startswith("PP-") and "." not in lic_key) else payload.get("id", lic_key),
        "max_servers": max_servers,
        "max_nodes": max_nodes,
        "max_users": max_users,
        "expire_at": expire_at,
        "expire_date": expire_date,
        "days_left": days_left,
        "machine_id": mid,
        "last_sync": last_sync,
        "message": f"商业许可证有效（{plan_info['name']}：{max_servers}服/{max_nodes}节/{max_users}户）"
    }


def save_license_key(db_conn, license_key: str, auth_url: str = DEFAULT_AUTH_SERVER) -> tuple:
    """
    保存并激活许可证 (支持 23 位专属短激活码与离线完整非对称凭据)
    返回 (success: bool, msg: str, status_dict)
    """
    init_license_tables(db_conn)
    license_key = license_key.strip()
    if not license_key:
        return False, "许可证密钥不能为空", None

    now = int(time.time())

    # 1. 23 位专属短激活码模式 (形如 PP-XXXX-XXXX-XXXX-XXXX)
    if license_key.startswith("PP-") and "." not in license_key:
        curr_mid = get_machine_id()

        # 1.1 先对短码进行 80-bit 紧凑防伪解密预校验
        decoded, dec_err = decode_short_code(license_key, curr_mid)

        # 1.2 在线优先激活：依次遍历授权中心候选列表 (优先域名 auth.yohoo.xyz，备用 IP)
        candidate_urls = [auth_url] + [c for c in AUTH_SERVER_CANDIDATES if c != auth_url]
        online_success = False
        online_reject_msg = None

        for srv in candidate_urls:
            try:
                req_data = json.dumps({
                    "code": license_key,
                    "machine_id": curr_mid,
                    "timestamp": now
                }).encode("utf-8")
                req = urllib.request.Request(
                    f"{srv}/api/v1/license/activate_code",
                    data=req_data,
                    headers={"Content-Type": "application/json", "User-Agent": "ProxyProbe-Core/2.0"}
                )
                with urllib.request.urlopen(req, timeout=2.5) as resp:
                    body = json.loads(resp.read().decode("utf-8"))

                if body.get("ok"):
                    raw_token = body.get("raw_token", "")
                    db_conn.execute("INSERT OR REPLACE INTO setting (key, value) VALUES ('license_key', ?)", (license_key,))
                    db_conn.execute("INSERT OR REPLACE INTO setting (key, value) VALUES ('license_raw_token', ?)", (raw_token,))
                    db_conn.execute("INSERT OR REPLACE INTO setting (key, value) VALUES ('license_revoked', '0')")
                    db_conn.execute("INSERT OR REPLACE INTO setting (key, value) VALUES ('license_activated_ts', ?)", (str(now),))
                    db_conn.execute("INSERT OR REPLACE INTO setting (key, value) VALUES ('license_last_sync_ts', ?)", (str(now),))
                    db_conn.execute("INSERT INTO license_log (timestamp, action, status, detail) VALUES (?, 'activate', 'online_success', ?)",
                                    (now, f"License Code: {license_key} Plan: {body.get('plan_type')} via {srv}"))
                    db_conn.commit()

                    status = get_current_license_status(db_conn)
                    return True, "商业许可证在线激活成功！", status
                else:
                    msg = body.get("message", "激活码校验未通过")
                    # 明确已被中心吊销或被其他设备占用时，直接阻断
                    if "吊销" in msg or "其他设备" in msg:
                        return False, msg, None
                    online_reject_msg = msg
            except Exception:
                continue

        # 1.3 离线兜底激活：若授权服务器暂时离线/超时/更换服务器，自动启用双轨离线验签激活
        if decoded:
            db_conn.execute("INSERT OR REPLACE INTO setting (key, value) VALUES ('license_key', ?)", (license_key,))
            db_conn.execute("INSERT OR REPLACE INTO setting (key, value) VALUES ('license_raw_token', '')")
            db_conn.execute("INSERT OR REPLACE INTO setting (key, value) VALUES ('license_revoked', '0')")
            db_conn.execute("INSERT OR REPLACE INTO setting (key, value) VALUES ('license_activated_ts', ?)", (str(now),))
            db_conn.execute("INSERT OR REPLACE INTO setting (key, value) VALUES ('license_last_sync_ts', ?)", (str(now),))
            db_conn.execute("INSERT INTO license_log (timestamp, action, status, detail) VALUES (?, 'activate', 'offline_fallback', ?)",
                            (now, f"License Code: {license_key} Plan: {decoded['plan_type']} (Offline Fallback)"))
            db_conn.commit()

            status = get_current_license_status(db_conn)
            plan_name = PLAN_MAP.get(decoded["plan_type"], {}).get("name", "商业版")
            return True, f"商业许可证离线激活成功！(授权中心未联网，已自动启用双轨离线兜底：{plan_name})", status

        return False, online_reject_msg or dec_err or "激活失败：无法连接授权中心且卡密离线校验未通过", None

    # 2. 离线非对称签名密钥模式 (PPLIC-...)
    payload, err = parse_and_verify_license(license_key)
    if err:
        return False, err, None

    # 保存许可证
    db_conn.execute("INSERT OR REPLACE INTO setting (key, value) VALUES ('license_key', ?)", (license_key,))
    db_conn.execute("INSERT OR REPLACE INTO setting (key, value) VALUES ('license_raw_token', ?)", (license_key,))
    db_conn.execute("INSERT OR REPLACE INTO setting (key, value) VALUES ('license_revoked', '0')")
    db_conn.execute("INSERT OR REPLACE INTO setting (key, value) VALUES ('license_activated_ts', ?)", (str(now),))
    db_conn.execute("INSERT OR REPLACE INTO setting (key, value) VALUES ('license_last_sync_ts', ?)", (str(now),))
    db_conn.execute("INSERT INTO license_log (timestamp, action, status, detail) VALUES (?, 'activate', 'success', ?)",
                    (now, f"License ID: {payload.get('id')} Customer: {payload.get('customer')}"))
    db_conn.commit()

    # 激活时立即触发一次打卡尝试
    try:
        req_data = json.dumps({
            "license_key": license_key,
            "machine_id": get_machine_id(),
            "version": "2.0.0",
            "timestamp": now
        }).encode("utf-8")
        req = urllib.request.Request(
            f"{auth_url}/api/v1/license/ping",
            data=req_data,
            headers={"Content-Type": "application/json", "User-Agent": "ProxyProbe-Core/2.0"}
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            if body.get("status") == "revoked":
                db_conn.execute("INSERT OR REPLACE INTO setting (key, value) VALUES ('license_revoked', '1')")
                db_conn.commit()
                return False, "该许可证已被中心授权服务器吊销冻结，无法激活！", None
    except Exception:
        pass

    status = get_current_license_status(db_conn)
    return True, "许可证激活成功！", status


# =============================================================================
# 在线心跳巡检与毫秒级黑名单同步
# =============================================================================
def ping_auth_server(db_path: str, auth_url: str = DEFAULT_AUTH_SERVER) -> bool:
    """单次在线心跳打卡与黑名单同步 (优先走域名，失败自动容灾轮询候选服务器)"""
    try:
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute("SELECT value FROM setting WHERE key='license_key'")
        row = cur.fetchone()
        lic_key = row[0].strip() if row and row[0] else ""
        if not lic_key:
            conn.close()
            return False

        mid = get_machine_id()
        now = int(time.time())
        req_data = json.dumps({
            "license_key": lic_key,
            "machine_id": mid,
            "version": "2.0.0",
            "timestamp": now
        }).encode("utf-8")

        candidate_urls = [auth_url] + [c for c in AUTH_SERVER_CANDIDATES if c != auth_url]
        synced = False

        for srv in candidate_urls:
            try:
                req = urllib.request.Request(
                    f"{srv}/api/v1/license/ping",
                    data=req_data,
                    headers={"Content-Type": "application/json", "User-Agent": "ProxyProbe-Core/2.0"}
                )
                with urllib.request.urlopen(req, timeout=3) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                    status = body.get("status", "ok")
                    if status == "revoked":
                        conn.execute("INSERT OR REPLACE INTO setting (key, value) VALUES ('license_revoked', '1')")
                        conn.execute("INSERT INTO license_log (timestamp, action, status, detail) VALUES (?, 'heartbeat', 'revoked', '远程吊销')", (now,))
                    else:
                        conn.execute("INSERT OR REPLACE INTO setting (key, value) VALUES ('license_revoked', '0')")
                        conn.execute("INSERT OR REPLACE INTO setting (key, value) VALUES ('license_last_sync_ts', ?)", (str(now),))
                    conn.commit()
                    synced = True
                    break
            except Exception:
                continue

        conn.close()
        return synced
    except Exception:
        # 心跳失败时静默容灾（不锁死用户，容纳断网宽限期）
        return False


def start_heartbeat_thread(db_path: str, auth_url: str = DEFAULT_AUTH_SERVER):
    """启动后台守护心跳线程 (每 30 秒检查一次发号中心黑名单与打卡)"""
    def _worker():
        # 启动后延时 3 秒首次打卡同步
        time.sleep(3)
        while True:
            try:
                ping_auth_server(db_path, auth_url)
            except Exception:
                pass
            time.sleep(30)  # 30秒巡检一次，确保吊销在半分钟内立刻生效

    t = threading.Thread(target=_worker, daemon=True, name="license_heartbeat")
    t.start()
    return t
