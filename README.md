# 🚀 ProxyProbe - 分布式服务器监控与 Xray / Sing-box / Realm 代理拓扑管理系统

<p align="center">
  <img src="https://img.shields.io/badge/Release-v2.4.0-blue.svg" alt="Release">
  <img src="https://img.shields.io/badge/Dual_Core-Xray_%2B_Sing--box_%2B_Realm-success.svg" alt="Cores">
  <img src="https://img.shields.io/badge/Subscription-Smart_UA_Adaptive-orange.svg" alt="Smart UA Subscription">
  <img src="https://img.shields.io/badge/GeoIP-Auto_Flag_Emoji-purple.svg" alt="Auto Flag Emoji">
  <img src="https://img.shields.io/badge/Theme-Sakura_%2B_Classic-pink.svg" alt="Sakura Theme">
  <img src="https://img.shields.io/badge/Responsive-Mobile_Optimized-brightgreen.svg" alt="Mobile Optimized">
  <img src="https://img.shields.io/badge/Backup-Telegram_Automated-blue.svg" alt="Telegram Backup">
  <img src="https://img.shields.io/badge/Backend-Rust_%2B_Python-red.svg" alt="Backend">
</p>

**ProxyProbe** 是一套现代化、高颜值、轻量且强大的**分布式服务器状态监控、代理节点拓扑调度与聚合订阅分发平台**。系统在高性能 Rust 分布式探针的基础上，深度融合了 **Xray-Core、Sing-box 与 Realm 多核心协同调度矩阵**，支持全主流代理协议拓扑、全平台客户端自适应万能订阅、节点国旗 Emoji 智能解析、AI 与流媒体自选检测、移动端精细适配与双主题自由切换。详细版本更新内容请参阅 [版本更新日志 (CHANGELOG.md)](CHANGELOG.md)。

---

## 🌟 核心特性

- ⚡ **超低资源极速探针**：
  - 主控端与探针核心采用 Rust 编写，探针客户端内存占用极低（< 15MB），CPU 常态占用接近 0%。
- 🔄 **Xray-Core + Sing-box + Realm 三核心协同调度**：
  - **Xray-Core**：负责承载 VLESS + Reality (Vision / XHTTP)、Trojan、VMess-WS、Shadowsocks 2022、SOCKS5 等 TCP/TLS 极致伪装协议。
  - **Sing-box**：原生驱动 Hysteria 2 (Hy2)、TUIC v5 等基于 QUIC / UDP 的极速网络协议。
  - **Realm**：高效低延迟端口中转转发调度，轻松组建多级中继拓扑。
- ⚡ **万能自适应智能订阅 (Universal Smart UA Subscription)**：
  - 单一订阅链接全客户端自适应：后端依据客户端 `User-Agent` 智能感知客户端类型，自动分发最优订阅配置（Clash/Mihomo -> Clash YAML 规则组；Sing-box -> Sing-box JSON 核心配置；Shadowrocket/v2rayN -> 标准 Base64 聚合节点链）。
  - 支持手动强制覆盖参数（`?clash=1`、`?singbox=1`、`?b64=1`）。
  - 用户面板化繁为简，突出醒目的「⚡ 复制万能智能订阅」核心按钮，搭配小火箭/Clash/Sing-box 一键唤醒导入与手机扫码导入，体验极致丝滑。
- 🌍 **节点自动识别国家地区国旗 Emoji (Auto GeoIP Flag)**：
  - 探针及节点管理自动根据被控端地理位置信息（`node.country`）或地区关键字（HK/JP/US/SG/TW/DE 等）智能解析并前置对应国家地区国旗 Emoji（🇭🇰/🇯🇵/🇺🇸/🇸🇬/🇨🇳/🇩🇪/🇬🇧 等）。
  - 全订阅协议（Clash YAML、Sing-box JSON、Base64）以及管理后台、用户自服务面板的节点展示名均自动携带国旗图标，节点归属一目了然。
- ⚙️ **节点创建弹窗极简降噪 (Decluttered Modal)**：
  - 节点添加/编辑弹窗重构：默认仅露出「服务器、中转模式、协议、节点名称、监听端口」核心必填项。
  - 复杂的 SNI 伪装域名、Dest 目标、Reality x25519 密钥、UUID / 连接密码全量收纳进「⚙️ 高级配置 (点击展开)」折叠卡片中，且默认自动完成安全密钥生成，实现开箱即用的极致简约。
