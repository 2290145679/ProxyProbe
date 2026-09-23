#!/usr/bin/env bash
# =============================================================================
# ProxyProbe 主控端一键部署脚本
# 适用于全新 Debian/Ubuntu/CentOS 服务器
#
# 用法：
#   curl -fsSL https://raw.githubusercontent.com/2290145679/ProxyProbe/main/scripts/deploy-hub.sh | bash
#   或
#   bash deploy-hub.sh
#
# 可选环境变量（提前设置可跳过交互提示）：
#   DOMAIN=tz.yohoo.xyz           你的域名（已解析到本机 IP）
#   ADMIN_PASS=yourpassword       管理员密码（留空则随机生成）
#   GITHUB_REPO=2290145679/ProxyProbe  GitHub 仓库（用于拉取代码）
# =============================================================================
set -e

# ---- 颜色输出 ----
R='\033[0;31m'; G='\033[0;32m'; Y='\033[0;33m'; B='\033[0;34m'; C='\033[0;36m'; N='\033[0m'; BOLD='\033[1m'
info()    { echo -e "${G}[+]${N} $*"; }
warn()    { echo -e "${Y}[!]${N} $*"; }
error()   { echo -e "${R}[-]${N} $*" >&2; }
header()  { echo -e "\n${BOLD}${B}========================================${N}"; echo -e "${BOLD}${B}  $*${N}"; echo -e "${BOLD}${B}========================================${N}"; }
die()     { error "$*"; exit 1; }

# ---- 检测 root ----
[ "$(id -u)" = "0" ] || die "请使用 root 用户运行此脚本"

# ---- 检测系统 ----
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS_ID="$ID"
    OS_VER="$VERSION_ID"
else
    die "无法识别操作系统"
fi

PKG_INSTALL=""
case "$OS_ID" in
    ubuntu|debian)  PKG_INSTALL="apt-get install -y" ;;
    centos|rhel|fedora|rocky|almalinux) PKG_INSTALL="yum install -y" ;;
    *) die "暂不支持的操作系统: $OS_ID" ;;
esac

ARCH=$(uname -m)
case "$ARCH" in
    x86_64|amd64) ARCH_SHORT="amd64"; ARCH_XRAY="64"; ARCH_REALM="x86_64" ;;
    aarch64|arm64) ARCH_SHORT="arm64"; ARCH_XRAY="arm64-v8a"; ARCH_REALM="aarch64" ;;
    *) die "不支持的架构: $ARCH" ;;
esac

ROOT="/opt/monitor"
DATA="$ROOT/data"
WEB_DIST="$ROOT/web-admin/dist"
SCRIPTS_DIR="$ROOT/scripts"
CADDYFILE="/etc/caddy/Caddyfile"
PM_SERVICE="/etc/systemd/system/proxy-manager.service"
HUB_SERVICE="/etc/systemd/system/monitor-hub.service"
GITHUB_REPO="${GITHUB_REPO:-2290145679/ProxyProbe}"
RAW_BASE="https://raw.githubusercontent.com/${GITHUB_REPO}/main"
REPO_BASE="https://github.com/${GITHUB_REPO}"

# ---- Banner ----
clear
echo -e "${BOLD}${C}"
echo "  ██████  ██████   ██████  ██   ██ ██    ██ ██████  ██████   ██████  ██████  ███████ "
echo "  ██   ██ ██   ██ ██    ██  ██ ██   ██  ██  ██   ██ ██   ██ ██    ██ ██   ██ ██      "
echo "  ██████  ██████  ██    ██   ███     ████   ██████  ██████  ██    ██ ██████  █████   "
echo "  ██      ██   ██ ██    ██  ██ ██     ██    ██      ██   ██ ██    ██ ██   ██ ██      "
echo "  ██      ██   ██  ██████  ██   ██    ██    ██      ██   ██  ██████  ██████  ███████ "
echo -e "${N}"
echo -e "  ${BOLD}ProxyProbe 主控端一键部署${N}  •  OS: ${OS_ID} ${OS_VER}  •  Arch: ${ARCH}"
echo ""

# ---- 收集配置信息 ----
header "配置信息"

# 域名
if [ -z "${DOMAIN:-}" ]; then
    read -r -p "  请输入你的域名（已解析到本机 IP）: " DOMAIN
fi
[ -z "$DOMAIN" ] && die "域名不能为空"

# 管理员密码
if [ -z "${ADMIN_PASS:-}" ]; then
    read -r -p "  请输入管理员密码（留空则随机生成）: " ADMIN_PASS
