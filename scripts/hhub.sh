#!/usr/bin/env bash
# ==============================================================================
# ProxyProbe 控制台管理工具 (hhub)
# 项目主页: https://github.com/2290145679/ProxyProbe
# ==============================================================================
# ---- 样式与颜色 ----
R='\033[0;31m'; G='\033[0;32m'; Y='\033[0;33m'; B='\033[0;34m'; C='\033[0;36m'
N='\033[0m'; BOLD='\033[1m'; D='\033[2m'

info()   { echo -e "${G}[+]${N} $*"; }
warn()   { echo -e "${Y}[!]${N} $*"; }
err()    { echo -e "${R}[-]${N} $*" >&2; }
die()    { echo -e "${R}[-]${N} $*" >&2; exit 1; }
rule()   { echo -e "${D}────────────────────────────────────────────────────────────${N}"; }

# ---- 权限检查 ----
if [ "$(id -u)" != "0" ]; then
    die "请使用 root 用户或 sudo hhub 运行此管理工具"
fi

ROOT="/opt/monitor"
DATA="$ROOT/data"
SCRIPTS_DIR="$ROOT/scripts"
WEB_DIST="$ROOT/web-admin/dist"
GITHUB_REPO="2290145679/ProxyProbe"
GITHUB_RAW="https://raw.githubusercontent.com/${GITHUB_REPO}/main"
GITHUB_API="https://api.github.com/repos/${GITHUB_REPO}/releases/latest"
# 公开发布仓库（分发资源）
RELEASE_REPO="2290145679/ProxyProbe-Release"
RELEASE_BASE="https://raw.githubusercontent.com/${RELEASE_REPO}/main"

