#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ProxyProbe Fast Release Automation Pipeline (符合红线 1 与红线 2 规范)
用法：
  python scripts/fast_release.py [--version v2.5.xx] [--msg "release commit message"]
"""

import os
import sys
import shutil
import tarfile
import time
import argparse
import subprocess
import paramiko

BUILD_SERVER_IP = "189.24.108.25"
BUILD_SERVER_PORT = 22
BUILD_SERVER_USER = "root"
BUILD_SERVER_PASS = "Wzdsrs0301."

WORKSPACE_DIR = r"c:\Users\80009425\Desktop\大豆包\自定义"
RELEASE_DIR = r"c:\Users\80009425\Desktop\大豆包\ProxyProbe-Release"
LOCAL_PROXY = "http://127.0.0.1:7897"

def run_cmd(cmd_list, cwd=WORKSPACE_DIR, check=True):
    print(f"[*] 执行命令: {' '.join(cmd_list)} in {cwd}")
    res = subprocess.run(cmd_list, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    if check and res.returncode != 0:
        print(f"[!] 命令失败 (退出码 {res.returncode}):\n{res.stderr}\n{res.stdout}")
        sys.exit(res.returncode)
    return res

def package_frontend():
    print("\n[1/6] 构建并打包前端静态资源 (web-admin-dist.tar.gz)...")
    admin_dist = os.path.join(WORKSPACE_DIR, "server", "web-admin", "dist")
    if not os.path.exists(admin_dist) or not os.listdir(admin_dist):
        print("  正在执行 npm run build...")
        run_cmd(["npm", "run", "build"], cwd=os.path.join(WORKSPACE_DIR, "server", "web-admin"))
    
    # 严格确保无嵌套 dist 目录
    admin_tar = os.path.join(RELEASE_DIR, "web-admin-dist.tar.gz")
    with tarfile.open(admin_tar, "w:gz") as tar:
        for item in os.listdir(admin_dist):
            tar.add(os.path.join(admin_dist, item), arcname=item)
    print(f"  已生成 {admin_tar} ({os.path.getsize(admin_tar)} 字节)")
    shutil.copy2(admin_tar, os.path.join(WORKSPACE_DIR, "web-admin-dist.tar.gz"))

def compile_and_deploy_remote():
    print("\n[2/6] 连接 Linux 编译机，执行 PyInstaller 静态 ELF 机器码封装...")
    ssh = paramiko.SSHClient()
    ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh.connect(BUILD_SERVER_IP, port=BUILD_SERVER_PORT, username=BUILD_SERVER_USER, password=BUILD_SERVER_PASS, timeout=30)
    sftp = ssh.open_sftp()

    # 探测目标主目录
    stdin, stdout, stderr = ssh.exec_command("[ -d /opt/proxyprobe ] && echo '/opt/proxyprobe' || echo '/opt/monitor'")
    remote_root = stdout.read().decode('utf-8').strip() or "/opt/proxyprobe"

    # 上传核心代码
    sftp.put(os.path.join(WORKSPACE_DIR, "proxy_manager.py"), f"{remote_root}/proxy_manager.py")
    if os.path.exists(os.path.join(WORKSPACE_DIR, "license_guard.py")):
        sftp.put(os.path.join(WORKSPACE_DIR, "license_guard.py"), f"{remote_root}/license_guard.py")
    sftp.put(os.path.join(WORKSPACE_DIR, "VERSION"), f"{remote_root}/VERSION")
    
    # 远程编译
    print("  正在 Linux 环境编译 proxy-manager-linux-amd64 二进制 (约 35~45 秒)...")
    build_cmd = f"""
    cd {remote_root}
    rm -rf /tmp/dist/proxy-manager-linux-amd64 /tmp/build
    /opt/pybuild_venv/bin/pyinstaller --clean --onefile --workpath /tmp/build --distpath /tmp/dist --name proxy-manager-linux-amd64 --strip --hidden-import license_guard proxy_manager.py
    ls -lh /tmp/dist/proxy-manager-linux-amd64
    """
    stdin, stdout, stderr = ssh.exec_command(build_cmd)
    exit_status = stdout.channel.recv_exit_status()
    if exit_status != 0:
        err = stderr.read().decode('utf-8', errors='replace')
        print(f"[!] 编译失败:\n{err}")
        sys.exit(1)
    
    print("  编译成功！正在安装至测试机并验证服务状态...")
    install_cmd = f"""
    install -m 0755 /tmp/dist/proxy-manager-linux-amd64 {remote_root}/proxy-manager
    systemctl restart proxy-manager.service
    sleep 2
    systemctl is-active proxy-manager.service
    """
    stdin, stdout, stderr = ssh.exec_command(install_cmd)
    status_out = stdout.read().decode('utf-8', errors='replace').strip()
    print(f"  服务状态: {status_out}")
    if "active" not in status_out:
        print("[!] 警告: 服务重启后未处于 active 状态，请检查日志！")

    # 回传二进制到 Release 仓库 (使用独立干净通道避免空闲超时)
    print("  正在回传 15MB 编译后的二进制到 ProxyProbe-Release...")
    sftp.close()
    ssh.close()

    ssh_trans = paramiko.SSHClient()
    ssh_trans.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    ssh_trans.connect(BUILD_SERVER_IP, port=BUILD_SERVER_PORT, username=BUILD_SERVER_USER, password=BUILD_SERVER_PASS, timeout=30)
    sftp_trans = ssh_trans.open_sftp()
    local_bin = os.path.join(RELEASE_DIR, "proxy-manager-linux-amd64")
    last_print = [0]
    def progress(transferred, total):
        now = time.time()
        if now - last_print[0] > 1 or transferred == total:
            last_print[0] = now
            pct = round(transferred / total * 100, 1)
            print(f"    传输进度: {pct}% ({transferred}/{total} 字节)", flush=True)
    sftp_trans.get(f"{remote_root}/proxy-manager", local_bin, callback=progress, max_concurrent_prefetch_requests=8)
    print(f"  回传完成: {local_bin} ({os.path.getsize(local_bin)} 字节)")

    # 清理远程临时构建文件
    ssh_trans.exec_command("rm -rf /tmp/dist /tmp/build")
    sftp_trans.close()
    ssh_trans.close()

def sync_release_metadata():
    print("\n[3/6] 同步版本元数据与安装脚本到 Release 库...")
    for f in ["VERSION", "version.json", "CHANGELOG.md"]:
        src = os.path.join(WORKSPACE_DIR, f)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(RELEASE_DIR, f))
    for s in ["deploy-hub.sh", "hhub.sh", "install-hub.sh", "install.sh"]:
        src = os.path.join(WORKSPACE_DIR, "scripts", s)
        if os.path.exists(src):
            shutil.copy2(src, os.path.join(RELEASE_DIR, s))
    print("  版本描述、元数据与分发脚本已就绪。")

def verify_red_line_2():
    print("\n[4/6] 严格核验【红线 2】(公开安全发布库绝对零明文代码)...")
    forbidden_exts = ('.py', '.ts', '.tsx', '.rs', '.go', '.c', '.cpp', '.java')
    found = []
    for root, dirs, files in os.walk(RELEASE_DIR):
        if '.git' in root:
            continue
        for f in files:
            if f.lower().endswith(forbidden_exts):
                found.append(os.path.join(root, f))
    if found:
        print(f"[!] 致命安全违规：在 Release 仓库发现明文源码文件: {found}")
        sys.exit(1)
    print("  [PASS] 验证通过：Release 仓库 100% 纯二进制与静态产物，绝无源码泄露风险！")

def push_git_repositories(commit_msg):
    print(f"\n[5/6] 严格遵循【红线 1】双仓库同步原子推送: \"{commit_msg}\"...")
    
    # 1. 私有源码库推送
    print("  正在推送私有库 ProxyProbe...")
    run_cmd(["git", "add", "."], cwd=WORKSPACE_DIR)
    r = run_cmd(["git", "status", "--porcelain"], cwd=WORKSPACE_DIR)
    if r.stdout.strip():
        run_cmd(["git", "commit", "-m", commit_msg], cwd=WORKSPACE_DIR)
    run_cmd(["git", "-c", f"http.proxy={LOCAL_PROXY}", "push", "origin", "main"], cwd=WORKSPACE_DIR)
    print("  私有源码库 ProxyProbe 推送成功！")

    # 2. 公开安全发行库推送
    print("  正在推送公开发行库 ProxyProbe-Release (含二进制合并冲突自愈)...")
    run_cmd(["git", "add", "."], cwd=RELEASE_DIR)
    r2 = run_cmd(["git", "status", "--porcelain"], cwd=RELEASE_DIR)
    if r2.stdout.strip():
        run_cmd(["git", "commit", "-m", f"release: {commit_msg}"], cwd=RELEASE_DIR)
    
    # 拉取远端 rebase 防止冲突
    rebase_res = run_cmd(["git", "-c", f"http.proxy={LOCAL_PROXY}", "pull", "--rebase", "origin", "main"], cwd=RELEASE_DIR, check=False)
    if rebase_res.returncode != 0:
        print("  检测到 Release 仓库二进制合并冲突，自动采用本地最新编译产物覆盖解决...")
        run_cmd(["git", "checkout", "--theirs", "proxy-manager-linux-amd64"], cwd=RELEASE_DIR, check=False)
        run_cmd(["git", "add", "proxy-manager-linux-amd64"], cwd=RELEASE_DIR, check=False)
        run_cmd(["git", "-c", "core.editor=true", "rebase", "--continue"], cwd=RELEASE_DIR, check=False)
    
    run_cmd(["git", "-c", f"http.proxy={LOCAL_PROXY}", "push", "origin", "main"], cwd=RELEASE_DIR)
    print("  公开发行库 ProxyProbe-Release 推送成功！")

def main():
    parser = argparse.ArgumentParser(description="ProxyProbe 一键全自动发版流水线")
    parser.add_argument("--version", help="指定新版本号 (例如 v2.5.26)")
    parser.add_argument("--msg", default="版本发布与优化更新", help="Git 提交信息")
    parser.add_argument("--skip-compile", action="store_true", help="跳过远程编译直接发版")
    args = parser.parse_args()

    if args.version:
        v = args.version.strip()
        if not v.startswith("v"):
            v = "v" + v
        with open(os.path.join(WORKSPACE_DIR, "VERSION"), "w", encoding="utf-8") as f:
            f.write(v)
        print(f"[*] 版本号已更新为: {v}")

    start_time = time.time()
    package_frontend()
    if not args.skip_compile:
        compile_and_deploy_remote()
    else:
        print("\n[2/6] 跳过远程编译步骤 (复用当前已就绪的本地最新二进制)...")
    sync_release_metadata()
    verify_red_line_2()
    push_git_repositories(args.msg)
    cost = round(time.time() - start_time, 1)
    print(f"\n[6/6] 全自动发版成功完成！总计耗时: {cost} 秒。")

if __name__ == "__main__":
    main()
