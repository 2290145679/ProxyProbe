#!/usr/bin/env python3
"""
ProxyProbe 商业许可证发布与在线管控中心 (License Management Center)
Copyright (c) 2026 ProxyProbe Contributors
设计准则：极简主义、大留白、单一深蓝主色、无渐变无投影堆叠、统一 8px 圆角、无弹窗、垂直居中
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

# 加载密码学库 (支持 cryptography 或内置纯 Python Ed25519 签名)
try:
    from cryptography.hazmat.primitives.asymmetric import ed25519
    _HAS_CRYPTO = True
except ImportError:
    _HAS_CRYPTO = False

PORT = int(os.environ.get("LICENSE_CENTER_PORT", 18888))
DB_PATH = os.environ.get("LICENSE_CENTER_DB", "/opt/license-center/license_center.db")

# 官方发号主私钥 (必须严格保密) 与 验签公钥
MASTER_PRIVATE_KEY_HEX = "875cf2bcc0c92bb602eb6c150693ed1e308321f803b7cbf3674ec028ebea0ff3"
MASTER_PUBLIC_KEY_HEX = "6637fdfd836e83fd31aa7c02698ab615d882bdb7533aaf2f83359480a1a5a4c3"

# =============================================================================
# 套餐规格标准定义 (Server / Node / User)
# =============================================================================
PLAN_CONFIGS = {
    "stardust": {
        "name": "星尘套餐",
        "desc": "入门体验",
        "max_servers": 3,
        "max_nodes": 6,
        "max_users": 6,
        "spec": "3服 · 6节 · 6户"
    },
    "planet": {
        "name": "行星套餐",
        "desc": "推荐热选",
        "max_servers": 5,
        "max_nodes": 12,
        "max_users": 12,
        "spec": "5服 · 12节 · 12户"
    },
    "star": {
        "name": "恒星套餐",
        "desc": "性价比之选",
        "max_servers": 8,
        "max_nodes": 18,
        "max_users": 18,
        "spec": "8服 · 18节 · 18户"
    },
    "galaxy": {
        "name": "星系套餐",
        "desc": "团队商务",
        "max_servers": 12,
        "max_nodes": 30,
        "max_users": 30,
        "spec": "12服 · 30节 · 30户"
    },
    "universe": {
        "name": "宇宙套餐",
        "desc": "旗舰尊享",
        "max_servers": 20,
        "max_nodes": 50,
        "max_users": 50,
        "spec": "20服 · 50节 · 50户"
    }
}

# =============================================================================
# Ed25519 纯 Python 兜底签名实现 (RFC 8032)
# =============================================================================
_q = 2**255 - 19
_l = 2**252 + 27742317777372353535851937790883648493

def _inv(x):
    return pow(x, _q - 2, _q)

_d = -121665 * _inv(121666) % _q
_I = pow(2, (_q - 1) // 4, _q)

def _xrecover(y):
    xx = (y * y - 1) * _inv(_d * y * y + 1)
    x = pow(xx, (_q + 3) // 8, _q)
    if (x * x - xx) % _q != 0:
        x = (x * _I) % _q
    if x % 2 != 0:
        x = _q - x
    return x

_By = 4 * _inv(5) % _q
_Bx = _xrecover(_By)
_B = [_Bx % _q, _By % _q]

def _edwards(P, Q):
    x1, y1 = P[0], P[1]
    x2, y2 = Q[0], Q[1]
    denom_x = (1 + _d * x1 * x2 * y1 * y2) % _q
    denom_y = (1 - _d * x1 * x2 * y1 * y2) % _q
    return [(x1 * y2 + x2 * y1) * _inv(denom_x) % _q, (y1 * y2 + x1 * x2) * _inv(denom_y) % _q]

def _scalarmult(P, e):
    if e == 0:
        return [0, 1]
    Q = _scalarmult(P, e // 2)
    Q = _edwards(Q, Q)
    if e & 1:
        Q = _edwards(Q, P)
    return Q

def _encodepoint(P):
    x = P[0]
    y = P[1]
    bits = [(y >> i) & 1 for i in range(255)] + [x & 1]
    return bytes(sum(bits[i * 8 + j] << j for j in range(8)) for i in range(32))

def _pure_python_sign(secret_bytes: bytes, msg: bytes) -> bytes:
    h = hashlib.sha512(secret_bytes).digest()
    a = int.from_bytes(h[:32], "little")
    a &= (1 << 254) - 8
    a |= 64
    A = _scalarmult(_B, a)
    A_bytes = _encodepoint(A)
    prefix = h[32:]
    r = int.from_bytes(hashlib.sha512(prefix + msg).digest(), "little") % _l
    R = _scalarmult(_B, r)
    R_bytes = _encodepoint(R)
    k = int.from_bytes(hashlib.sha512(R_bytes + A_bytes + msg).digest(), "little") % _l
    S = (r + k * a) % _l
    return R_bytes + S.to_bytes(32, "little")

def sign_payload(payload_bytes: bytes) -> bytes:
    priv_bytes = bytes.fromhex(MASTER_PRIVATE_KEY_HEX)
    if _HAS_CRYPTO:
        try:
            priv = ed25519.Ed25519PrivateKey.from_private_bytes(priv_bytes)
            return priv.sign(payload_bytes)
        except Exception:
            pass
    return _pure_python_sign(priv_bytes, payload_bytes)

def generate_license_string(payload: dict) -> str:
    payload_json = json.dumps(payload, sort_keys=True, separators=(',', ':')).encode("utf-8")
    sig = sign_payload(payload_json)
    p_b64 = base64.urlsafe_b64encode(payload_json).decode("utf-8").rstrip("=")
    s_b64 = base64.urlsafe_b64encode(sig).decode("utf-8").rstrip("=")
    return f"PPLIC-{p_b64}.{s_b64}"

def generate_short_code() -> str:
    """生成 23 位专属短激活码: PP-XXXX-XXXX-XXXX-XXXX (采用 Base32 无歧义大写字符)"""
    chars = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
    p1 = "".join(secrets.choice(chars) for _ in range(4))
    p2 = "".join(secrets.choice(chars) for _ in range(4))
    p3 = "".join(secrets.choice(chars) for _ in range(4))
    p4 = "".join(secrets.choice(chars) for _ in range(4))
    return f"PP-{p1}-{p2}-{p3}-{p4}"

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
            note TEXT DEFAULT '',
            bound_mid TEXT DEFAULT '',
            activated_at INTEGER DEFAULT 0
        )
        """)
        cursor = conn.execute("PRAGMA table_info(licenses)")
        columns = [row[1] for row in cursor.fetchall()]
        if "max_servers" not in columns:
            conn.execute("ALTER TABLE licenses ADD COLUMN max_servers INTEGER DEFAULT 1")
        if "max_users" not in columns:
            conn.execute("ALTER TABLE licenses ADD COLUMN max_users INTEGER DEFAULT 1")
        if "note" not in columns:
            conn.execute("ALTER TABLE licenses ADD COLUMN note TEXT DEFAULT ''")
        if "bound_mid" not in columns:
            conn.execute("ALTER TABLE licenses ADD COLUMN bound_mid TEXT DEFAULT ''")
        if "activated_at" not in columns:
            conn.execute("ALTER TABLE licenses ADD COLUMN activated_at INTEGER DEFAULT 0")

        conn.execute("CREATE INDEX IF NOT EXISTS idx_lic_mid ON licenses(machine_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_lic_status ON licenses(status)")
    conn.close()