# ---- 读取当前配置 ----
get_current_config() {
    # 1. 尝试从 Caddyfile 解析域名/IP、外部 Web 端口及协议 (HTTP/HTTPS)
    CUR_DOMAIN=""
    CUR_WEB_PORT="443"
    CUR_PROTO="https"
    CUR_IS_IP=0
    if [ -f /etc/caddy/Caddyfile ]; then
        FIRST_LINE=$(grep -E '^(http://)?[a-zA-Z0-9.-]+(:[0-9]+)?\s*\{' /etc/caddy/Caddyfile 2>/dev/null | head -n 1 | awk '{print $1}' | tr -d '{' || true)
        if [ -n "$FIRST_LINE" ]; then
            if [[ "$FIRST_LINE" == http://* ]]; then
                CUR_PROTO="http"
                FIRST_LINE="${FIRST_LINE#http://}"
            fi
            if [[ "$FIRST_LINE" == *:* ]]; then
                CUR_DOMAIN="${FIRST_LINE%%:*}"
                CUR_WEB_PORT="${FIRST_LINE##*:}"
            else
                CUR_DOMAIN="$FIRST_LINE"
                [ "$CUR_PROTO" = "http" ] && CUR_WEB_PORT="80" || CUR_WEB_PORT="443"
            fi
        fi
    fi

    if [[ "$CUR_DOMAIN" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || [[ "$CUR_DOMAIN" =~ ^\[?[0-9a-fA-F:]+\]?$ ]]; then
        CUR_IS_IP=1
        CUR_PROTO="http"
    fi

    # 2. 从 monitor-hub.service 解析内部 HUB 端口
    CUR_HUB_PORT="28080"
    if [ -f /etc/systemd/system/monitor-hub.service ]; then
        _HP=$(grep -oE -- '--listen 127.0.0.1:[0-9]+' /etc/systemd/system/monitor-hub.service 2>/dev/null | awk -F: '{print $2}' || true)
        if [ -n "$_HP" ]; then CUR_HUB_PORT="$_HP"; fi
    fi

    # 3. 从 proxy-manager.service 解析内部 PM 端口
    CUR_PM_PORT="28090"
    if [ -f /etc/systemd/system/proxy-manager.service ]; then
        _PP=$(grep -oE -- '--port [0-9]+' /etc/systemd/system/proxy-manager.service 2>/dev/null | awk '{print $2}' || true)
        if [ -n "$_PP" ]; then CUR_PM_PORT="$_PP"; fi
    fi
    return 0
}

# ---- 打印 Banner ----
show_banner() {
    clear
    echo -e "${BOLD}${C}"
    echo "  ██████╗ ██████╗  ██████╗ ██╗  ██╗██╗   ██╗██████╗ ██████╗  ██████╗ ██████╗ ███████╗"
    echo "  ██╔══██╗██╔══██╗██╔═══██╗╚██╗██╔╝╚██╗ ██╔╝██╔══██╗██╔══██╗██╔═══██╗██╔══██╗██╔════╝"
    echo "  ██████╔╝██████╔╝██║   ██║ ╚███╔╝  ╚████╔╝ ██████╔╝██████╔╝██║   ██║██████╔╝█████╗  "
    echo "  ██╔═══╝ ██╔══██╗██║   ██║ ██╔██╗   ╚██╔╝  ██╔═══╝ ██╔══██╗██║   ██║██╔══██╗██╔══╝  "
    echo "  ██║     ██║  ██║╚██████╔╝██╔╝ ██╗   ██║   ██║     ██║  ██║╚██████╔╝██████╔╝███████╗"
    echo "  ╚═╝     ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚═╝     ╚═╝  ╚═╝ ╚═════╝ ╚═════╝ ╚══════╝"
    echo -e "${N}"
    echo -e "  ${BOLD}ProxyProbe 运维控制台${N} (hhub)  •  github.com/${GITHUB_REPO}"
    rule
}

# ---- 1. 查看系统运行状态 ----
view_status() {
    get_current_config
    echo ""
    echo -e "${BOLD}═══════════════════ 系统运行状态 ═══════════════════${N}"
    
    # 服务状态
    _check_service() {
        local svc="$1"
        local name="$2"
        if systemctl is-active --quiet "$svc" 2>/dev/null; then
            echo -e "  $name ($svc):  ${G}● 运行中 (Active)${N}"
        else
            echo -e "  $name ($svc):  ${R}○ 已停止 (Inactive)${N}"
        fi
    }

    _check_service "caddy" "Caddy 网关服务      "
    _check_service "monitor-hub" "探针主控服务 (Rust) "
    _check_service "proxy-manager" "代理中枢服务 (ProxyManager)"

    echo ""
    echo -e "${BOLD}═══════════════════ 网络与访问信息 ═════════════════${N}"
    echo -e "  绑定地址:         ${BOLD}${CUR_DOMAIN:-未配置}${N} $([ "$CUR_IS_IP" = "1" ] && echo -e "(${C}纯 IP 模式 - HTTP${N})" || echo -e "(${C}域名模式 - HTTPS${N})")"
    echo -e "  Web 外部访问端口: ${BOLD}${CUR_WEB_PORT}${N}"
    echo -e "  探针主控内部端口: ${BOLD}${CUR_HUB_PORT}${N} (127.0.0.1 本地反代)"
    echo -e "  代理管理内部端口: ${BOLD}${CUR_PM_PORT}${N} (127.0.0.1 本地反代)"
    
    local site_suffix=""
    if [ "$CUR_PROTO" = "http" ]; then
        [ "$CUR_WEB_PORT" != "80" ] && site_suffix=":$CUR_WEB_PORT"
        if [ -n "$CUR_DOMAIN" ]; then
            echo ""
            echo -e "  探针公开大屏:     ${C}http://${CUR_DOMAIN}${site_suffix}/${N}"
            echo -e "  管理控制面板:     ${C}http://${CUR_DOMAIN}${site_suffix}/admin${N}"
        fi
    else
        [ "$CUR_WEB_PORT" != "443" ] && site_suffix=":$CUR_WEB_PORT"
        if [ -n "$CUR_DOMAIN" ]; then
            echo ""
            echo -e "  探针公开大屏:     ${C}https://${CUR_DOMAIN}${site_suffix}/${N}"
            echo -e "  管理控制面板:     ${C}https://${CUR_DOMAIN}${site_suffix}/admin${N}"
        fi
    fi

    # 用户数与节点数统计
    if [ -f "$DATA/monitor.db" ]; then
        local stats
        stats=$(python3 -c "
import sqlite3
try:
    conn = sqlite3.connect('$DATA/monitor.db')
    u = conn.execute('SELECT count(*) FROM proxy_user').fetchone()[0]
    n = conn.execute('SELECT count(*) FROM proxy_node').fetchone()[0]
    s = conn.execute('SELECT count(*) FROM node').fetchone()[0]
    print(f'{u}|{n}|{s}')
except Exception:
    print('0|0|0')
" 2>/dev/null || echo "0|0|0")
        local u_count=$(echo "$stats" | cut -d'|' -f1)
        local n_count=$(echo "$stats" | cut -d'|' -f2)
        local s_count=$(echo "$stats" | cut -d'|' -f3)
        echo ""
        echo -e "${BOLD}═══════════════════ 业务数据概览 ═══════════════════${N}"
        echo -e "  代理用户总数:     ${BOLD}${u_count:-0}${N} 人"
        echo -e "  代理节点总数:     ${BOLD}${n_count:-0}${N} 个"
        echo -e "  监控服务器数:     ${BOLD}${s_count:-0}${N} 台"
    fi
    echo ""
}

# ---- 2. 重启所有服务 ----
restart_all() {
    echo ""
    info "正在重启所有 ProxyProbe 服务..."
    systemctl restart monitor-hub proxy-manager caddy
    sleep 2
    info "服务重启完成！"
    view_status
}

# ---- 3. 停止所有服务 ----
stop_all() {
    echo ""
    warn "正在停止所有 ProxyProbe 服务..."
    systemctl stop monitor-hub proxy-manager caddy 2>/dev/null || true
    info "所有服务已停止！"
}

# ---- 4. 启动所有服务 ----
start_all() {
    echo ""
    info "正在启动所有 ProxyProbe 服务..."
    systemctl start monitor-hub proxy-manager caddy
    sleep 2
    info "服务启动完成！"
    view_status
}

# ---- 5. 修改 Web 外部访问端口 ----
change_web_port() {
    get_current_config
    echo ""
    echo -e "${BOLD}─── 修改 Web 外部访问端口 ───${N}"
    echo -e "  当前端口: ${BOLD}${CUR_WEB_PORT}${N} ($([ "$CUR_IS_IP" = "1" ] && echo "纯 IP 模式 HTTP" || echo "域名模式 HTTPS"))"
    if [ "$CUR_IS_IP" = "1" ] || [ "$CUR_PROTO" = "http" ]; then
        echo -e "  ${D}💡 提示: 纯 IP 模式下默认 80 为标准 HTTP 端口。若改为其他端口（如 8080），访问后台需加上端口号。${N}"
    else
        echo -e "  ${D}💡 提示: 默认 443 为标准 HTTPS 端口，浏览器直接访问域名即可。${N}"
        echo -e "  ${Y}⚠️  注意: 若改为非 443（如 8443），访问面板需加上端口号；若使用 Cloudflare，请选用其支持的端口。${N}"
    fi
    echo ""
    read -r -p "  请输入新的 Web 访问端口 [1-65535] (回车保持当前): " NEW_PORT
    [ -z "$NEW_PORT" ] && { info "未做任何修改"; return; }

    case "$NEW_PORT" in
        ''|*[!0-9]*) err "端口必须为纯数字！"; return ;;
        *) if [ "$NEW_PORT" -lt 1 ] || [ "$NEW_PORT" -gt 65535 ]; then
             err "端口超出有效范围 (1-65535)！"; return
           fi ;;
    esac

    if [ "$NEW_PORT" = "$CUR_HUB_PORT" ] || [ "$NEW_PORT" = "$CUR_PM_PORT" ]; then
        err "外部端口不能与内部端口 ($CUR_HUB_PORT / $CUR_PM_PORT) 相同！"
        return
    fi

    info "正在更新 Caddyfile 配置..."
    if [ "$CUR_IS_IP" = "1" ] || [ "$CUR_PROTO" = "http" ]; then
        sed -i -E "s/^(http:\/\/)?[a-zA-Z0-9.-]+(:[0-9]+)?\s*\{/http:\/\/${CUR_DOMAIN}:${NEW_PORT} {/" /etc/caddy/Caddyfile
    else
        if [ "$NEW_PORT" = "443" ]; then
            sed -i -E "s/^(http:\/\/)?[a-zA-Z0-9.-]+(:[0-9]+)?\s*\{/${CUR_DOMAIN} {/" /etc/caddy/Caddyfile
            sed -i -E "s/--site https:\/\/[a-zA-Z0-9.-]+(:[0-9]+)?/--site https:\/\/${CUR_DOMAIN}/" /etc/systemd/system/monitor-hub.service
        else
            sed -i -E "s/^(http:\/\/)?[a-zA-Z0-9.-]+(:[0-9]+)?\s*\{/${CUR_DOMAIN}:${NEW_PORT} {/" /etc/caddy/Caddyfile
            sed -i -E "s/--site https:\/\/[a-zA-Z0-9.-]+(:[0-9]+)?/--site https:\/\/${CUR_DOMAIN}:${NEW_PORT}/" /etc/systemd/system/monitor-hub.service
        fi
    fi

    # 防火墙放行新端口
    iptables -I INPUT -p tcp --dport "$NEW_PORT" -j ACCEPT 2>/dev/null || true
    iptables -I INPUT -p udp --dport "$NEW_PORT" -j ACCEPT 2>/dev/null || true
    command -v ufw >/dev/null 2>&1 && ufw allow "$NEW_PORT" >/dev/null 2>&1 || true
    command -v firewall-cmd >/dev/null 2>&1 && {
        firewall-cmd --add-port="${NEW_PORT}/tcp" --permanent 2>/dev/null || true
        firewall-cmd --reload 2>/dev/null || true
    }

    systemctl daemon-reload
    systemctl restart monitor-hub caddy
    info "Web 外部端口已成功更新为: ${BOLD}${NEW_PORT}${N}"
}

# ---- 6. 修改内部端口 (monitor-hub & proxy-manager) ----
change_internal_ports() {
    get_current_config
    echo ""
    echo -e "${BOLD}─── 修改内部服务监听端口 (127.0.0.1 本地回环) ───${N}"
    echo -e "  当前探针主控 (monitor-hub) 端口:    ${BOLD}${CUR_HUB_PORT}${N}"
    echo -e "  当前代理中枢 (proxy-manager) 端口:  ${BOLD}${CUR_PM_PORT}${N}"
    echo -e "  ${D}💡 提示: 内部端口仅供本机 Caddy 网关反代使用，不对外暴露公网。直接回车保持不变。${N}"
    echo ""
    read -r -p "  请输入新的探针主控本地端口 [默认: ${CUR_HUB_PORT}]: " NEW_HP
    NEW_HP="${NEW_HP:-$CUR_HUB_PORT}"

    read -r -p "  请输入新的代理中枢本地端口 [默认: ${CUR_PM_PORT}]: " NEW_PP
    NEW_PP="${NEW_PP:-$CUR_PM_PORT}"

    if [ "$NEW_HP" = "$NEW_PP" ]; then
        err "两个内部端口不能相同！"; return
    fi
    if [ "$NEW_HP" = "$CUR_WEB_PORT" ] || [ "$NEW_PP" = "$CUR_WEB_PORT" ]; then
        err "内部端口不能与外部 Web 访问端口 ($CUR_WEB_PORT) 相同！"; return
    fi

    # 更新 monitor-hub.service
    if [ "$NEW_HP" != "$CUR_HUB_PORT" ]; then
        sed -i -E "s/--listen 127\.0\.0\.1:[0-9]+/--listen 127.0.0.1:${NEW_HP}/" /etc/systemd/system/monitor-hub.service
        sed -i -E "s/reverse_proxy 127\.0\.0\.1:${CUR_HUB_PORT}/reverse_proxy 127.0.0.1:${NEW_HP}/g" /etc/caddy/Caddyfile
    fi

    # 更新 proxy-manager.service
    if [ "$NEW_PP" != "$CUR_PM_PORT" ]; then
        if grep -q -- '--port' /etc/systemd/system/proxy-manager.service; then
            sed -i -E "s/--port [0-9]+/--port ${NEW_PP}/" /etc/systemd/system/proxy-manager.service
        else
            sed -i -E "s#(ExecStart=/usr/bin/python3 /opt/monitor/proxy_manager.py)#\1 --port ${NEW_PP}#" /etc/systemd/system/proxy-manager.service
        fi
        sed -i -E "s/reverse_proxy 127\.0\.0\.1:${CUR_PM_PORT}/reverse_proxy 127.0.0.1:${NEW_PP}/g" /etc/caddy/Caddyfile
    fi

    systemctl daemon-reload
    systemctl restart monitor-hub proxy-manager caddy
    info "内部端口已成功更新！(monitor-hub: $NEW_HP, proxy-manager: $NEW_PP)"
}

# ---- 7. 修改绑定域名/IP ----
change_domain() {
    get_current_config
    echo ""
    echo -e "${BOLD}─── 修改绑定域名或公网 IP ───${N}"
    echo -e "  当前地址: ${BOLD}${CUR_DOMAIN}${N} ($([ "$CUR_IS_IP" = "1" ] && echo "纯 IP 模式" || echo "域名模式"))"
    echo -e "  ${D}💡 提示: 若输入域名，将启用 Caddy 自动申请 SSL 证书 (HTTPS)；若输入 IP，将使用纯 IP 模式 (HTTP)。${N}"
    echo ""
    read -r -p "  请输入新的域名或服务器公网 IP: " NEW_DOM
    [ -z "$NEW_DOM" ] && { info "未做任何修改"; return; }

    # 清洗
    NEW_DOM=$(echo "$NEW_DOM" | tr -d '[:space:]' | sed -E 's#^https?://##' | sed 's#/.*$##')
    [ -z "$NEW_DOM" ] && { err "无效的地址！"; return; }

    NEW_IS_IP=0
    if [[ "$NEW_DOM" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || [[ "$NEW_DOM" =~ ^\[?[0-9a-fA-F:]+\]?$ ]]; then
        NEW_IS_IP=1
    fi

    info "正在更新 Caddyfile 与系统服务配置..."
    if [ "$NEW_IS_IP" = "1" ]; then
        # 切换到纯 IP 模式 (HTTP)
        sed -i '/email admin@/d' /etc/caddy/Caddyfile 2>/dev/null || true
        # 替换站点行
        sed -i -E "s/^(http:\/\/)?[a-zA-Z0-9.-]+(:[0-9]+)?\s*\{/http:\/\/${NEW_DOM}:${CUR_WEB_PORT} {/" /etc/caddy/Caddyfile
        # 移除 monitor-hub 的 --site 参数
        sed -i -E "s/ --site https?:\/\/[a-zA-Z0-9.-]+(:[0-9]+)?//" /etc/systemd/system/monitor-hub.service
    else
        # 切换到域名模式 (HTTPS)
        if ! grep -q "email admin@" /etc/caddy/Caddyfile; then
            sed -i "1i {\\n    email admin@${NEW_DOM}\\n}" /etc/caddy/Caddyfile
        else
            sed -i -E "s/email admin@[a-zA-Z0-9.-]+/email admin@${NEW_DOM}/" /etc/caddy/Caddyfile
        fi
        if [ "$CUR_WEB_PORT" = "443" ]; then
            sed -i -E "s/^(http:\/\/)?[a-zA-Z0-9.-]+(:[0-9]+)?\s*\{/${NEW_DOM} {/" /etc/caddy/Caddyfile
            if grep -q -- '--site' /etc/systemd/system/monitor-hub.service; then
                sed -i -E "s/--site https:\/\/[a-zA-Z0-9.-]+(:[0-9]+)?/--site https:\/\/${NEW_DOM}/" /etc/systemd/system/monitor-hub.service
            else
                sed -i -E "s/(ExecStart=.*monitor-hub [^\n]+)/\1 --site https:\/\/${NEW_DOM}/" /etc/systemd/system/monitor-hub.service
            fi
        else
            sed -i -E "s/^(http:\/\/)?[a-zA-Z0-9.-]+(:[0-9]+)?\s*\{/${NEW_DOM}:${CUR_WEB_PORT} {/" /etc/caddy/Caddyfile
            if grep -q -- '--site' /etc/systemd/system/monitor-hub.service; then
                sed -i -E "s/--site https:\/\/[a-zA-Z0-9.-]+(:[0-9]+)?/--site https:\/\/${NEW_DOM}:${CUR_WEB_PORT}/" /etc/systemd/system/monitor-hub.service
            else
                sed -i -E "s/(ExecStart=.*monitor-hub [^\n]+)/\1 --site https:\/\/${NEW_DOM}:${CUR_WEB_PORT}/" /etc/systemd/system/monitor-hub.service
            fi
        fi
    fi

    systemctl daemon-reload
    systemctl restart monitor-hub
    systemctl restart caddy
    sleep 3
    info "地址已更新为: ${BOLD}${NEW_DOM}${N}"
    [ "$NEW_IS_IP" = "1" ] && info "纯 IP 模式已生效 (HTTP)！" || info "域名 HTTPS 模式已生效，Caddy 已开始自动申请新 SSL 证书！"
}

# ---- 8. 重置/修改管理员密码 ----
reset_admin_password() {
    echo ""
    echo -e "${BOLD}─── 重置管理员登录密码 ───${N}"
    echo -e "  ${D}💡 提示: 将同时更新「普通用户中心」与「主控管理后台」两个登录入口的密码。${N}"
    echo ""
    read -r -p "  请输入新的管理员密码 (留空则随机生成): " NEW_PASS
    if [ -z "$NEW_PASS" ]; then
        NEW_PASS=$(tr -dc 'A-Za-z0-9!@#%^&*' < /dev/urandom | head -c 16)
        warn "已随机生成新密码: ${BOLD}${NEW_PASS}${N}  ← 请务必牢记！"
    fi

    _DB="/opt/monitor/data/monitor.db"
    if [ ! -f "$_DB" ]; then
        err "数据库文件不存在: $_DB"; return
    fi

    ADMIN_PASS="$NEW_PASS" DB_PATH="$_DB" python3 - << 'PYEOF'
import os, sqlite3, hashlib, secrets
db_path = os.environ.get("DB_PATH", "/opt/monitor/data/monitor.db")
admin_pass = os.environ.get("ADMIN_PASS", "")
if not admin_pass:
    exit(1)

db = sqlite3.connect(db_path)
try:
    salt = secrets.token_hex(16)
    h = hashlib.sha256((salt + admin_pass).encode("utf-8")).hexdigest()
    pwd_hash = f"{salt}:{h}"
    db.execute("UPDATE proxy_user SET password_hash=? WHERE username='admin'", (pwd_hash,))

    try:
        from argon2 import PasswordHasher
        ph = PasswordHasher()
        argon_h = ph.hash(admin_pass)
        db.execute("CREATE TABLE IF NOT EXISTS setting (key TEXT PRIMARY KEY, value TEXT)")
        db.execute("INSERT OR REPLACE INTO setting (key, value) VALUES ('admin_password_hash', ?)", (argon_h,))
    except Exception as err:
        print(f"  [!] Argon2 哈希设置跳过: {err}")

    db.commit()
    print("  [+] 管理员密码已成功重置！")
finally:
    db.close()
PYEOF

    systemctl restart proxy-manager monitor-hub
    info "密码修改成功！当前密码: ${BOLD}${NEW_PASS}${N}"
}

# ---- 9. 一键无损热升级系统 ----
upgrade_system() {
    echo ""
    echo -e "${BOLD}─── 一键检查并无损升级 ProxyProbe ───${N}"
    info "正在拉取最新代码与静态前端..."

    ARCH=$(uname -m)
    case "$ARCH" in
        x86_64|amd64)   ARCH_HUB="amd64" ;;
        aarch64|arm64)  ARCH_HUB="arm64" ;;
        *) ARCH_HUB="amd64" ;;
    esac

    # 1. 升级 proxy-manager 二进制
    info "正在更新 proxy-manager 二进制..."
    curl -fsSL "${RELEASE_BASE}/proxy-manager-linux-${ARCH_HUB}" \
        -o "$ROOT/proxy-manager.new" 2>/dev/null && {
        chmod +x "$ROOT/proxy-manager.new"
        mv -f "$ROOT/proxy-manager.new" "$ROOT/proxy-manager"
        info "proxy-manager 二进制已更新"
    } || warn "proxy-manager 二进制下载跳过或已是最新"

    # 2. 更新 install.sh（从 Release 库）
    curl -fsSL "${RELEASE_BASE}/install.sh" -o "$SCRIPTS_DIR/install.sh.new" 2>/dev/null && \
        mv -f "$SCRIPTS_DIR/install.sh.new" "$SCRIPTS_DIR/install.sh" && \
        chmod +x "$SCRIPTS_DIR/install.sh" && info "install.sh 已更新" || true

    # 3. 更新 hhub 控制台脚本本身（从 Release 库）
    curl -fsSL "${RELEASE_BASE}/hhub.sh" -o "/usr/local/bin/hhub.new" 2>/dev/null && \
        mv -f "/usr/local/bin/hhub.new" "/usr/local/bin/hhub" && \
        chmod +x "/usr/local/bin/hhub" && info "hhub 控制台已更新" || true

    # 4. 更新前端 dist（从 Release 库下载 tar.gz）
    _TMP_DIST="/tmp/web-admin-dist-upgrade-$$.tar.gz"
    if curl -fsSL "${RELEASE_BASE}/web-admin-dist.tar.gz" -o "$_TMP_DIST" 2>/dev/null; then
        tar -xzf "$_TMP_DIST" -C "$WEB_DIST" 2>/dev/null
        # 兼容展平：若历史压缩包包含 dist/ 子层级，自动移动至根目录
        if [ -d "$WEB_DIST/dist" ] && [ -f "$WEB_DIST/dist/index.html" ]; then
            cp -rf "$WEB_DIST/dist/"* "$WEB_DIST/" 2>/dev/null || mv -f "$WEB_DIST/dist/"* "$WEB_DIST/" 2>/dev/null
            rm -rf "$WEB_DIST/dist"
        fi
        [ -f "$WEB_DIST/index.html" ] && info "前端管理面板资源已更新完毕" || warn "前端资源解压失败"
        rm -f "$_TMP_DIST"
    else
        rm -f "$_TMP_DIST"
        warn "前端资源下载跳过"
    fi

    # 5. 更新 monitor-hub 核心二进制
    info "正在更新 monitor-hub 探针核心二进制..."
    curl -fsSL "${RELEASE_BASE}/monitor-hub-linux-${ARCH_HUB}" \
        -o "$ROOT/monitor-hub.new" 2>/dev/null && {
        chmod +x "$ROOT/monitor-hub.new"
        mv -f "$ROOT/monitor-hub.new" "$ROOT/monitor-hub"
        info "monitor-hub 核心已更新"
    } || warn "monitor-hub 下载跳过或已是最新"

    # 确保 Caddyfile 路由配置正确
    if [ -f /etc/caddy/Caddyfile ]; then
        if grep -q "handle /admin\*" /etc/caddy/Caddyfile; then
            sed -i 's|handle /admin\*|handle_path /admin*|g' /etc/caddy/Caddyfile
        fi
        if ! grep -q "redir /admin /admin/" /etc/caddy/Caddyfile; then
            sed -i '/handle_path \/admin\*/i \    redir /admin /admin/' /etc/caddy/Caddyfile
        fi
    fi

    # 重启服务
    systemctl daemon-reload
    systemctl restart proxy-manager monitor-hub caddy
    caddy reload --config /etc/caddy/Caddyfile --force 2>/dev/null || true
    echo ""
    info "🎉 恭喜！ProxyProbe 已全部无损升级为最新版本！"
}

# ---- 10. 查看服务实时日志 ----
view_logs() {
    echo ""
    echo -e "${BOLD}─── 选择要查看的实时运行日志 ───${N}"
    echo "  [1] 代理业务中枢日志 (proxy-manager: 节点同步/设备限制/流量统计)"
    echo "  [2] 探针核心日志     (monitor-hub: 遥测心跳/前端 API)"
    echo "  [3] Caddy 网关访问日志 (SSL证书/外部HTTP请求反代)"
    echo "  [0] 返回上级菜单"
    echo ""
    read -r -p "  请选择 [0-3]: " log_choice
    case "$log_choice" in
        1) journalctl -u proxy-manager -f ;;
        2) journalctl -u monitor-hub -f ;;
        3) journalctl -u caddy -f ;;
        *) return ;;
    esac
}

