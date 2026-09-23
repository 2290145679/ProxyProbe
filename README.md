# 🚀 ProxyProbe - 分布式服务器监控与 Xray / Sing-box 双核心代理管理系统

<p align="center">
  <img src="https://img.shields.io/badge/Release-v2.0.0-blue.svg" alt="Release">
  <img src="https://img.shields.io/badge/Dual_Core-Xray_Core_%2B_Sing--box-success.svg" alt="Dual Core">
  <img src="https://img.shields.io/badge/Protocols-15_Types_Supported-purple.svg" alt="Protocols">
  <img src="https://img.shields.io/badge/Frontend-Vite_%2B_React_%2B_Tailwind-cyan.svg" alt="Frontend">
  <img src="https://img.shields.io/badge/Backend-Rust_%2B_Python-orange.svg" alt="Backend">
  <img src="https://img.shields.io/badge/License-MIT-green.svg" alt="License">
</p>

**ProxyProbe** 是一套现代化、高颜值且极度轻量的**分布式服务器状态监控与全自动代理协议拓扑管理平台**。项目在高性能分布式探针的基础上，深度融合了 **Xray-Core 与 Sing-box 双核心调度体系**，彻底解决了多节点下跨协议部署繁琐、配置容易冲突、客户端格式不兼容的痛点。

---

## 🌟 核心特性

- ⚡ **超低资源开销**：主控端与探针核心采用 Rust 编写，探针端内存占用极低（< 15MB），CPU 占用常态接近 0%。
- 🔄 **Xray-Core + Sing-box 双核心协同**：
  - **Xray-Core**：负责承载 VLESS + Reality (Vision / XHTTP)、Trojan、VMess-WS、Shadowsocks 2022、SOCKS5 等 TCP/TLS 极致伪装协议。
  - **Sing-box**：原生驱动 Hysteria 2 (Hy2)、TUIC v5 等基于 QUIC / UDP 的极速网络协议。
- 🛡️ **智能核心在线管理**：
  - 管理后台顶部直观呈现 Xray 与 Sing-box 双核心的运行版本与健康状态。
  - 支持后台一键 **【安装核心】** 与 **【卸载核心】**，自动生成高强度 ECC 自签名证书（prime256v1）并配置 Systemd 守护进程。
- 🚦 **服务器双核心红绿灯感知与防呆拦截**：
  - 新建节点弹窗中，所属服务器实时显示核心就绪情况：`[🟢/🔴 Xray]  [🟢/🔴 Sing-box]`。
  - 若所选服务器尚未安装目标协议所需核心（例如在未安装 Sing-box 的探针节点创建 Hy2），前端与后端均自动弹出警示并严格拦截，杜绝创建出无效节点。
- 📶 **一键实时连通性与握手测速**：
  - 节点列表内置 **【测试】** 按钮，一键发起全链路 TLS / UDP 握手测试，毫秒级回显实际网络延迟。
- 🔗 **聚合订阅一键分发**：
  - 自动将所有已启用节点整合成通用 Base64 聚合订阅，支持 **Clash Verge Rev、v2rayN、Shadowrocket、Sing-box、Loon、Surge** 等客户端一键导入。
- 🚀 **探针+代理双核心一键安装**：
  - 探针端仅需一条 `curl` 命令，即可全自动部署探针、双核心与守护进程，后续在后台所做改动 5 秒内自动热同步。

---

## 📐 系统架构

```
                      ┌───────────────────────────────────────────────┐
                      │            Caddy 统一反向代理网关 (443)         │
                      │                 your-domain.com               │
                      └───────┬──────────────┬──────────────┬─────────┘
                              │              │              │
      /admin*, /install.sh    │ /api/proxy/* │              │ /api/*, /ws, /
      静态资源与一键脚本分发   │ 代理管理API  │              │ 探针公开状态面板
                              ▼              ▼              ▼
                    ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
                    │  web-admin   │ │proxy_manager │ │ monitor-hub  │
                    │ (Vite React) │ │(Python:28090)│ │ (Rust:28080) │
                    └──────────────┘ └───────┬──────┘ └──────┬───────┘
                                             │               │
                                             ▼               ▼
                                     ┌───────────────────────────────┐
                                     │    SQLite 数据库共享存储       │
                                     │      /opt/monitor/data/       │
                                     │          monitor.db           │
                                     └───────────────────────────────┘
                                                     ▲
                                                     │ 5秒自动同步 /agent-sync
                      ┌──────────────────────────────┴────────────────┐
                      │                                               │
             ┌─────────────────┐                             ┌─────────────────┐
             │  探针被控节点 A   │                             │  探针被控节点 B   │
             │   monitor-agent │                             │   monitor-agent │
             │   proxy_agent.py│                             │   proxy_agent.py│
             │   Xray + Singbox│                             │   Xray + Singbox│
             └─────────────────┘                             └─────────────────┘
```

---

## 🚀 一键部署

### 主控端一键安装（全新服务器）

