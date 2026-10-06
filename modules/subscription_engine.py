# -*- coding: utf-8 -*-
"""
ProxyProbe 客户端多协议订阅与动态分流配置生成引擎 (Subscription Engine)
支持协议: VLESS Reality / VLESS WS / VMess WS / Trojan / Hysteria 2 / TUIC / SS 2022 / AnyTLS / SOCKS5
支持客户端: Clash Meta (Mihomo) / Verge / Sing-box / SFA / SFI / Surge / Shadowrocket / v2rayN 等
"""

import os
import re
import json
import time
import base64
import secrets
import uuid
import sqlite3
from urllib.parse import quote
try:
    import yaml
except ImportError:
    yaml = None

_ENV_GET_DB = None
_ENV_GET_SETTING = None

def init_subscription_context(get_db_fn=None, get_setting_fn=None):
    global _ENV_GET_DB, _ENV_GET_SETTING
    if get_db_fn:
        _ENV_GET_DB = get_db_fn
    if get_setting_fn:
        _ENV_GET_SETTING = get_setting_fn

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

def format_host_for_uri(host):
    if not host:
        return "127.0.0.1"
    host_str = str(host).strip()
    if ":" in host_str and not host_str.startswith("["):
        return f"[{host_str}]"
    return host_str

def ensure_user_credentials(user):
    user_id = user["id"]
    sub_token = user.get("sub_token") or f"user_{user_id}"
    u_uuid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"monitor_user_{user_id}_{sub_token}"))
    u_pwd = f"u{user_id}_{sub_token[:12]}"
    return u_uuid, u_pwd

def gen_random_password(length=16):
    return secrets.token_urlsafe(length)[:length]

def format_node_link(node, user=None, server_country_map=None):
    try:
        proto = node.get("protocol") or ""
        uuid_str = node.get("uuid") or ""
        pwd_str = node.get("password") or uuid_str
        if user:
            u_uuid, u_pwd = ensure_user_credentials(user)
            uuid_str = u_uuid
            if proto != "ss2022":
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
            sni = node.get("sni") or "bing.com"
            return f"trojan://{pwd_str}@{uri_host}:{port}?security=tls&headerType=none&type=tcp&sni={sni}&allowInsecure=1#{name}"

        elif proto == "ss2022":
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

        elif proto == "anytls":
            sni = node.get("sni") or "www.bing.com"
            return f"anytls://{pwd_str}@{uri_host}:{port}?sni={sni}&allowInsecure=1#{name}"

        return ""
    except Exception as e:
        print(f"[Error] format_node_link exception for node {node.get('id')}: {e}")
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
    {"ip_is_private": True, "outbound": "DIRECT"},
    {"clash_mode": "Direct", "outbound": "DIRECT"},
    {"clash_mode": "Global", "outbound": "PROXY"},
    {"domain_suffix": [".cn", "baidu.com", "qq.com", "weixin.com", "taobao.com", "bilibili.com", "jd.com", "163.com", "zhihu.com"], "outbound": "DIRECT"},
    {"domain_suffix": ["openai.com", "chatgpt.com", "anthropic.com", "claude.ai", "google.com", "youtube.com", "github.com", "twitter.com", "x.com", "telegram.org", "netflix.com"], "outbound": "PROXY"},
    {"outbound": "PROXY"}
], indent=2, ensure_ascii=False)

DEFAULT_SINGBOX_MINIMAL_RULES = json.dumps([
    {"ip_is_private": True, "outbound": "DIRECT"},
    {"clash_mode": "Direct", "outbound": "DIRECT"},
    {"clash_mode": "Global", "outbound": "PROXY"},
    {"domain_suffix": [".cn", "baidu.com", "qq.com", "weixin.com", "taobao.com"], "outbound": "DIRECT"},
    {"outbound": "PROXY"}
], indent=2, ensure_ascii=False)