- 🌸 **全新高颜值樱花浪漫主题 (Sakura Theme)**：
  - 内置经典工业灰与浪漫落樱粉双主题引擎，界面灵动优雅。
  - 主题设置随用户账号持久化存储，管理员与普通用户可按需独立随心切换。
- 📱 **移动端与全端响应式深度适配**：
  - 针对手机端、Pad 及超宽/超窄视口重新优化网格排版与弹性布局，彻底消灭横向滚动条。
  - 顶部导航栏、卡片状态组、操作按钮及退出登录项均做手机触控微调，单手滑动丝滑自如。
- 🎯 **AI 与流媒体解锁检测自定义筛选**：
  - 针对节点流媒体（Netflix、Disney+、YouTube 等）与 AI 矩阵（ChatGPT、Claude、Gemini 等）提供全自动流媒体解锁探测。
  - 支持用户自定义勾选“仅关注的服务”，告别全量大卡片冗余堆叠，界面清爽聚焦。
- 📶 **全链路握手测速与红绿灯防呆拦截**：
  - 节点列表内置 **【测试】** 按钮，一键发起全链路 TLS / UDP 握手测试，毫秒级回显实际往返延迟。
  - 新建节点弹窗中，所属服务器实时显示核心就绪情况：`[🟢/🔴 Xray]  [🟢/🔴 Sing-box]  [🟢/🔴 Realm]`，未安装核心自动拦截防呆。
- 🤖 **Telegram 自动化数据热备份**：
  - 内置 SQLite 在线热备份（Online Backup API）与 Gzip 压缩归档，零停机备份。
  - 支持对接 Telegram Bot，定时将数据库备份文件及用户节点统计简报自动推送到指定的 TG 会话。
- 🖥️ **可视化终端运维工具 `hhub`**：
  - 纯 IP 模式与域名 HTTPS 模式一键智能无损切换，自动处理 80 / 443 端口与防火墙规则。
  - 支持一键服务启停、重置密码、修改端口、实时日志滚屏、无损热升级与数据库还原。
- 🔒 **无源码独立二进制分发**：
  - 代理管理中枢编译为独立 Linux ELF 二进制程序分发，杜绝生产服务器源码泄露风险。

---

## 📐 系统架构

```
                      ┌───────────────────────────────────────────────┐
                      │            Caddy 统一反向代理网关 (443 / 80)    │
                      │                 your-domain.com / IP          │
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
             │ Xray+Singbox+Rlm│                             │ Xray+Singbox+Rlm│
             └─────────────────┘                             └─────────────────┘
```

---

## 🚀 一键部署

### 主控端一键安装（全新服务器）

> 推荐操作系统：**Ubuntu 22.04+ / Debian 11+**。支持纯 IP 安装或预先解析域名。

```bash
curl -fsSL https://raw.githubusercontent.com/2290145679/ProxyProbe-Release/main/deploy-hub.sh | bash
```

脚本会交互式引导完成配置：
- 📌 **绑定域名或公网 IP**（输入域名将自动申请 SSL 证书，输入 IP 则启用纯 IP 模式）
- 🔑 **管理员密码**（留空则自动生成高强度安全随机密码）
- 🌐 **外部访问端口**（域名模式默认 443，纯 IP 模式默认 80，支持自定义）
- ⚙️ **内部通信端口**（默认 28080 / 28090 本地回环反代）

脚本自动执行并完成：
- ✅ 安装系统核心依赖（Python3、curl、git、openssl 等）
- ✅ 安装并配置 **Caddy**（自动化 SSL 证书或 IP 反代网关）
- ✅ 安装 **monitor-hub** 探针主控核心（Rust 编写，超低资源开销）
- ✅ 安装 **proxy-manager** 代理中枢核心（独立 Linux ELF 二进制程序）
- ✅ 部署现代化前端静态资源（React SPA，支持樱花/经典多主题）
- ✅ 配置 systemd 守护进程并开启开机自启
- ✅ 安装 `hhub` 终端可视化运维控制台
- ✅ 自动放行防火墙端口与 ACME 验证端口

安装完成后，打开浏览器访问 `https://your-domain.com/admin`（或 `http://your-ip:port/admin`）即可登录控制面板。

---

### 非交互静默部署（脚本预设参数）

适用于批量运维或自动化安装脚本：

