# -*- coding: utf-8 -*-
"""
ProxyProbe 平滑换机与跨机搬家核心引擎 (Migration Engine)
完美支持：纯IP对纯IP、纯IP对域名、域名对纯IP、域名对域名四大拓扑
"""

import os
import re
import time
import shutil
import sqlite3
import tempfile
import threading
import subprocess

_MIGRATION_TOKENS = {}
_MIGRATION_LOCK = threading.Lock()

_ENV_DB_PATH = "/opt/proxyprobe/data/monitor.db"
_ENV_GET_DB = None
_ENV_GET_IP = None

def init_migration_context(db_path, get_db_fn, get_ip_fn):
    global _ENV_DB_PATH, _ENV_GET_DB, _ENV_GET_IP
    _ENV_DB_PATH = db_path
    _ENV_GET_DB = get_db_fn
    _ENV_GET_IP = get_ip_fn

def clean_expired_migration_tokens():
    now = time.time()
    with _MIGRATION_LOCK:
        expired = [k for k, v in _MIGRATION_TOKENS.items() if v.get("expires_at", 0) < now]
        for k in expired:
            _MIGRATION_TOKENS.pop(k, None)

def is_ip_address(val):
    if not val:
        return False
    clean = str(val).split(":")[0].strip().replace("[", "").replace("]", "")
    return bool(re.match(r"^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}$", clean) or ":" in clean)

