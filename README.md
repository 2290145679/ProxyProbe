# 🚀 ProxyProbe - 分布式服务器监控与 Xray / Sing-box 双核心代理管理系统

<p align="center">
  <img src="https://img.shields.io/badge/Release-v2.0.0-blue.svg" alt="Release">
  <img src="https://img.shields.io/badge/Dual_Core-Xray_Core_%2B_Sing--box-success.svg" alt="Dual Core">
  <img src="https://img.shields.io/badge/Protocols-15_Types_Supported-purple.svg" alt="Protocols">
  <img src="https://img.shields.io/badge/Frontend-Vite_%2B_React_%2B_Tailwind-cyan.svg" alt="Frontend">
  <img src="https://img.shields.io/badge/Backend-Rust_%2B_Python-orange.svg" alt="Backend">
  <img src="https://img.shields.io/badge/License-Commercial-red.svg" alt="License">
</p>

**ProxyProbe** 是一套现代化、高颜值且极度轻量的**分布式服务器状态监控与全自动代理协议拓扑管理平台**。项目在高性能分布式探针的基础上，深度融合了 **Xray-Core 与 Sing-box 双核心调度体系**，彻底解决了多节点下跨协议部署繁琐、配置容易冲突、客户端格式不兼容的痛点。详细版本更新内容请参阅 [版本更新日志 (Changelog)](CHANGELOG.md)。

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
  - 若所选服务器尚未安装目标协议所需核心，前端与后端均自动弹出警示并严格拦截，杜绝创建出无效节点。
- 📶 **一键实时连通性与握手测速**：
  - 节点列表内置 **【测试】** 按钮，一键发起全链路 TLS / UDP 握手测试，毫秒级回显实际网络延迟。
- 🔗 **聚合订阅一键分发**：
  - 自动将所有已启用节点整合成通用 Base64 聚合订阅，支持 **Clash Verge Rev、v2rayN、Shadowrocket、Sing-box、Loon、Surge** 等客户端一键导入。
- 🔑 **商业许可证双轨授权**：
  - 探针监控功能**永久免费**；节点管理功能需要商业授权激活。
  - 支持离线 Ed25519 签名验签 + 机器指纹绑定 + 在线吊销管控。
- 🔒 **二进制发布保护**：
  - 核心业务逻辑编译为独立 Linux ELF 可执行文件发布，客户服务器上无明文源码。

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
                    │  web-admin   │ │proxy-manager │ │ monitor-hub  │
                    │ (Vite React) │ │ (ELF Binary) │ │ (Rust:28080) │
                    └──────────────┘ └───────┬──────┘ └──────┬───────┘
                                             │               │
                                             ▼               ▼
                                     ┌───────────────────────────────┐
                                     │    SQLite 数据库共享存储       │
                                     │      /opt/monitor/data/       │
                                     │          monitor.db           │
                                     └───────────────────────────────┘
                                                     ▲
                                                     │ 5秒自动同步
                      ┌──────────────────────────────┴────────────────┐
                      │                                               │
             ┌─────────────────┐                             ┌─────────────────┐
             │  探针被控节点 A   │                             │  探针被控节点 B   │
             │   monitor-agent │                             │   monitor-agent │
             │   Xray + Singbox│                             │   Xray + Singbox│
             └─────────────────┘                             └─────────────────┘
```

---

## 🚀 一键部署

> **本仓库为私有仓库，部署文件通过 GitHub Release 公开分发。**

### 主控端一键安装（全新服务器）

> 推荐操作系统：**Ubuntu 22.04+ / Debian 11+**，已将域名 DNS 解析到本机 IP。

```bash
curl -fsSL https://github.com/2290145679/ProxyProbe/releases/latest/download/deploy-hub.sh | bash
```

脚本会交互式询问：
- 📌 绑定域名（必填，用于自动申请 SSL 证书）
- 🔑 管理员密码（留空则随机生成）
- 🌐 外部访问端口（默认 443，支持自定义）
- ⚙️ 内部服务端口（默认 28080 / 28090，支持自定义）

脚本自动完成：
- ✅ 安装系统依赖（Python3、curl、git、openssl 等）
- ✅ 安装并配置 **Caddy**（自动申请 SSL 证书）
- ✅ 下载 **monitor-hub** 探针主控二进制（Rust，超低资源占用）
- ✅ 下载 **proxy-manager** 代理管理二进制（含商业授权核心）
- ✅ 下载并部署前端管理面板
- ✅ 配置所有 systemd 服务并设置开机自启
- ✅ 安装 `hhub` 终端运维控制台
- ✅ 初始化管理员账户
- ✅ 自动放行防火墙端口

安装完成后访问 `https://your-domain.com/admin` 即可登录后台。

