#!/usr/bin/env bash
# =============================================================================
# ProxyProbe 主控端一键部署脚本
# 项目主页: https://github.com/2290145679/ProxyProbe
#
# 用法（直接运行，交互式提示）：
#   curl -fsSL https://raw.githubusercontent.com/2290145679/ProxyProbe/main/scripts/deploy-hub.sh | bash
#
# 非交互模式（提前设置环境变量）：
#   export DOMAIN=your-domain.com ADMIN_PASS=yourpassword
#   curl -fsSL https://raw.githubusercontent.com/2290145679/ProxyProbe/main/scripts/deploy-hub.sh | bash
# =============================================================================
set -e

# ---- 颜色 ----
R='\033[0;31m'; G='\033[0;32m'; Y='\033[0;33m'; B='\033[0;34m'; C='\033[0;36m'
N='\033[0m'; BOLD='\033[1m'
info()   { echo -e "${G}[+]${N} $*"; }
warn()   { echo -e "${Y}[!]${N} $*"; }
die()    { echo -e "${R}[-]${N} $*" >&2; exit 1; }
header() { echo -e "\n${BOLD}${B}══════════════════════════════════════${N}"; echo -e "${BOLD}${B}  $*${N}"; echo -e "${BOLD}${B}══════════════════════════════════════${N}"; }

# ---- 前置检查 ----
[ "$(id -u)" = "0" ] || die "请使用 root 用户运行此脚本"

if [ -f /etc/os-release ]; then . /etc/os-release; OS_ID="$ID"; else die "无法识别操作系统"; fi

ARCH=$(uname -m)
case "$ARCH" in
  x86_64|amd64)   ARCH_HUB="amd64";  ARCH_XRAY="64";       ARCH_REALM="x86_64"  ;;
  aarch64|arm64)  ARCH_HUB="arm64";  ARCH_XRAY="arm64-v8a"; ARCH_REALM="aarch64" ;;
  *) die "不支持的架构: $ARCH" ;;
esac

# ---- 项目配置（全部来自本仓库）----
GITHUB_REPO="2290145679/ProxyProbe"
GITHUB_RAW="https://raw.githubusercontent.com/${GITHUB_REPO}/main"
GITHUB_RELEASES="https://github.com/${GITHUB_REPO}/releases/latest/download"
GITHUB_API="https://api.github.com/repos/${GITHUB_REPO}/releases/latest"

ROOT="/opt/monitor"
DATA="$ROOT/data"
WEB_DIST="$ROOT/web-admin/dist"
SCRIPTS_DIR="$ROOT/scripts"

# ---- Banner ----
clear
echo -e "${BOLD}${C}"
echo "  ██████╗ ██████╗  ██████╗ ██╗  ██╗██╗   ██╗██████╗ ██████╗  ██████╗ ██████╗ ███████╗"
echo "  ██╔══██╗██╔══██╗██╔═══██╗╚██╗██╔╝╚██╗ ██╔╝██╔══██╗██╔══██╗██╔═══██╗██╔══██╗██╔════╝"
echo "  ██████╔╝██████╔╝██║   ██║ ╚███╔╝  ╚████╔╝ ██████╔╝██████╔╝██║   ██║██████╔╝█████╗  "
echo "  ██╔═══╝ ██╔══██╗██║   ██║ ██╔██╗   ╚██╔╝  ██╔═══╝ ██╔══██╗██║   ██║██╔══██╗██╔══╝  "
echo "  ██║     ██║  ██║╚██████╔╝██╔╝ ██╗   ██║   ██║     ██║  ██║╚██████╔╝██████╔╝███████╗"
echo "  ╚═╝     ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚═╝     ╚═╝  ╚═╝ ╚═════╝ ╚═════╝ ╚══════╝"
echo -e "${N}"
echo -e "  ${BOLD}主控端一键部署${N}  •  github.com/${GITHUB_REPO}  •  OS: ${OS_ID}  •  Arch: ${ARCH}"
echo ""

# ---- 收集配置 ----
header "📋 配置信息"

if [ -z "${DOMAIN:-}" ]; then
  read -r -p "  请输入你的域名（已解析到本机 IP）: " DOMAIN
fi
[ -z "$DOMAIN" ] && die "域名不能为空"

if [ -z "${ADMIN_PASS:-}" ]; then
  read -r -p "  请输入管理员密码（留空则随机生成）: " ADMIN_PASS
fi
if [ -z "$ADMIN_PASS" ]; then
  ADMIN_PASS=$(tr -dc 'A-Za-z0-9!@#%^&*' < /dev/urandom | head -c 16)
  warn "已随机生成密码: ${BOLD}${ADMIN_PASS}${N}  ← 请务必记录！"
fi

echo ""
echo -e "  域名:       ${BOLD}${DOMAIN}${N}"
echo -e "  管理密码:   ${BOLD}${ADMIN_PASS}${N}"
echo -e "  下载来源:   ${BOLD}github.com/${GITHUB_REPO}${N}"
echo ""
read -r -p "  确认以上配置并开始安装？[y/N] " _CONFIRM
case "$_CONFIRM" in y|Y|yes) ;; *) echo "  已取消"; exit 0 ;; esac

