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
# Ed25519 签名实现
# =============================================================================
def sign_payload(payload_bytes: bytes) -> bytes:
    priv_bytes = bytes.fromhex(MASTER_PRIVATE_KEY_HEX)
    if _HAS_CRYPTO:
        priv = ed25519.Ed25519PrivateKey.from_private_bytes(priv_bytes)
        return priv.sign(payload_bytes)
    else:
        # 降级纯 Python 签名（通过简易扩展或确保安装 cryptography）
        raise RuntimeError("请在服务器上安装 python3-cryptography 以进行私钥签名: apt-get install -y python3-cryptography")


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
            max_nodes INTEGER,
            issued_at INTEGER,
            expire_at INTEGER,
            license_key TEXT,
            status TEXT DEFAULT 'active',
            last_ping_ip TEXT DEFAULT '',
            last_ping_at INTEGER DEFAULT 0,
            note TEXT DEFAULT ''
        )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_lic_mid ON licenses(machine_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_lic_status ON licenses(status)")
    conn.close()


# =============================================================================
# 前端 HTML 仪表盘单页应用 (现代 Tailwind CSS + 极简暗黑风格)
# =============================================================================
DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="zh-CN" class="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>ProxyProbe 商业许可证发号与管控中心</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script>
    tailwind.config = {
      darkMode: 'class',
      theme: {
        extend: {
          colors: {
            brand: { 500: '#6366f1', 600: '#4f46e5', 700: '#4338ca' }
          }
        }
      }
    }
  </script>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css">
  <style>
    body { background-color: #0b0f19; color: #f3f4f6; }
    .card { background-color: #111827; border: 1px solid #1f2937; }
  </style>
</head>
<body class="min-h-screen p-4 sm:p-8 font-sans">
  <div class="max-w-6xl mx-auto space-y-6">

    <!-- 顶部 Header -->
    <header class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-6 border-b border-gray-800">
      <div class="flex items-center gap-3">
        <div class="size-11 rounded-xl bg-brand-600/20 border border-brand-500/30 flex items-center justify-center text-brand-500 shadow-inner">
          <i class="fa-solid fa-shield-halved text-xl"></i>
        </div>
        <div>
          <h1 class="text-xl font-bold tracking-tight text-white flex items-center gap-2">
            ProxyProbe 许可证发号与管控中心
            <span class="text-xs font-normal px-2.5 py-0.5 rounded-full bg-brand-500/10 text-brand-400 border border-brand-500/20">双轨混合架构</span>
          </h1>
          <p class="text-xs text-gray-400 mt-0.5">Ed25519 机器指纹数字签名 + 实时在线心跳与黑名单吊销</p>
        </div>
      </div>
      <div class="flex items-center gap-2">
        <button onclick="openModal()" class="px-4 py-2 bg-brand-600 hover:bg-brand-500 text-white text-xs font-medium rounded-lg flex items-center gap-2 shadow-sm transition">
          <i class="fa-solid fa-plus"></i> 生成新许可证
        </button>
        <button onclick="loadLicenses()" class="p-2 border border-gray-700 hover:bg-gray-800 text-gray-300 rounded-lg text-xs transition" title="刷新列表">
          <i class="fa-solid fa-rotate"></i>
        </button>
      </div>
    </header>

    <!-- 统计指标卡片 -->
    <div class="grid grid-cols-2 sm:grid-cols-4 gap-4">
      <div class="card rounded-xl p-4">
        <span class="text-xs text-gray-400 block mb-1">累计签发</span>
        <span id="stat-total" class="text-2xl font-bold text-white">0</span>
      </div>
      <div class="card rounded-xl p-4">
        <span class="text-xs text-emerald-400 block mb-1">有效授权</span>
        <span id="stat-active" class="text-2xl font-bold text-emerald-400">0</span>
      </div>
      <div class="card rounded-xl p-4">
        <span class="text-xs text-rose-400 block mb-1">已吊销黑名单</span>
        <span id="stat-revoked" class="text-2xl font-bold text-rose-400">0</span>
      </div>
      <div class="card rounded-xl p-4">
        <span class="text-xs text-amber-400 block mb-1">24H 在线心跳机器</span>
        <span id="stat-online" class="text-2xl font-bold text-amber-400">0</span>
      </div>
    </div>

    <!-- 许可证列表表格 -->
    <div class="card rounded-xl overflow-hidden shadow-sm">
      <div class="p-4 border-b border-gray-800 flex items-center justify-between">
        <h2 class="text-sm font-semibold text-gray-200 flex items-center gap-2">
          <i class="fa-solid fa-list-check text-gray-400"></i> 已签发许可证列表
        </h2>
        <span id="list-count" class="text-xs text-gray-500">共 0 条</span>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full text-left text-xs text-gray-300">
          <thead class="bg-gray-900/60 text-gray-400 uppercase border-b border-gray-800 text-[11px]">
            <tr>
              <th class="px-4 py-3">客户备注</th>
              <th class="px-4 py-3">绑定机器识别码</th>
              <th class="px-4 py-3">规格类型</th>
              <th class="px-4 py-3">到期时间</th>
              <th class="px-4 py-3">状态</th>
              <th class="px-4 py-3">最近在线心跳</th>
              <th class="px-4 py-3 text-right">操作</th>
            </tr>
          </thead>
          <tbody id="license-tbody" class="divide-y divide-gray-800/60 font-mono text-[11px]">
            <tr><td colspan="7" class="p-8 text-center text-gray-500 font-sans">正在加载许可证数据...</td></tr>
          </tbody>
        </table>
      </div>
    </div>

  </div>

  <!-- 新增许可证弹窗 -->
  <div id="modal" class="fixed inset-0 bg-black/70 backdrop-blur-sm hidden flex items-center justify-center p-4 z-50">
    <div class="card rounded-2xl max-w-lg w-full p-6 space-y-4 shadow-2xl border-gray-700">
      <div class="flex items-center justify-between border-b border-gray-800 pb-3">
        <h3 class="text-base font-bold text-white flex items-center gap-2">
          <i class="fa-solid fa-key text-brand-500"></i> 签发新商业许可证
        </h3>
        <button onclick="closeModal()" class="text-gray-400 hover:text-white"><i class="fa-solid fa-xmark text-lg"></i></button>
      </div>

      <form id="gen-form" onsubmit="handleGenerate(event)" class="space-y-3.5 text-xs">
        <div>
          <label class="block font-medium text-gray-300 mb-1">客户姓名 / 备注标识</label>
          <input id="input-customer" type="text" required placeholder="如：VIP客户-老王" class="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-brand-500 font-sans" />
        </div>

        <div>
          <div class="flex items-center justify-between mb-1">
            <label class="block font-medium text-gray-300">客户机器识别码 (Machine ID)</label>
            <button type="button" onclick="setAnyMachine()" class="text-brand-400 hover:underline text-[11px]">设置为全网通 (ANY)</button>
          </div>
          <input id="input-mid" type="text" required placeholder="如：PP-8A3F-9B12-4C67" class="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white font-mono focus:outline-none focus:border-brand-500 uppercase" />
        </div>

        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="block font-medium text-gray-300 mb-1">授权规格类型</label>
            <select id="input-plan" class="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-brand-500 font-sans">
              <option value="pro">商业专业版 (限制50节点)</option>
              <option value="enterprise">企业旗舰版 (无限节点)</option>
            </select>
          </div>
          <div>
            <label class="block font-medium text-gray-300 mb-1">有效时长</label>
            <select id="input-duration" class="w-full bg-gray-900 border border-gray-700 rounded-lg px-3 py-2 text-white focus:outline-none focus:border-brand-500 font-sans">
              <option value="30">1 个月 (30天)</option>
              <option value="90">3 个月 (90天)</option>
              <option value="365" selected>1 年 (365天)</option>
              <option value="0">永久买断 (Lifetime)</option>
            </select>
          </div>
        </div>

        <div class="pt-2 flex justify-end gap-2">
          <button type="button" onclick="closeModal()" class="px-4 py-2 border border-gray-700 hover:bg-gray-800 text-gray-300 rounded-lg">取消</button>
          <button type="submit" id="btn-submit" class="px-4 py-2 bg-brand-600 hover:bg-brand-500 text-white font-medium rounded-lg flex items-center gap-1.5 shadow">
            <i class="fa-solid fa-signature"></i> 一键生成并签名
          </button>
        </div>
      </form>

      <!-- 结果展示框 -->
      <div id="gen-result" class="hidden space-y-2 pt-3 border-t border-gray-800">
        <span class="text-emerald-400 font-medium text-xs flex items-center gap-1.5">
          <i class="fa-solid fa-circle-check"></i> 许可证已生成，请复制发送给客户：
        </span>
        <textarea id="result-key" readonly class="w-full h-24 bg-gray-950 font-mono text-[11px] p-2.5 rounded-lg border border-emerald-500/40 text-emerald-300 select-all resize-none"></textarea>
        <button onclick="copyResult()" id="btn-copy" class="w-full py-2 bg-emerald-600 hover:bg-emerald-500 text-white font-medium rounded-lg text-xs flex items-center justify-center gap-1.5">
          <i class="fa-solid fa-copy"></i> 一键复制完整许可证
        </button>
      </div>
    </div>
  </div>

  <script>
    async function loadLicenses() {
      try {
        const res = await fetch('/api/v1/license/list');
        const data = await res.json();
        renderTable(data.licenses || []);
      } catch (err) {
        console.error(err);
      }
    }

    function renderTable(list) {
      const tbody = document.getElementById('license-tbody');
      document.getElementById('list-count').innerText = `共 ${list.length} 条`;
      
      let active = 0, revoked = 0, online = 0;
      const now = Math.floor(Date.now() / 1000);

      if (list.length === 0) {
        tbody.innerHTML = '<tr><td colspan="7" class="p-8 text-center text-gray-500 font-sans">暂无签发记录，点击右上角【+ 生成新许可证】即可添加</td></tr>';
      } else {
        tbody.innerHTML = list.map(lic => {
          if (lic.status === 'active') active++;
          if (lic.status === 'revoked') revoked++;
          if (lic.last_ping_at && (now - lic.last_ping_at) < 86400) online++;

          const isExpired = lic.expire_at > 0 && now > lic.expire_at;
          const statusBadge = lic.status === 'revoked' 
            ? '<span class="px-2 py-0.5 rounded text-[10px] bg-rose-500/10 text-rose-400 border border-rose-500/20">已吊销</span>'
            : (isExpired 
              ? '<span class="px-2 py-0.5 rounded text-[10px] bg-amber-500/10 text-amber-400 border border-amber-500/20">已过期</span>'
              : '<span class="px-2 py-0.5 rounded text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">生效中</span>');

          const expText = lic.expire_at === 0 
            ? '<span class="text-purple-400">永久买断</span>' 
            : new Date(lic.expire_at * 1000).toLocaleDateString('zh-CN');

          const pingText = lic.last_ping_at 
            ? `<span class="text-gray-300 font-sans">${new Date(lic.last_ping_at * 1000).toLocaleString('zh-CN')}</span><br><span class="text-gray-500 text-[10px]">${lic.last_ping_ip || ''}</span>`
            : '<span class="text-gray-600 font-sans">暂未心跳</span>';

          return `
            <tr class="hover:bg-gray-900/40 transition">
              <td class="px-4 py-3 font-sans font-medium text-white">${lic.customer}</td>
              <td class="px-4 py-3 font-mono text-gray-300 select-all">${lic.machine_id}</td>
              <td class="px-4 py-3 font-sans">${lic.plan_type === 'enterprise' ? '企业旗舰版' : '商业专业版'}</td>
              <td class="px-4 py-3 font-sans">${expText}</td>
              <td class="px-4 py-3">${statusBadge}</td>
              <td class="px-4 py-3">${pingText}</td>
              <td class="px-4 py-3 text-right space-x-1.5 font-sans">
                <button onclick="copyLic('${lic.license_key}')" class="px-2 py-1 bg-gray-800 hover:bg-gray-700 text-gray-300 rounded text-[11px]" title="复制密钥">
                  <i class="fa-solid fa-copy"></i> 复制
                </button>
                ${lic.status === 'active' 
                  ? `<button onclick="toggleRevoke('${lic.id}', 'revoke')" class="px-2 py-1 bg-rose-900/40 hover:bg-rose-900/60 text-rose-300 rounded text-[11px]" title="在线吊销封禁">吊销</button>`
                  : `<button onclick="toggleRevoke('${lic.id}', 'unrevoke')" class="px-2 py-1 bg-emerald-900/40 hover:bg-emerald-900/60 text-emerald-300 rounded text-[11px]" title="恢复有效状态">恢复</button>`
                }
              </td>
            </tr>
          `;
        }).join('');
      }

      document.getElementById('stat-total').innerText = list.length;
      document.getElementById('stat-active').innerText = active;
      document.getElementById('stat-revoked').innerText = revoked;
      document.getElementById('stat-online').innerText = online;
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
    }

    async function handleGenerate(e) {
      e.preventDefault();
      const customer = document.getElementById('input-customer').value.trim();
      const machine_id = document.getElementById('input-mid').value.trim().toUpperCase();
      const plan_type = document.getElementById('input-plan').value;
      const days = parseInt(document.getElementById('input-duration').value);

      const btn = document.getElementById('btn-submit');
      btn.disabled = true;
      btn.innerText = '正在签名生成...';

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
          loadLicenses();
        } else {
          alert('生成失败: ' + (data.message || '未知错误'));
        }
      } catch (err) {
        alert('请求失败: ' + err.message);
      } finally {
        btn.disabled = false;
        btn.innerHTML = '<i class="fa-solid fa-signature"></i> 一键生成并签名';
      }
    }

    function copyResult() {
      const text = document.getElementById('result-key').value;
      navigator.clipboard.writeText(text).then(() => {
        document.getElementById('btn-copy').innerHTML = '<i class="fa-solid fa-check"></i> 已复制到剪贴板！';
        setTimeout(() => {
          document.getElementById('btn-copy').innerHTML = '<i class="fa-solid fa-copy"></i> 一键复制完整许可证';
        }, 2000);
      });
    }

    function copyLic(key) {
      navigator.clipboard.writeText(key).then(() => alert('已复制许可证密钥！'));
    }

    async function toggleRevoke(id, action) {
      if (!confirm(action === 'revoke' ? '确定要吊销此许可证吗？客户下次在线心跳时将被停用。' : '确定要恢复此许可证吗？')) return;
      try {
        const res = await fetch('/api/v1/license/' + action, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id })
        });
        const data = await res.json();
        if (data.ok) loadLicenses();
        else alert(data.message || '操作失败');
      } catch (err) {
        alert(err.message);
      }
    }

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
            mid = req.get("machine_id", "").strip()
            client_ip = self.client_address[0]
            now = int(time.time())

            if not lic_key:
                self.send_json({"status": "invalid", "message": "缺失许可证"}, 400)
                return

            conn = get_db()
            cur = conn.execute("SELECT id, status FROM licenses WHERE license_key = ? OR machine_id = ?", (lic_key, mid))
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
            plan_type = req.get("plan_type", "pro")
            days = int(req.get("days", 365))

            if not mid:
                self.send_json({"ok": False, "message": "机器识别码不能为空"}, 400)
                return

            now = int(time.time())
            expire_at = (now + days * 86400) if days > 0 else 0
            lic_id = f"LIC-{time.strftime('%Y%m')}-{secrets.token_hex(4).upper()}"
            max_nodes = 50 if plan_type == "pro" else 0

            payload = {
                "id": lic_id,
                "type": plan_type,
                "customer": customer,
                "machine_id": mid,
                "max_nodes": max_nodes,
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
                INSERT INTO licenses (id, customer, machine_id, plan_type, max_nodes, issued_at, expire_at, license_key, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'active')
                """, (lic_id, customer, mid, plan_type, max_nodes, now, expire_at, lic_key))
            conn.close()

            self.send_json({
                "ok": True,
                "license_id": lic_id,
                "license_key": lic_key,
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
