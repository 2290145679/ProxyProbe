#!/usr/bin/env bash
# =============================================================================
# ProxyProbe 代理管理核心独立二进制编译脚本 (PyInstaller)
# 将 proxy_manager.py 编译为独立 Linux ELF 二进制程序，彻底杜绝源码泄露
# =============================================================================
set -e

echo "[+] 正在检查并安装编译依赖..."
if command -v apt-get >/dev/null 2>&1; then
  apt-get update -qq && apt-get install -y -qq python3-pip python3-venv binutils gcc python3-dev
elif command -v yum >/dev/null 2>&1; then
  yum install -y python3-pip binutils gcc python3-devel
fi

TMP_VENV="/tmp/pybuild_venv_$$"
rm -rf "$TMP_VENV"
python3 -m venv "$TMP_VENV"
"$TMP_VENV/bin/pip" install --upgrade pip -q
"$TMP_VENV/bin/pip" install pyinstaller -q

echo "[+] 正在将 proxy_manager.py 编译为独立二进制 ELF 机器码文件..."
"$TMP_VENV/bin/pyinstaller" \
  --clean \
  --onefile \
  --name proxy-manager \
  --strip \
  --hidden-import license_guard \
  proxy_manager.py

rm -rf "$TMP_VENV" build proxy-manager.spec
chmod +x dist/proxy-manager

echo "=================================================="
echo "  [+] 编译成功！"
echo "  产物路径: dist/proxy-manager"
echo "  文件大小: $(du -sh dist/proxy-manager | cut -f1)"
echo "  文件类型: $(file dist/proxy-manager | cut -d: -f2-)"
echo "=================================================="