> 推荐操作系统：**Ubuntu 22.04+ / Debian 11+**，已将域名 DNS 解析到本机 IP。

\\ash
curl -fsSL https://raw.githubusercontent.com/2290145679/ProxyProbe/main/scripts/deploy-hub.sh | bash
\
脚本会自动完成：
- ✅ 安装系统依赖（Python3、curl、git、openssl 等）
- ✅ 安装并配置 **Caddy**（自动申请 SSL 证书）
- ✅ 安装 **monitor-hub** 探针主控（Rust 编写，超低资源占用）
- ✅ 部署 **proxy_manager**（代理协议管理守护进程）
- ✅ 从 GitHub 拉取最新前端构建产物
- ✅ 配置所有 systemd 服务并设置开机自启
- ✅ 初始化管理员账户
- ✅ 自动放行防火墙端口

安装完成后访问 https://your-domain.com/admin 即可登录后台。

---

### 手动指定参数（非交互模式）

\\ash
export DOMAIN=your-domain.com
export ADMIN_PASS=your-password
curl -fsSL https://raw.githubusercontent.com/2290145679/ProxyProbe/main/scripts/deploy-hub.sh | bash
\
---

### 添加被控探针节点（一键接入）

1. 在管理后台「服务器」页面添加节点，复制生成的**安装指令**（已自动包含 TOKEN）。
2. 在被控服务器上直接粘贴运行即可，脚本会自动：
   - 安装系统级 \monitor-agent\ 性能探针
   - 按需部署 \Xray-core\ / \Sing-box\ / \Realm\ 代理核心
   - 自动生成自签 ECC 证书
   - 启动 \proxy-agent.service\ 后台同步进程（5 秒热同步）
---

## 💻 本地前端开发与构建

项目前端采用现代 React 技术栈（Vite + React + Tailwind CSS + Lucide Icons）：

```bash
# 1. 进入前端目录
cd upstream-monitor/web-admin

# 2. 安装依赖
npm install

# 3. 开发预览
npm run dev

# 4. 编译生产代码
npm run build
```
编译产物会自动输出至 `upstream-monitor/web-admin/dist`。

---

## 📂 项目结构说明

```
ProxyProbe/
├── proxy_manager.py           # 代理管理后端（用户/节点/流量/设备限制/订阅生成）
├── server/                    # Rust 探针主控（monitor-hub）
│   ├── src/                   # Rust 源码（axum + tokio + rusqlite）
│   ├── Cargo.toml             # 包定义（repository 指向本仓库）
│   └── web-admin/             # 管理后台前端源码（Vite + React + Tailwind）
│       └── src/components/
│           ├── UserDashboard.tsx  # 用户界面（订阅、节点、IP隐藏、探针入口）
│           ├── ProxyUsers.tsx     # 用户管理（设备限制、流量配额）
│           ├── ProxyNodes.tsx     # 节点管理（双核心/防呆拦截）
│           └── ProxyServers.tsx   # 服务器管理（一键安装指令生成）
├── web-admin/dist/            # 前端构建产物（部署时使用）
├── scripts/
│   ├── deploy-hub.sh          # 主控端一键部署（仅从本仓库下载）
│   └── install.sh             # 子节点一键安装（探针+代理核心）
├── .github/workflows/
│   └── release.yml            # 打 tag 时自动编译 monitor-hub 二进制并发布 Release
├── systemd/
│   └── proxy-manager.service  # proxy-manager 系统服务定义
└── config/
    └── Caddyfile              # Caddy 反向代理配置模板
```

---

## ❓ 常见问题排查 (FAQ)

### Q1: 新建了 Hysteria 2 节点却连不上？
- **检查核心安装**：请检查该节点服务器是否安装了 `Sing-box`。在后台“所属服务器”下拉列表中，Sing-box 标点为红色 `🔴` 代表尚未安装。
- **一键补装**：在目标服务器终端重新执行探针一键安装指令即可自动补装 Sing-box 核心。
- **防火墙端口**：Hysteria 2 使用 UDP 传输协议，请确保云服务商控制台（如阿里云、腾讯云、AWS 安全组）已放行对应的 **UDP 端口**。

### Q2: 节点列表中的【测试】按钮是测什么的？
- 该按钮会向后端发起真实链路握手：
  - 若为 TCP 协议（如 Reality / Trojan），测试 TCP 连接与 TLS Client Hello 握手；
  - 若为 UDP 协议（如 Hysteria 2），测试 UDP 端口连通与协议套接字握手；
- 测试通过后会以绿色字样显示实际网络往返延迟（如 `45ms`），极大方便排查各节点的健康状况。

### Q3: 为什么订阅无法更新？
- 请检查后台“聚合订阅服务”卡片中的 Token 是否有效；
- 若曾点击过【重置 Token】，原先已导入客户端的订阅链接将失效，需重新复制最新链接导入客户端。

---

## 📄 开源许可证

本项目基于 [MIT License](LICENSE) 开源发布。