fi
if [ -z "$ADMIN_PASS" ]; then
    ADMIN_PASS=$(tr -dc 'A-Za-z0-9!@#%^&*' < /dev/urandom | head -c 16)
    warn "已随机生成管理员密码: ${BOLD}${ADMIN_PASS}${N}"
    warn "请务必记录此密码！"
fi

echo ""
echo -e "  域名:          ${BOLD}${DOMAIN}${N}"
echo -e "  管理员密码:    ${BOLD}${ADMIN_PASS}${N}"
echo -e "  GitHub 仓库:   ${BOLD}${GITHUB_REPO}${N}"
echo ""
read -r -p "  确认以上配置并开始安装？[y/N] " CONFIRM
case "$CONFIRM" in y|Y|yes) ;; *) echo "  已取消"; exit 0 ;; esac

# ---- 步骤 1: 安装系统依赖 ----
header "步骤 1/8: 安装系统依赖"

if [ "$OS_ID" = "ubuntu" ] || [ "$OS_ID" = "debian" ]; then
    apt-get update -y
    apt-get install -y curl wget git python3 python3-pip unzip tar openssl sqlite3 \
        iptables ca-certificates gnupg lsb-release debian-keyring debian-archive-keyring apt-transport-https
elif [ "$OS_ID" = "centos" ] || [ "$OS_ID" = "rhel" ] || [ "$OS_ID" = "rocky" ] || [ "$OS_ID" = "almalinux" ]; then
    yum update -y
    yum install -y curl wget git python3 unzip tar openssl sqlite iptables ca-certificates
fi
info "系统依赖安装完成"

# ---- 步骤 2: 安装 Caddy ----
header "步骤 2/8: 安装 Caddy Web 服务器"

if ! command -v caddy >/dev/null 2>&1; then
    if [ "$OS_ID" = "ubuntu" ] || [ "$OS_ID" = "debian" ]; then
        curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
        curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | tee /etc/apt/sources.list.d/caddy-stable.list
        apt-get update -y
        apt-get install -y caddy
    elif [ "$OS_ID" = "centos" ] || [ "$OS_ID" = "rhel" ] || [ "$OS_ID" = "rocky" ] || [ "$OS_ID" = "almalinux" ]; then
        yum install -y yum-utils
        yum-config-manager --add-repo https://copr.fedorainfracloud.org/coprs/g/caddy/caddy/repo/epel-7/group_caddy-caddy-epel-7.repo || true
        # 备用: 直接下载 caddy 二进制
        CADDY_VER=$(curl -sSL "https://api.github.com/repos/caddyserver/caddy/releases/latest" 2>/dev/null | grep '"tag_name"' | head -n1 | cut -d'"' -f4 || echo "v2.9.1")
        curl -fsSL "https://github.com/caddyserver/caddy/releases/download/${CADDY_VER}/caddy_${CADDY_VER#v}_linux_${ARCH_SHORT}.tar.gz" | tar -xz -C /tmp/
        install -m 0755 /tmp/caddy /usr/local/bin/caddy
        # 创建 systemd 服务
        groupadd --system caddy 2>/dev/null || true
        useradd --system --gid caddy --create-home --home-dir /var/lib/caddy --shell /usr/sbin/nologin caddy 2>/dev/null || true
        cat > /etc/systemd/system/caddy.service << 'CADDY_UNIT'
[Unit]
Description=Caddy
Documentation=https://caddyserver.com/docs/
After=network.target network-online.target
Requires=network-online.target

[Service]
Type=notify
ExecStart=/usr/local/bin/caddy run --environ --config /etc/caddy/Caddyfile
ExecReload=/usr/local/bin/caddy reload --config /etc/caddy/Caddyfile --force
TimeoutStopSec=5s
LimitNOFILE=1048576
PrivateTmp=true
ProtectSystem=full
AmbientCapabilities=CAP_NET_ADMIN CAP_NET_BIND_SERVICE

[Install]
WantedBy=multi-user.target
CADDY_UNIT
    fi
fi
info "Caddy 已就绪: $(caddy version 2>/dev/null || /usr/local/bin/caddy version)"

# ---- 步骤 3: 安装 monitor-hub 探针主控 ----
header "步骤 3/8: 安装 monitor-hub 探针主控"

mkdir -p "$ROOT" "$DATA" "$SCRIPTS_DIR"

