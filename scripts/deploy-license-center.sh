#!/usr/bin/env bash
# ==============================================================================
# ProxyProbe 商业许可证发布与管控中心 一键部署与管理脚本
# 项目主页: https://github.com/2290145679/ProxyProbe
# ==============================================================================
set -e

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
    die "请使用 root 用户或 sudo bash deploy-license-center.sh 运行此部署脚本"
fi

TARGET_DIR="/opt/license-center"
SERVICE_FILE="/etc/systemd/system/license-center.service"
PORT="${LICENSE_CENTER_PORT:-18888}"
DB_PATH="${LICENSE_CENTER_DB:-$TARGET_DIR/license_center.db}"

clear
echo -e "${BOLD}${C}"
echo "  ██████╗ ██████╗  ██████╗ ██╗  ██╗██╗   ██╗██████╗ ██████╗  ██████╗ ██████╗ ███████╗"
echo "  ██╔══██╗██╔══██╗██╔═══██╗╚██╗██╔╝╚██╗ ██╔╝██╔══██╗██╔══██╗██╔═══██╗██╔══██╗██╔════╝"
echo "  ██████╔╝██████╔╝██║   ██║ ╚███╔╝  ╚████╔╝ ██████╔╝██████╔╝██║   ██║██████╔╝█████╗  "
echo "  ██╔═══╝ ██╔══██╗██║   ██║ ██╔██╗   ╚██╔╝  ██╔═══╝ ██╔══██╗██║   ██║██╔══██╗██╔══╝  "
echo "  ██║     ██║  ██║╚██████╔╝██╔╝ ██╗   ██║   ██║     ██║  ██║╚██████╔╝██████╔╝███████╗"
echo "  ╚═╝     ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚═╝     ╚═╝  ╚═╝ ╚═════╝ ╚═════╝ ╚══════╝"
echo -e "${N}"
echo -e "  ${BOLD}ProxyProbe 商业许可证发布与管控中心 · 部署向导${N}"
rule

info "正在检查系统基础环境..."
if ! command -v python3 &>/dev/null; then
    warn "未检测到 Python 3，正在安装..."
    if command -v apt-get &>/dev/null; then
        apt-get update -qq && apt-get install -y -qq python3 python3-pip
    elif command -v yum &>/dev/null; then
        yum install -y -q python3 python3-pip
    else
        die "未能自动安装 Python3，请先手动安装"
    fi
fi

# 探测外网 IPv4
DETECTED_IP=$(curl -4 -s --connect-timeout 3 https://api.ipify.org 2>/dev/null || \
              curl -4 -s --connect-timeout 3 https://ifconfig.me 2>/dev/null || \
              ip -4 addr show scope global | grep -oP '(?<=inet\s)\d+(\.\d+){3}' | head -n 1 || echo "127.0.0.1")

mkdir -p "$TARGET_DIR"

info "正在安装/同步发号服务核心程序..."

# 若本地当前目录存在 server.py 则直接拷贝，否则从私有/当前脚本源拉取
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [ -f "$SCRIPT_DIR/../license-center/server.py" ]; then
    cp -f "$SCRIPT_DIR/../license-center/server.py" "$TARGET_DIR/server.py"
elif [ -f "$SCRIPT_DIR/server.py" ]; then
    cp -f "$SCRIPT_DIR/server.py" "$TARGET_DIR/server.py"
fi

if [ ! -f "$TARGET_DIR/server.py" ]; then
    die "未找到 server.py 发号服务端代码，请确保文件存在"
fi

chmod 755 "$TARGET_DIR/server.py"

info "正在配置 Systemd 守护单元 (${SERVICE_FILE})..."
cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=ProxyProbe Commercial License Management Center
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=$TARGET_DIR
ExecStart=/usr/bin/python3 $TARGET_DIR/server.py
Restart=always
RestartSec=5
Environment=LICENSE_CENTER_PORT=$PORT
Environment=LICENSE_CENTER_DB=$DB_PATH

[Install]
WantedBy=multi-user.target
EOF

info "重载系统服务并启动发号管控中心..."
systemctl daemon-reload
systemctl enable license-center.service --quiet
systemctl restart license-center.service

sleep 1

if systemctl is-active --quiet license-center.service; then
    info "商业许可证发布与管控中心启动成功！"
    echo ""
    rule
    echo -e "${BOLD}${G}🎉 ProxyProbe 商业许可证发布中心搭建完毕！${N}"
    rule
    echo -e "  服务端口:     ${BOLD}${PORT}${N}"
    echo -e "  数据存储:     ${BOLD}${DB_PATH}${N}"
    echo -e "  在线访问地址: ${C}${BOLD}http://${DETECTED_IP}:${PORT}${N}"
    echo -e "  服务状态:     ${G}● 运行中 (Active)${N}"
    rule
    echo -e "  查看服务日志: ${BOLD}journalctl -u license-center -f${N}"
    echo -e "  重启服务命令: ${BOLD}systemctl restart license-center${N}"
    rule
else
    err "服务启动失败，请检查运行日志: journalctl -u license-center -e --no-pager"
    exit 1
fi
