# 🚀 ProxyProbe - 分布式服务器监控与 Xray / Sing-box / Realm 代理拓扑管理平台

<p align="center">
  <a href="https://github.com/2290145679/ProxyProbe/releases"><img src="https://img.shields.io/badge/Release-v2.5.31-blue.svg?style=flat-square" alt="Release"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-MIT-green.svg?style=flat-square" alt="License"></a>
  <img src="https://img.shields.io/badge/Status-100%25_Open_Source-success.svg?style=flat-square" alt="Open Source">
  <img src="https://img.shields.io/badge/Dual_Core-Xray_%2B_Sing--box_%2B_Realm-brightgreen.svg?style=flat-square" alt="Cores">
  <img src="https://img.shields.io/badge/Routing-Smart_Rules_Center-teal.svg?style=flat-square" alt="Smart Routing Rules">
  <img src="https://img.shields.io/badge/Subscription-Adaptive_UA-orange.svg?style=flat-square" alt="Adaptive Subscription">
  <img src="https://img.shields.io/badge/GeoIP-Auto_Flag_Emoji-purple.svg?style=flat-square" alt="Auto Flag Emoji">
  <img src="https://img.shields.io/badge/Theme-Sakura_%2B_Classic-pink.svg?style=flat-square" alt="Dual Theme">
  <img src="https://img.shields.io/badge/Platform-Linux-red.svg?style=flat-square" alt="Platform">
</p>

**ProxyProbe** 是一套现代化、高颜值、轻量且强大的**开源分布式服务器状态监控、多协议代理节点拓扑调度、聚合订阅智能分发与客户端分流规则管理系统**。

平台在高性能分布式探针的基础上，深度融合了 **Xray-Core、Sing-box 与 Realm 多核心协同调度矩阵**，全面支持主流前沿代理协议拓扑、全平台客户端自适应订阅、Clash 与 Sing-box 客户端分流规则中心、面板免终端一键无损热升级、节点国旗 Emoji 智能解析、实时网络延迟波动热力图、套餐与独享带宽硬件级限速调度、移动端深度适配与双主题自由切换。系统已全面开源，没有任何商业配额门禁，100% 独立离线运行。

---

## 🌟 核心功能特性

### 1. 🔀 客户端分流规则可视化中心 (Client Routing Rules Center)
- 后台内置「国内外智能分流 (默认推荐)」、「极简轻量」、「全局代理」、「自定义专家」四大经典预设。
- 支持对 Clash YAML 规则组与 Sing-box JSON 路由规则进行在线语法高亮、快捷标签注入、格式化校验与完整客户端配置在线预览，新手即开即用，专家随心定制。

### 2. ⚡ 多核心协同调度与前沿协议支持
- **Xray-Core**：承载 VLESS + Reality (Vision / XHTTP)、Trojan、VMess-WS、Shadowsocks 2022 等 TCP/TLS 极致伪装协议。
- **Sing-box**：原生驱动 AnyTLS、Hysteria 2 (Hy2)、TUIC v5 等基于 QUIC / UDP 的极速网络协议。
- **Realm**：高效低延迟端口中转转发调度，轻松组建多级中继拓扑。

### 3. 🚦 智能套餐速率与用户专属带宽管理
- 支持针对不同套餐配置默认带宽限速（例如套餐 A 限速 100 Mbps、套餐 B 300 Mbps 或不限速），支持为特定用户设置专属独享带宽限制。
- 采用 Linux HTB 硬件级流量控制，限速规则全节点自动同步生效，用户端仪表盘清晰直显当前套餐与速率状态。

### 4. 📈 探针实时网络延迟与历史波动可视化
- 探针大屏主视图直观呈现主流网络延迟数据，免去频繁进入二级菜单切换查看。
- 配备近期延迟历史波动热力条，通过智能色彩分级（翠绿极佳、明黄良好、橙色一般、红色较高）清晰展示网络质量起伏。

### 5. 📲 全协议自适应智能订阅 (Adaptive Smart Subscription)
- 单一订阅链接全客户端自适应：依据客户端 `User-Agent` 智能感知类型，自动下发最优配置（Clash/Mihomo -> YAML 规则组；Sing-box -> JSON 核心配置；Shadowrocket/v2rayN -> 标准聚合节点链）。
- 支持手动强制覆盖参数（`?clash=1`、`?singbox=1`、`?b64=1`）。
- 用户面板突出醒目的「⚡ 复制订阅」核心按钮，搭配客户端一键唤醒导入与手机扫码导入。

### 6. 🌍 节点自动识别国家地区国旗 Emoji (Auto GeoIP Flag)
- 根据被控端地理位置或地区关键字（HK/JP/US/SG/TW/DE 等）智能解析并前置对应国旗 Emoji（🇭🇰/🇯🇵/🇺🇸/🇸🇬/🇨🇳/🇩🇪 等）。
- 全订阅协议以及管理后台、用户自服务面板均自动呈现国旗图标，节点归属一目了然。

### 7. 🔑 统一极简登录入口与智能角色路由
- 去除繁琐的入口切换，采用全新统一登录卡片，支持账号/邮箱登录。
- 根据用户角色智能自适应跳转：管理员直接进入管理控制面板，普通客户无缝进入用户服务中心。