# ---- 步骤 1: 安装系统依赖 ----
header "步骤 1/8 · 安装系统依赖"

if [ "$OS_ID" = "ubuntu" ] || [ "$OS_ID" = "debian" ]; then
  apt-get update -y -qq
  apt-get install -y -qq curl wget git python3 unzip tar openssl sqlite3 \
    iptables ca-certificates gnupg lsb-release apt-transport-https
else
  yum install -y curl wget git python3 unzip tar openssl sqlite iptables ca-certificates 2>/dev/null || \
  dnf install -y curl wget git python3 unzip tar openssl sqlite iptables ca-certificates 2>/dev/null || true
fi
info "系统依赖安装完成"

# ---- 步骤 2: 安装 Caddy ----
header "步骤 2/8 · 安装 Caddy（自动 SSL）"

if ! command -v caddy >/dev/null 2>&1; then
  if [ "$OS_ID" = "ubuntu" ] || [ "$OS_ID" = "debian" ]; then
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
      | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
      | tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
    apt-get update -y -qq && apt-get install -y -qq caddy
  else
    # 通用：直接下载二进制
    _CADDY_VER=$(curl -sSL "https://api.github.com/repos/caddyserver/caddy/releases/latest" \
      2>/dev/null | grep '"tag_name"' | head -1 | cut -d'"' -f4 || echo "v2.9.1")
    curl -fsSL "https://github.com/caddyserver/caddy/releases/download/${_CADDY_VER}/caddy_${_CADDY_VER#v}_linux_${ARCH_HUB}.tar.gz" \
      | tar -xz -C /tmp/ caddy
    install -m 0755 /tmp/caddy /usr/local/bin/caddy
    groupadd --system caddy 2>/dev/null || true
    useradd --system --gid caddy --create-home --home-dir /var/lib/caddy \
      --shell /usr/sbin/nologin caddy 2>/dev/null || true
    mkdir -p /etc/caddy
    cat > /etc/systemd/system/caddy.service << 'CADDY_SVC'
[Unit]
Description=Caddy
After=network-online.target
Wants=network-online.target
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
CADDY_SVC
  fi
fi
info "Caddy 已就绪: $(caddy version 2>/dev/null || /usr/local/bin/caddy version 2>/dev/null || echo 'ok')"

# ---- 步骤 3: 下载 ProxyProbe monitor-hub ----
header "步骤 3/8 · 安装 ProxyProbe 探针主控 (monitor-hub)"

mkdir -p "$ROOT" "$DATA" "$SCRIPTS_DIR"

# 获取最新 Release 版本号
info "正在查询最新版本..."
_LATEST_TAG=$(curl -sSL "$GITHUB_API" 2>/dev/null | grep '"tag_name"' | head -1 | cut -d'"' -f4 || echo "")

if [ -z "$_LATEST_TAG" ]; then
  warn "无法通过 API 获取版本号，尝试直接下载 latest..."
  _DOWNLOAD_URL="${GITHUB_RELEASES}/monitor-hub-linux-${ARCH_HUB}"
else
  info "最新版本: ${_LATEST_TAG}"
  _DOWNLOAD_URL="https://github.com/${GITHUB_REPO}/releases/download/${_LATEST_TAG}/monitor-hub-linux-${ARCH_HUB}"
fi

info "正在下载 monitor-hub-linux-${ARCH_HUB}..."
curl -fsSL "$_DOWNLOAD_URL" -o "$ROOT/monitor-hub" || \
  die "下载失败！请确认 GitHub Release 中已有编译好的二进制文件。\n  访问 https://github.com/${GITHUB_REPO}/releases 查看"
chmod +x "$ROOT/monitor-hub"
info "monitor-hub 已就绪"

# 创建系统用户
id -u monitor >/dev/null 2>&1 || \
  useradd --system --no-create-home --shell /usr/sbin/nologin monitor 2>/dev/null || true
chown -R monitor:monitor "$DATA" 2>/dev/null || true

# 创建 monitor-hub systemd 服务
cat > /etc/systemd/system/monitor-hub.service << EOF
[Unit]
Description=ProxyProbe Monitor Hub
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
info "monitor-hub 已启动（端口 28080）"

# ---- 步骤 4: 下载 proxy_manager.py 和前端资源 ----
header "步骤 4/8 · 下载 ProxyProbe 代理管理程序和前端"

# proxy_manager.py（核心代理管理后端）
info "正在下载 proxy_manager.py..."
curl -fsSL "${GITHUB_RAW}/proxy_manager.py" -o "$ROOT/proxy_manager.py" || \
  die "下载 proxy_manager.py 失败，请检查网络"

# install.sh（子节点安装脚本，供 Caddy 对外分发）
curl -fsSL "${GITHUB_RAW}/scripts/install.sh" -o "$SCRIPTS_DIR/install.sh" 2>/dev/null || true
chmod +x "$SCRIPTS_DIR/install.sh" 2>/dev/null || true

