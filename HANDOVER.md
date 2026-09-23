# ProxyProbe - AI 开发者全量交接文档 (Handover Document)

> **文档生成时间**：2026-09-23  
> **面向对象**：后续接手此项目的 AI 辅助编程系统 / 全栈开发者  
> **仓库地址**：`https://github.com/2290145679/ProxyProbe`  
> **许可证说明**：MIT License（Copyright 2026 2290145679, 部分保留原版 stqfdyr 声明，完全允许商业收费与闭源拓展）

---

## 1. 项目定位与架构全景

**ProxyProbe** 是一套**分布式轻量级服务器探针监控 + Xray / Sing-box / Realm 代理拓扑调度与多协议聚合管理系统**。

它将原本分离的「探针监控面板」与「代理服务面板」深度融合为单一系统：
- **主控端**：运行 Rust 探针主控（端口 28080）+ Python 代理控制守护进程（端口 28090）+ Caddy 网关（443 SSL）+ Vite/React 前端 SPA。
- **被控端**：仅需一条指令，即可同时启动 `monitor-agent`（性能上报）+ `proxy-agent.service`（配置同步）+ 按需部署代理核心（Xray / Sing-box / Realm）。

### 架构调用图

```
                           ┌───────────────────────────────────────────────┐
                           │            Caddy 统一反向代理网关 (:443)        │
                           │                 tz.yohoo.xyz                  │
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
                                          │     SQLite 统一存储共享库     │
                                          │      /opt/monitor/data/       │
                                          │          monitor.db           │
                                          └───────────────────────────────┘
                                                          ▲
                                                          │ 5秒自动长轮询 /api/proxy/agent-sync
                           ┌──────────────────────────────┴────────────────┐
                           │                                               │
                  ┌─────────────────┐                             ┌─────────────────┐
                  │   被控节点 A     │                             │   被控节点 B     │
                  │   monitor-agent │ (上报CPU/内存/网络/磁盘)     │   monitor-agent │
                  │   proxy_agent.py│ (拉取并热载Xray/Singbox配置)│   proxy_agent.py│
                  │   Xray + Singbox│                             │   Realm 端口转发 │
                  └─────────────────┘                             └─────────────────┘
```

---

## 2. 核心技术栈与选型

| 层级 | 技术选型 | 说明 |
|------|---------|------|
| **网关层** | Caddy v2 | 自动申请/续签 Let's Encrypt SSL 证书，处理反向代理路由 |
| **探针主控** | Rust (Axum + Tokio + Rusqlite) | 极高性能，超低内存占用（< 20MB），负责 WebSocket 心跳与告警 |
| **代理控制后端** | Python 3 (单文件守护进程) | `proxy_manager.py`，负责用户权限、节点分发、流量统计、设备限制 |
| **数据持久化** | SQLite 3 | 存储于 `/opt/monitor/data/monitor.db`，Rust 与 Python 共享操作 |
| **前端管理后台** | React 18 + Vite + Tailwind CSS + Lucide Icons | 现代化卡片 UI，支持暗黑模式，具备防呆校验 |
| **代理协议核心** | Xray-core + Sing-box + Realm | Xray 承载 TCP/TLS 协议，Sing-box 承载 Hy2/TUIC，Realm 处理中转 |
| **CI / CD 构建** | GitHub Actions (cross) | 打 tag 自动交叉编译 Linux amd64/arm64 静态二进制并发布 Release |

---

## 3. 代码仓库全量文件目录速查