# ---- 11. 数据库备份与恢复 ----
manage_backup() {
    echo ""
    echo -e "${BOLD}─── SQLite 数据库备份与还原 ───${N}"
    echo "  [1] 立即创建数据库备份"
    echo "  [2] 从历史备份还原数据"
    echo "  [0] 返回上级菜单"
    echo ""
    read -r -p "  请选择 [0-2]: " b_choice
    case "$b_choice" in
        1)
            local ts
            ts=$(date +"%Y%m%d_%H%M%S")
            local backup_file="$DATA/monitor_backup_${ts}.db"
            if [ -f "$DATA/monitor.db" ]; then
                python3 -c "
import sqlite3
src = sqlite3.connect('$DATA/monitor.db')
dst = sqlite3.connect('$backup_file')
src.backup(dst)
dst.close()
src.close()
" 2>/dev/null || cp "$DATA/monitor.db" "$backup_file"
                chmod 600 "$backup_file"
                info "备份成功！文件保存在: ${BOLD}${backup_file}${N}"
            else
                err "数据库文件不存在！"
            fi
            ;;
        2)
            echo ""
            echo "  可用的历史备份列表："
            local list
            list=$(ls -t "$DATA"/monitor_backup_*.db 2>/dev/null || true)
            if [ -z "$list" ]; then
                warn "未找到任何历史备份文件！"; return
            fi
            local idx=1
            declare -A backup_map
            for f in $list; do
                echo "    [$idx] $(basename "$f") ($(stat -c%y "$f" 2>/dev/null | cut -d'.' -f1))"
                backup_map[$idx]="$f"
                idx=$((idx + 1))
            done
            read -r -p "  请选择要还原的编号 [1-$((idx - 1))]: " sel
            local target_f="${backup_map[$sel]:-}"
            if [ -n "$target_f" ] && [ -f "$target_f" ]; then
                warn "⚠️ 还原将覆盖当前数据库数据！"
                read -r -p "  确认要还原吗？[y/N]: " confirm_r
                case "$confirm_r" in
                    y|Y|yes)
                        systemctl stop proxy-manager monitor-hub
                        cp -f "$target_f" "$DATA/monitor.db"
                        chown -R monitor:monitor "$DATA" 2>/dev/null || true
                        chmod 775 "$DATA" "$DATA/monitor.db" 2>/dev/null || true
                        systemctl start monitor-hub proxy-manager
                        info "数据库已还原成功并重启服务！"
                        ;;
                    *) info "已取消操作" ;;
                esac
            else
                err "无效的序号选择！"
            fi
            ;;
        *) return ;;
    esac
}

