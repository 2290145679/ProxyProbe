#!/usr/bin/env bash
# =============================================================================
# ProxyProbe 主控端一键部署脚本
# 项目主页: https://github.com/2290145679/ProxyProbe
#
# 用法（直接运行，交互式提示）：
#   curl -fsSL https://raw.githubusercontent.com/2290145679/ProxyProbe-Release/main/deploy-hub.sh | bash
#
# 非交互模式（提前设置环境变量）：
#   export DOMAIN=your-domain.com ADMIN_PASS=yourpassword
#   curl -fsSL https://raw.githubusercontent.com/2290145679/ProxyProbe-Release/main/deploy-hub.sh | bash
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

# ---- 项目配置 ----
GITHUB_REPO="2290145679/ProxyProbe"
GITHUB_API="https://api.github.com/repos/${GITHUB_REPO}/releases/latest"
# 公开发布仓库（源码仓库私有，所有分发文件在此公开仓库）
RELEASE_REPO="2290145679/ProxyProbe-Release"
RELEASE_BASE="https://raw.githubusercontent.com/${RELEASE_REPO}/main"

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

validate_port() {
  local p="$1"
  local name="$2"
  case "$p" in
    ''|*[!0-9]*) die "${name} 必须为纯数字！" ;;
    *) if [ "$p" -lt 1 ] || [ "$p" -gt 65535 ]; then
         die "${name} 超出有效端口范围 (1-65535)！"
       fi ;;
  esac
}

# ---- 收集配置 ----
header "📋 配置信息"