```
ProxyProbe/
├── .github/
│   └── workflows/
│       └── release.yml             # GitHub Actions: 自动交叉编译 monitor-hub 静态二进制并发布 Release
├── config/
│   ├── Caddyfile                   # 生产环境 Caddy 网关路由规则配置模板
│   ├── agent.env.example           # 探针客户端环境变量示例
│   └── xray-config.json            # Xray 基础模板配置
├── database/
│   ├── schema.sql                  # 核心数据库表结构定义
│   └── dump.sql                    # 数据库初始化种子数据
├── scripts/
│   ├── deploy-hub.sh               # ★ 主控端全新服务器一键部署脚本（仅从本仓库拉取）
│   ├── install.sh                  # ★ 被控节点一键安装增强脚本（联动安装探针+代理核心）
│   ├── install-hub.sh              # 探针主控备用部署脚本
│   └── vless-server.sh             # 单机一键部署备用工具
├── server/                         # ★ Rust 探针主控服务端源码（原 upstream-monitor 重构命名）
│   ├── Cargo.toml                  # Rust 包描述（包名已整合，仓库指向本 repo）
│   ├── Cargo.lock                  # 依赖版本锁定
│   ├── build.rs                    # 构建脚本（下载主题资源并嵌入）
│   ├── web-theme.pin               # 探针默认前端主题版本钉住文件
│   ├── src/
│   │   ├── main.rs                 # 主程序入口、命令行参数、服务启动
│   │   ├── api.rs                  # RESTful API 路由（服务器管理、探针数据读取）
│   │   ├── agent_ws.rs             # WebSocket 处理器，接收各节点的性能遥测
│   │   ├── auth.rs                 # 鉴权系统（Session / Token）
│   │   ├── db.rs                   # SQLite 数据交互与迁移逻辑
│   │   ├── frontend.rs             # 静态网页资源内嵌服务
│   │   └── notify.rs               # 告警通道（Telegram 等）
│   └── web-admin/                  # 前端 React 源码目录
│       ├── package.json            # 前端依赖配置
│       ├── vite.config.ts          # Vite 打包配置（base: /admin/）
│       └── src/
│           ├── App.tsx             # 路由分发器（判断管理员 Admin vs 普通用户 UserDashboard）
│           └── components/
│               ├── Admin.tsx       # 管理员后台主容器（选项卡：服务器、用户、节点、设置）
│               ├── Login.tsx       # 统一登录页（支持管理员与普通代理用户）
│               ├── ProxyUsers.tsx  # 管理员端用户管理（设备限制列、流量限制、到期时间）
│               ├── ProxyNodes.tsx  # 管理员端节点管理（双核心状态检测、防呆校验）
│               ├── UserDashboard.tsx # ★ 普通用户自服务中心（聚合订阅、IP隐藏眼睛切换、在线设备、探针跳转）
│               └── ui/             # Radix / Tailwind 通用 UI 原子组件
├── web-admin/dist/                 # ★ 前端编译产物（已纳入 Git，供 Caddy 直接托管）
├── systemd/
│   ├── monitor-hub.service         # Rust 探针主控 systemd 单元
│   ├── proxy-manager.service       # Python 代理管理器 systemd 单元
│   └── monitor-agent.service       # 探针被控端 systemd 单元
├── proxy_manager.py                # ★ 代理管理控制核心单文件守护进程（约3500行）
├── LICENSE                         # MIT 许可证（包含作者与原作者双版权声明）
└── README.md                       # 项目主文档
```

---

## 4. 关键核心模块与设计细节说明

### 4.1 代理管理核心 (`proxy_manager.py`)
这是整个代理业务的大脑，单文件独立运行于后台，监听 `127.0.0.1:28090`：
1. **数据库初始化与自动迁移 (`init_db`)**：
   - 自动在 SQLite 中建表：`proxy_user`, `proxy_node`, `node_proxy_status`, `session`, `proxy_session_user`, `setting`。
   - 自动检测并执行 `ALTER TABLE proxy_user ADD COLUMN device_limit INTEGER DEFAULT 0`。
2. **多设备连接限制机制 (Device Limit)**：
   - **日志增量监听 (`update_device_tracker`)**：每 3 秒增量扫描 `/var/log/xray/access.log` 和 `/var/log/sing-box/access.log`。
   - **滑动窗口算法**：提取访问日志中的客户端 IP 与用户标识（email: user_X），维护内存字典 `_user_active_ips = { user_id: { ip: last_seen_epoch } }`。
   - **超时剔除**：超过 180 秒（3 分钟）未活动的 IP 自动过期移除。
   - **动态断网与恢复**：`is_user_over_device_limit(user)` 判断活跃 IP 数是否超过 `device_limit`。若超限，`get_active_users()` 会在下一次生成配置时自动将其踢出 Xray/Singbox 入站配置；当设备断开降回阈值内后，3 秒内自动恢复连通性。
   - **订阅熔断提示**：超限时访问订阅接口 `/api/proxy/sub`，自动返回说明性节点提示用户设备已达上限。
3. **流量精准统计**：
   - Xray 通过调用 `xray api statsquery` 读取各用户的 uplink / downlink 流量，累加至 SQLite `proxy_user.used_traffic`。
   - 达到流量上限或过期的用户自动标记为 `expired` / `over_traffic`，不予下发节点入站。
4. **节点防呆与核心感知**：
   - 探针上报节点信息中携带核心运行状态。在添加节点时，若所选服务器未安装该协议对应核心（例如在未安装 Sing-box 的服务器添加 Hy2），系统会拦截创建并给出明确提示。

### 4.2 前端双身份控制体系 (`UserDashboard.tsx` vs `ProxyUsers.tsx`)
1. **身份路由**：
   - 访问 `/admin` 登录后，后端根据会话判断用户等级：
     - `is_admin = 1`：渲染完整控制台（服务器、节点、用户、系统全局配置）。
     - 普通用户：渲染 `UserDashboard.tsx` 自服务视图。