# 前端 dist（通过 git sparse-checkout 只拉取 web-admin/dist）
info "正在下载前端资源..."
mkdir -p "$WEB_DIST"
_TMP_REPO="/tmp/proxyprobe_$$"
rm -rf "$_TMP_REPO"

if git clone --depth 1 --filter=blob:none --sparse \
    "https://github.com/${GITHUB_REPO}.git" "$_TMP_REPO" 2>/dev/null; then
  cd "$_TMP_REPO"
  git sparse-checkout set web-admin/dist scripts 2>/dev/null || true
  git checkout 2>/dev/null || true
  [ -d "$_TMP_REPO/web-admin/dist" ] && cp -r "$_TMP_REPO/web-admin/dist/." "$WEB_DIST/"
  [ -f "$_TMP_REPO/scripts/install.sh" ] && cp "$_TMP_REPO/scripts/install.sh" "$SCRIPTS_DIR/install.sh"
  cd /
  rm -rf "$_TMP_REPO"
fi

[ -f "$WEB_DIST/index.html" ] && info "前端资源已就绪" || \
  warn "前端资源可能未完整下载，请检查 $WEB_DIST"

# ---- 步骤 5: 配置 proxy-manager 服务 ----
header "步骤 5/8 · 启动代理管理服务 (proxy-manager)"

cat > /etc/systemd/system/proxy-manager.service << 'PM_EOF'
[Unit]
Description=ProxyProbe Proxy Manager
After=network.target monitor-hub.service

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
info "proxy-manager 已启动（端口 28090）"

# ---- 步骤 6: 配置 Caddy ----
header "步骤 6/8 · 配置 Caddy 反向代理"

mkdir -p /etc/caddy
cat > /etc/caddy/Caddyfile << CADDY_EOF
$DOMAIN {
    # 代理管理 API（订阅、用户、节点等）
    handle /api/proxy/* {
        reverse_proxy 127.0.0.1:28090
    }

    # 子节点安装脚本（由 proxy-manager 动态生成）
    handle /proxy-agent.sh {
        reverse_proxy 127.0.0.1:28090
    }

    # 子节点探针安装脚本与离线二进制分发
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

    # 管理后台前端（React SPA）
    handle_path /admin* {
        root * $WEB_DIST
        try_files {path} /index.html
        file_server
    }

    # 探针主控（状态页 + WebSocket 心跳 + API）
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

# ---- 步骤 7: 初始化管理员账户 ----
header "步骤 7/8 · 初始化管理员账户"

# 等待 proxy-manager 初始化数据库
_DB="$DATA/monitor.db"
for i in $(seq 1 20); do [ -f "$_DB" ] && break; sleep 1; done

if [ -f "$_DB" ]; then
  python3 - << PYEOF
import sqlite3, hashlib
db = sqlite3.connect("$_DB")
db.execute("UPDATE proxy_user SET password=? WHERE username='admin'",
           (hashlib.sha256("${ADMIN_PASS}".encode()).hexdigest(),))
db.commit(); db.close()
print("  [+] 管理员密码已设置")
PYEOF
  systemctl restart proxy-manager
  sleep 1
else
  warn "数据库尚未创建，请稍后在 /admin 手动设置密码"
fi

# ---- 步骤 8: 防火墙 ----
header "步骤 8/8 · 放行防火墙端口"

for _PORT in 80 443; do
  iptables -I INPUT -p tcp --dport "$_PORT" -j ACCEPT 2>/dev/null || true
  iptables -I INPUT -p udp --dport "$_PORT" -j ACCEPT 2>/dev/null || true
  command -v ufw >/dev/null 2>&1 && ufw allow "$_PORT" >/dev/null 2>&1 || true
  command -v firewall-cmd >/dev/null 2>&1 && \
    firewall-cmd --add-port="${_PORT}/tcp" --permanent 2>/dev/null || true
done
command -v firewall-cmd >/dev/null 2>&1 && firewall-cmd --reload 2>/dev/null || true
info "防火墙端口已放行 (80, 443)"

# ---- 完成 ----
echo ""
echo -e "${BOLD}${G}══════════════════════════════════════════════${N}"
echo -e "${BOLD}${G}  🎉  ProxyProbe 部署完成！${N}"
echo -e "${BOLD}${G}══════════════════════════════════════════════${N}"
echo ""
echo -e "  探针首页:   ${C}https://${DOMAIN}/${N}"
echo -e "  管理后台:   ${C}https://${DOMAIN}/admin${N}"
echo ""
echo -e "  账号: ${BOLD}admin${N}"
echo -e "  密码: ${BOLD}${ADMIN_PASS}${N}"
echo ""
echo -e "  ${BOLD}服务状态检查：${N}"
echo -e "  ${Y}systemctl status monitor-hub proxy-manager caddy${N}"
echo ""
echo -e "  ${BOLD}下一步：${N}"
echo -e "  1. 访问 ${C}https://${DOMAIN}/admin${N} 登录管理后台"
echo -e "  2. 在「服务器」页面添加子节点，复制一键安装指令"
echo -e "  3. 在「用户」页面创建代理用户"
echo ""