DEFAULT_SINGBOX_GLOBAL_RULES = json.dumps([
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

REGION_MAP = {
    "HK": ("🇭🇰 香港地区", 1),
    "TW": ("🇹🇼 台湾地区", 2),
    "JP": ("🇯🇵 日本地区", 3),
    "SG": ("🇸🇬 新加坡地区", 4),
    "US": ("🇺🇸 美国地区", 5),
    "KR": ("🇰🇷 韩国地区", 6),
    "UK": ("🇬🇧 英国地区", 7),
    "GB": ("🇬🇧 英国地区", 7),
    "DE": ("🇩🇪 德国地区", 8),
    "FR": ("🇫🇷 法国地区", 9),
    "CA": ("🇨🇦 加拿大地区", 10),
    "AU": ("🇦🇺 澳大利亚地区", 11),
    "RU": ("🇷🇺 俄罗斯地区", 12),
    "MY": ("🇲🇾 马来西亚地区", 13),
    "TH": ("🇹🇭 泰国地区", 14),
    "IN": ("🇮🇳 印度地区", 15),
    "PH": ("🇵🇭 菲律宾地区", 16),
    "VN": ("🇻🇳 越南地区", 17),
}

KEYWORD_RULES = [
    (r"(?:香港|hong\s*kong|hongkong|hkg|\bhk\b|🇭🇰)", "HK"),
    (r"(?:台湾|taiwan|taipei|taichung|\btw\b|tpe|🇹🇼)", "TW"),
    (r"(?:日本|japan|tokyo|osaka|东京|大阪|\bjp\b|🇯🇵)", "JP"),
    (r"(?:新加坡|singapore|lion\s*city|狮城|\bsg\b|sin|🇸🇬)", "SG"),
    (r"(?:美国|united\s*states|america|usa|los\s*angeles|san\s*jose|seattle|new\s*york|硅谷|洛杉矶|圣何塞|西雅图|纽约|\bus\b|美西|美东|🇺🇸)", "US"),
    (r"(?:韩国|korea|seoul|首尔|\bkr\b|kor|🇰🇷)", "KR"),
    (r"(?:英国|united\s*kingdom|london|great\s*britain|伦敦|\buk\b|\bgb\b|gbr|🇬🇧)", "UK"),
    (r"(?:德国|germany|frankfurt|berlin|法兰克福|柏林|\bde\b|deu|🇩🇪)", "DE"),
    (r"(?:法国|france|paris|巴黎|\bfr\b|fra|🇫🇷)", "FR"),
    (r"(?:加拿大|canada|toronto|vancouver|多伦多|温哥华|\bca\b|can|🇨🇦)", "CA"),
    (r"(?:澳大利亚|australia|sydney|melbourne|澳洲|悉尼|墨尔本|\bau\b|aus|🇦🇺)", "AU"),
    (r"(?:俄罗斯|russia|moscow|莫斯科|\bru\b|rus|🇷🇺)", "RU"),
    (r"(?:马来西亚|malaysia|kuala\s*lumpur|吉隆坡|\bmy\b|mys|🇲🇾)", "MY"),
    (r"(?:泰国|thailand|bangkok|曼谷|\bth\b|tha|🇹🇭)", "TH"),
    (r"(?:印度|india|mumbai|孟买|\bin\b|ind|🇮🇳)", "IN"),
    (r"(?:菲律宾|philippines|manila|马尼拉|\bph\b|phl|🇵🇭)", "PH"),
    (r"(?:越南|vietnam|hanoi|ho\s*chi\s*minh|河内|胡志明|\bvn\b|vnm|🇻🇳)", "VN"),
]

def detect_node_region(node, server_country_map=None):
    """
    智能推断节点所属地区与国旗标识
    支持：节点名称关键词、落地目标服务器名称、中转出口解析、后台关联服务器物理国家代码
    """
    name = (node.get("name") or "").strip()
    target_text = name
    if "➔" in name:
        target_text = name.split("➔")[-1]
    elif "->" in name:
        target_text = name.split("->")[-1]

    # 1. 优先从落地出口名称或目标文本中提取关键词
    for pattern, code in KEYWORD_RULES:
        if re.search(pattern, target_text, re.IGNORECASE):
            return REGION_MAP.get(code, (f"{code} 地区", 99))

    # 2. 从关联服务器国家代码映射提取 (ISO 2-letter, 如 HK/JP/US/DE)
    sid = node.get("server_id")
    if server_country_map and sid in server_country_map:
        code = str(server_country_map[sid]).strip().upper()
        if code in REGION_MAP:
            return REGION_MAP[code]

    # 3. 从全名或所属服务器名称匹配
    full_text = f"{name} {node.get('server_name', '')}"
    for pattern, code in KEYWORD_RULES:
        if re.search(pattern, full_text, re.IGNORECASE):
            return REGION_MAP.get(code, (f"{code} 地区", 99))

    return ("🌐 其他地区", 999)

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
                "port": 65535
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
            if proto != "ss2022":
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
        elif proto == "anytls":
            sni = n.get("sni") or "www.bing.com"
            proxy_item = {
                "name": name,
                "type": "anytls",
                "server": host,
                "port": port,
                "password": pwd_str,
                "sni": sni,
                "skip-cert-verify": True,
                "udp": True
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
            sni = n.get("sni") or "bing.com"
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

    # 动态为当前用户实际拥有的节点识别并构建地区策略组
    region_groups = {}
    for node, name in zip(nodes, names):
        if name == "DIRECT":
            continue
        reg_title, reg_rank = detect_node_region(node, server_country_map)
        if reg_title not in region_groups:
            region_groups[reg_title] = (reg_rank, [])
        region_groups[reg_title][1].append(name)

    sorted_regions = sorted(region_groups.items(), key=lambda x: (x[1][0], x[0]))
    region_group_names = [r[0] for r in sorted_regions]

    proxy_groups = [
        {
            "name": "节点选择",
            "type": "select",
            "proxies": ["自动选择"] + region_group_names + info_names + names
        },
        {
            "name": "自动选择",
            "type": "url-test",
            "url": "http://www.gstatic.com/generate_204",
            "interval": 300,
            "tolerance": 50,
            "proxies": list(names)
        }
    ]

    for reg_name, (reg_rank, reg_nodes) in sorted_regions:
        proxy_groups.append({
            "name": reg_name,
            "type": "url-test",
            "url": "http://www.gstatic.com/generate_204",
            "interval": 300,
            "tolerance": 50,
            "proxies": reg_nodes
        })

    clash_cfg = {
        "port": 7890,
        "socks-port": 7891,
        "allow-lan": False,
        "mode": "rule",
        "log-level": "info",
        "unified-delay": True,
        "proxies": info_proxies + proxies,
        "proxy-groups": proxy_groups,
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
            if "cipher" in p and p['cipher']:
                lines.append(f"    cipher: {p['cipher']}")
            if "uuid" in p:
                lines.append(f"    uuid: \"{p['uuid']}\"")
            if "password" in p:
                lines.append(f"    password: \"{p['password']}\"")
            if "username" in p and p['username']:
                lines.append(f"    username: \"{p['username']}\"")
            if "alterId" in p:
                lines.append(f"    alterId: {p['alterId']}")
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
            if "xhttp-opts" in p:
                lines.append("    xhttp-opts:")
                lines.append(f"      path: \"{p['xhttp-opts'].get('path', '/xhttp')}\"")
                lines.append(f"      mode: {p['xhttp-opts'].get('mode', 'auto')}")
            if "ws-opts" in p:
                lines.append("    ws-opts:")
                lines.append(f"      path: \"{p['ws-opts'].get('path', '/ws-proxy')}\"")
                if "headers" in p["ws-opts"]:
                    lines.append("      headers:")
                    for hk, hv in p["ws-opts"]["headers"].items():
                        lines.append(f"        {hk}: \"{hv}\"")
        lines.append("proxy-groups:")
        lines.append("  - name: \"节点选择\"")
        lines.append("    type: select")
        lines.append("    proxies:")
        lines.append("      - \"自动选择\"")
        for rname in region_group_names:
            lines.append(f"      - \"{rname}\"")
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
        for reg_name, (reg_rank, reg_nodes) in sorted_regions:
            lines.append(f"  - name: \"{reg_name}\"")
            lines.append("    type: url-test")
            lines.append("    url: http://www.gstatic.com/generate_204")
            lines.append("    interval: 300")
            lines.append("    tolerance: 50")
            lines.append("    proxies:")
            for rn in reg_nodes:
                lines.append(f"      - \"{rn}\"")
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
            if proto != "ss2022":
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
                    "utls": {
                        "enabled": True,
                        "fingerprint": "chrome"
                    },
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
        elif proto == "anytls":
            sni = n.get("sni") or "www.bing.com"
            node_item = {
                "type": "anytls",
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
            sni = n.get("sni") or "bing.com"
            node_item = {
                "type": "trojan",
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
        elif proto == "socks5":
            uname = (n.get("username") or "").strip()
            if user:
                uname = user.get("username", "")
            s_item = {
                "type": "socks",
                "tag": tag,
                "server": host,
                "server_port": port
            }
            if uname:
                s_item["username"] = uname
                s_item["password"] = pwd_str
            node_item = s_item
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

    # 动态为当前用户实际拥有的节点识别并构建地区策略组
    region_groups = {}
    for node, tag in zip(nodes, valid_nodes):
        reg_title, reg_rank = detect_node_region(node, server_country_map)
        if reg_title not in region_groups:
            region_groups[reg_title] = (reg_rank, [])
        region_groups[reg_title][1].append(tag)

    sorted_regions = sorted(region_groups.items(), key=lambda x: (x[1][0], x[0]))
    region_group_tags = [r[0] for r in sorted_regions]

    selector_tags = (["AUTO"] + region_group_tags + valid_nodes + ["DIRECT"]) if valid_nodes else ["DIRECT"]
    urltest_tags = valid_nodes if valid_nodes else ["DIRECT"]

    sb_proxy_groups = [
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
    ]

    for reg_name, (reg_rank, reg_tags) in sorted_regions:
        sb_proxy_groups.append({
            "type": "urltest",
            "tag": reg_name,
            "outbounds": reg_tags,
            "url": "https://www.gstatic.com/generate_204",
            "interval": "3m",
            "tolerance": 50
        })

    config = {
        "outbounds": sb_proxy_groups + outbounds + [
            {
                "type": "direct",
                "tag": "DIRECT"
            },
            {
                "type": "block",
                "tag": "BLOCK"
            }
        ],
        "route": {
            "rules": get_active_singbox_rules(),
            "auto_detect_interface": True
        }
    }
    return json.dumps(config, indent=2, ensure_ascii=False)