DETECTED_IP=$(curl -s4 --max-time 3 https://api.ipify.org 2>/dev/null || \
              curl -s4 --max-time 3 https://ifconfig.me 2>/dev/null || \
              curl -s4 --max-time 3 https://icanhazip.com 2>/dev/null || true)
DETECTED_IP=$(echo "$DETECTED_IP" | tr -d '[:space:]')

if [ -z "${DOMAIN:-}" ]; then
  echo -e "  ${BOLD}访问域名或 IP 配置${N}:"
  echo -e "  ${D}• 若有域名（已解析到本机）：输入域名（如 probe.example.com），Caddy 自动申请 SSL 证书并启用 HTTPS${N}"
  echo -e "  ${D}• 若无域名：直接回车或输入公网 IP（检测到: ${DETECTED_IP:-未识别}），将以纯 IP 模式运行 (HTTP)${N}"
  if [ -n "$DETECTED_IP" ]; then
    read -r -p "  请输入域名或公网 IP [回车默认使用纯 IP: ${DETECTED_IP}]: " INPUT_DOMAIN </dev/tty || true
    DOMAIN="${INPUT_DOMAIN:-$DETECTED_IP}"
  else
    read -r -p "  请输入你的域名或公网 IP: " DOMAIN </dev/tty || true
  fi
fi
[ -z "$DOMAIN" ] && die "域名或公网 IP 不能为空"
DOMAIN=$(echo "$DOMAIN" | tr -d '[:space:]' | sed -E 's#^https?://##' | sed 's#/.*$##')
[ -z "$DOMAIN" ] && die "解析后的有效地址为空，请检查输入"

# 判断是 IP 还是域名
IS_IP=0
if [[ "$DOMAIN" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]] || [[ "$DOMAIN" =~ ^\[?[0-9a-fA-F:]+\]?$ ]]; then
  IS_IP=1
fi

if [ -z "${ADMIN_PASS:-}" ]; then
  read -r -p "  请输入管理员密码（留空则随机生成）: " ADMIN_PASS </dev/tty || true
fi
if [ -z "$ADMIN_PASS" ]; then
  ADMIN_PASS=$(tr -dc 'A-Za-z0-9!@#%^&*' < /dev/urandom | head -c 16)
  warn "已随机生成密码: ${BOLD}${ADMIN_PASS}${N}  ← 请务必记录！"
fi

# Web 外部访问端口
if [ "$IS_IP" = "1" ]; then
  if [ -z "${WEB_PORT:-}" ]; then
    echo ""
    echo -e "  ${BOLD}Web 外部访问端口 (纯 IP 模式 - HTTP)${N}:"
    echo -e "  ${D}• 默认 80 为标准 HTTP 端口，浏览器直接访问 http://${DOMAIN} 即可${N}"
    echo -e "  ${D}• 若修改为非 80（如 8080），访问后台需加上端口号 (http://${DOMAIN}:8080/admin)${N}"
    read -r -p "  请输入 Web 外部访问端口 [回车默认 80]: " INPUT_WEB_PORT </dev/tty || true
    WEB_PORT="${INPUT_WEB_PORT:-80}"
  fi
  validate_port "$WEB_PORT" "Web 外部端口"
else
  if [ -z "${WEB_PORT:-}" ]; then
    echo ""
    echo -e "  ${BOLD}Web 外部访问端口 (域名模式 - HTTPS)${N}:"
    echo -e "  ${D}• 默认 443 为标准 HTTPS 端口，浏览器直接访问域名即可${N}"
    echo -e "  ${D}• 若修改为非 443（如 8443），访问后台需加上端口号 (https://$DOMAIN:8443)${N}"
    echo -e "  ${D}• 若使用 Cloudflare CDN 加速代理，仅支持特定的 HTTPS 端口: 2053, 2083, 2087, 2096, 8443${N}"
    echo -e "  ${D}• 注意: Caddy 仍需要监听 80 端口用于 Let's Encrypt 申请 SSL 证书验证${N}"
    read -r -p "  请输入 Web 外部访问端口 [回车默认 443]: " INPUT_WEB_PORT </dev/tty || true
    WEB_PORT="${INPUT_WEB_PORT:-443}"
  fi
  validate_port "$WEB_PORT" "Web 外部端口"
  [ "$WEB_PORT" = "80" ] && die "域名 HTTPS 模式下 Web 外部端口不能设为 80，该端口由 Caddy 用于 ACME 证书申请！"
fi

# 探针主控 (monitor-hub) 本地端口
if [ -z "${HUB_PORT:-}" ]; then
  echo ""
  echo -e "  ${BOLD}探针主控 (monitor-hub) 本地监听端口${N}:"
  echo -e "  ${D}• 仅供本机 127.0.0.1 内部通信使用，不对外公网暴露${N}"
  echo -e "  ${D}• 若本机其他程序占用了 28080 端口，可在此自定义${N}"
  read -r -p "  请输入探针主控内部端口 [回车默认 28080]: " INPUT_HUB_PORT </dev/tty || true
  HUB_PORT="${INPUT_HUB_PORT:-28080}"
fi
validate_port "$HUB_PORT" "探针内部端口"

# 代理管理中枢 (proxy-manager) 本地端口
if [ -z "${PM_PORT:-}" ]; then
  echo ""
  echo -e "  ${BOLD}代理管理中枢 (proxy-manager) 本地监听端口${N}:"
  echo -e "  ${D}• 仅供本机 127.0.0.1 内部通信使用，不对外公网暴露${N}"
  echo -e "  ${D}• 若本机其他程序占用了 28090 端口，可在此自定义${N}"
  read -r -p "  请输入代理中枢内部端口 [回车默认 28090]: " INPUT_PM_PORT </dev/tty || true
  PM_PORT="${INPUT_PM_PORT:-28090}"
fi
validate_port "$PM_PORT" "代理中枢内部端口"

# 冲突校验
[ "$HUB_PORT" = "$PM_PORT" ] && die "探针内部端口 ($HUB_PORT) 不能与代理中枢内部端口 ($PM_PORT) 相同！"
[ "$WEB_PORT" = "$HUB_PORT" ] && die "Web 外部端口 ($WEB_PORT) 不能与探针内部端口 ($HUB_PORT) 冲突！"
[ "$WEB_PORT" = "$PM_PORT" ] && die "Web 外部端口 ($WEB_PORT) 不能与代理中枢内部端口 ($PM_PORT) 冲突！"

if [ "$IS_IP" = "1" ]; then
  SITE_URL="http://${DOMAIN}"
  [ "$WEB_PORT" != "80" ] && SITE_URL="http://${DOMAIN}:${WEB_PORT}"
  DEPLOY_MODE="纯 IP 模式 (HTTP)"
else
  SITE_URL="https://${DOMAIN}"
  [ "$WEB_PORT" != "443" ] && SITE_URL="https://${DOMAIN}:${WEB_PORT}"
  DEPLOY_MODE="域名模式 (HTTPS 自动证书)"
fi

echo ""
echo -e "  部署模式:           ${BOLD}${DEPLOY_MODE}${N}"
echo -e "  访问地址:           ${BOLD}${SITE_URL}${N}"
echo -e "  管理密码:           ${BOLD}${ADMIN_PASS}${N}"
echo -e "  Web 外部访问端口:   ${BOLD}${WEB_PORT}${N}"
echo -e "  探针主控内部端口:   ${BOLD}${HUB_PORT}${N} (127.0.0.1)"
echo -e "  代理管理内部端口:   ${BOLD}${PM_PORT}${N} (127.0.0.1)"
echo -e "  下载来源:           ${BOLD}github.com/${GITHUB_REPO}${N}"
echo ""

if [ -n "${NON_INTERACTIVE:-}" ] || [ -n "${YES:-}" ] || [ ! -t 0 ]; then
  _CONFIRM="y"
else
  read -r -p "  确认以上配置并开始安装？[y/N] " _CONFIRM
fi
case "$_CONFIRM" in y|Y|yes) ;; *) echo "  已取消"; exit 0 ;; esac