### 8. 🔄 面板一键无损在线热升级
- 系统自动静默检测最新版本，发现新版本时界面状态栏智能提醒。
- 管理员可在面板直接查看更新日志，点击「一键无损热升级」即可自动拉取最新组件平滑重启，免登 SSH 终端，零配置丢失。

### 9. 📱 移动端与双主题深度适配
- 全面深度适配手机、平板与桌面屏幕，100% 消除水平滚动条，触控微调丝滑自如。
- 内置经典工业灰与浪漫落樱粉双主题引擎，界面灵动优雅，支持深色/浅色模式随心切换。

### 10. 🎯 AI 与流媒体解锁探测
- 支持对节点流媒体（Netflix、Disney+、YouTube 等）与主流 AI 矩阵（ChatGPT、Claude、Gemini 等）进行自动可用性探测。
- 支持自定义关注服务，告别卡片冗余堆叠，界面聚焦清爽。

### 11. 🚨 智能健康诊断与 Telegram 报警
- 节点列表内置端到端真实握手测速，毫秒级回显实际延迟。
- 支持对接 Telegram Bot，支持定时将数据库热备份文件、服务器到期提醒及异常节点告警自动推送到指定群组或会话。

### 12. 🖥️ 可视化终端运维工具 `hhub`
- 纯 IP 模式与域名 HTTPS 模式一键智能无损切换，自动申请 SSL 证书并配置防火墙。
- 提供一键服务启停、重置管理员账号与密码、修改端口、实时日志滚屏、无损热升级与数据库还原等便捷运维操作。

---

## 🚀 快速一键部署

### 主控端一键安装（全新服务器）

> 推荐操作系统：**Ubuntu 22.04+ / Debian 11+**。支持纯 IP 安装或预先解析域名。

```bash
curl -fsSL https://raw.githubusercontent.com/2290145679/ProxyProbe-Release/main/deploy-hub.sh | bash
```

脚本会交互式引导完成配置：
- 📌 **绑定域名或公网 IP**（输入域名将自动申请 SSL 证书，输入 IP 则启用纯 IP 模式）
- 👤 **管理员账号**（回车默认 `admin`，支持自定义）
- 🔑 **管理员密码**（留空则自动生成高强度安全随机密码）
- 🌐 **外部访问端口**（域名模式默认 443，纯 IP 模式默认 80，支持自定义）

安装完成后，打开浏览器访问 `https://your-domain.com/admin`（或 `http://your-ip:port/admin`）即可登录控制面板。

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
| `[8]` | **重置/修改管理员账号与密码** | 一键同步更新系统唯一管理员账号与安全凭证 |
| `[9]` | **一键无损热升级系统** | 自动比对最新版本，无缝更新且保留所有数据 |
| `[10]` | **查看服务实时日志** | 动态滚屏查看系统运行日志与调试排查 |
| `[11]` | **数据库备份与还原** | 一键创建 SQLite 备份或从历史存档点还原 |
| `[12]` | **卸载 ProxyProbe** | 支持选择保留历史数据或完全彻底清理 |

---

## ❓ 常见问题排查 (FAQ)

### Q1: 如何添加一台被控服务器或探针节点？
- 进入后台「服务器管理」点击「添加服务器」，输入名称后复制终端一键安装命令；
- 在被控服务器上粘贴执行该命令即可完成探针对接；
- 脚本已内建多系统自愈逻辑，无论是标准 Debian/Ubuntu 还是 Alpine 最小容器、NAT 机器或纯 IPv6 机器，均会自动配置 DNS64 与网络依赖完成免干预接入。

### Q2: 新建了 Hysteria 2 / AnyTLS 节点客户端无法连接？
- **检查核心安装状态**：在后台新建节点时，查看所属服务器旁的状态指示灯。Sing-box 显示为绿色即代表核心已就绪。
- **防火墙端口放行**：Hysteria 2 基于 UDP 协议传输，请确保安全组与云服务器控制台已放行节点配置对应的 **UDP 端口**。

### Q3: 刚开始用 IP 部署，后面解析好域名如何平滑切换？
- 无需重新安装！在服务器终端输入 `hhub`，选择 `[7] 修改绑定域名/IP`；
- 输入解析好的新域名，脚本会自动申请 Let's Encrypt SSL 证书并开启 HTTPS；
- 切换完成后，管理后台、大屏展示以及所有用户的**聚合订阅复制地址会自动变为最新域名**。

### Q4: 节点出现偶尔显示“无法联通”但实际正常？
- 跨国机房之间局部 IPv4 骨干网络可能存在偶发抖动或丢包；
- ProxyProbe 内置两级自愈感知巡检机制，当主控向远程节点直接探测超时，会自动回退拉取探针 Agent 真实存活状态进行二次校验，避免面板误报假死。

---

## 📄 开源许可证与社区贡献

本项目采用 [MIT License](LICENSE) 开源协议。

- 欢迎提交 [Issues](https://github.com/2290145679/ProxyProbe/issues) 报告 Bug 或提出新特性建议！
- 欢迎提交 Pull Request 一同完善 ProxyProbe 社区生态！
- 如果觉得本项目对您有所帮助，请给项目点一个 ⭐️ **Star** 鼓励一下作者！
