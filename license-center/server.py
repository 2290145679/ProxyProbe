#!/usr/bin/env python3
"""
ProxyProbe 商业许可证发号与在线管控中心 (License Management Center)
Copyright (c) 2026 ProxyProbe Contributors
"""

import os
import sys
import json
import time
import base64
import sqlite3
import hashlib
import secrets
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# 加载密码学库 (支持 cryptography 或内置 Ed25519 签名)
try:
    from cryptography.hazmat.primitives.asymmetric import ed25519
    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False

PORT = int(os.environ.get("LICENSE_CENTER_PORT", 18888))
DB_PATH = os.environ.get("LICENSE_CENTER_DB", "/opt/license-center/license_center.db")
ADMIN_TOKEN = os.environ.get("LICENSE_ADMIN_TOKEN", "AJIBpq8GNNJeL*fyWV")

# 官方发号主私钥 (必须严格保密)
MASTER_PRIVATE_KEY_HEX = "875cf2bcc0c92bb602eb6c150693ed1e308321f803b7cbf3674ec028ebea0ff3"
MASTER_PUBLIC_KEY_HEX = "6637fdfd836e83fd31aa7c02698ab615d882bdb7533aaf2f83359480a1a5a4c3"

# =============================================================================
# 套餐规格标准定义 (Server / Node / User)
# 免费版: 1 / 1 / 1
# 1. 星尘: 3 / 6 / 6
# 2. 行星: 5 / 12 / 12
# 3. 恒星: 8 / 18 / 18
# 4. 星系: 12 / 30 / 30
# 5. 宇宙: 20 / 50 / 50
# =============================================================================
PLAN_CONFIGS = {
    "stardust": {
        "name": "星尘套餐",
        "badge": "星尘",
        "tag": "入门首选",
        "max_servers": 3,
        "max_nodes": 6,
        "max_users": 6,
        "spec": "3服 · 6节 · 6户",
        "theme": "cyan"
    },
    "planet": {
        "name": "行星套餐",
        "badge": "行星",
        "tag": "推荐热销",
        "max_servers": 5,
        "max_nodes": 12,
        "max_users": 12,
        "spec": "5服 · 12节 · 12户",
        "theme": "emerald"
    },
    "star": {
        "name": "恒星套餐",
        "badge": "恒星",
        "tag": "高性价比",
        "max_servers": 8,
        "max_nodes": 18,
        "max_users": 18,
        "spec": "8服 · 18节 · 18户",
        "theme": "amber"
    },
    "galaxy": {
        "name": "星系套餐",
        "badge": "星系",
        "tag": "团队首选",
        "max_servers": 12,
        "max_nodes": 30,
        "max_users": 30,
        "spec": "12服 · 30节 · 30户",
        "theme": "indigo"
    },
    "universe": {
        "name": "宇宙套餐",
        "badge": "宇宙",
        "tag": "旗舰至尊",
        "max_servers": 20,
        "max_nodes": 50,
        "max_users": 50,
        "spec": "20服 · 50节 · 50户",
        "theme": "purple"
    }
}


# =============================================================================
# Ed25519 签名实现
# =============================================================================
def sign_payload(payload_bytes: bytes) -> bytes:
    priv_bytes = bytes.fromhex(MASTER_PRIVATE_KEY_HEX)
    if _HAS_CRYPTO:
        priv = ed25519.Ed25519PrivateKey.from_private_bytes(priv_bytes)
        return priv.sign(payload_bytes)
    else:
        raise RuntimeError("请在服务器上安装 python3-cryptography: apt-get install -y python3-cryptography")


def generate_license_string(payload: dict) -> str:
    payload_json = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode("utf-8")
    sig = sign_payload(payload_json)
    p_b64 = base64.urlsafe_b64encode(payload_json).decode("utf-8").rstrip("=")
    s_b64 = base64.urlsafe_b64encode(sig).decode("utf-8").rstrip("=")
    return f"PPLIC-{p_b64}.{s_b64}"


