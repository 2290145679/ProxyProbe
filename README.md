# 🚀 ProxyProbe - 分布式服务器监控与 Xray / Sing-box / Realm 代理拓扑管理系统

<p align="center">
  <img src="https://img.shields.io/badge/Release-v2.5.25-blue.svg" alt="Release">
  <img src="https://img.shields.io/badge/Routing-Smart_Rules_Center-brightgreen.svg" alt="Smart Routing Rules">
  <img src="https://img.shields.io/badge/Update-One--Click_Upgrade-orange.svg" alt="One-Click Upgrade">
  <img src="https://img.shields.io/badge/Dual_Core-Xray_%2B_Sing--box_%2B_Realm-success.svg" alt="Cores">
  <img src="https://img.shields.io/badge/Subscription-Smart_UA_Adaptive-blue.svg" alt="Smart UA Subscription">
  <img src="https://img.shields.io/badge/GeoIP-Auto_Flag_Emoji-purple.svg" alt="Auto Flag Emoji">
  <img src="https://img.shields.io/badge/Theme-Sakura_%2B_Classic-pink.svg" alt="Sakura Theme">
  <img src="https://img.shields.io/badge/Platform-Linux-red.svg" alt="Platform">
</p>

**ProxyProbe** 是一套现代化、高颜值、轻量且强大的**分布式服务器状态监控、代理节点拓扑调度、聚合订阅分发与客户端智能分流规则管理平台**。系统在高性能分布式探针的基础上，深度融合了 **Xray-Core、Sing-box 与 Realm 多核心协同调度矩阵**，支持主流前沿代理协议拓扑、全平台客户端自适应订阅、Clash 与 Sing-box 客户端分流规则中心、面板免终端一键无损热升级、节点国旗 Emoji 智能解析、AI 与流媒体自选检测、移动端深度适配与双主题自由切换。

---

## 🎁 公测福利：免费领取商业卡密与每日签到续期

为感谢社区用户的支持，ProxyProbe 目前正处于**全功能公开测试阶段**，所有用户均可**免费领取商业版授权**：

* 🚀 **免费领取 60 天行星商业套餐**：
  部署好 ProxyProbe 面板后，加入官方内测交流群，私聊官方 Telegram 机器人直接发送面板中的 **17 位机器识别码**（例如：`PP-8A3F-9B12-4C67`），系统全自动秒发 60 天行星商业授权并自动激活绑定！
* 🎁 **每日签到抽奖续期**：
  拥有授权后，每天私聊机器人发送 `/checkin` 或点击「🎁 每日签到」，天天免费随机抽取 **1 ~ 3 天** 额外有效期，无上限持续续期！