def update_caddy_domain_alias(new_domain):
    """
    自动为新服务器上的 Caddyfile 追加域名或 IP 别名反代配置并 reload。
    - 若为域名：自动申请 Let's Encrypt / ZeroSSL 证书并启用 HTTPS
    - 若为纯 IP：配置 HTTP 模式，注入伪装 Origin 头，避免证书申请失败
    """
    if not new_domain or new_domain in ("127.0.0.1", "localhost", "::1"):
        return False, "域名或 IP 无效"
    new_domain = str(new_domain).strip().lower()
    if ":" in new_domain and not new_domain.startswith("["):
        new_domain = new_domain.split(":")[0]

    caddy_paths = [
        "/etc/caddy/Caddyfile",
        "/opt/proxyprobe/config/Caddyfile",
        "/opt/monitor/config/Caddyfile"
    ]
    caddy_file = None
    for p in caddy_paths:
        if os.path.exists(p):
            caddy_file = p
            break
    if not caddy_file:
        return False, "未找到系统 Caddyfile"

    try:
        with open(caddy_file, "r", encoding="utf-8") as f:
            content = f.read()

        if re.search(r'\b' + re.escape(new_domain) + r'\b', content):
            return True, "Caddyfile 中已存在该配置"

        lines = content.splitlines()

        if is_ip_address(new_domain):
            # 纯 IP 模式：单独注入 HTTP 监听块，避免 ACME 证书报错
            ip_block = f"""
http://{new_domain}, http://{new_domain}:80 {{
    handle /api/proxy/* {{
        reverse_proxy 127.0.0.1:28090
    }}
    handle /sub* {{
        reverse_proxy 127.0.0.1:28090
    }}
    handle /proxy-agent.sh {{
        reverse_proxy 127.0.0.1:28090
    }}
    handle_path /admin* {{
        root * /opt/proxyprobe/web-admin/dist
        try_files {{path}} /index.html
        file_server
    }}
    handle {{
        reverse_proxy 127.0.0.1:28080 {{
            header_up Host {{host}}
            header_up X-Real-IP {{remote_host}}
            header_up Origin https://probe.local
            header_up Sec-Fetch-Site same-origin
        }}
    }}
}}
"""
            content = content + "\n" + ip_block
            with open(caddy_file, "w", encoding="utf-8") as f:
                f.write(content.strip() + "\n")
        else:
            # 域名模式：追加到现有站点定义或新建块
            replaced = False
            for idx, line in enumerate(lines):
                stripped = line.strip()
                if "{" in stripped and not stripped.startswith("#") and not stripped.startswith("handle") and not stripped.startswith(":") and not stripped.startswith("http://"):
                    site_part = stripped.split("{")[0].strip()
                    if site_part:
                        new_site = f"{site_part}, {new_domain} {{"
                        lines[idx] = line.replace(stripped, new_site)
                        replaced = True
                        break

            if not replaced:
                domain_block = f"""
{new_domain} {{
    handle /api/proxy/* {{
        reverse_proxy 127.0.0.1:28090
    }}
    handle /sub* {{
        reverse_proxy 127.0.0.1:28090
    }}
    handle /proxy-agent.sh {{
        reverse_proxy 127.0.0.1:28090
    }}
    handle_path /admin* {{
        root * /opt/proxyprobe/web-admin/dist
        try_files {{path}} /index.html
        file_server
    }}
    handle {{
        reverse_proxy 127.0.0.1:28080
    }}
}}
"""
                lines.append(domain_block)

            with open(caddy_file, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")

        subprocess.run(["systemctl", "reload", "caddy"], capture_output=True)
        return True, f"已自动为 Caddyfile 添加配置 {new_domain} 并重载生效"
    except Exception as e:
        return False, f"更新 Caddyfile 异常: {e}"

def apply_restored_database(raw_db_bytes, source_domain="", source_ip="", target_domain="", db_path=None, get_db_fn=None, get_ip_fn=None):
    """
    原子级热装载迁移数据库，并刷新配置与迁移状态标记
    自动适配：纯IP对纯IP、纯IP对域名、域名对纯IP、域名对域名四大场景
    """
    eff_db_path = db_path or _ENV_DB_PATH
    eff_get_db = get_db_fn or _ENV_GET_DB or (lambda: sqlite3.connect(eff_db_path))
    eff_get_ip = get_ip_fn or _ENV_GET_IP or (lambda: "127.0.0.1")

    fd, tmp_db = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    try:
        with open(tmp_db, "wb") as f_out:
            f_out.write(raw_db_bytes)

        # 校验 SQLite 合法性
        chk_conn = sqlite3.connect(tmp_db)
        chk_cur = chk_conn.execute("SELECT COUNT(*) FROM node")
        node_count = chk_cur.fetchone()[0]
        chk_cur2 = chk_conn.execute("SELECT COUNT(*) FROM proxy_user")
        user_count = chk_cur2.fetchone()[0]
        chk_cur3 = chk_conn.execute("SELECT COUNT(*) FROM proxy_node")
        rule_count = chk_cur3.fetchone()[0]
        chk_conn.close()

        # 备份现有数据库（若存在）
        if os.path.exists(eff_db_path):
            bak_path = eff_db_path + ".bak_before_migration"
            try:
                shutil.copy2(eff_db_path, bak_path)
            except Exception:
                pass

        # 原子写入主库
        dst = sqlite3.connect(eff_db_path)
        src = sqlite3.connect(tmp_db)
        try:
            src.backup(dst)
        finally:
            src.close()
            dst.close()

        # 确保其他潜在路径也同步
        for alt_path in ("/opt/proxyprobe/data/monitor.db", "/opt/monitor/data/monitor.db", "/opt/proxyprobe/data/proxyprobe.db"):
            if os.path.exists(os.path.dirname(alt_path)) and alt_path != eff_db_path:
                try:
                    shutil.copy2(tmp_db, alt_path)
                except Exception:
                    pass

        pub_ip = eff_get_ip()
        eff_target = (target_domain or "").strip()

        # 判断最终生效站点的 URL 协议与主机名
        if eff_target:
            if is_ip_address(eff_target):
                effective_site_url = f"http://{eff_target}"
            else:
                effective_site_url = f"https://{eff_target}"
        else:
            # 未指定 target_domain 时：
            if source_domain and not is_ip_address(source_domain):
                effective_site_url = f"https://{source_domain}"
            else:
                effective_site_url = f"http://{pub_ip or '127.0.0.1'}"

        # 在新库中写入迁移完成标记和元数据
        conn = eff_get_db()
        with conn:
            conn.execute("INSERT OR REPLACE INTO setting (key, value) VALUES ('migration_just_completed', '1')")
            if source_domain:
                conn.execute("INSERT OR REPLACE INTO setting (key, value) VALUES ('migration_source_domain', ?)", (source_domain,))
            if eff_target:
                conn.execute("INSERT OR REPLACE INTO setting (key, value) VALUES ('migration_target_domain', ?)", (eff_target,))
            conn.execute("INSERT OR REPLACE INTO setting (key, value) VALUES ('site_url', ?)", (effective_site_url,))
            if source_ip:
                conn.execute("INSERT OR REPLACE INTO setting (key, value) VALUES ('migration_source_ip', ?)", (source_ip,))
            conn.execute("INSERT OR REPLACE INTO setting (key, value) VALUES ('migration_completed_at', ?)", (str(int(time.time())),))
        conn.close()

        # 自动配置 Caddy 别名 (域名和 IP 均优雅适配)
        if eff_target:
            update_caddy_domain_alias(eff_target)
        if source_domain and not is_ip_address(source_domain):
            update_caddy_domain_alias(source_domain)
        elif pub_ip:
            update_caddy_domain_alias(pub_ip)

        # 异步重启 monitor-hub
        def _async_hub_reload():
            time.sleep(1)
            subprocess.run(["systemctl", "restart", "monitor-hub"], capture_output=True)
        threading.Thread(target=_async_hub_reload, daemon=True).start()

        return True, {
            "node_count": node_count,
            "user_count": user_count,
            "rule_count": rule_count,
            "site_url": effective_site_url
        }
    except Exception as e:
        return False, str(e)
    finally:
        if os.path.exists(tmp_db):
            try:
                os.remove(tmp_db)
            except Exception:
                pass

def generate_clone_script(source_host, source_domain, token, target_domain=""):
    eff_target = (target_domain or "").strip()
    is_src_ip = is_ip_address(source_domain)
    is_tgt_ip = is_ip_address(eff_target) if eff_target else is_src_ip

    tpl = """#!/bin/bash
# ==============================================================================
# ProxyProbe 面板全自动一键克隆安装工具
# 完美适配：纯IP对纯IP、纯IP对域名、域名对纯IP、域名对域名四大场景
# 从源面板 [__SOURCE_DOMAIN__] 1:1 无损平移克隆至本机
# ==============================================================================
set -e

if [ "$(id -u)" != "0" ]; then
    echo -e "\\033[0;31m[-] 错误: 请以 root 用户身份运行此克隆脚本！\\033[0m" >&2
    exit 1
fi

echo -e "\\033[0;32m"
cat << 'BANNER'
  ____                      ____            _          
 |  _ \\ _ __ _____  ___   _|  _ \\ _ __ ___ | |__   ___ 
 | |_) | '__/ _ \\ \\/ / | | | |_) | '__/ _ \\| '_ \\ / _ \\
 |  __/| | | (_) >  <| |_| |  __/| | | (_) | |_) |  __/
 |_|   |_|  \\___/_/\\_\\\\__, |_|   |_|  \\___/|_.__/ \\___|
                      |___/   -- 一键全自动克隆安装助手
BANNER
echo -e "\\033[0m"

SOURCE_HOST="__SOURCE_HOST__"
SOURCE_DOMAIN="__SOURCE_DOMAIN__"
TARGET_DOMAIN_INPUT="__TARGET_DOMAIN__"
TOKEN="__TOKEN__"

echo "[+] [1/5] 正在检测系统架构与基础运行环境..."
ARCH="$(uname -m)"
case "$ARCH" in
    x86_64|amd64) ARCH_TYPE="amd64" ;;
    aarch64|arm64) ARCH_TYPE="arm64" ;;
    *) echo "[-] 暂不支持的系统架构: $ARCH" >&2; exit 1 ;;
esac

MY_IP=$(curl -fsSL4 --max-time 3 https://api.ipify.org 2>/dev/null || curl -fsSL4 --max-time 3 https://icanhazip.com 2>/dev/null || ip route get 1 2>/dev/null | awk '{print $7;exit}' || echo "127.0.0.1")

# 判断目标模式：纯 IP 还是域名
IS_TARGET_IP=0
if [ -z "$TARGET_DOMAIN_INPUT" ]; then
    if [[ "$SOURCE_DOMAIN" =~ ^[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+$ ]] || [ "$SOURCE_DOMAIN" = "127.0.0.1" ] || [ "$SOURCE_DOMAIN" = "localhost" ]; then
        IS_TARGET_IP=1
        TARGET_DOMAIN="$MY_IP"
    else
        IS_TARGET_IP=0
        TARGET_DOMAIN="$SOURCE_DOMAIN"
    fi
elif [[ "$TARGET_DOMAIN_INPUT" =~ ^[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+$ ]]; then
    IS_TARGET_IP=1
    TARGET_DOMAIN="$TARGET_DOMAIN_INPUT"
else
    IS_TARGET_IP=0
    TARGET_DOMAIN="$TARGET_DOMAIN_INPUT"
fi

echo "[+] 本机外网 IP: $MY_IP"
echo "[+] 源主控地址: $SOURCE_DOMAIN"
if [ "$IS_TARGET_IP" = "1" ]; then
    echo -e "[+] 运行模式: \\033[1;33m⚡ 纯 IP 模式 (HTTP)\\033[0m"
    echo "[+] 目标主机: $TARGET_DOMAIN"
else
    echo -e "[+] 运行模式: \\033[1;36m🌐 域名模式 (HTTPS - 自动 SSL)\\033[0m"
    echo "[+] 目标域名: $TARGET_DOMAIN"
fi

ROOT="/opt/proxyprobe"
mkdir -p "$ROOT/data"
mkdir -p "$ROOT/web-admin/dist"
mkdir -p "$ROOT/data/themes/default/dist"
mkdir -p "$ROOT/scripts"
mkdir -p "/etc/caddy"

if command -v apt-get >/dev/null 2>&1; then
    apt-get update -y -qq >/dev/null 2>&1 || true
    apt-get install -y -qq curl tar gzip sqlite3 >/dev/null 2>&1 || true
elif command -v yum >/dev/null 2>&1; then
    yum install -y -q curl tar gzip sqlite >/dev/null 2>&1 || true
fi

CLEAN_SRC=$(echo "$SOURCE_HOST" | sed -E 's#^https?://##' | sed 's#:[0-9]\\+$##')

if [ ! -f "$ROOT/monitor-hub" ]; then
    echo "[+] [2/5] 正在安装 ProxyProbe 监控与代理主控核心..."
    INSTALL_FETCHED=0
    for BASE_TRY in "https://$SOURCE_HOST" "http://$SOURCE_HOST" "http://${CLEAN_SRC}:28090" "http://${CLEAN_SRC}:28080"; do
        if curl -fsSLk --max-time 8 "$BASE_TRY/install-hub.sh" -o /tmp/deploy-hub.sh 2>/dev/null && [ -s /tmp/deploy-hub.sh ]; then
            INSTALL_FETCHED=1
            break
        fi
    done
    if [ "$INSTALL_FETCHED" = "1" ]; then
        bash /tmp/deploy-hub.sh --non-interactive --domain "$TARGET_DOMAIN" || true
    else
        curl -fsSL "https://raw.githubusercontent.com/2290145679/ProxyProbe/main/scripts/deploy-hub.sh" -o /tmp/deploy-hub.sh 2>/dev/null || true
        if [ -f /tmp/deploy-hub.sh ]; then
            bash /tmp/deploy-hub.sh --non-interactive --domain "$TARGET_DOMAIN" || true
        fi
    fi
    rm -f /tmp/deploy-hub.sh
fi

echo "[+] [3/5] 正在从源服务器安全拉取数据库快照 (自动多协议容灾)..."
TMP_GZ="/tmp/mig_db.tar.gz"
rm -f "$TMP_GZ"
PULL_OK=0

for PULL_BASE in "https://$SOURCE_HOST" "http://$SOURCE_HOST" "http://${CLEAN_SRC}:28090" "http://${CLEAN_SRC}:28080" "http://$SOURCE_DOMAIN"; do
    if curl -fsSLk "$PULL_BASE/api/proxy/migration/clone-db?token=$TOKEN" -o "$TMP_GZ" 2>/dev/null && [ -s "$TMP_GZ" ]; then
        if gzip -t "$TMP_GZ" 2>/dev/null; then
            PULL_OK=1
            echo "[+] 成功通过 $PULL_BASE 获取数据快照！"
            break
        fi
    fi
done

if [ "$PULL_OK" != "1" ]; then
    echo -e "\\033[0;31m[-] 从源服务器拉取数据库失败或凭据已过期！请重新在源面板生成克隆指令。\\033[0m" >&2
    exit 1
fi

echo "[+] [4/5] 正在解压并热装载完整业务数据库..."
TARGET_DB="$ROOT/data/monitor.db"
systemctl stop monitor-hub 2>/dev/null || true
gzip -dc "$TMP_GZ" > "$TARGET_DB"
rm -f "$TMP_GZ"

cp -f "$TARGET_DB" "$ROOT/data/proxyprobe.db" 2>/dev/null || true

if [ "$IS_TARGET_IP" = "1" ]; then
    EFFECTIVE_SITE_URL="http://$TARGET_DOMAIN"
else
    EFFECTIVE_SITE_URL="https://$TARGET_DOMAIN"
fi

sqlite3 "$TARGET_DB" << SQL_EOF
INSERT OR REPLACE INTO setting (key, value) VALUES ('migration_just_completed', '1');
INSERT OR REPLACE INTO setting (key, value) VALUES ('migration_source_domain', '$SOURCE_DOMAIN');
INSERT OR REPLACE INTO setting (key, value) VALUES ('migration_target_domain', '$TARGET_DOMAIN');
INSERT OR REPLACE INTO setting (key, value) VALUES ('site_url', '$EFFECTIVE_SITE_URL');
INSERT OR REPLACE INTO setting (key, value) VALUES ('migration_source_ip', '$SOURCE_HOST');
INSERT OR REPLACE INTO setting (key, value) VALUES ('migration_completed_at', '$(date +%s)');
SQL_EOF

chown -R monitor:monitor "$ROOT/data" 2>/dev/null || true
chmod 0640 "$TARGET_DB" 2>/dev/null || true

echo "[+] [5/5] 正在配置 Caddy 反向代理与重载核心服务..."
CADDY_CFG="/etc/caddy/Caddyfile"

if [ "$IS_TARGET_IP" = "1" ]; then
    cat > "$CADDY_CFG" << CADDY_IP_EOF
http://$MY_IP, http://$MY_IP:80, :80 {
    handle /api/proxy/* {
        reverse_proxy 127.0.0.1:28090
    }
    handle /sub* {
        reverse_proxy 127.0.0.1:28090
    }
    handle /proxy-agent.sh {
        reverse_proxy 127.0.0.1:28090
    }
    handle_path /admin* {
        root * $ROOT/web-admin/dist
        try_files {path} /index.html
        file_server
    }
    handle {
        reverse_proxy 127.0.0.1:28080 {
            header_up Host {host}
            header_up X-Real-IP {remote_host}
            header_up Origin https://probe.local
            header_up Sec-Fetch-Site same-origin
        }
    }
}
CADDY_IP_EOF
else
    DOMAINS_LINE="$TARGET_DOMAIN"
    if [ "$SOURCE_DOMAIN" != "$TARGET_DOMAIN" ] && ! [[ "$SOURCE_DOMAIN" =~ ^[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+$ ]]; then
        DOMAINS_LINE="$TARGET_DOMAIN, $SOURCE_DOMAIN"
    fi
    cat > "$CADDY_CFG" << CADDY_DOM_EOF
$DOMAINS_LINE {
    handle /api/proxy/* {
        reverse_proxy 127.0.0.1:28090
    }
    handle /sub* {
        reverse_proxy 127.0.0.1:28090
    }
    handle /proxy-agent.sh {
        reverse_proxy 127.0.0.1:28090
    }
    handle_path /admin* {
        root * $ROOT/web-admin/dist
        try_files {path} /index.html
        file_server
    }
    handle {
        reverse_proxy 127.0.0.1:28080
    }
}
CADDY_DOM_EOF
fi

systemctl daemon-reload 2>/dev/null || true
systemctl restart caddy 2>/dev/null || true
systemctl restart monitor-hub 2>/dev/null || true
systemctl restart proxy-manager 2>/dev/null || true

echo ""
echo -e "\\033[0;32m=========================================================="
echo -e "  🎉 恭喜！ProxyProbe 面板已全部克隆完毕并启动就绪！"
echo -e "==========================================================\\033[0m"
echo -e "本机公网 IP: \\033[1;36m$MY_IP\\033[0m"

if [ "$IS_TARGET_IP" = "1" ]; then
    echo -e "运行模式: \\033[1;33m⚡ 纯 IP 模式 (HTTP)\\033[0m"
    echo -e "面板登录地址: \\033[4;34mhttp://$MY_IP/admin\\033[0m"
    echo ""
    echo -e "\\033[1;33m👉 纯 IP 模式接入与接管指引（无需任何 DNS 解析）：\\033[0m"
    echo -e "1. 浏览器访问 \\033[4;34mhttp://$MY_IP/admin\\033[0m 登录后台，首次将弹出资产接管报告卡片；"
    echo -e "2. \\033[1m子服务器节点\\033[0m：由于没有域名自动切换，请登录后台在「服务器」列表点击复制对接指令并在各子服务器终端执行一次，节点秒级上线！"
    echo -e "3. \\033[1m客户端订阅\\033[0m：用户的订阅地址已自动切换为本机 IP (http://$MY_IP/...)，客户端更新订阅链接即可！"
elif [ "$TARGET_DOMAIN" != "$SOURCE_DOMAIN" ]; then
    echo -e "运行模式: \\033[1;36m🌐 新域名模式 (HTTPS)\\033[0m"
    echo -e "新主控域名: \\033[1;36m$TARGET_DOMAIN\\033[0m"
    echo -e "原主控地址: \\033[1;36m$SOURCE_DOMAIN\\033[0m"
    echo ""
    echo -e "\\033[1;33m👉 新域名接入指引：\\033[0m"
    echo -e "1. 请前往 DNS 控制台，将新域名 \\033[1m$TARGET_DOMAIN\\033[0m 的 A 记录解析至本机 IP: \\033[1;32m$MY_IP\\033[0m"
    echo -e "2. 浏览器访问 \\033[4;34mhttps://$TARGET_DOMAIN\\033[0m 登录后台；"
    echo -e "3. 子服务器节点：在后台「服务器」列表复制新对接指令并执行，节点密钥完全保留秒级恢复！"
    echo -e "4. 客户端订阅：用户订阅链接域名已变更为 $TARGET_DOMAIN，客户端点击更新订阅即可！"
    if ! [[ "$SOURCE_DOMAIN" =~ ^[0-9]+\\.[0-9]+\\.[0-9]+\\.[0-9]+$ ]]; then
        echo -e "🌟 双域名免换小技巧：若原域名 $SOURCE_DOMAIN 依然归您所有，在 DNS 将其 CNAME 解析指向 $TARGET_DOMAIN，子节点与客户端可 0 改动无感过渡！"
    fi
else
    echo -e "运行模式: \\033[1;36m🌐 原域名无感接管模式 (HTTPS)\\033[0m"
    echo -e "主控域名: \\033[1;36m$SOURCE_DOMAIN\\033[0m"
    echo ""
    echo -e "\\033[1;33m👉 终极接入指引（仅需一步即可无缝接管）：\\033[0m"
    echo -e "请前往你的域名 DNS 控制台，将 \\033[1m$SOURCE_DOMAIN\\033[0m 的 A 记录修改为本机 IP: \\033[1;32m$MY_IP\\033[0m"
    echo ""
    echo -e "💡 DNS 生效后（约1分钟）："
    echo -e "1. 浏览器访问 \\033[4;34mhttps://$SOURCE_DOMAIN\\033[0m 登录，首次将弹出迁移成功卡片；"
    echo -e "2. 所有子服务器节点将全自动重连上线，客户端订阅无需任何变更！"
fi
echo -e "\\033[0;32m==========================================================\\033[0m"
"""
    return (tpl
        .replace("__SOURCE_HOST__", source_host)
        .replace("__SOURCE_DOMAIN__", source_domain)
        .replace("__TARGET_DOMAIN__", eff_target)
        .replace("__TOKEN__", token))