# =============================================================================
# 数据库管理
# =============================================================================
def get_db():
    os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()
    with conn:
        conn.execute("""
        CREATE TABLE IF NOT EXISTS licenses (
            id TEXT PRIMARY KEY,
            customer TEXT,
            machine_id TEXT,
            plan_type TEXT,
            max_servers INTEGER DEFAULT 1,
            max_nodes INTEGER DEFAULT 1,
            max_users INTEGER DEFAULT 1,
            issued_at INTEGER,
            expire_at INTEGER,
            license_key TEXT,
            status TEXT DEFAULT 'active',
            last_ping_ip TEXT DEFAULT '',
            last_ping_at INTEGER DEFAULT 0,
            note TEXT DEFAULT ''
        )
        """)
        cursor = conn.execute("PRAGMA table_info(licenses)")
        columns = [row[1] for row in cursor.fetchall()]
        if "max_servers" not in columns:
            conn.execute("ALTER TABLE licenses ADD COLUMN max_servers INTEGER DEFAULT 1")
        if "max_users" not in columns:
            conn.execute("ALTER TABLE licenses ADD COLUMN max_users INTEGER DEFAULT 1")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_lic_mid ON licenses(machine_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_lic_status ON licenses(status)")
    conn.close()


# =============================================================================
# 前端 HTML (旗舰重构 · 极简暗黑 Linear/Vercel 级设计 · 完美手机自适应 · 全无原生弹窗)
# =============================================================================
DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="zh-CN" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
  <title>ProxyProbe · 商业许可证中心</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      darkMode: 'class',
      theme: {
        extend: {
          colors: {
            app: {
              bg: '#090a0f',
              card: '#12141c',
              hover: '#181b26',
              border: '#202433',
              subtle: '#2d3345',
            }
          }
        }
      }
    }
  </script>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600&display=swap');
    
    * {
      -webkit-tap-highlight-color: transparent;
    }
    body {
      background-color: #090a0f;
      color: #f1f5f9;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "PingFang SC", "Noto Sans SC", sans-serif;
      overflow-x: hidden;
    }
    .mono {
      font-family: 'JetBrains Mono', monospace;
    }
    .app-card {
      background: #12141c;
      border: 1px solid #202433;
    }
    .app-input {
      background: #0d0f17;
      border: 1px solid #242938;
      color: #ffffff;
      outline: none;
      transition: all 0.15s ease;
    }
    .app-input:focus {
      border-color: #6366f1;
      box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.2);
    }
    /* 现代 Toast 动画 */
    @keyframes toastIn {
      from { opacity: 0; transform: translate(-50%, 20px); }
      to { opacity: 1; transform: translate(-50%, 0); }
    }
    .toast-anim {
      animation: toastIn 0.2s cubic-bezier(0.16, 1, 0.3, 1) forwards;
    }
  </style>