```bash
export DOMAIN=your-domain.com ADMIN_PASS=yourpassword
curl -fsSL https://raw.githubusercontent.com/2290145679/ProxyProbe-Release/main/deploy-hub.sh | bash
```

---

### 添加被控探针节点（一键秒级接入）

1. 在管理后台「服务器」页面点击添加服务器，复制系统自动生成的**一键安装指令**（已包含独立通信 TOKEN）。
2. 在被控服务器终端直接粘贴执行，脚本将自动完成：
   - 部署 `monitor-agent` 系统监控探针
   - 按需极速安装 `Xray-core` / `Sing-box` / `Realm` 核心
   - 自动签发 ECC 加密证书
   - 启动 `proxy-agent.service` 后台同步进程（5 秒热同步节点变更）

---

## 🖥️ hhub 终端运维控制台

安装完成后，在任意 SSH 终端中直接输入：

```bash
hhub
```

即可进入可视化运维控制台，随时调整配置：

| 序号 | 功能模块 | 说明 |
|:---:|:---|:---|
| `[1]` | **查看系统运行状态** | 实时查看 Caddy / 探针 / 代理中枢运行状态与外部访问链接 |
| `[2]` | **一键重启所有服务** | 平滑热重启全套服务组件 |
| `[3]` | **停止所有服务** | 临时关停业务与监控服务 |
| `[4]` | **启动所有服务** | 批量拉起后台守护进程 |
| `[5]` | **修改 Web 外部端口** | 自动同步 Caddyfile 并同步放行系统防火墙端口 |
| `[6]` | **修改内部通信端口** | 探针主控与代理中枢本地监听端口独立调整 |
| `[7]` | **修改绑定域名 / IP** | **纯 IP 模式与域名 HTTPS 模式自由无损切换**，端口自动适配（80 ↔ 443）并自动申请证书 |
| `[8]` | **重置管理员密码** | 同时更新普通用户中心与主控管理后台两个入口密码 |
| `[9]` | **一键无损热升级系统** | 自动比对远端版本，无缝拉取最新二进制与前端资源，保留所有数据库数据 |
| `[10]` | **查看服务实时日志** | 动态查看代理中枢、探针核心与 Caddy 网关的 real-time journal 日志 |
| `[11]` | **数据库备份与还原** | 一键创建带时间戳的 SQLite 备份或从历史存档点还原 |
| `[12]` | **卸载 ProxyProbe** | 支持选择保留历史数据或完全彻底清理 |

---

## ❓ 常见问题排查 (FAQ)

### Q1: 新建了 Hysteria 2 / TUIC 节点却连接失败？
- **检查核心安装状态**：在后台新建节点时，查看“所属服务器”旁的核心状态指示灯。Sing-box 显示为红色 `🔴` 代表尚未安装该核心。
- **一键补装**：在目标服务器终端重新执行该服务器对应的探针一键安装指令即可自动补齐缺失的核心。
- **防火墙端口放行**：Hysteria 2 与 TUIC 均基于 UDP 协议传输，请确保安全组与云服务商控制台已放行节点配置的 **UDP 端口**。

### Q2: 节点列表中的【测试】按钮是测什么的？
- 该按钮用于进行真实的端到端网络握手：
  - 对 TCP 伪装协议（如 VLESS-Reality、Trojan），发起 TCP 建连与 TLS Client Hello 握手；
  - 对 UDP 协议（如 Hysteria 2），测试 UDP 连通与协议套接字握手；
- 握手成功后会以绿色标签直观呈现实际网络往返延迟（如 `38ms`）。

### Q3: 刚开始用 IP 部署，后面解析好域名如何平滑切换？
- 无需重新安装！在服务器终端输入 `hhub`，选择 `[7] 修改绑定域名/IP`；
- 输入您解析好的新域名，脚本会自动将外部端口从 80 切换为 443、放行 ACME 验证端口并触发 Caddy 自动申请 SSL 证书；
- 切换完成后，管理后台、大屏展示以及所有用户的**聚合订阅复制地址会自动变为最新域名**。

### Q4: 订阅地址更新后，客户端需要做什么？
- 后台的订阅链接完全动态自适应当前访问域名，若在后台点击了【重置 Token】，原订阅链接会失效，只需重新复制一次最新订阅地址导入客户端即可。

---

## 📄 许可证说明

本项目为**商业私有软件**，保留所有权利。未经官方授权许可，不得非法反编译、逆向工程、篡改或转售本软件的源码与可执行程序。