* 💬 **官方内测交流群**：[点击加入 Telegram 群聊](https://t.me/+e6WnZExf5KE4NDE9)
* 🤖 **官方发卡与签到机器人**：[@hhubproxyprobe_bot](https://t.me/hhubproxyprobe_bot)
* 📖 **官方 Wiki 使用手册**：[https://wiki.yohoo.xyz](https://wiki.yohoo.xyz)
* 🔍 **在线 Demo 演示站**：[https://demo.yohoo.xyz](https://demo.yohoo.xyz)

---

## 🌟 核心功能特性

### 1. 🔀 客户端分流规则可视化中心 (Client Routing Rules Center)
- 后台内置「国内外智能分流 (默认推荐)」、「极简轻量」、「全局代理」、「自定义专家」四大经典预设。
- 支持对 Clash YAML 规则组与 Sing-box JSON 路由规则进行在线语法高亮、快捷标签注入、格式化校验与完整客户端配置在线预览，即开即用。

### 2. ⚡ 多核心协同调度与前沿协议支持
- **Xray-Core**：承载 VLESS + Reality (Vision / XHTTP)、Trojan、VMess-WS、Shadowsocks 2022 等 TCP/TLS 伪装协议。
- **Sing-box**：原生驱动 AnyTLS、Hysteria 2 (Hy2)、TUIC v5 等基于 QUIC / UDP 的极速网络协议。
- **Realm**：高效低延迟端口中转转发调度，轻松组建多级中继拓扑。

### 3. 📲 全协议自适应智能订阅 (Adaptive Smart Subscription)
- 单一订阅链接全客户端自适应：依据客户端 `User-Agent` 智能感知类型，自动下发最优配置（Clash/Mihomo -> YAML 规则组；Sing-box -> JSON 核心配置；Shadowrocket/v2rayN -> 标准聚合节点链）。
- 支持手动强制覆盖参数（`?clash=1`、`?singbox=1`、`?b64=1`）。
- 用户面板突出醒目的「⚡ 复制订阅」核心按钮，搭配客户端一键唤醒导入与手机扫码导入。

### 4. 🔄 面板一键无损在线热升级
- 系统自动静默检测最新版本，发现新版本时界面状态栏智能提醒。
- 管理员可在面板直接查看更新日志，点击「一键无损热升级」即可自动拉取最新组件平滑重启，免登 SSH 终端，零配置丢失。

### 5. 🌍 节点自动识别国家地区国旗 Emoji
- 根据被控端地理位置或地区关键字（HK/JP/US/SG/TW/DE 等）智能解析并前置对应国旗 Emoji（🇭🇰/🇯🇵/🇺🇸/🇸🇬/🇨🇳/🇩🇪 等）。
- 全订阅协议以及管理后台、用户自服务面板均自动呈现国旗图标，节点归属一目了然。

### 6. 📱 移动端与多主题深度适配
- 全面适配手机、平板与桌面超宽屏幕，消除水平滚动条，触控微调丝滑自如。
- 内置经典工业灰与浪漫落樱粉双主题引擎，界面灵动优雅，支持深色/浅色模式随心切换。

### 7. 🎯 AI 与流媒体解锁探测
- 支持对节点流媒体（Netflix、Disney+、YouTube 等）与主流 AI 矩阵（ChatGPT、Claude、Gemini 等）进行自动可用性探测。
- 支持自定义关注服务，告别卡片冗余堆叠，界面聚焦清爽。

### 8. 🚨 智能健康诊断与 Telegram 报警
- 节点列表内置握手测速，一键发起全链路 TLS / UDP 握手测试，毫秒级回显实际延迟。
- 支持对接 Telegram Bot，支持定时将数据库热备份文件、服务器到期提醒及异常节点告警自动推送到指定群组或会话。

### 9. 🖥️ 可视化终端运维工具 `hhub`
- 纯 IP 模式与域名 HTTPS 模式一键智能无损切换，自动申请 SSL 证书并配置防火墙。
- 提供一键服务启停、重置密码、修改端口、实时日志滚屏、无损热升级与数据库还原等便捷运维操作。

---

## 🚀 快速一键部署

### 主控端一键安装（全新服务器）

> 推荐操作系统：**Ubuntu 22.04+ / Debian 11+**。支持纯 IP 安装或预先解析域名。

```bash
curl -fsSL https://raw.githubusercontent.com/2290145679/ProxyProbe-Release/main/deploy-hub.sh | bash
```

脚本会交互式引导完成配置：
- 📌 **绑定域名或公网 IP**（输入域名将自动申请 SSL 证书，输入 IP 则启用纯 IP 模式）
- 🔑 **管理员密码**（留空则自动生成高强度安全随机密码）
- 🌐 **外部访问端口**（域名模式默认 443，纯 IP 模式默认 80，支持自定义）

安装完成后，打开浏览器访问 `https://your-domain.com/admin`（或 `http://your-ip:port/admin`）即可登录控制面板。

---

### 非交互静默部署（适用于自动化部署）

```bash
export DOMAIN=your-domain.com ADMIN_PASS=yourpassword
curl -fsSL https://raw.githubusercontent.com/2290145679/ProxyProbe-Release/main/deploy-hub.sh | bash
```

---

### 添加被控探针节点（秒级接入）

1. 在管理后台「服务器」页面点击添加服务器，复制系统自动生成的**一键安装指令**。
2. 在被控服务器终端直接粘贴执行，脚本将自动部署探针、按需补齐核心并开始 5 秒级实时数据同步。

---

## 🖥️ hhub 终端运维控制台

安装完成后，在服务器 SSH 终端中直接输入：

```bash
hhub
```

即可进入可视化运维控制台，随时调整配置：

| 选项 | 功能模块 | 说明 |
|:---:|:---|:---|
| `[1]` | **查看系统运行状态** | 实时查看网关、探针与中枢运行状态与外部访问链接 |
| `[2]` | **一键重启所有服务** | 平滑热重启全套服务组件 |
| `[3]` | **停止所有服务** | 临时关停业务与监控服务 |
| `[4]` | **启动所有服务** | 批量拉起后台守护进程 |
| `[5]` | **修改 Web 外部端口** | 自动同步网关并放行系统防火墙端口 |
| `[6]` | **修改内部通信端口** | 探针主控与中枢本地监听端口独立调整 |
| `[7]` | **修改绑定域名 / IP** | **纯 IP 模式与域名 HTTPS 模式自由无损切换**，自动申请与续期证书 |
| `[8]` | **重置管理员密码** | 同时更新普通用户中心与主控管理后台密码 |
| `[9]` | **一键无损热升级系统** | 自动比对最新版本，无缝更新且保留所有数据 |
| `[10]` | **查看服务实时日志** | 动态滚屏查看系统运行日志与调试排查 |
| `[11]` | **数据库备份与还原** | 一键创建 SQLite 备份或从历史存档点还原 |
| `[12]` | **卸载 ProxyProbe** | 支持选择保留历史数据或完全彻底清理 |

---

## ❓ 常见问题排查 (FAQ)

### Q1: 如何免费领取商业版授权？
- 部署好面板后，进入管理后台「商业授权」页面查看您的 **17 位机器识别码**（如 `PP-8A3F-9B12-4C67`）。
- 加入 [官方内测交流群](https://t.me/+e6WnZExf5KE4NDE9)，私聊官方机器人 [@hhubproxyprobe_bot](https://t.me/hhubproxyprobe_bot)，把机器识别码发送给机器人即可秒发 60 天行星商业授权！
- 每天还可在机器人私聊中发送 `/checkin` 免费抽取 1~3 天额外时长，无上限持续续期！

### Q2: 新建了 Hysteria 2 节点却无法连接？
- **检查核心安装状态**：在后台新建节点时，查看所属服务器旁的状态指示灯。Sing-box 显示为绿色即代表已就绪。
- **防火墙端口放行**：Hysteria 2 基于 UDP 协议传输，请确保安全组与云服务器控制台已放行节点配置的 **UDP 端口**。

### Q3: 刚开始用 IP 部署，后面解析好域名如何平滑切换？
- 无需重新安装！在服务器终端输入 `hhub`，选择 `[7] 修改绑定域名/IP`；
- 输入解析好的新域名，脚本会自动申请 SSL 证书并开启 HTTPS；
- 切换完成后，管理后台、大屏展示以及所有用户的**聚合订阅复制地址会自动变为最新域名**。

---

## 📄 许可证与支持

本项目保留所有权利。更多使用教程与高级技巧，请参阅 [官方 Wiki 知识库](https://wiki.yohoo.xyz)。