</head>
<body class="min-h-screen antialiased flex flex-col justify-between">

  <!-- 顶部悬浮 Toast 消息容器 -->
  <div id="toast" class="fixed bottom-6 left-1/2 -translate-x-1/2 z-50 pointer-events-none hidden">
    <div id="toast-inner" class="toast-anim px-4 py-2.5 rounded-xl bg-zinc-900/95 border border-zinc-700/80 text-white text-xs font-medium shadow-2xl flex items-center gap-2 backdrop-blur-md">
      <span id="toast-icon">✓</span>
      <span id="toast-msg">已复制</span>
    </div>
  </div>

  <!-- 主体容器 -->
  <div class="max-w-5xl w-full mx-auto p-4 sm:p-6 lg:p-8 space-y-5">

    <!-- 顶部导航栏 -->
    <header class="flex items-center justify-between gap-3 pb-4 border-b border-app-border">
      <div class="flex items-center gap-3">
        <div class="size-9 rounded-xl bg-gradient-to-br from-indigo-500 to-indigo-700 flex items-center justify-center text-white font-bold text-sm shadow-md shadow-indigo-500/20">
          <svg class="size-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
          </svg>
        </div>
        <div>
          <div class="flex items-center gap-2">
            <h1 class="text-base sm:text-lg font-bold text-white tracking-tight">ProxyProbe 许可证中心</h1>
            <span class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
              <span class="size-1.5 rounded-full bg-emerald-400 animate-pulse mr-1.5"></span> 在线发号
            </span>
          </div>
          <p class="text-xs text-zinc-400">Ed25519 双轨签名与实时吊销管控系统</p>
        </div>
      </div>

      <div class="flex items-center gap-2">
        <button onclick="loadLicenses()" class="p-2 border border-app-border hover:bg-app-hover rounded-xl text-zinc-300 text-xs transition active:scale-95" title="刷新列表">
          <svg class="size-4" id="refresh-icon" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
          </svg>
        </button>
        <button onclick="openModal()" class="px-3.5 py-2 bg-indigo-600 hover:bg-indigo-500 text-white font-medium text-xs rounded-xl flex items-center gap-1.5 shadow-lg shadow-indigo-600/30 transition active:scale-95">
          <svg class="size-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 4v16m8-8H4" />
          </svg>
          <span>生成新许可证</span>
        </button>
      </div>
    </header>

    <!-- 4 个核心统计指标 (Bento 风格卡片) -->
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-3">
      <div class="app-card rounded-xl p-3.5 flex flex-col justify-between">
        <div class="flex items-center justify-between text-xs text-zinc-400">
          <span>累计签发</span>
          <span class="text-zinc-500">Total</span>
        </div>
        <div class="text-2xl font-bold mono text-white mt-2" id="stat-total">0</div>
      </div>

      <div class="app-card rounded-xl p-3.5 flex flex-col justify-between">
        <div class="flex items-center justify-between text-xs text-emerald-400">
          <span>有效授权</span>
          <span class="size-2 rounded-full bg-emerald-500"></span>
        </div>
        <div class="text-2xl font-bold mono text-emerald-400 mt-2" id="stat-active">0</div>
      </div>

      <div class="app-card rounded-xl p-3.5 flex flex-col justify-between">
        <div class="flex items-center justify-between text-xs text-rose-400">
          <span>已吊销冻结</span>
          <span class="size-2 rounded-full bg-rose-500"></span>
        </div>
        <div class="text-2xl font-bold mono text-rose-400 mt-2" id="stat-revoked">0</div>
      </div>

      <div class="app-card rounded-xl p-3.5 flex flex-col justify-between">
        <div class="flex items-center justify-between text-xs text-cyan-400">
          <span>24H心跳活跃</span>
          <span class="size-2 rounded-full bg-cyan-500 animate-pulse"></span>
        </div>
        <div class="text-2xl font-bold mono text-cyan-400 mt-2" id="stat-online">0</div>
      </div>
    </div>

    <!-- 搜索与筛选工具栏 -->
    <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
      <div class="relative flex-1">
        <svg class="size-4 absolute left-3.5 top-1/2 -translate-y-1/2 text-zinc-500" fill="none" viewBox="0 0 24 24" stroke="currentColor">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
        </svg>
        <input id="search-input" oninput="filterLicenses()" type="text" placeholder="搜索客户备注、机器码、套餐规格..." class="app-input w-full text-xs rounded-xl pl-9 pr-3.5 py-2 placeholder:text-zinc-500" />
      </div>

      <!-- 快速状态过滤 Pills -->
      <div class="flex items-center gap-1.5 self-start sm:self-auto shrink-0">
        <button onclick="setFilter('all', this)" class="filter-btn px-2.5 py-1.5 rounded-lg text-xs font-medium bg-app-card border border-indigo-500/50 text-indigo-300">全部</button>
        <button onclick="setFilter('active', this)" class="filter-btn px-2.5 py-1.5 rounded-lg text-xs font-medium bg-app-card border border-app-border text-zinc-400 hover:text-zinc-200">生效中</button>
        <button onclick="setFilter('revoked', this)" class="filter-btn px-2.5 py-1.5 rounded-lg text-xs font-medium bg-app-card border border-app-border text-zinc-400 hover:text-zinc-200">已吊销</button>
        <span id="list-count" class="text-xs text-zinc-500 mono ml-1">共 0 条</span>
      </div>
    </div>

    <!-- 桌面端表格视图 (屏幕 >= 768px 显示) -->
    <div class="hidden md:block app-card rounded-xl overflow-hidden shadow-sm">
      <table class="w-full text-left text-xs">
        <thead class="bg-app-bg border-b border-app-border text-zinc-400 text-[11px] uppercase tracking-wider">
          <tr>
            <th class="py-3 px-4 font-semibold">客户备注</th>
            <th class="py-3 px-4 font-semibold">授权套餐</th>
            <th class="py-3 px-4 font-semibold">配额 (服/节/户)</th>
            <th class="py-3 px-4 font-semibold">绑定机器码</th>
            <th class="py-3 px-4 font-semibold">有效期限</th>
            <th class="py-3 px-4 font-semibold">状态</th>
            <th class="py-3 px-4 font-semibold text-right">操作</th>
          </tr>
        </thead>
        <tbody id="desktop-tbody" class="divide-y divide-app-border mono text-[11px]">
          <tr><td colspan="7" class="py-12 text-center text-zinc-500 font-sans">正在加载许可证数据...</td></tr>
        </tbody>
      </table>
    </div>

    <!-- 移动端卡片式流视图 (屏幕 < 768px 显示，极简清晰，完全零横向滚动) -->
    <div id="mobile-cards" class="md:hidden space-y-3">
      <div class="py-12 text-center text-xs text-zinc-500">正在加载数据...</div>
    </div>

  </div>

  <!-- 底部微版权 -->
  <footer class="py-4 text-center text-[11px] text-zinc-600 border-t border-app-border/40">
    ProxyProbe License Engine · 双轨混合鉴权架构
  </footer>

  <!-- 签发新许可证 Modal 弹窗 -->
  <div id="modal" class="fixed inset-0 bg-black/80 backdrop-blur-md hidden flex items-center justify-center p-3.5 z-50">
    <div class="app-card rounded-2xl max-w-lg w-full p-5 sm:p-6 space-y-4 shadow-2xl border-app-border max-h-[94vh] overflow-y-auto">
      
      <div class="flex items-center justify-between border-b border-app-border pb-3.5">
        <div>
          <h3 class="text-sm sm:text-base font-bold text-white">签发商业许可证</h3>
          <p class="text-xs text-zinc-400 mt-0.5">选择商业套餐并使用官方 Ed25519 私钥签名</p>
        </div>
        <button onclick="closeModal()" class="text-zinc-400 hover:text-white p-1 rounded-lg">
          <svg class="size-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      <form id="gen-form" onsubmit="handleGenerate(event)" class="space-y-4 text-xs font-sans">
        <!-- 客户备注 -->
        <div>
          <label class="block text-zinc-300 font-medium mb-1">客户姓名 / 备注标识</label>
          <input id="input-customer" type="text" required placeholder="如：VIP客户-老王、某某科技" class="app-input w-full rounded-xl px-3.5 py-2 text-xs" />
        </div>

        <!-- 机器识别码 -->
        <div>
          <div class="flex items-center justify-between mb-1">
            <label class="text-zinc-300 font-medium">目标机器识别码 (Machine ID)</label>
            <button type="button" onclick="setAnyMachine()" class="text-indigo-400 hover:text-indigo-300 text-[11px] font-medium flex items-center gap-1">
              <svg class="size-3" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M13.828 10.172a4 4 0 00-5.656 0l-4 4a4 4 0 105.656 5.656l1.102-1.101m-.758-4.899a4 4 0 005.656 0l4-4a4 4 0 00-5.656-5.656l-1.1 1.1" />
              </svg>
              一键设为全网通 ANY
            </button>
          </div>
          <input id="input-mid" type="text" required placeholder="如：PP-8A3F-9B12-4C67" class="app-input w-full rounded-xl px-3.5 py-2 font-mono uppercase text-xs" />
        </div>

        <!-- 5 大套餐选择 (卡片药丸) -->
        <div>
          <label class="block text-zinc-300 font-medium mb-1.5">选择商业套餐</label>
          <div class="grid grid-cols-2 sm:grid-cols-3 gap-2" id="plan-selector">
            <!-- 动态生成 -->
          </div>
          <input type="hidden" id="input-plan" value="planet" />
        </div>

        <!-- 有效期选择 -->
        <div>
          <label class="block text-zinc-300 font-medium mb-1.5">授权有效期</label>
          <div class="grid grid-cols-4 gap-2">
            <button type="button" onclick="selectDuration(30, this)" class="dur-btn py-2 rounded-xl border border-app-border bg-app-bg text-zinc-400 text-center text-xs">1 个月</button>
            <button type="button" onclick="selectDuration(90, this)" class="dur-btn py-2 rounded-xl border border-app-border bg-app-bg text-zinc-400 text-center text-xs">3 个月</button>
            <button type="button" onclick="selectDuration(365, this)" class="dur-btn py-2 rounded-xl border-indigo-500 bg-indigo-500/10 text-indigo-300 font-semibold text-center text-xs">1 年</button>
            <button type="button" onclick="selectDuration(0, this)" class="dur-btn py-2 rounded-xl border border-app-border bg-app-bg text-zinc-400 text-center text-xs">永久买断</button>
          </div>
          <input type="hidden" id="input-duration" value="365" />
        </div>

        <div class="pt-2 flex justify-end gap-2.5 border-t border-app-border">
          <button type="button" onclick="closeModal()" class="px-4 py-2 border border-app-border hover:bg-app-hover text-zinc-300 rounded-xl text-xs">取消</button>
          <button type="submit" id="btn-submit" class="px-5 py-2 bg-indigo-600 hover:bg-indigo-500 text-white font-semibold rounded-xl text-xs shadow-lg shadow-indigo-600/30 transition active:scale-95 flex items-center gap-1.5">
            <span>签名并立即签发</span>
          </button>
        </div>
      </form>

      <!-- 签发成功结果 -->
      <div id="gen-result" class="hidden space-y-3 pt-3.5 border-t border-app-border">
        <div class="flex items-center justify-between text-xs text-emerald-400 font-medium">
          <span class="flex items-center gap-1">
            <svg class="size-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
              <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7" />
            </svg>
            许可证已成功签名入库
          </span>
          <span id="result-plan-tag" class="text-[11px] text-zinc-400"></span>
        </div>
        <textarea id="result-key" readonly class="app-input w-full h-20 mono text-[11px] p-3 rounded-xl select-all resize-none"></textarea>
        <button onclick="copyResult()" id="btn-copy" class="w-full py-2.5 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold rounded-xl text-xs transition flex items-center justify-center gap-1.5">
          <svg class="size-4" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2v-1M8 5a2 2 0 002 2h2a2 2 0 002-2M8 5a2 2 0 012-2h2a2 2 0 012 2m0 0h2a2 2 0 012 2v3m2 4H10m0 0l3-3m-3 3l3 3" />
          </svg>
          一键复制许可证密钥
        </button>
      </div>
    </div>
  </div>

  <!-- 吊销确认 Modal 弹窗 (告别原生 confirm) -->
  <div id="confirm-modal" class="fixed inset-0 bg-black/80 backdrop-blur-md hidden flex items-center justify-center p-4 z-50">
    <div class="app-card rounded-2xl max-w-sm w-full p-5 space-y-4 shadow-2xl border-app-border text-xs">
      <div class="flex items-start gap-3">
        <div class="size-10 rounded-full bg-rose-500/10 text-rose-400 flex items-center justify-center shrink-0 border border-rose-500/20">
          <svg class="size-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        </div>
        <div>
          <h4 class="text-sm font-bold text-white" id="confirm-title">确认吊销许可证</h4>
          <p class="text-zinc-400 mt-1" id="confirm-desc">吊销后客户端在下次心跳时将立即被停用所有代理节点功能。</p>
        </div>
      </div>
      <div class="flex justify-end gap-2 pt-2 border-t border-app-border">
        <button onclick="closeConfirmModal()" class="px-3.5 py-1.5 border border-app-border hover:bg-app-hover text-zinc-300 rounded-xl text-xs">取消</button>
        <button id="confirm-ok-btn" class="px-4 py-1.5 bg-rose-600 hover:bg-rose-500 text-white font-semibold rounded-xl text-xs transition">确认吊销</button>
      </div>
    </div>
  </div>

  <script>
    const PLANS = """ + json.dumps(PLAN_CONFIGS, ensure_ascii=False) + """;
    let allLicenses = [];
    let currentFilter = 'all';

    // 提示 Toast 消息工具
    function showToast(msg, isError = false) {
      const toast = document.getElementById('toast');
      const toastInner = document.getElementById('toast-inner');
      const toastMsg = document.getElementById('toast-msg');
      const toastIcon = document.getElementById('toast-icon');

      toastMsg.innerText = msg;
      toastIcon.innerText = isError ? '✕' : '✓';
      toastInner.className = isError 
        ? 'toast-anim px-4 py-2 rounded-xl bg-rose-950 border border-rose-800 text-rose-200 text-xs font-medium shadow-2xl flex items-center gap-2'
        : 'toast-anim px-4 py-2 rounded-xl bg-zinc-900 border border-zinc-700 text-zinc-100 text-xs font-medium shadow-2xl flex items-center gap-2';

      toast.classList.remove('hidden');
      clearTimeout(window._toastTimer);
      window._toastTimer = setTimeout(() => {
        toast.classList.add('hidden');
      }, 2200);
    }

    // 渲染套餐选择卡片
    function renderPlanSelector() {
      const container = document.getElementById('plan-selector');
      container.innerHTML = Object.entries(PLANS).map(([key, p]) => `
        <button type="button" onclick="selectPlan('${key}', this)" class="plan-card p-2.5 rounded-xl border text-left transition ${key === 'planet' ? 'border-indigo-500 bg-indigo-500/10 text-white' : 'border-app-border bg-app-bg text-zinc-400'}">
          <div class="flex items-center justify-between mb-1">
            <span class="font-bold text-xs text-white">${p.name}</span>
            <span class="text-[9px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 font-mono">${p.badge}</span>
          </div>
          <div class="text-[10px] text-zinc-400 mono">${p.spec}</div>
        </button>
      `).join('');
    }

    function selectPlan(key, btn) {
      document.getElementById('input-plan').value = key;
      document.querySelectorAll('.plan-card').forEach(b => {
        b.className = 'plan-card p-2.5 rounded-xl border border-app-border bg-app-bg text-zinc-400 text-left transition';
      });
      btn.className = 'plan-card p-2.5 rounded-xl border border-indigo-500 bg-indigo-500/10 text-white text-left transition';
    }

    function selectDuration(days, btn) {
      document.getElementById('input-duration').value = days;
      document.querySelectorAll('.dur-btn').forEach(b => {
        b.className = 'dur-btn py-2 rounded-xl border border-app-border bg-app-bg text-zinc-400 text-center text-xs';
      });
      btn.className = 'dur-btn py-2 rounded-xl border-indigo-500 bg-indigo-500/10 text-indigo-300 font-semibold text-center text-xs';
    }

    async function loadLicenses() {
      const icon = document.getElementById('refresh-icon');
      if (icon) icon.classList.add('animate-spin');
      try {
        const res = await fetch('/api/v1/license/list');
        const data = await res.json();
        allLicenses = data.licenses || [];
        renderAll();
      } catch (err) {
        showToast('获取列表失败', true);
      } finally {
        if (icon) setTimeout(() => icon.classList.remove('animate-spin'), 350);
      }
    }

    function setFilter(filter, btn) {
      currentFilter = filter;
      document.querySelectorAll('.filter-btn').forEach(b => {
        b.className = 'filter-btn px-2.5 py-1.5 rounded-lg text-xs font-medium bg-app-card border border-app-border text-zinc-400 hover:text-zinc-200';
      });
      btn.className = 'filter-btn px-2.5 py-1.5 rounded-lg text-xs font-medium bg-app-card border border-indigo-500/50 text-indigo-300';
      filterLicenses();
    }

    function filterLicenses() {
      const q = document.getElementById('search-input').value.trim().toLowerCase();
      let list = allLicenses;

      if (currentFilter === 'active') {
        list = list.filter(l => l.status === 'active');
      } else if (currentFilter === 'revoked') {
        list = list.filter(l => l.status === 'revoked');
      }

      if (q) {
        list = list.filter(l => 
          (l.customer || '').toLowerCase().includes(q) ||
          (l.machine_id || '').toLowerCase().includes(q) ||
          (l.plan_type || '').toLowerCase().includes(q) ||
          (l.id || '').toLowerCase().includes(q)
        );
      }

      renderList(list);
    }

    function renderAll() {
      let active = 0, revoked = 0, online = 0;
      const now = Math.floor(Date.now() / 1000);

      allLicenses.forEach(lic => {
        if (lic.status === 'active') active++;
        if (lic.status === 'revoked') revoked++;
        if (lic.last_ping_at && (now - lic.last_ping_at) < 86400) online++;
      });

      document.getElementById('stat-total').innerText = allLicenses.length;
      document.getElementById('stat-active').innerText = active;
      document.getElementById('stat-revoked').innerText = revoked;
      document.getElementById('stat-online').innerText = online;

      filterLicenses();
    }

    function renderList(list) {
      document.getElementById('list-count').innerText = `共 ${list.length} 条`;
      const now = Math.floor(Date.now() / 1000);

      renderDesktop(list, now);
      renderMobile(list, now);
    }

    // 1. 桌面端表格渲染
    function renderDesktop(list, now) {
      const tbody = document.getElementById('desktop-tbody');
      if (list.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="py-12 text-center text-zinc-500 font-sans">暂无数据记录</td></tr>';
        return;
      }

      tbody.innerHTML = list.map(lic => {
        const isExpired = lic.expire_at > 0 && now > lic.expire_at;
        const statusBadge = lic.status === 'revoked'
          ? '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] bg-rose-500/10 text-rose-400 border border-rose-500/20 font-sans"><span class="size-1 rounded-full bg-rose-400 mr-1.5"></span>已吊销</span>'
          : (isExpired 
            ? '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] bg-amber-500/10 text-amber-400 border border-amber-500/20 font-sans">已过期</span>'
            : '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 font-sans"><span class="size-1 rounded-full bg-emerald-400 mr-1.5"></span>生效中</span>');

        const expText = lic.expire_at === 0 ? '永久买断' : new Date(lic.expire_at * 1000).toLocaleDateString('zh-CN');
        const plan = PLANS[lic.plan_type] || { name: lic.plan_type, max_servers: lic.max_servers || 1, max_nodes: lic.max_nodes || 1, max_users: lic.max_users || 1 };
        const maxServers = lic.max_servers || plan.max_servers;
        const maxNodes = lic.max_nodes || plan.max_nodes;
        const maxUsers = lic.max_users || plan.max_users;

        return `
          <tr class="hover:bg-app-hover/50 transition">
            <td class="py-3 px-4 font-sans">
              <div class="font-medium text-white">${lic.customer}</div>
              <div class="text-[10px] text-zinc-500 mono">${lic.id}</div>
            </td>
            <td class="py-3 px-4 font-sans text-zinc-300">
              <span class="px-2 py-0.5 rounded-md bg-app-card border border-app-border text-[11px] font-medium">${plan.name}</span>
            </td>
            <td class="py-3 px-4 mono text-zinc-300">
              <span class="text-cyan-400">${maxServers}</span>服 / 
              <span class="text-emerald-400">${maxNodes}</span>节 / 
              <span class="text-amber-400">${maxUsers}</span>户
            </td>
            <td class="py-3 px-4 mono text-zinc-400 select-all">${lic.machine_id}</td>
            <td class="py-3 px-4 font-sans text-zinc-400">${expText}</td>
            <td class="py-3 px-4">${statusBadge}</td>
            <td class="py-3 px-4 text-right space-x-1.5 font-sans">
              <button onclick="copyLic('${lic.license_key}')" class="px-2.5 py-1 bg-app-card hover:bg-app-hover border border-app-border text-zinc-300 rounded-lg text-[11px] transition">
                复制密钥
              </button>
              ${lic.status === 'active'
                ? `<button onclick="confirmAction('${lic.id}', 'revoke')" class="px-2.5 py-1 text-rose-400 hover:bg-rose-950/30 border border-rose-900/40 rounded-lg text-[11px] transition">吊销</button>`
                : `<button onclick="confirmAction('${lic.id}', 'unrevoke')" class="px-2.5 py-1 text-emerald-400 hover:bg-emerald-950/30 border border-emerald-900/40 rounded-lg text-[11px] transition">恢复</button>`
              }
            </td>
          </tr>
        `;
      }).join('');
    }

    // 2. 移动端自适应卡片流 (极简视觉，全屏幕无横向拖动)
    function renderMobile(list, now) {
      const container = document.getElementById('mobile-cards');
      if (list.length === 0) {
        container.innerHTML = '<div class="app-card rounded-xl p-8 text-center text-xs text-zinc-500">暂无数据记录</div>';
        return;
      }

      container.innerHTML = list.map(lic => {
        const isExpired = lic.expire_at > 0 && now > lic.expire_at;
        const statusBadge = lic.status === 'revoked'
          ? '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] bg-rose-500/10 text-rose-400 border border-rose-500/20"><span class="size-1 rounded-full bg-rose-400 mr-1.5"></span>已吊销</span>'
          : (isExpired 
            ? '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] bg-amber-500/10 text-amber-400 border border-amber-500/20">已过期</span>'
            : '<span class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20"><span class="size-1 rounded-full bg-emerald-400 mr-1.5"></span>生效中</span>');

        const expText = lic.expire_at === 0 ? '永久' : new Date(lic.expire_at * 1000).toLocaleDateString('zh-CN');
        const plan = PLANS[lic.plan_type] || { name: lic.plan_type, max_servers: lic.max_servers || 1, max_nodes: lic.max_nodes || 1, max_users: lic.max_users || 1 };
        const maxServers = lic.max_servers || plan.max_servers;
        const maxNodes = lic.max_nodes || plan.max_nodes;
        const maxUsers = lic.max_users || plan.max_users;

        return `
          <div class="app-card rounded-xl p-4 space-y-2.5">
            <div class="flex items-center justify-between">
              <div>
                <span class="font-bold text-sm text-white">${lic.customer}</span>
                <span class="text-[10px] text-zinc-500 mono ml-1.5">#${lic.id.slice(-6)}</span>
              </div>
              ${statusBadge}
            </div>

            <div class="flex items-center justify-between text-xs">
              <span class="px-2 py-0.5 rounded-md bg-app-bg border border-app-border text-zinc-300 font-medium">
                ${plan.name} · <strong class="mono text-indigo-400">${maxServers}服/${maxNodes}节/${maxUsers}户</strong>
              </span>
              <span class="text-zinc-400">${expText}</span>
            </div>

            <div class="text-[11px] mono text-zinc-400 bg-app-bg rounded-lg px-2.5 py-1.5 flex items-center justify-between border border-app-border/60">
              <span class="truncate mr-2 select-all">${lic.machine_id}</span>
              <span class="text-[10px] text-zinc-500 shrink-0">${lic.last_ping_at ? '已打卡' : '暂未打卡'}</span>
            </div>

            <div class="flex items-center gap-2 pt-2 border-t border-app-border/70">
              <button onclick="copyLic('${lic.license_key}')" class="flex-1 py-1.5 bg-app-bg hover:bg-app-hover border border-app-border text-zinc-200 rounded-lg text-xs font-medium transition active:scale-95">
                复制密钥
              </button>
              ${lic.status === 'active'
                ? `<button onclick="confirmAction('${lic.id}', 'revoke')" class="px-4 py-1.5 text-rose-400 hover:bg-rose-950/30 border border-rose-900/40 rounded-lg text-xs font-medium transition active:scale-95">吊销</button>`
                : `<button onclick="confirmAction('${lic.id}', 'unrevoke')" class="px-4 py-1.5 text-emerald-400 hover:bg-emerald-950/30 border border-emerald-900/40 rounded-lg text-xs font-medium transition active:scale-95">恢复</button>`
              }
            </div>
          </div>
        `;
      }).join('');
    }

    function openModal() {
      document.getElementById('modal').classList.remove('hidden');
      document.getElementById('gen-result').classList.add('hidden');
      document.getElementById('input-customer').value = '';
      document.getElementById('input-mid').value = '';
    }

    function closeModal() {
      document.getElementById('modal').classList.add('hidden');
    }

    function setAnyMachine() {
      document.getElementById('input-mid').value = 'ANY';
      showToast('已填入全网通 ANY');
    }

    async function handleGenerate(e) {
      e.preventDefault();
      const customer = document.getElementById('input-customer').value.trim();
      const machine_id = document.getElementById('input-mid').value.trim().toUpperCase();
      const plan_type = document.getElementById('input-plan').value;
      const days = parseInt(document.getElementById('input-duration').value);

      const btn = document.getElementById('btn-submit');
      btn.disabled = true;
      btn.innerText = '签名生成中...';

      try {
        const res = await fetch('/api/v1/license/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ customer, machine_id, plan_type, days })
        });
        const data = await res.json();
        if (data.ok) {
          document.getElementById('gen-result').classList.remove('hidden');
          document.getElementById('result-key').value = data.license_key;
          const plan = PLANS[plan_type] || {};
          document.getElementById('result-plan-tag').innerText = `${plan.name || plan_type} (${plan.spec || ''})`;
          loadLicenses();
          showToast('新许可证已生成！');
        } else {
          showToast(data.message || '生成失败', true);
        }
      } catch (err) {
        showToast('请求失败: ' + err.message, true);
      } finally {
        btn.disabled = false;
        btn.innerText = '签名并立即签发';
      }
    }

    function copyResult() {
      const text = document.getElementById('result-key').value;
      navigator.clipboard.writeText(text).then(() => {
        showToast('许可证密钥已成功复制到剪贴板！');
      });
    }

    function copyLic(key) {
      navigator.clipboard.writeText(key).then(() => {
        showToast('已复制密钥到剪贴板！');
      });
    }

    // 模态框确认操作 (替代原生 confirm)
    let pendingAction = null;
    function confirmAction(id, action) {
      pendingAction = { id, action };
      const title = document.getElementById('confirm-title');
      const desc = document.getElementById('confirm-desc');
      const okBtn = document.getElementById('confirm-ok-btn');

      if (action === 'revoke') {
        title.innerText = '确认吊销许可证？';
        desc.innerText = '吊销后客户端在下次心跳时将立即被停用所有代理节点功能，且无法创建新节点。';
        okBtn.innerText = '确认吊销';
        okBtn.className = 'px-4 py-1.5 bg-rose-600 hover:bg-rose-500 text-white font-semibold rounded-xl text-xs transition';
      } else {
        title.innerText = '确认恢复许可证？';
        desc.innerText = '恢复后该许可证将重返生效状态，客户端心跳同步后立即恢复节点管理。';
        okBtn.innerText = '确认恢复';
        okBtn.className = 'px-4 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white font-semibold rounded-xl text-xs transition';
      }

      document.getElementById('confirm-modal').classList.remove('hidden');
      okBtn.onclick = executePendingAction;
    }

    function closeConfirmModal() {
      document.getElementById('confirm-modal').classList.add('hidden');
      pendingAction = null;
    }

    async function executePendingAction() {
      if (!pendingAction) return;
      const { id, action } = pendingAction;
      closeConfirmModal();

      try {
        const res = await fetch('/api/v1/license/' + action, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id })
        });
        const data = await res.json();
        if (data.ok) {
          showToast(action === 'revoke' ? '许可证已吊销！' : '许可证已恢复生效！');
          loadLicenses();
        } else {
          showToast(data.message || '操作失败', true);
        }
      } catch (err) {
        showToast(err.message, true);
      }
    }

    renderPlanSelector();
    loadLicenses();
  </script>