# ---- 步骤 1: 安装系统依赖 ----
header "步骤 1/8 · 安装系统依赖"

if [ "$OS_ID" = "ubuntu" ] || [ "$OS_ID" = "debian" ]; then
  apt-get update -y -qq
  apt-get install -y -qq curl wget git python3 python3-argon2 unzip tar openssl sqlite3 \
    iptables ca-certificates gnupg lsb-release apt-transport-https
else
  yum install -y curl wget git python3 unzip tar openssl sqlite iptables ca-certificates 2>/dev/null || \
  dnf install -y curl wget git python3 unzip tar openssl sqlite iptables ca-certificates 2>/dev/null || true
fi
info "系统依赖安装完成"

# ---- 步骤 2: 安装 Caddy ----
header "步骤 2/8 · 安装 Caddy（自动 SSL）"

if ! command -v caddy >/dev/null 2>&1; then
  INSTALLED=0
  if [ "$OS_ID" = "ubuntu" ] || [ "$OS_ID" = "debian" ]; then
    (
      curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' \
        | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
      curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' \
        | tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
      apt-get update -y -qq && apt-get install -y -qq caddy
    ) 2>/dev/null && INSTALLED=1 || true
  fi

  if [ "$INSTALLED" = "0" ] && ! command -v caddy >/dev/null 2>&1; then
    info "正在通过官方发布包下载 Caddy..."
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

# 若服务器此前运行过旧服务或中途中断，先停止运行，防止 Linux 内核锁定二进制文件(ETXTBSY / Error on write)
systemctl stop monitor-hub.service 2>/dev/null || true
systemctl stop proxy-manager.service 2>/dev/null || true

mkdir -p "$ROOT" "$DATA" "$SCRIPTS_DIR"

info "正在下载 monitor-hub-linux-${ARCH_HUB}..."
_TMP_HUB="/tmp/monitor-hub-$$"
rm -f "$_TMP_HUB"
_DOWNLOAD_URL="${RELEASE_BASE}/monitor-hub-linux-${ARCH_HUB}"
if curl -fsSL "$_DOWNLOAD_URL" -o "$_TMP_HUB" 2>/dev/null || \
   wget -qO "$_TMP_HUB" "$_DOWNLOAD_URL" 2>/dev/null || \
   python3 -c "import urllib.request; urllib.request.urlretrieve('$_DOWNLOAD_URL', '$_TMP_HUB')" 2>/dev/null; then
  chmod +x "$_TMP_HUB"
  mv -f "$_TMP_HUB" "$ROOT/monitor-hub"
  info "monitor-hub 已就绪"
