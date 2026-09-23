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

## 🛠️ 部署指南

### 第一步：准备主控端环境 (主控 VPS)

推荐操作系统：**Ubuntu 22.04+ / Debian 11+**

1. **安装基础依赖**：
   ```bash
   apt-get update -y && apt-get install -y python3 python3-pip curl unzip git iptables
   ```

2. **克隆本项目代码**：
   ```bash
   git clone https://github.com/2290145679/ProxyProbe.git /opt/monitor
   cd /opt/monitor
   ```

3. **配置目录权限与数据库初始化**：
   ```bash
   mkdir -p /opt/monitor/data /opt/monitor/scripts /etc/xray /etc/sing-box
   # 若首次运行，导入基础表结构
   sqlite3 /opt/monitor/data/monitor.db < database/schema.sql
   ```

---

### 第二步：配置并启动主控端服务

1. **部署 Systemd 服务单元**：
   ```bash
   cp systemd/monitor-hub.service /etc/systemd/system/
   cp systemd/proxy-manager.service /etc/systemd/system/
   systemctl daemon-reload
   systemctl enable --now monitor-hub.service
   systemctl enable --now proxy-manager.service
   ```

2. **配置 Caddy 反向代理网关 (自带自动申请 SSL)**：
   编辑 `/etc/caddy/Caddyfile`（将 `your-domain.com` 替换为您解析好的域名）：
   ```caddy
   your-domain.com {
       encode gzip

       # 1. 代理管理后台 API
       handle /api/proxy/* {
           reverse_proxy 127.0.0.1:28090
       }

       # 2. 探针端同步脚本与部署入口
       handle /proxy-agent.sh {
           reverse_proxy 127.0.0.1:28090
       }

       # 3. 探针安装脚本分发
       handle /install.sh {
           root * /opt/monitor/scripts
           try_files /install.sh
           file_server
       }

       # 4. 管理后台前端静态资源
       handle_path /admin* {
           root * /opt/monitor/web-admin/dist
           try_files {path} /index.html
           file_server
       }

       # 5. Monitor 探针主控 API 与 WebSocket
       handle {
           reverse_proxy 127.0.0.1:28080
       }
   }
   ```
   重启 Caddy：
   ```bash
   systemctl restart caddy
   ```

3. **进入管理后台**：
   - 访问 `https://your-domain.com/admin`
   - 首次登录后即可进入面板。

---

### 第三步：添加被控探针节点 (一键接入)

1. 在管理后台的“服务器管理”中添加一个新节点，复制生成的节点 **TOKEN**。
2. 登录需要被监控的被控端服务器，运行以下**一条指令**即可完成全部安装：
   ```bash
   curl -fsSL https://your-domain.com/install.sh | bash -s -- --server https://your-domain.com --token <您的节点TOKEN>
   ```
3. 脚本会自动完成以下操作：
   - 安装系统级 `monitor-agent` 性能探针；
   - 自动部署 `Xray-core` 与 `Sing-box` 双核心环境；
   - 自动生成自签 ECC 证书；
   - 启动 `proxy-agent.service` 后台同步进程，每 5 秒与主控端保持同步。

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
├── proxy_manager.py           # 核心代理管理后端守护进程 (双核心调度/配置下发/鉴权)
├── config/
│   ├── Caddyfile              # 生产环境网关路由及 SSL 反代规则模板
│   ├── agent.env.example      # 探针环境变量参考示例
│   └── xray-config.json       # Xray 默认模板配置
├── database/
│   ├── schema.sql             # 基础数据库表结构 (包含 proxy_node, node_proxy_status)
│   └── dump.sql               # 初始数据备份
├── scripts/
│   ├── install-hub.sh         # 主控端自动化部署脚本
│   ├── install.sh             # 探针节点一键安装增强脚本
│   └── vless-server.sh        # 单机一键部署备用工具
├── systemd/
│   ├── monitor-hub.service    # 探针主控守护进程服务
│   ├── monitor-agent.service  # 探针被控端服务
│   └── proxy-manager.service  # 代理管理守护进程服务
├── upstream-monitor/          # 探针监控核心源码与管理后台前端
│   ├── src/                   # Rust 探针主控服务端源码
│   └── web-admin/             # React + Vite 前端管理后台源码
│       └── src/components/
│           ├── ProxyNodes.tsx # 代理协议管理核心组件 (双核心卡片/节点列表/测速/防呆)
│           └── Admin.tsx      # 管理后台主容器
└── README.md                  # 项目详细文档
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