# =============================================================================
# 极简实用主义纯白/浅灰设计页面 (无渐变、无阴影堆叠、8px统一圆角、无弹窗、垂直居中)
# =============================================================================
DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no, viewport-fit=cover">
  <title>ProxyProbe · 商业许可证发布</title>
  <style>
    *, *::before, *::after {
      box-sizing: border-box;
      margin: 0;
      padding: 0;
      -webkit-tap-highlight-color: transparent;
    }

    body {
      background-color: #f8fafc;
      color: #0f172a;
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", "PingFang SC", "Noto Sans SC", sans-serif;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 16px;
      line-height: 1.5;
    }

    .mono {
      font-family: Consolas, "Liberation Mono", Menlo, Courier, monospace;
    }

    /* 核心居中卡片容器：无渐变、无发光、无多重阴影，纯粹 1px 微边框 */
    .card {
      background-color: #ffffff;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      width: 100%;
      max-width: 520px;
      padding: 32px 28px;
    }

    @media (max-width: 640px) {
      body {
        padding: 16px;
      }
      .card {
        padding: 24px 16px;
      }
    }

    /* 标题与副标题 */
    .title {
      font-size: 22px;
      font-weight: 600;
      color: #0f172a;
      letter-spacing: -0.01em;
    }

    .subtitle {
      font-size: 14px;
      color: #64748b;
      margin-top: 4px;
      margin-bottom: 24px;
    }

    /* 表单组 */
    .form-group {
      margin-bottom: 18px;
    }

    .label-row {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 6px;
    }

    .form-label {
      font-size: 14px;
      font-weight: 500;
      color: #334155;
    }

    .text-link {
      font-size: 13px;
      color: #0f172a;
      background: none;
      border: none;
      cursor: pointer;
      text-decoration: underline;
      text-underline-offset: 3px;
      padding: 0;
    }
    .text-link:hover {
      color: #1e293b;
    }

    /* 输入框：统一 8px 圆角，focus 时仅边框变深色，绝对不发光、无 box-shadow */
    .form-input {
      width: 100%;
      height: 40px;
      padding: 8px 12px;
      font-size: 14px;
      color: #0f172a;
      background-color: #ffffff;
      border: 1px solid #cbd5e1;
      border-radius: 8px;
      outline: none;
      transition: border-color 0.15s ease;
    }

    .form-input:focus {
      border-color: #0f172a;
      box-shadow: none;
      outline: none;
    }

    .form-input.has-error {
      border-color: #dc2626;
    }

    .form-input:disabled {
      background-color: #f1f5f9;
      color: #94a3b8;
      cursor: not-allowed;
    }

    /* 错误提示：红色小字，紧贴输入框下方，不用弹窗 */
    .error-msg {
      font-size: 12px;
      color: #dc2626;
      margin-top: 5px;
      display: none;
    }

    .error-msg.visible {
      display: block;
    }

    /* 套餐选择网格 */
    .plan-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 8px;
    }

    @media (max-width: 480px) {
      .plan-grid {
        grid-template-columns: repeat(2, 1fr);
      }
    }

    .plan-btn {
      background-color: #ffffff;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      padding: 10px 8px;
      text-align: left;
      cursor: pointer;
      transition: border-color 0.15s ease, background-color 0.15s ease;
      outline: none;
    }

    .plan-btn:hover {
      border-color: #94a3b8;
    }

    .plan-btn.selected {
      border-color: #0f172a;
      background-color: #f8fafc;
    }

    .plan-btn-name {
      font-size: 13px;
      font-weight: 600;
      color: #0f172a;
    }

    .plan-btn-spec {
      font-size: 11px;
      color: #64748b;
      margin-top: 3px;
      font-family: Consolas, monospace;
    }

    /* 配额微调输入行 */
    .quota-row {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 8px;
      margin-top: 8px;
      padding: 10px 12px;
      background-color: #f8fafc;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
    }

    .quota-col label {
      font-size: 11px;
      color: #64748b;
      display: block;
      margin-bottom: 4px;
    }

    .quota-col input {
      height: 32px;
      padding: 4px 8px;
      font-size: 13px;
    }

    /* 时长选择网格 */
    .duration-grid {
      display: grid;
      grid-template-columns: repeat(5, 1fr);
      gap: 6px;
    }

    .duration-btn {
      height: 36px;
      background-color: #ffffff;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      font-size: 13px;
      color: #475569;
      cursor: pointer;
      transition: all 0.15s ease;
      outline: none;
    }

    .duration-btn:hover {
      border-color: #94a3b8;
    }

    .duration-btn.selected {
      background-color: #0f172a;
      border-color: #0f172a;
      color: #ffffff;
      font-weight: 500;
    }

    /* 数量选择网格 */
    .count-grid {
      display: grid;
      grid-template-columns: repeat(4, 1fr) 76px;
      gap: 6px;
    }

    @media (max-width: 480px) {
      .count-grid {
        grid-template-columns: repeat(4, 1fr);
      }
      .count-input-col {
        grid-column: span 4;
      }
    }

    /* 批量单张密钥列表 */
    .batch-list {
      max-height: 180px;
      overflow-y: auto;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
      background-color: #ffffff;
    }

    .batch-item {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 8px 12px;
      border-bottom: 1px solid #f1f5f9;
      font-size: 13px;
    }

    .batch-item:last-child {
      border-bottom: none;
    }

    /* 按钮：单一深蓝主色 #0f172a，hover 仅轻微加深颜色，统一 8px 圆角 */
    .btn-primary {
      width: 100%;
      height: 42px;
      background-color: #0f172a;
      color: #ffffff;
      border: none;
      border-radius: 8px;
      font-size: 14px;
      font-weight: 500;
      cursor: pointer;
      transition: background-color 0.15s ease;
      margin-top: 8px;
      display: flex;
      align-items: center;
      justify-content: center;
      gap: 6px;
    }

    .btn-primary:hover:not(:disabled) {
      background-color: #1e293b;
    }

    .btn-primary:active:not(:disabled) {
      background-color: #020617;
    }

    .btn-primary:disabled {
      background-color: #94a3b8;
      cursor: not-allowed;
    }

    .btn-secondary {
      width: 100%;
      height: 40px;
      background-color: #ffffff;
      color: #0f172a;
      border: 1px solid #cbd5e1;
      border-radius: 8px;
      font-size: 14px;
      font-weight: 500;
      cursor: pointer;
      transition: all 0.15s ease;
      margin-top: 8px;
    }

    .btn-secondary:hover {
      background-color: #f8fafc;
      border-color: #94a3b8;
    }

    /* 签发成功结果面板 */
    .result-panel {
      display: none;
      margin-top: 20px;
      padding: 16px;
      background-color: #f8fafc;
      border: 1px solid #cbd5e1;
      border-radius: 8px;
    }

    .result-panel.visible {
      display: block;
    }

    .result-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 10px;
    }

    .result-title {
      font-size: 14px;
      font-weight: 600;
      color: #0f172a;
    }

    .result-plan-tag {
      font-size: 12px;
      color: #475569;
      font-family: Consolas, monospace;
    }

    .result-textarea {
      width: 100%;
      height: 76px;
      padding: 10px;
      font-size: 12px;
      font-family: Consolas, "Liberation Mono", Courier, monospace;
      color: #0f172a;
      background-color: #ffffff;
      border: 1px solid #cbd5e1;
      border-radius: 8px;
      resize: none;
      outline: none;
      margin-bottom: 10px;
      line-height: 1.4;
    }

    .result-textarea:focus {
      border-color: #0f172a;
    }

    .result-hint {
      font-size: 12px;
      color: #64748b;
      margin-top: 8px;
      line-height: 1.5;
    }

    /* 底部极简折叠：已签发记录 */
    .history-toggle-row {
      margin-top: 24px;
      padding-top: 18px;
      border-top: 1px solid #e2e8f0;
      display: flex;
      align-items: center;
      justify-content: space-between;
    }

    .history-toggle-btn {
      font-size: 13px;
      color: #64748b;
      background: none;
      border: none;
      cursor: pointer;
      padding: 0;
      display: inline-flex;
      align-items: center;
      gap: 4px;
    }

    .history-toggle-btn:hover {
      color: #0f172a;
    }

    .history-container {
      display: none;
      margin-top: 14px;
      max-height: 280px;
      overflow-y: auto;
      border: 1px solid #e2e8f0;
      border-radius: 8px;
    }

    .history-container.visible {
      display: block;
    }

    .history-item {
      padding: 10px 12px;
      border-bottom: 1px solid #f1f5f9;
      font-size: 12px;
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }

    .history-item:last-child {
      border-bottom: none;
    }

    .history-info {
      flex: 1;
      min-width: 0;
    }

    .history-name {
      font-weight: 500;
      color: #0f172a;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }

    .history-sub {
      font-size: 11px;
      color: #64748b;
      font-family: Consolas, monospace;
      margin-top: 2px;
    }

    .history-actions {
      display: flex;
      align-items: center;
      gap: 6px;
      flex-shrink: 0;
    }

    .btn-action-small {
      padding: 4px 8px;
      font-size: 11px;
      border-radius: 6px;
      background-color: #ffffff;
      border: 1px solid #cbd5e1;
      color: #334155;
      cursor: pointer;
      outline: none;
    }

    .btn-action-small:hover {
      border-color: #0f172a;
      color: #0f172a;
    }

    .btn-action-revoke {
      color: #dc2626;
      border-color: #fca5a5;
    }

    .btn-action-revoke:hover {
      background-color: #fee2e2;
      border-color: #dc2626;
      color: #b91c1c;
    }

    /* 状态徽标 */
    .badge {
      display: inline-block;
      padding: 2px 6px;
      font-size: 11px;
      border-radius: 4px;
      font-weight: 500;
    }
    .badge-active {
      background-color: #f0fdf4;
      color: #166534;
      border: 1px solid #bbf7d0;
    }
    .badge-revoked {
      background-color: #fef2f2;
      color: #991b1b;
      border: 1px solid #fecaca;
    }

    /* 轻量复制提示条 */
    .toast-tip {
      position: fixed;
      bottom: 24px;
      left: 50%;
      transform: translateX(-50%);
      background-color: #0f172a;
      color: #ffffff;
      font-size: 13px;
      padding: 8px 16px;
      border-radius: 8px;
      opacity: 0;
      pointer-events: none;
      transition: opacity 0.2s ease;
      z-index: 99;
    }
    .toast-tip.show {
      opacity: 1;
    }
  </style>
</head>
<body>

  <!-- 轻量复制提示 -->
  <div id="toast" class="toast-tip">已复制到剪贴板</div>

  <!-- 主卡片（垂直居中，8px统一圆角，大量留白） -->
  <div class="card">
    
    <div class="title">ProxyProbe 商业许可证发布</div>
    <div class="subtitle">基于 Ed25519 非对称密码学签发商业授权许可</div>

    <!-- 签发表单 -->
    <form id="license-form" onsubmit="handleSubmit(event)">

      <!-- 1. 目标机器码 -->
      <div class="form-group">
        <div class="label-row">
          <label class="form-label" for="input-mid">目标机器识别码 (Machine ID)</label>
          <button type="button" class="text-link" onclick="setAnyMachine()">设为全网通 (ANY)</button>
        </div>
        <input 
          id="input-mid" 
          type="text" 
          class="form-input mono" 
          placeholder="如：PP-8A3F-9B12-4C67 或填 ANY" 
          autocomplete="off"
        />
        <div id="error-mid" class="error-msg">请输入目标机器码，或点击右上角设为 ANY</div>
      </div>

      <!-- 3. 商业套餐规格选择 -->
      <div class="form-group">
        <label class="form-label">商业套餐规格</label>
        <div class="plan-grid" id="plan-selector">
          <!-- 动态渲染 5 档套餐 -->
        </div>
        <input type="hidden" id="input-plan" value="planet" />

        <!-- 细分配额调整 -->
        <div class="quota-row">
          <div class="quota-col">
            <label for="input-servers">服务器上限</label>
            <input id="input-servers" type="number" min="1" max="999" class="form-input mono" value="5" />
          </div>
          <div class="quota-col">
            <label for="input-nodes">代理节点上限</label>
            <input id="input-nodes" type="number" min="1" max="999" class="form-input mono" value="12" />
          </div>
          <div class="quota-col">
            <label for="input-users">用户数上限</label>
            <input id="input-users" type="number" min="1" max="999" class="form-input mono" value="12" />
          </div>
        </div>
      </div>

      <!-- 4. 授权有效期选择 -->
      <div class="form-group">
        <label class="form-label">授权有效期限</label>
        <div class="duration-grid">
          <button type="button" class="duration-btn" onclick="selectDuration(30, this)">1个月</button>
          <button type="button" class="duration-btn" onclick="selectDuration(90, this)">3个月</button>
          <button type="button" class="duration-btn" onclick="selectDuration(180, this)">半年</button>
          <button type="button" class="duration-btn selected" onclick="selectDuration(365, this)">1年</button>
          <button type="button" class="duration-btn" onclick="selectDuration(0, this)">永久</button>
        </div>
        <input type="hidden" id="input-duration" value="365" />
      </div>

      <!-- 5. 签发数量选择 (支持批量签发) -->
      <div class="form-group">
        <div class="label-row">
          <label class="form-label" for="input-count">签发数量 (张)</label>
          <span style="font-size: 11px; color: #64748b;">支持 1 ~ 100 张批量生成</span>
        </div>
        <div class="count-grid">
          <button type="button" class="duration-btn selected" onclick="selectCount(1, this)">1张</button>
          <button type="button" class="duration-btn" onclick="selectCount(5, this)">5张</button>
          <button type="button" class="duration-btn" onclick="selectCount(10, this)">10张</button>
          <button type="button" class="duration-btn" onclick="selectCount(20, this)">20张</button>
          <div class="count-input-col">
            <input id="input-count" type="number" min="1" max="100" class="form-input mono" value="1" placeholder="数量" oninput="onCustomCount(this)" style="height: 36px; padding: 4px 6px; text-align: center;" />
          </div>
        </div>
      </div>

      <!-- 通用错误提示（紧贴按钮上方） -->
      <div id="error-general" class="error-msg" style="text-align: center; margin-bottom: 8px;"></div>

      <!-- 提交按钮：默认态 / 加载中 -->
      <button id="btn-submit" type="submit" class="btn-primary">
        签发商业许可证
      </button>
    </form>

    <!-- 6. 成功状态展示区域 (完成签发后平滑展开) -->
    <div id="result-panel" class="result-panel">
      <div class="result-header">
        <span id="result-title" class="result-title">✓ 许可证签发成功</span>
        <span id="result-tag" class="result-plan-tag"></span>
      </div>
      <textarea id="result-key" class="result-textarea mono" readonly onclick="this.select()" style="height: 84px; cursor: pointer;" title="点击全选文本"></textarea>
      
      <div style="display: flex; gap: 8px;">
        <button id="btn-copy-all" type="button" class="btn-primary" style="margin-top: 0; flex: 1;" onclick="copyResultKeys()">
          复制许可证密钥
        </button>
        <button type="button" class="btn-secondary" style="margin-top: 0; width: 110px; flex-shrink: 0;" onclick="downloadKeys()">
          导出 .txt
        </button>
      </div>

      <!-- 批量单张密钥列表 (超过1张时展示) -->
      <div id="batch-keys-container" style="display: none; margin-top: 12px;">
        <div style="font-size: 12px; font-weight: 500; color: #64748b; margin-bottom: 6px;">单张独立授权码列表：</div>
        <div id="batch-keys-list" class="batch-list"></div>
      </div>

      <button type="button" class="btn-secondary" onclick="resetForm()">
        继续签发
      </button>
      
      <p class="result-hint">
        使用说明：将上方生成的 23 位专属授权码交付给客户，客户在 ProxyProbe 客户端后台「商业授权」页面直接粘贴提交即可即刻激活。
      </p>
    </div>

    <!-- 6. 底部历史记录折叠区 -->
    <div class="history-toggle-row">
      <button type="button" class="history-toggle-btn" onclick="toggleHistory()">
        <span id="history-arrow">▼</span> 查看已签发记录 (<span id="history-count">0</span>)
      </button>
      <button type="button" class="text-link" onclick="loadLicenses()" style="font-size: 12px;">刷新</button>
    </div>

    <div id="history-box" class="history-container">
      <div id="history-list">
        <div style="padding: 16px; text-align: center; color: #94a3b8; font-size: 12px;">暂无历史签发记录</div>
      </div>
    </div>

  </div>

  <script>
    const PLANS = """ + json.dumps(PLAN_CONFIGS, ensure_ascii=False) + """;
    let allLicenses = [];
    let isHistoryOpen = false;

    // Toast 轻量复制提示
    function showToast(text) {
      const el = document.getElementById('toast');
      el.innerText = text;
      el.classList.add('show');
      clearTimeout(window._toastT);
      window._toastT = setTimeout(() => {
        el.classList.remove('show');
      }, 1800);
    }

    // 渲染套餐按钮
    function renderPlanSelector() {
      const container = document.getElementById('plan-selector');
      container.innerHTML = Object.entries(PLANS).map(([key, p]) => `
        <button 
          type="button" 
          onclick="selectPlan('${key}', this)" 
          class="plan-btn ${key === 'planet' ? 'selected' : ''}"
        >
          <div class="plan-btn-name">${p.name}</div>
          <div class="plan-btn-spec">${p.spec}</div>
        </button>
      `).join('');
    }

    function selectPlan(key, btn) {
      document.getElementById('input-plan').value = key;
      document.querySelectorAll('.plan-btn').forEach(b => b.classList.remove('selected'));
      btn.classList.add('selected');

      const p = PLANS[key];
      if (p) {
        document.getElementById('input-servers').value = p.max_servers;
        document.getElementById('input-nodes').value = p.max_nodes;
        document.getElementById('input-users').value = p.max_users;
      }
    }

    function selectDuration(days, btn) {
      document.getElementById('input-duration').value = days;
      document.querySelectorAll('.duration-grid .duration-btn').forEach(b => b.classList.remove('selected'));
      btn.classList.add('selected');
    }

    let currentBatchCount = 1;
    let currentBatchKeys = [];

    function selectCount(num, btn) {
      currentBatchCount = num;
      document.getElementById('input-count').value = num;
      document.querySelectorAll('.count-grid .duration-btn').forEach(b => b.classList.remove('selected'));
      if (btn) btn.classList.add('selected');
    }

    function onCustomCount(input) {
      let val = parseInt(input.value, 10);
      if (isNaN(val) || val < 1) val = 1;
      if (val > 100) val = 100;
      currentBatchCount = val;
      document.querySelectorAll('.count-grid .duration-btn').forEach(b => {
        b.classList.toggle('selected', parseInt(b.innerText, 10) === val);
      });
    }

    function setAnyMachine() {
      document.getElementById('input-mid').value = 'ANY';
      clearError('mid');
    }

    // 清除错误信息
    function clearError(field) {
      const errEl = document.getElementById('error-' + field);
      const inputEl = document.getElementById('input-' + field);
      if (errEl) errEl.classList.remove('visible');
      if (inputEl) inputEl.classList.remove('has-error');
      const genErr = document.getElementById('error-general');
      if (genErr) genErr.classList.remove('visible');
    }

    function showError(field, msg) {
      const errEl = document.getElementById('error-' + field);
      const inputEl = document.getElementById('input-' + field);
      if (errEl) {
        if (msg) errEl.innerText = msg;
        errEl.classList.add('visible');
      }
      if (inputEl) {
        inputEl.classList.add('has-error');
        inputEl.focus();
      }
    }

    // 监听输入，实时清除对应错误
    document.getElementById('input-mid').addEventListener('input', () => clearError('mid'));

    // 跨环境通用剪贴板复制实现 (解决 HTTP 协议下 navigator.clipboard 无法使用的浏览器限制)
    function copyTextToClipboard(text) {
      return new Promise((resolve, reject) => {
        if (navigator.clipboard && window.isSecureContext) {
          navigator.clipboard.writeText(text).then(resolve).catch(() => {
            if (fallbackCopy(text)) resolve(); else reject(new Error('复制失败'));
          });
          return;
        }
        if (fallbackCopy(text)) {
          resolve();
        } else {
          reject(new Error('浏览器限制，请手动选择复制'));
        }
      });
    }

    function fallbackCopy(text) {
      const textArea = document.createElement("textarea");
      textArea.value = text;
      textArea.style.position = "fixed";
      textArea.style.left = "-999999px";
      textArea.style.top = "-999999px";
      textArea.setAttribute("readonly", "");
      document.body.appendChild(textArea);
      textArea.select();
      textArea.setSelectionRange(0, 99999);
      let ok = false;
      try {
        ok = document.execCommand("copy");
      } catch (e) {
        ok = false;
      }
      document.body.removeChild(textArea);
      return ok;
    }

    function copyResultKeys() {
      const el = document.getElementById('result-key');
      const val = el.value.trim();
      if (!val) return;
      el.select();
      copyTextToClipboard(val).then(() => {
        const count = currentBatchKeys.length;
        showToast(count > 1 ? `已成功复制全部 ${count} 张许可证密钥` : '已成功复制许可证密钥');
      }).catch(() => {
        showToast('已全选文本，请直接按 Ctrl+C 复制');
      });
    }

    function copySingleKey(key) {
      copyTextToClipboard(key).then(() => {
        showToast('已复制密钥: ' + key);
      }).catch(() => {
        showToast('复制失败，请手动选取');
      });
    }

    function downloadKeys() {
      const val = document.getElementById('result-key').value.trim();
      if (!val) return;
      const blob = new Blob([val + '\n'], { type: 'text/plain;charset=utf-8' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `ProxyProbe_Licenses_${Date.now()}.txt`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
      showToast('已导出 .txt 文件');
    }

    // 表单提交
    async function handleSubmit(e) {
      e.preventDefault();
      clearError('mid');

      const customer = "商业许可";
      const mid = document.getElementById('input-mid').value.trim().toUpperCase();
      const plan_type = document.getElementById('input-plan').value;
      const days = parseInt(document.getElementById('input-duration').value, 10);
      const count = currentBatchCount || 1;
      const max_servers = parseInt(document.getElementById('input-servers').value, 10) || 1;
      const max_nodes = parseInt(document.getElementById('input-nodes').value, 10) || 1;
      const max_users = parseInt(document.getElementById('input-users').value, 10) || 1;

      // 前端校验
      let hasErr = false;
      if (!mid) {
        showError('mid', '请输入目标机器识别码或设为 ANY');
        hasErr = true;
      }
      if (hasErr) return;

      // 进入加载中状态
      const btn = document.getElementById('btn-submit');
      btn.disabled = true;
      btn.innerText = count > 1 ? `正在批量签名签发 (${count} 张)...` : '正在签名签发中...';

      try {
        const res = await fetch('/api/v1/license/generate', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            customer,
            machine_id: mid,
            plan_type,
            days,
            count,
            max_servers,
            max_nodes,
            max_users
          })
        });

        const data = await res.json();
        if (res.ok && data.ok) {
          currentBatchKeys = data.license_keys || [data.license_key];
          const totalCount = data.count || currentBatchKeys.length;

          // 成功态：展示结果面板
          document.getElementById('result-panel').classList.add('visible');
          document.getElementById('result-key').value = data.license_key;
          document.getElementById('result-title').innerText = totalCount > 1 ? `✓ 成功批量签发 ${totalCount} 张许可证` : '✓ 许可证签发成功';
          document.getElementById('result-tag').innerText = `${data.plan_name} (${data.max_servers}服/${data.max_nodes}节/${data.max_users}户)`;
          document.getElementById('btn-copy-all').innerText = totalCount > 1 ? `复制全部许可证 (共 ${totalCount} 张)` : '复制许可证密钥';

          // 动态渲染批量逐张列表
          const batchContainer = document.getElementById('batch-keys-container');
          const batchListEl = document.getElementById('batch-keys-list');
          if (totalCount > 1) {
            batchContainer.style.display = 'block';
            batchListEl.innerHTML = currentBatchKeys.map((k, idx) => `
              <div class="batch-item">
                <span class="mono" style="font-weight: 500; color: #0f172a;">${idx + 1}. ${k}</span>
                <button type="button" class="btn-action-small" onclick="copySingleKey('${k}')">复制</button>
              </div>
            `).join('');
          } else {
            batchContainer.style.display = 'none';
          }
          
          // 隐藏表单
          document.getElementById('license-form').style.display = 'none';
          loadLicenses();
          showToast(totalCount > 1 ? `成功批量签发 ${totalCount} 张许可证` : '许可证签发成功');
        } else {
          // 错误态：展示错误提示
          if (data.field) {
            showError(data.field, data.message);
          } else {
            const genErr = document.getElementById('error-general');
            genErr.innerText = data.message || '签发失败，请重试';
            genErr.classList.add('visible');
          }
        }
      } catch (err) {
        const genErr = document.getElementById('error-general');
        genErr.innerText = '网络请求失败，请检查服务连接';
        genErr.classList.add('visible');
      } finally {
        btn.disabled = false;
        btn.innerText = '签发商业许可证';
      }
    }

    function resetForm() {
      document.getElementById('result-panel').classList.remove('visible');
      document.getElementById('batch-keys-container').style.display = 'none';
      document.getElementById('license-form').style.display = 'block';
      document.getElementById('input-mid').value = '';
      clearError('mid');
      selectCount(1, document.querySelector('.count-grid .duration-btn'));
      selectPlan('planet', document.querySelectorAll('.plan-btn')[1] || document.querySelector('.plan-btn'));
    }

    // 历史记录折叠与渲染
    function toggleHistory() {
      const box = document.getElementById('history-box');
      const arrow = document.getElementById('history-arrow');
      isHistoryOpen = !isHistoryOpen;
      if (isHistoryOpen) {
        box.classList.add('visible');
        arrow.innerText = '▲';
        loadLicenses();
      } else {
        box.classList.remove('visible');
        arrow.innerText = '▼';
      }
    }

    async function loadLicenses() {
      try {
        const res = await fetch('/api/v1/license/list');
        const data = await res.json();
        allLicenses = data.licenses || [];
        document.getElementById('history-count').innerText = allLicenses.length;
        renderHistoryList();
      } catch (e) {
        // Ignored
      }
    }

    function renderHistoryList() {
      const listEl = document.getElementById('history-list');
      if (allLicenses.length === 0) {
        listEl.innerHTML = '<div style="padding: 16px; text-align: center; color: #94a3b8; font-size: 12px;">暂无历史签发记录</div>';
        return;
      }

      listEl.innerHTML = allLicenses.map(lic => {
        const plan = PLANS[lic.plan_type] || { name: lic.plan_type };
        const isActive = lic.status === 'active';
        return `
          <div class="history-item">
            <div class="history-info">
              <div class="history-name">${plan.name} · ${lic.id}</div>
              <div class="history-sub">${lic.machine_id}${lic.bound_mid ? ' [已激活设备: ' + lic.bound_mid + ']' : ''} · ${lic.max_servers}服/${lic.max_nodes}节/${lic.max_users}户</div>
            </div>
            <div class="history-actions">
              <span class="badge ${isActive ? 'badge-active' : 'badge-revoked'}">
                ${isActive ? '有效' : '已吊销'}
              </span>
              <button type="button" class="btn-action-small" onclick="copySingleKey('${lic.id}')">复制</button>
              ${isActive 
                ? `<button type="button" class="btn-action-small btn-action-revoke" onclick="toggleRevoke('${lic.id}', 'revoke')">吊销</button>`
                : `<button type="button" class="btn-action-small" onclick="toggleRevoke('${lic.id}', 'unrevoke')">恢复</button>`
              }
            </div>
          </div>
        `;
      }).join('');
    }

    async function toggleRevoke(id, action) {
      try {
        const res = await fetch('/api/v1/license/' + action, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ id })
        });
        const data = await res.json();
        if (data.ok) {
          showToast(action === 'revoke' ? '已吊销' : '已恢复');
          loadLicenses();
        }
      } catch {
        showToast('操作失败');
      }
    }

    // 初始化渲染
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
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, HEAD")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS, HEAD")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_HEAD(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()

    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path

        # 1. 首页发布 UI
        if path in ("/", "/index.html"):
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
            client_ip = self.headers.get("X-Forwarded-For", "").split(",")[0].strip() or self.client_address[0]
            now = int(time.time())

            if not lic_key:
                self.send_json({"status": "invalid", "message": "缺失许可证"}, 400)
                return

            conn = get_db()
            cur = conn.execute("SELECT id, status FROM licenses WHERE license_key = ? OR id = ?", (lic_key, lic_key))
            row = cur.fetchone()
            if not row and mid and mid != "ANY":
                cur = conn.execute("SELECT id, status FROM licenses WHERE machine_id = ? OR bound_mid = ?", (mid, mid))
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

        # 2. 客户端短激活码激活与防伪凭据获取 (/api/v1/license/activate_code)
        if path == "/api/v1/license/activate_code":
            code = req.get("code", "").strip()
            mid = req.get("machine_id", "").strip().upper()
            now = int(time.time())
            client_ip = self.headers.get("X-Forwarded-For", "").split(",")[0].strip() or self.client_address[0]

            if not code:
                self.send_json({"ok": False, "message": "激活码不能为空"}, 400)
                return

            conn = get_db()
            cur = conn.execute("SELECT * FROM licenses WHERE id = ? OR license_key = ?", (code, code))
            row = cur.fetchone()
            if not row:
                conn.close()
                self.send_json({"ok": False, "message": "激活码不存在或已被作废"}, 404)
                return

            lic = dict(row)
            if lic.get("status") == "revoked":
                conn.close()
                self.send_json({"ok": False, "message": "该许可证已被中心授权服务器吊销冻结"}, 403)
                return

            expire_at = lic.get("expire_at", 0)
            if expire_at and expire_at > 0 and expire_at < now:
                conn.close()
                self.send_json({"ok": False, "message": "该许可证已过期"}, 403)
                return

            # 机器码绑定校验
            assigned_mid = lic.get("machine_id", "").strip().upper()
            bound_mid = lic.get("bound_mid", "").strip().upper()

            if assigned_mid and assigned_mid != "ANY" and assigned_mid != mid:
                conn.close()
                self.send_json({"ok": False, "message": f"该激活码已锁定目标机器识别码 {assigned_mid}，与当前设备不符"}, 403)
                return

            if bound_mid and bound_mid != "ANY" and bound_mid != mid:
                conn.close()
                self.send_json({"ok": False, "message": f"该激活码已被其他设备 ({bound_mid}) 激活绑定，如需换绑请联系管理员"}, 403)
                return

            # 更新激活与绑定信息
            with conn:
                conn.execute("""
                    UPDATE licenses
                    SET bound_mid = CASE WHEN (bound_mid IS NULL OR bound_mid = '' OR bound_mid = 'ANY') THEN ? ELSE bound_mid END,
                        activated_at = CASE WHEN (activated_at IS NULL OR activated_at = 0) THEN ? ELSE activated_at END,
                        last_ping_at = ?,
                        last_ping_ip = ?
                    WHERE id = ?
                """, (mid, now, now, client_ip, lic["id"]))
            conn.close()

            self.send_json({
                "ok": True,
                "raw_token": lic["license_key"],
                "license_id": lic["id"],
                "plan_type": lic["plan_type"],
                "max_servers": lic["max_servers"],
                "max_nodes": lic["max_nodes"],
                "max_users": lic["max_users"],
                "expire_at": lic["expire_at"],
                "message": "激活成功"
            })
            return

        # 3. 签发新许可证 API (/api/v1/license/generate)
        if path == "/api/v1/license/generate":
            try:
                customer = req.get("customer", "").strip() or "商业授权"
                mid = req.get("machine_id", "").strip().upper()
                plan_type = req.get("plan_type", "planet")
                days = int(req.get("days", 365))
                count = int(req.get("count", 1))
                if count < 1:
                    count = 1
                if count > 100:
                    count = 100

                if not mid:
                    self.send_json({"ok": False, "field": "machine_id", "message": "请输入目标机器识别码或设为 ANY"}, 400)
                    return

                now = int(time.time())
                expire_at = (now + days * 86400) if days > 0 else 0

                plan_cfg = PLAN_CONFIGS.get(plan_type, PLAN_CONFIGS["planet"])
                max_servers = int(req.get("max_servers") or plan_cfg["max_servers"])
                max_nodes = int(req.get("max_nodes") or plan_cfg["max_nodes"])
                max_users = int(req.get("max_users") or plan_cfg["max_users"])

                conn = get_db()
                generated_licenses = []
                generated_keys = []

                with conn:
                    for _ in range(count):
                        # 生成 23 位专属短激活码: PP-XXXX-XXXX-XXXX-XXXX
                        short_code = generate_short_code()

                        # 生成 Ed25519 底层签名凭证载荷 (用于离线防伪与核心校验)
                        payload = {
                            "id": short_code,
                            "type": plan_type,
                            "customer": customer,
                            "machine_id": mid,
                            "max_servers": max_servers,
                            "max_nodes": max_nodes,
                            "max_users": max_users,
                            "issued_at": now,
                            "expire_at": expire_at
                        }
                        lic_key = generate_license_string(payload)

                        conn.execute("""
                        INSERT INTO licenses (id, customer, machine_id, plan_type, max_servers, max_nodes, max_users, issued_at, expire_at, license_key, status, bound_mid, activated_at)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'active', '', 0)
                        """, (short_code, customer, mid, plan_type, max_servers, max_nodes, max_users, now, expire_at, lic_key))

                        generated_licenses.append({
                            "id": short_code,
                            "license_key": short_code,
                            "raw_token": lic_key,
                            "expire_at": expire_at
                        })
                        generated_keys.append(short_code)

                conn.close()

                self.send_json({
                    "ok": True,
                    "count": count,
                    "licenses": generated_licenses,
                    "license_keys": generated_keys,
                    "license_id": generated_keys[0],
                    "license_key": "\n".join(generated_keys),
                    "plan_type": plan_type,
                    "plan_name": plan_cfg.get("name", plan_type),
                    "customer": customer,
                    "machine_id": mid,
                    "max_servers": max_servers,
                    "max_nodes": max_nodes,
                    "max_users": max_users,
                    "expire_at": expire_at,
                    "message": f"成功签发 {count} 张许可证" if count > 1 else "许可证签发成功"
                })
            except Exception as e:
                self.send_json({"ok": False, "message": f"服务器内部错误: {e}"}, 500)
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

        # 5. 删除许可证 API (/api/v1/license/delete)
        if path == "/api/v1/license/delete":
            lic_id = req.get("id")
            conn = get_db()
            with conn:
                conn.execute("DELETE FROM licenses WHERE id = ?", (lic_id,))
            conn.close()
            self.send_json({"ok": True, "message": "许可证记录已删除"})
            return

        self.send_json({"error": "Not Found"}, 404)

def run_server():
    init_db()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), LicenseServerHandler)
    print(f"ProxyProbe License Center listening on 0.0.0.0:{PORT}")
    server.serve_forever()

if __name__ == "__main__":
    run_server()