else
  rm -f "$_TMP_HUB"
  die "下载失败！请检查网络，或访问 https://github.com/${RELEASE_REPO} 确认文件存在"
fi

# 创建系统用户
id -u monitor >/dev/null 2>&1 || \
  useradd --system --no-create-home --shell /usr/sbin/nologin monitor 2>/dev/null || true
chown -R monitor:monitor "$DATA" 2>/dev/null || true
chmod 775 "$DATA" 2>/dev/null || true

# 创建 monitor-hub systemd 服务
systemctl disable monitor-hub.service 2>/dev/null || true
rm -f /etc/systemd/system/multi-user.target.wants/monitor-hub.service
rm -f /etc/systemd/system/monitor-hub.service

if [ "$IS_IP" = "1" ]; then
  HUB_EXEC="$ROOT/monitor-hub --listen 127.0.0.1:$HUB_PORT --db $DATA/monitor.db"
else
  HUB_EXEC="$ROOT/monitor-hub --listen 127.0.0.1:$HUB_PORT --db $DATA/monitor.db --site $SITE_URL"
fi

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
ExecStart=$HUB_EXEC
Restart=always
RestartSec=5
LimitNOFILE=65536

[Install]
WantedBy=multi-user.target
EOF

chmod 644 /etc/systemd/system/monitor-hub.service
systemctl daemon-reload
systemctl enable --force monitor-hub.service 2>/dev/null || {
  mkdir -p /etc/systemd/system/multi-user.target.wants
  ln -sf /etc/systemd/system/monitor-hub.service /etc/systemd/system/multi-user.target.wants/monitor-hub.service
}
systemctl restart monitor-hub.service
sleep 2
info "monitor-hub 已启动（端口 $HUB_PORT）"

# ---- 步骤 4: 下载 ProxyProbe 代理管理程序和前端 ----
# ---- 步骤 4: 下载 ProxyProbe 代理管理程序和前端 ----
header "步骤 4/8 · 下载 ProxyProbe 代理管理程序和前端"

# 从公开发布仓库下载编译好的二进制 proxy-manager
_PM_BIN_URL="${RELEASE_BASE}/proxy-manager-linux-${ARCH_HUB}"
_TMP_BIN="/tmp/proxy-manager-$$"
HAS_BINARY=0
info "正在下载 proxy-manager-linux-${ARCH_HUB}..."
if curl -fsSL "$_PM_BIN_URL" -o "$_TMP_BIN" 2>/dev/null || wget -qO "$_TMP_BIN" "$_PM_BIN_URL" 2>/dev/null; then
  chmod +x "$_TMP_BIN"
  mv -f "$_TMP_BIN" "$ROOT/proxy-manager"
  HAS_BINARY=1
  info "已下载编译好的二进制管理程序 proxy-manager"
else
  rm -f "$_TMP_BIN"
fi

if [ "$HAS_BINARY" = "0" ]; then
  die "无法下载 proxy-manager 二进制！请访问 https://github.com/${RELEASE_REPO} 确认文件存在"
fi

# install.sh（子节点安装脚本，供 Caddy 对外分发）—— 从公开发行库下载
info "正在下载 install.sh..."
curl -fsSL "${RELEASE_BASE}/install.sh" -o "$SCRIPTS_DIR/install.sh" 2>/dev/null || \
  wget -qO "$SCRIPTS_DIR/install.sh" "${RELEASE_BASE}/install.sh" 2>/dev/null || true
chmod +x "$SCRIPTS_DIR/install.sh" 2>/dev/null || true

# hhub（运维控制台 CLI 工具）—— 从公开发行库下载
info "正在安装 hhub 终端控制台工具..."
curl -fsSL "${RELEASE_BASE}/hhub.sh" -o "/usr/local/bin/hhub" 2>/dev/null || \
  wget -qO "/usr/local/bin/hhub" "${RELEASE_BASE}/hhub.sh" 2>/dev/null || true
chmod +x "/usr/local/bin/hhub" 2>/dev/null || true