2. **普通用户视图特性 (`UserDashboard.tsx`)**：
   - **聚合订阅导入**：支持 Clash Verge / v2rayN / Shadowrocket / Sing-box / 纯节点链接一键复制或导入。
   - **节点 IP 脱敏安全**：节点列表 IP 默认采用掩码显示（如 `189.***.***25`），并提供“小眼睛”切换按钮，按需查看真实 IP。
   - **设备限制展示**：仪表盘显式显示“在线设备 / 设备上限”（例如 `1 / 2 台`）。超限时展示黄色警告横幅。
   - **探针入口跳转**：导航栏及节点卡片右上角均提供「服务器探针」链接，一键跳转到探针公开状态页（`/`）。

### 4.3 自动化构建与一键部署设计
1. **主控端一键部署 (`scripts/deploy-hub.sh`)**：
   - 采用纯自身生态源：不再拉取第三方仓库的二进制，所有资源直接从 `github.com/2290145679/ProxyProbe` 获取。
   - 探针主控从本仓库的 GitHub Release Assets 下载 `monitor-hub-linux-amd64`。
   - 前端从本仓库通过 `git sparse-checkout` 直接拉取最新 `web-admin/dist`。
   - 自动生成符合规范的 Caddyfile、创建 Systemd 单元、设置管理员密码并放行防火墙。
2. **被控端一键安装 (`scripts/install.sh`)**：
   - 支持参数 `--xray`、`--singbox`、`--realm` 选项。
   - 探针客户端（`monitor-agent`）安装后自动联动调用 `proxy-agent.sh`。

---

## 5. 日常运维、开发与调试操作指南

### 5.1 本地前端开发与构建
```bash
# 进入前端源码目录
cd server/web-admin

# 安装依赖
npm install

# 本地热更新调试
npm run dev

# 编译生产资源
npm run build

# 同步产物到根目录 web-admin/dist（以便部署与 Git 追踪）
# Windows PowerShell:
Remove-Item "..\..\web-admin\dist\*" -Recurse -Force
Copy-Item "dist\*" "..\..\web-admin\dist\" -Recurse -Force
```

### 5.2 主控端常用维护指令（在服务器上）
```bash
# 查看所有组件运行状态
systemctl status caddy monitor-hub proxy-manager

# 重启代理管理器（修改 proxy_manager.py 后执行）
systemctl restart proxy-manager

# 查看代理管理实时日志与设备检测过程
journalctl -u proxy-manager -f

# 查看探针主控日志
journalctl -u monitor-hub -f

# 查看 Caddy 网关反代日志
journalctl -u caddy -f
```

### 5.3 数据库直接调试
```bash
# 打开生产 SQLite 数据库
sqlite3 /opt/monitor/data/monitor.db

# 常用查询语句
SELECT id, username, device_limit, used_traffic, traffic_limit, expire_time FROM proxy_user;
SELECT id, name, protocol, server_host, server_port FROM proxy_node;
```

---

## 6. GitHub Release 编译说明

当需要发布新版本或更新 Rust 探针核心时：
1. 提交修改并推送到 `main` 分支。
2. 打上形如 `vX.Y.Z` 的 Git Tag 并推送到 GitHub：
   ```bash
   git tag v1.0.1
   git push origin v1.0.1
   ```
3. GitHub Actions (`.github/workflows/release.yml`) 会自动启动：
   - 下载前端依赖并执行 `npm run build`。
   - 下载并打包 `scripts/theme.sh` 探针默认主题。
   - 使用 `cross` 分别交叉编译出 `x86_64` 和 `aarch64` 的 musl 静态可执行文件。
   - 自动创建 GitHub Release 并附加 `monitor-hub-linux-amd64` 与 `monitor-hub-linux-arm64`。

---

## 7. 给下一任 AI 的建议与待拓展方向 (Backlog)

1. **分布式被控节点多设备限制支持**：
   - 当前的设备限制逻辑（`update_device_tracker`）是主控端读取本地 `/var/log/xray/access.log`。若被控节点是独立的远程 VPS，可考虑在 `proxy_agent.py` 中将远端日志扫描结果在 `sync_step` 握手时同步回传给主控端。
2. **多语言与主题定制**：
   - 前端已支持暗色/亮色切换，后续可考虑增加中英文 i18n 多语言支持。
3. **更丰富的协议生成**：
   - 目前已支持 VLESS-Reality、Trojan、Hysteria 2、TUIC、SOCKS5 等。后续若有更前沿的协议（如 TUIC v5 细节调优、VLESS over gRPC），可直接在 `proxy_manager.py` 的 `format_node_link` 与配置渲染器中补充。