# 下载 monitor-hub 二进制
if [ ! -f "$ROOT/monitor-hub" ]; then
    info "正在下载 monitor-hub 二进制..."
    HUB_VER=$(curl -sSL "https://api.github.com/repos/monitor-probe/monitor/releases/latest" 2>/dev/null | grep '"tag_name"' | head -n1 | cut -d'"' -f4 || echo "")
    if [ -z "$HUB_VER" ]; then
        die "无法获取 monitor-hub 版本，请检查网络连接"
    fi
    curl -fsSL "https://github.com/monitor-probe/monitor/releases/download/${HUB_VER}/monitor-hub-linux-${ARCH_SHORT}" -o "$ROOT/monitor-hub" || \
    curl -fsSL "https://ghproxy.net/https://github.com/monitor-probe/monitor/releases/download/${HUB_VER}/monitor-hub-linux-${ARCH_SHORT}" -o "$ROOT/monitor-hub"
    chmod +x "$ROOT/monitor-hub"
fi
info "monitor-hub 已就绪: $("$ROOT/monitor-hub" --version 2>/dev/null | head -n1 || echo 'monitor-hub')"

# 创建系统用户
id -u monitor >/dev/null 2>&1 || useradd --system --no-create-home --shell /usr/sbin/nologin monitor
chown -R monitor:monitor "$DATA"

# 创建 monitor-hub.service
cat > "$HUB_SERVICE" << EOF
[Unit]
Description=Monitor Hub
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=monitor
Group=monitor
WorkingDirectory=$ROOT
ExecStart=$ROOT/monitor-hub --listen :28080 --data $DATA --site https://$DOMAIN
Restart=always
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable monitor-hub
systemctl restart monitor-hub
sleep 2
info "monitor-hub 服务已启动"

# ---- 步骤 4: 下载 ProxyProbe 代码 ----
header "步骤 4/8: 拉取 ProxyProbe 代码"

TMP_REPO="/tmp/proxyprobe_deploy"
rm -rf "$TMP_REPO"

# 下载 proxy_manager.py
info "正在下载 proxy_manager.py..."
curl -fsSL "${RAW_BASE}/proxy_manager.py" -o "$ROOT/proxy_manager.py" || \
    die "无法下载 proxy_manager.py"

# 下载 install.sh (子节点安装脚本，放到 scripts 目录供 Caddy 对外分发)
curl -fsSL "${RAW_BASE}/scripts/install.sh" -o "$SCRIPTS_DIR/install.sh" || true
chmod +x "$SCRIPTS_DIR/install.sh" 2>/dev/null || true

# 下载前端构建产物
info "正在下载前端资源..."
mkdir -p "$WEB_DIST"

# 通过 GitHub API 下载 web-admin/dist 目录的所有文件
# 使用 git 浅克隆以获取 dist 目录（比逐文件下载可靠）
if command -v git >/dev/null 2>&1; then
    git clone --depth 1 --filter=blob:none --sparse \
        "${REPO_BASE}.git" "$TMP_REPO" 2>/dev/null || true
    if [ -d "$TMP_REPO" ]; then
        cd "$TMP_REPO"
        git sparse-checkout set web-admin/dist scripts 2>/dev/null || true
        git checkout 2>/dev/null || true
        if [ -d "$TMP_REPO/web-admin/dist" ]; then
            cp -r "$TMP_REPO/web-admin/dist/." "$WEB_DIST/"
            info "前端资源已就绪"
        fi
        if [ -f "$TMP_REPO/scripts/install.sh" ]; then
            cp "$TMP_REPO/scripts/install.sh" "$SCRIPTS_DIR/install.sh"
        fi
        cd /
    fi
fi

# 验证前端是否下载成功
[ -f "$WEB_DIST/index.html" ] || warn "前端资源可能未正确下载，请手动检查 $WEB_DIST"

rm -rf "$TMP_REPO"
info "代码拉取完成"

# ---- 步骤 5: 配置 proxy-manager 服务 ----
header "步骤 5/8: 配置 proxy-manager 服务"

cat > "$PM_SERVICE" << 'PM_EOF'
[Unit]
Description=Monitor Proxy Protocol Manager Daemon
After=network.target

[Service]
Type=simple
User=root
ExecStart=/usr/bin/python3 /opt/monitor/proxy_manager.py
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
PM_EOF

systemctl daemon-reload
systemctl enable proxy-manager
systemctl restart proxy-manager
sleep 2
info "proxy-manager 服务已启动 (端口 28090)"

# ---- 步骤 6: 配置 Caddy ----
header "步骤 6/8: 配置 Caddy 反向代理"

mkdir -p /etc/caddy