# 前端 dist —— 从公开发行库下载 web-admin-dist.tar.gz
info "正在下载前端资源..."
mkdir -p "$WEB_DIST"
_TMP_DIST="/tmp/web-admin-dist-$$.tar.gz"
if curl -fsSL "${RELEASE_BASE}/web-admin-dist.tar.gz" -o "$_TMP_DIST" 2>/dev/null || \
   wget -qO "$_TMP_DIST" "${RELEASE_BASE}/web-admin-dist.tar.gz" 2>/dev/null; then
  tar -xzf "$_TMP_DIST" -C "$WEB_DIST" 2>/dev/null
  # 兼容展平：若历史压缩包包含 dist/ 子层级，自动移动至根目录
  if [ -d "$WEB_DIST/dist" ] && [ -f "$WEB_DIST/dist/index.html" ]; then
    cp -rf "$WEB_DIST/dist/"* "$WEB_DIST/" 2>/dev/null || mv -f "$WEB_DIST/dist/"* "$WEB_DIST/" 2>/dev/null
    rm -rf "$WEB_DIST/dist"
  fi
  [ -f "$WEB_DIST/index.html" ] && info "前端资源已就绪" || warn "前端资源解压可能不完整"
  rm -f "$_TMP_DIST"
else
  rm -f "$_TMP_DIST"
  warn "前端资源下载失败，请检查 https://github.com/${RELEASE_REPO} 中是否有 web-admin-dist.tar.gz"
fi

[ -f "/usr/local/bin/hhub" ] && cp "/usr/local/bin/hhub" "$SCRIPTS_DIR/hhub.sh" 2>/dev/null || true

# ---- 步骤 5: 配置 proxy-manager 服务 ----
header "步骤 5/8 · 启动代理管理服务 (proxy-manager)"

systemctl disable proxy-manager.service 2>/dev/null || true
rm -f /etc/systemd/system/multi-user.target.wants/proxy-manager.service
rm -f /etc/systemd/system/proxy-manager.service

if [ -f "$ROOT/proxy-manager" ] && [ -x "$ROOT/proxy-manager" ]; then
  PM_CMD="$ROOT/proxy-manager --port $PM_PORT"
  info "使用编译好的二进制程序运行 proxy-manager"
else
  PM_CMD="/usr/bin/python3 $ROOT/proxy_manager.py --port $PM_PORT"
  info "使用 Python 脚本运行 proxy-manager"
fi

cat > /etc/systemd/system/proxy-manager.service << PM_EOF
[Unit]
Description=ProxyProbe Proxy Manager
After=network.target monitor-hub.service

[Service]
Type=simple
User=root
ExecStart=$PM_CMD
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
PM_EOF

chmod 644 /etc/systemd/system/proxy-manager.service
systemctl daemon-reload
systemctl enable --force proxy-manager.service 2>/dev/null || {
  mkdir -p /etc/systemd/system/multi-user.target.wants
  ln -sf /etc/systemd/system/proxy-manager.service /etc/systemd/system/multi-user.target.wants/proxy-manager.service
}
systemctl restart proxy-manager.service
sleep 2
info "proxy-manager 已启动（端口 $PM_PORT）"

# ---- 步骤 6: 配置 Caddy ----
header "步骤 6/8 · 配置 Caddy 反向代理"

mkdir -p /etc/caddy

if [ "$IS_IP" = "1" ]; then
  # 纯 IP 模式：使用标准 HTTP 监听，禁用 ACME，并为探针主控注入 Header 避免 Origin 拒绝
  cat > /etc/caddy/Caddyfile << CADDY_EOF