# ---- 12. 卸载 ProxyProbe ----
uninstall_proxyprobe() {
    echo ""
    echo -e "${BOLD}${R}─── 卸载 ProxyProbe ───${N}"
    warn "您即将卸载 ProxyProbe 探针监控与代理管理系统！"
    echo ""
    echo "  [1] 安全卸载：停止并移除所有服务与程序，【保留】数据库与配置"
    echo "  [2] 彻底清除：清除所有服务、程序，并【彻底删除】数据库与全部数据"
    echo "  [0] 取消退出"
    echo ""
    read -r -p "  请确认您的选择 [0-2]: " u_sel
    case "$u_sel" in
        1|2)
            read -r -p "  ⚠️ 再次确认：确定要卸载吗？[y/N]: " u_confirm
            case "$u_confirm" in y|Y|yes) ;; *) info "已取消卸载"; return ;; esac
            
            info "正在停止并禁用 systemd 服务..."
            systemctl stop monitor-hub proxy-manager caddy 2>/dev/null || true
            systemctl disable monitor-hub proxy-manager caddy 2>/dev/null || true
            
            rm -f /etc/systemd/system/monitor-hub.service \
                  /etc/systemd/system/proxy-manager.service \
                  /etc/systemd/system/caddy.service \
                  /etc/systemd/system/multi-user.target.wants/monitor-hub.service \
                  /etc/systemd/system/multi-user.target.wants/proxy-manager.service \
                  /etc/systemd/system/multi-user.target.wants/caddy.service
            systemctl daemon-reload
            
            rm -f /usr/local/bin/hhub /usr/local/bin/caddy
            rm -rf /opt/monitor/web-admin /opt/monitor/scripts /opt/monitor/monitor-hub /opt/monitor/proxy_manager.py
            
            if [ "$u_sel" = "2" ]; then
                rm -rf /opt/monitor /etc/caddy /var/lib/caddy
                info "已彻底清除 ProxyProbe 的全部文件与数据库。"
            else
                info "程序已卸载。数据库已保留在: /opt/monitor/data/"
            fi
            info "卸载已完成！"
            exit 0
            ;;
        *) info "已取消卸载"; return ;;
    esac
}