cat > "$CADDYFILE" << CADDY_EOF
$DOMAIN {
    # 代理协议与订阅 API
    handle /api/proxy/* {
        reverse_proxy 127.0.0.1:28090
    }

    # 远端一键代理脚本
    handle /proxy-agent.sh {
        reverse_proxy 127.0.0.1:28090
    }

    # 节点安装脚本与二进制离线分发
    handle /install.sh {
        root * $SCRIPTS_DIR
        try_files /install.sh
        file_server
    }

    handle /Xray-linux-*.zip {
        root * $SCRIPTS_DIR
        file_server
    }

    handle /sing-box-linux-*.tar.gz {
        root * $SCRIPTS_DIR
        file_server
    }

    handle /realm-*.tar.gz {
        root * $SCRIPTS_DIR
        file_server
    }

    # 后台管理界面
    handle_path /admin* {
        root * $WEB_DIST
        try_files {path} /index.html
        file_server
    }

    # 探针主控（首页 + WebSocket + API）
    handle {
        reverse_proxy 127.0.0.1:28080
    }
}
CADDY_EOF

systemctl daemon-reload
systemctl enable caddy
systemctl restart caddy
sleep 3
info "Caddy 已配置并启动"

# ---- 步骤 7: 设置管理员账户 ----
header "步骤 7/8: 初始化管理员账户"

# 等待 proxy-manager 的数据库初始化完成
sleep 3

PASS_HASH=$(python3 -c "from hashlib import sha256; print(sha256('${ADMIN_PASS}'.encode()).hexdigest())")
DB_FILE="$DATA/monitor.db"

# 等待数据库文件出现（最多 15 秒）
for i in $(seq 1 15); do
    [ -f "$DB_FILE" ] && break
    sleep 1
done

if [ -f "$DB_FILE" ]; then
    # 更新管理员密码（admin 用户在 init_db 中默认创建）
    python3 << PYEOF
import sqlite3, hashlib
db = sqlite3.connect("$DB_FILE")
db.execute("UPDATE proxy_user SET password=? WHERE username='admin'",
           (hashlib.sha256("${ADMIN_PASS}".encode()).hexdigest(),))
db.commit()
db.close()
print("  管理员密码已更新")
PYEOF
    # 重启 proxy-manager 使修改生效
    systemctl restart proxy-manager
    sleep 1
    info "管理员账户初始化完成"
else
    warn "数据库文件尚未创建，请启动后在 /admin 页面手动设置密码"
fi

# ---- 步骤 8: 防火墙放行端口 ----
header "步骤 8/8: 配置防火墙"

open_port() {
    local port=$1 proto=$2
    iptables -I INPUT -p "$proto" --dport "$port" -j ACCEPT 2>/dev/null || true
    if command -v ufw >/dev/null 2>&1; then
        ufw allow "${port}/${proto}" >/dev/null 2>&1 || true
    fi
    if command -v firewall-cmd >/dev/null 2>&1; then
        firewall-cmd --add-port="${port}/${proto}" --permanent 2>/dev/null || true
    fi
}

open_port 80 tcp
open_port 443 tcp
open_port 443 udp   # HTTP/3 QUIC
open_port 28080 tcp
open_port 28090 tcp

if command -v firewall-cmd >/dev/null 2>&1; then
    firewall-cmd --reload 2>/dev/null || true
fi
info "防火墙端口已放行: 80, 443, 28080, 28090"

# ---- 完成 ----
header "🎉 部署完成！"

echo ""
echo -e "  ${BOLD}访问地址${N}"
echo -e "  ┌─────────────────────────────────────────────────┐"
echo -e "  │  探针首页:   ${C}https://$DOMAIN/${N}               │"
echo -e "  │  管理后台:   ${C}https://$DOMAIN/admin${N}          │"
echo -e "  ├─────────────────────────────────────────────────┤"
echo -e "  │  管理员账号: ${BOLD}admin${N}                              │"
echo -e "  │  管理员密码: ${BOLD}${ADMIN_PASS}${N}                     │"
echo -e "  └─────────────────────────────────────────────────┘"
echo ""
echo -e "  ${BOLD}节点服务器安装指令（在后台「添加服务器」页面获取）${N}"
echo -e "  服务检查命令："
echo -e "    ${Y}systemctl status caddy monitor-hub proxy-manager${N}"
echo ""
echo -e "  ${BOLD}下一步：${N}"
echo -e "  1. 访问 ${C}https://$DOMAIN/admin${N} 登录管理后台"
echo -e "  2. 在「服务器」页面添加节点服务器（会自动生成安装指令）"
echo -e "  3. 在「用户」页面创建代理用户"
echo ""