http://$DOMAIN:$WEB_PORT {
    # 代理管理 API（订阅、用户、节点等）
    handle /api/proxy/* {
        reverse_proxy 127.0.0.1:$PM_PORT
    }

    # 子节点安装脚本（由 proxy-manager 动态生成）
    handle /proxy-agent.sh {
        reverse_proxy 127.0.0.1:$PM_PORT
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
    redir /admin /admin/
    handle_path /admin* {
        root * $WEB_DIST
        try_files {path} /index.html
        file_server
    }

    # 探针主控（纯 IP 模式：注入伪装 Origin 头与 Sec-Fetch-Site 满足安全校验）
    handle {
        reverse_proxy 127.0.0.1:$HUB_PORT {
            header_up Host {host}
            header_up X-Real-IP {remote_host}
            header_up Origin https://probe.local
            header_up Sec-Fetch-Site same-origin
        }
    }
}
CADDY_EOF
else
  # 域名模式：配置自动 SSL 证书与双轨降级
  CADDY_SITE="$DOMAIN"
  [ "$WEB_PORT" != "443" ] && CADDY_SITE="${DOMAIN}:${WEB_PORT}"

  cat > /etc/caddy/Caddyfile << CADDY_EOF
{
    email admin@${DOMAIN}
}

$CADDY_SITE {
    # 代理管理 API（订阅、用户、节点等）
    handle /api/proxy/* {
        reverse_proxy 127.0.0.1:$PM_PORT
    }

    # 子节点安装脚本（由 proxy-manager 动态生成）
    handle /proxy-agent.sh {
        reverse_proxy 127.0.0.1:$PM_PORT
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
    redir /admin /admin/
    handle_path /admin* {
        root * $WEB_DIST
        try_files {path} /index.html
        file_server
    }

    # 探针主控（状态页 + WebSocket 心跳 + API）
    handle {
        reverse_proxy 127.0.0.1:$HUB_PORT
    }
}
CADDY_EOF
fi

systemctl daemon-reload
systemctl enable --force caddy.service 2>/dev/null || {
  mkdir -p /etc/systemd/system/multi-user.target.wants
  ln -sf /etc/systemd/system/caddy.service /etc/systemd/system/multi-user.target.wants/caddy.service
}
systemctl restart caddy.service
sleep 3
info "Caddy 已配置并启动"

# ---- 步骤 7: 初始化管理员账户 ----
header "步骤 7/8 · 初始化管理员账户"

# 等待 proxy-manager 初始化数据库及 proxy_user 表
_DB="$DATA/monitor.db"
for i in $(seq 1 30); do
  if [ -f "$_DB" ] && python3 -c "import sqlite3; conn=sqlite3.connect('$_DB'); conn.execute('SELECT id FROM proxy_user LIMIT 1'); conn.close()" 2>/dev/null; then
    break
  fi
  sleep 1
done

if [ -f "$_DB" ]; then
  ADMIN_PASS="$ADMIN_PASS" DB_PATH="$_DB" python3 - << 'PYEOF'
import os, sqlite3, hashlib, secrets
db_path = os.environ.get("DB_PATH", "/opt/monitor/data/monitor.db")
admin_pass = os.environ.get("ADMIN_PASS", "")
if not admin_pass:
    exit(0)

db = sqlite3.connect(db_path)
try:
    salt = secrets.token_hex(16)
    h = hashlib.sha256((salt + admin_pass).encode("utf-8")).hexdigest()
    pwd_hash = f"{salt}:{h}"
    db.execute("UPDATE proxy_user SET password_hash=? WHERE username='admin'", (pwd_hash,))

    # 同步设置 monitor-hub 的管理员应急密码哈希 (Argon2)
    try:
        from argon2 import PasswordHasher
        ph = PasswordHasher()
        argon_h = ph.hash(admin_pass)
        db.execute("CREATE TABLE IF NOT EXISTS setting (key TEXT PRIMARY KEY, value TEXT)")
        db.execute("INSERT OR REPLACE INTO setting (key, value) VALUES ('admin_password_hash', ?)", (argon_h,))
        db.execute("INSERT OR IGNORE INTO setting (key, value) VALUES ('site_name', 'HHUB')")
    except Exception as err:
        print(f"  [!] Argon2 哈希设置跳过: {err}")

    db.commit()
    print("  [+] 管理员密码已设置成功（统一密码即刻生效）")
except Exception as e:
    print(f"  [!] 管理员密码设置提示: {e}")
finally:
    db.close()
PYEOF
  systemctl restart proxy-manager
  systemctl restart monitor-hub
  sleep 1
else
  warn "数据库尚未就绪，请稍后在 /admin 手动设置密码"
fi

# ---- 步骤 8: 防火墙 ----
header "步骤 8/8 · 放行防火墙端口"

PORTS_TO_OPEN="80 443"
[ "$WEB_PORT" != "443" ] && [ "$WEB_PORT" != "80" ] && PORTS_TO_OPEN="80 443 $WEB_PORT"

for _PORT in $PORTS_TO_OPEN; do
  iptables -I INPUT -p tcp --dport "$_PORT" -j ACCEPT 2>/dev/null || true
  iptables -I INPUT -p udp --dport "$_PORT" -j ACCEPT 2>/dev/null || true
  command -v ufw >/dev/null 2>&1 && ufw allow "$_PORT" >/dev/null 2>&1 || true
  command -v firewall-cmd >/dev/null 2>&1 && \
    firewall-cmd --add-port="${_PORT}/tcp" --permanent 2>/dev/null || true
done
command -v firewall-cmd >/dev/null 2>&1 && firewall-cmd --reload 2>/dev/null || true
info "防火墙端口已放行 ($PORTS_TO_OPEN)"

# ---- 完成 ----
if [ "$IS_IP" = "1" ]; then
  SITE_SUFFIX=""
  [ "$WEB_PORT" != "80" ] && SITE_SUFFIX=":$WEB_PORT"
  DASH_URL="http://${DOMAIN}${SITE_SUFFIX}/"
  ADMIN_URL="http://${DOMAIN}${SITE_SUFFIX}/admin"
else
  SITE_SUFFIX=""
  [ "$WEB_PORT" != "443" ] && SITE_SUFFIX=":$WEB_PORT"
  DASH_URL="https://${DOMAIN}${SITE_SUFFIX}/"
  ADMIN_URL="https://${DOMAIN}${SITE_SUFFIX}/admin"
fi

echo ""
echo -e "${BOLD}${G}══════════════════════════════════════════════${N}"
echo -e "${BOLD}${G}  🎉  ProxyProbe 部署完成！${N}"
echo -e "${BOLD}${G}══════════════════════════════════════════════${N}"
echo ""
echo -e "  部署模式:           ${BOLD}${DEPLOY_MODE}${N}"
echo -e "  探针公开大屏:       ${C}${DASH_URL}${N}"
echo -e "  管理控制面板:       ${C}${ADMIN_URL}${N}"
echo ""
echo -e "  管理账号:           ${BOLD}admin${N}"
echo -e "  管理密码:           ${BOLD}${ADMIN_PASS}${N}"
echo ""
echo -e "  Web 外部访问端口:   ${BOLD}${WEB_PORT}${N}"
echo -e "  探针主控内部端口:   ${BOLD}${HUB_PORT}${N} (127.0.0.1 本地回环)"
echo -e "  代理管理内部端口:   ${BOLD}${PM_PORT}${N} (127.0.0.1 本地回环)"
echo ""
echo -e "${BOLD}${C}══════════════════════════════════════════════${N}"
echo -e "  ${BOLD}${C}✨ 快捷运维工具已安装！${N}"
echo -e "  在任意终端直接输入 ${BOLD}${G}hhub${N} 即可进入控制台："
echo -e "  • 一键无损升级系统 (代码/前端/核心二进制)"
echo -e "  • 修改 Web 外部访问端口 / 内部监听端口 / 绑定域名或 IP"
echo -e "  • 重置管理员登录密码"
echo -e "  • 实时查看服务运行日志 / 服务批量重启、停止、启动"
echo -e "  • SQLite 数据库备份与还原"
echo -e "  • 安全卸载与数据管理"
echo -e "${BOLD}${C}══════════════════════════════════════════════${N}"
echo ""
echo -e "  ${BOLD}下一步：${N}"
echo -e "  1. 访问 ${C}${ADMIN_URL}${N} 登录管理后台"
echo -e "  2. 在「服务器」页面添加子节点，复制一键安装指令"
echo -e "  3. 在「用户」页面创建代理用户"
echo ""