# ---- 主交互循环 ----
press_any_key() {
    echo ""
    read -r -n 1 -s -p "按任意键返回主菜单..."
    echo ""
}

main_menu() {
    while true; do
        show_banner
        get_current_config
        
        # 顶部概要
        local site_suffix=""
        local panel_url=""
        if [ "$CUR_IS_IP" = "1" ] || [ "$CUR_PROTO" = "http" ]; then
            [ "$CUR_WEB_PORT" != "80" ] && site_suffix=":$CUR_WEB_PORT"
            panel_url="http://${CUR_DOMAIN}${site_suffix}/admin"
            echo -e "  地址: ${BOLD}${CUR_DOMAIN:-未配置}${N} (${C}纯 IP 模式 - HTTP${N})  •  Web 端口: ${BOLD}${CUR_WEB_PORT}${N}  •  状态: $(systemctl is-active --quiet monitor-hub && echo -e "${G}运行中${N}" || echo -e "${R}停止${N}")"
        else
            [ "$CUR_WEB_PORT" != "443" ] && site_suffix=":$CUR_WEB_PORT"
            panel_url="https://${CUR_DOMAIN}${site_suffix}/admin"
            echo -e "  域名: ${BOLD}${CUR_DOMAIN:-未配置}${N} (${C}域名模式 - HTTPS${N})  •  Web 端口: ${BOLD}${CUR_WEB_PORT}${N}  •  状态: $(systemctl is-active --quiet monitor-hub && echo -e "${G}运行中${N}" || echo -e "${R}停止${N}")"
        fi
        [ -n "$CUR_DOMAIN" ] && echo -e "  面板地址: ${C}${panel_url}${N}"
        rule
        
        echo -e "  ${BOLD}【服务管理】${N}"
        echo -e "    ${C}[1]${N} 查看系统详细状态 (端口/服务/数据量)"
        echo -e "    ${C}[2]${N} 重启所有服务 (Caddy + Hub + ProxyManager)"
        echo -e "    ${C}[3]${N} 停止所有服务"
        echo -e "    ${C}[4]${N} 启动所有服务"
        echo ""
        echo -e "  ${BOLD}【配置与网络】${N}"
        echo -e "    ${C}[5]${N} 修改 Web 外部访问端口 (当前: ${BOLD}${CUR_WEB_PORT}${N})"
        echo -e "    ${C}[6]${N} 修改内部探针与代理端口 (当前: ${BOLD}${CUR_HUB_PORT} / ${CUR_PM_PORT}${N})"
        echo -e "    ${C}[7]${N} 修改绑定域名或公网 IP (当前: ${BOLD}${CUR_DOMAIN}${N})"
        echo -e "    ${C}[8]${N} 重置/修改管理员密码"
        echo ""
        echo -e "  ${BOLD}【系统运维】${N}"
        echo -e "    ${C}[9]${N} 一键无损热升级系统 (代码/前端/二进制)"
        echo -e "   ${C}[10]${N} 实时监控服务运行日志"
        echo -e "   ${C}[11]${N} 数据库一键备份与恢复"
        echo -e "   ${C}[12]${N} 卸载 ProxyProbe"
        echo ""
        echo -e "    ${C}[0]${N} 退出控制台"
        rule

        read -r -p "  请输入选项 [0-12]: " opt
        case "$opt" in
            1) view_status; press_any_key ;;
            2) restart_all; press_any_key ;;
            3) stop_all; press_any_key ;;
            4) start_all; press_any_key ;;
            5) change_web_port; press_any_key ;;
            6) change_internal_ports; press_any_key ;;
            7) change_domain; press_any_key ;;
            8) reset_admin_password; press_any_key ;;
            9) upgrade_system; press_any_key ;;
            10) view_logs ;;
            11) manage_backup; press_any_key ;;
            12) uninstall_proxyprobe ;;
            0|q|Q|exit) clear; exit 0 ;;
            *) warn "无效选项，请重新选择"; sleep 1 ;;
        esac
    done
}

# 支持快捷子命令直接调用，如 `hhub status`, `hhub restart`, `hhub log`
case "${1:-}" in
    status) view_status; exit 0 ;;
    restart) restart_all; exit 0 ;;
    stop) stop_all; exit 0 ;;
    start) start_all; exit 0 ;;
    log|logs) view_logs; exit 0 ;;
    update|upgrade) upgrade_system; exit 0 ;;
    backup) manage_backup; exit 0 ;;
    *) main_menu ;;
esac