---

### 非交互静默部署（预设参数）

```bash
export DOMAIN=your-domain.com ADMIN_PASS=yourpassword
curl -fsSL https://github.com/2290145679/ProxyProbe/releases/latest/download/deploy-hub.sh | bash
```

---

### 添加被控探针节点（一键接入）

1. 在管理后台「服务器」页面添加节点，复制生成的**安装指令**（已自动包含 TOKEN）。
2. 在被控服务器上直接粘贴运行即可，脚本自动：
   - 安装 `monitor-agent` 性能探针
   - 按需部署 `Xray-core` / `Sing-box` / `Realm` 代理核心
   - 自动生成自签 ECC 证书
   - 启动 `proxy-agent.service` 后台同步进程（5 秒热同步）

---

## 🖥️ hhub 终端运维控制台

安装完成后，SSH 登录服务器，直接输入：

```bash
hhub
```

即可进入可视化终端管理菜单，支持：

| 功能 | 说明 |
|:---|:---|
| 查看系统状态 | 服务存活、端口占用、用户节点数 |
| 一键重启 / 停止 / 启动 | 控制所有服务 |
| 修改 Web 外部端口 | 自动同步 Caddyfile 与防火墙 |
| 修改内部通信端口 | 探针端口与代理端口独立调整 |
| 修改绑定域名 | 自动重置 Caddy 申请新 SSL |
| 重置管理员密码 | 双端同步更新 |
| 一键无损热升级 | 自动拉取最新 Release 文件 |
| 实时查看日志 | proxy-manager / monitor-hub / caddy |
| 数据库备份与还原 | 自动打时间戳 |
| 安全卸载 | 支持保留数据库或彻底清除 |

---

## 🔑 商业授权说明

| 功能项 | 免费体验版 | 商业授权版 |
|:---|:---:|:---:|
| 探针全功能（服务器状态/CPU/内存/流量监控）| ✅ 无限制 | ✅ 无限制 |
| 公开探针状态大屏 | ✅ 支持 | ✅ 支持 |
| 服务器管理配额 | 最多 **1** 台 | 🚀 **无限制** |
| 代理协议节点配额 | 最多 **1** 个 | 🚀 **无限制** |
| 客户端用户配额 | 最多 **1** 个 | 🚀 **无限制** |
| Xray / Sing-box / Realm 多协议拓扑 | ✅ 支持完整体验 | 🚀 全核心集群调度 |
| 聚合订阅链接一键生成分发 | ✅ 支持 | 🚀 支持 |
| 节点连通性毫秒级测速 | ✅ 支持 | 🚀 支持 |
| 独立用户流量限制与设备数限制 | ✅ 支持 | 🚀 支持 |

如需扩容服务器、解锁多节点集群与无限用户分发，请联系项目作者获取商业授权激活码。

---

## ❓ 常见问题排查 (FAQ)

### Q1: 新建了 Hysteria 2 节点却连不上？
- **检查核心安装**：请检查该节点服务器是否安装了 `Sing-box`。在后台"所属服务器"下拉列表中，Sing-box 标点为红色 `🔴` 代表尚未安装。
- **一键补装**：在目标服务器终端重新执行探针一键安装指令即可自动补装 Sing-box 核心。
- **防火墙端口**：Hysteria 2 使用 UDP 传输协议，请确保云服务商控制台已放行对应的 **UDP 端口**。

### Q2: 节点列表中的【测试】按钮是测什么的？
- 该按钮会向后端发起真实链路握手：
  - 若为 TCP 协议（如 Reality / Trojan），测试 TCP 连接与 TLS Client Hello 握手；
  - 若为 UDP 协议（如 Hysteria 2），测试 UDP 端口连通与协议套接字握手；
- 测试通过后会以绿色字样显示实际网络往返延迟（如 `45ms`）。

### Q3: 为什么订阅无法更新？
- 请检查后台"聚合订阅服务"卡片中的 Token 是否有效；
- 若曾点击过【重置 Token】，原先已导入客户端的订阅链接将失效，需重新复制最新链接导入客户端。

### Q4: 部署时提示下载 proxy-manager 失败？
- 请确认 Release 中存在对应架构的 `proxy-manager-linux-amd64`（或 `arm64`）文件。
- 访问 Release 页面检查：`https://github.com/2290145679/ProxyProbe/releases`

---

## 📄 许可证

本项目为**商业私有软件**，保留所有权利。未经授权，不得复制、修改、分发本项目的源码或二进制文件。