</body>
</html>
"""


# =============================================================================
# HTTP 路由与业务逻辑
# =============================================================================
class LicenseServerHandler(BaseHTTPRequestHandler):
    def send_json(self, data, code=200):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # 1. 首页仪表盘 UI
        if path == "/" or path == "/index.html":
            body = DASHBOARD_HTML.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        # 2. 获取所有许可证列表
        if path == "/api/v1/license/list":
            conn = get_db()
            cur = conn.execute("SELECT * FROM licenses ORDER BY issued_at DESC")
            rows = [dict(r) for r in cur.fetchall()]
            conn.close()
            self.send_json({"ok": True, "licenses": rows})
            return

        # 3. 获取所有套餐配置
        if path == "/api/v1/license/plans":
            self.send_json({"ok": True, "plans": PLAN_CONFIGS})
            return

        self.send_json({"error": "Not Found"}, 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        content_len = int(self.headers.get("Content-Length", 0))
        raw_body = self.rfile.read(content_len).decode("utf-8") if content_len > 0 else "{}"
        try:
            req = json.loads(raw_body)
        except Exception:
            req = {}

        # 1. 客户端心跳上报 API (/api/v1/license/ping)
        if path == "/api/v1/license/ping":
            lic_key = req.get("license_key", "").strip()
            mid = req.get("machine_id", "").strip().upper()
            client_ip = self.client_address[0]
            now = int(time.time())

            if not lic_key:
                self.send_json({"status": "invalid", "message": "缺失许可证"}, 400)
                return

            conn = get_db()
            # 严格匹配许可证 key
            cur = conn.execute("SELECT id, status FROM licenses WHERE license_key = ?", (lic_key,))
            row = cur.fetchone()
            if not row and mid and mid != "ANY":
                cur = conn.execute("SELECT id, status FROM licenses WHERE machine_id = ?", (mid,))
                row = cur.fetchone()
            
            if row:
                lic_id = row["id"]
                current_status = row["status"]
                with conn:
                    conn.execute("UPDATE licenses SET last_ping_at = ?, last_ping_ip = ? WHERE id = ?", (now, client_ip, lic_id))
                conn.close()

                if current_status == "revoked":
                    self.send_json({"status": "revoked", "message": "许可证已被吊销"})
                    return
            else:
                conn.close()

            self.send_json({"status": "ok", "timestamp": now})
            return

        # 2. 签发新许可证 API (/api/v1/license/generate)
        if path == "/api/v1/license/generate":
            customer = req.get("customer", "VIP客户").strip()
            mid = req.get("machine_id", "").strip().upper()
            plan_type = req.get("plan_type", "planet")
            days = int(req.get("days", 365))

            if not mid:
                self.send_json({"ok": False, "message": "机器识别码不能为空"}, 400)
                return

            now = int(time.time())
            expire_at = (now + days * 86400) if days > 0 else 0
            lic_id = f"LIC-{time.strftime('%Y%m')}-{secrets.token_hex(4).upper()}"
            
            plan_cfg = PLAN_CONFIGS.get(plan_type, PLAN_CONFIGS["planet"])
            max_servers = plan_cfg["max_servers"]
            max_nodes = plan_cfg["max_nodes"]
            max_users = plan_cfg["max_users"]

            payload = {
                "id": lic_id,
                "type": plan_type,
                "customer": customer,
                "machine_id": mid,
                "max_servers": max_servers,
                "max_nodes": max_nodes,
                "max_users": max_users,
                "issued_at": now,
                "expire_at": expire_at
            }

            try:
                lic_key = generate_license_string(payload)
            except Exception as e:
                self.send_json({"ok": False, "message": f"签名失败: {e}"}, 500)
                return

            conn = get_db()
            with conn:
                conn.execute("""
                INSERT INTO licenses (id, customer, machine_id, plan_type, max_servers, max_nodes, max_users, issued_at, expire_at, license_key, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active')
                """, (lic_id, customer, mid, plan_type, max_servers, max_nodes, max_users, now, expire_at, lic_key))
            conn.close()

            self.send_json({
                "ok": True,
                "license_id": lic_id,
                "license_key": lic_key,
                "plan_type": plan_type,
                "max_servers": max_servers,
                "max_nodes": max_nodes,
                "max_users": max_users,
                "expire_at": expire_at,
                "message": "生成成功"
            })
            return

        # 3. 吊销许可证 API (/api/v1/license/revoke)
        if path == "/api/v1/license/revoke":
            lic_id = req.get("id")
            conn = get_db()
            with conn:
                conn.execute("UPDATE licenses SET status = 'revoked' WHERE id = ?", (lic_id,))
            conn.close()
            self.send_json({"ok": True, "message": "许可证已吊销"})
            return

        # 4. 恢复许可证 API (/api/v1/license/unrevoke)
        if path == "/api/v1/license/unrevoke":
            lic_id = req.get("id")
            conn = get_db()
            with conn:
                conn.execute("UPDATE licenses SET status = 'active' WHERE id = ?", (lic_id,))
            conn.close()
            self.send_json({"ok": True, "message": "许可证已恢复"})
            return

        self.send_json({"error": "Not Found"}, 404)


def run_server():
    init_db()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), LicenseServerHandler)
    print(f"ProxyProbe License Management Center listening on 0.0.0.0:{PORT}")
    server.serve_forever()


if __name__ == "__main__":
    run_server()
