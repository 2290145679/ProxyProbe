-- Monitor + Proxy Manager 数据库结构定义

-- 1. 原 Monitor 探针配置表
CREATE TABLE IF NOT EXISTS setting (
  key   TEXT PRIMARY KEY,
  value TEXT NOT NULL
);

-- 2. 原 Monitor 服务器节点表
CREATE TABLE IF NOT EXISTS node (
  id            INTEGER PRIMARY KEY,
  name          TEXT    NOT NULL,
  token         TEXT    NOT NULL UNIQUE,
  sort          INTEGER NOT NULL DEFAULT 0,
  public        INTEGER NOT NULL DEFAULT 1,
  price         REAL    NOT NULL DEFAULT 0,
  currency      TEXT    NOT NULL DEFAULT 'USD',
  billing_cycle TEXT    NOT NULL DEFAULT 'monthly',
  expires_at    TEXT,
  remark        TEXT    NOT NULL DEFAULT '',
  traffic_limit INTEGER NOT NULL DEFAULT 0,
  traffic_mode  TEXT    NOT NULL DEFAULT 'sum',
  traffic_reset_day INTEGER NOT NULL DEFAULT 1,
  hostname TEXT NOT NULL DEFAULT '', os TEXT NOT NULL DEFAULT '',
  kernel   TEXT NOT NULL DEFAULT '', arch TEXT NOT NULL DEFAULT '',
  virt     TEXT NOT NULL DEFAULT '', cpu_name TEXT NOT NULL DEFAULT '',
  cpu_cores INTEGER NOT NULL DEFAULT 0, mem_total INTEGER NOT NULL DEFAULT 0,
  swap_total INTEGER NOT NULL DEFAULT 0, disk_total INTEGER NOT NULL DEFAULT 0,
  agent_version TEXT NOT NULL DEFAULT '', ip TEXT NOT NULL DEFAULT '',
  ipv4 TEXT NOT NULL DEFAULT '', ipv6 TEXT NOT NULL DEFAULT '',
  country TEXT NOT NULL DEFAULT '',
  country_ip TEXT NOT NULL DEFAULT '',
  country_pin TEXT NOT NULL DEFAULT '',
  ipv4_pin TEXT NOT NULL DEFAULT '', ipv6_pin TEXT NOT NULL DEFAULT '',
  last_seen INTEGER NOT NULL DEFAULT 0,
  notify INTEGER NOT NULL DEFAULT 0,
  down_since INTEGER NOT NULL DEFAULT 0,
  created_at INTEGER NOT NULL
);

-- 3. 原 Monitor 流量记录表
CREATE TABLE IF NOT EXISTS traffic (
  node_id  INTEGER PRIMARY KEY REFERENCES node(id) ON DELETE CASCADE,
  boot_id  TEXT    NOT NULL DEFAULT '',
  last_rx  INTEGER NOT NULL DEFAULT 0,
  last_tx  INTEGER NOT NULL DEFAULT 0,
  total_rx INTEGER NOT NULL DEFAULT 0,
  total_tx INTEGER NOT NULL DEFAULT 0,
  month_rx INTEGER NOT NULL DEFAULT 0,
  month_tx INTEGER NOT NULL DEFAULT 0,
  month_start TEXT NOT NULL DEFAULT '',
  day_rx INTEGER NOT NULL DEFAULT 0,
  day_tx INTEGER NOT NULL DEFAULT 0,
  day_start TEXT NOT NULL DEFAULT ''
);

-- 4. 原 Monitor 性能指标表
CREATE TABLE IF NOT EXISTS metric (
  node_id INTEGER NOT NULL REFERENCES node(id) ON DELETE CASCADE,
  ts      INTEGER NOT NULL,
  cpu REAL NOT NULL,
  mem_used INTEGER NOT NULL, swap_used INTEGER NOT NULL, disk_used INTEGER NOT NULL,
  net_rx INTEGER NOT NULL, net_tx INTEGER NOT NULL,
  tcp INTEGER NOT NULL, udp INTEGER NOT NULL, procs INTEGER NOT NULL,
  PRIMARY KEY (node_id, ts)
) WITHOUT ROWID;

-- 5. 原 Monitor 管理员会话表
CREATE TABLE IF NOT EXISTS session (
  token_hash TEXT PRIMARY KEY,
  expires_at INTEGER NOT NULL
);

-- 6. 【新增】代理协议节点表
CREATE TABLE IF NOT EXISTS proxy_node (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  server_id INTEGER DEFAULT 0,             -- 所属探针服务器 ID (0 为本机)
  server_name TEXT DEFAULT '本机',          -- 服务器显示名称
  server_host TEXT DEFAULT '',              -- 服务器连接公网 IP / 域名
  name TEXT NOT NULL,                      -- 节点名称（如：新加坡-VLESS-01）
  protocol TEXT NOT NULL,                  -- 协议类型 (vless_reality / vless_ws / trojan)
  port INTEGER NOT NULL,                   -- 节点监听端口
  uuid TEXT NOT NULL,                      -- 用户认证 UUID
  flow TEXT DEFAULT 'xtls-rprx-vision',    -- 流控模式
  sni TEXT DEFAULT 'www.apple.com',        -- Reality 伪装域名
  dest TEXT DEFAULT 'www.apple.com:443',   -- Reality 回落目标
  public_key TEXT,                         -- Reality x25519 公钥
  private_key TEXT,                        -- Reality x25519 私钥
  short_id TEXT,                           -- Reality short_id
  ws_path TEXT DEFAULT '/ws-proxy',        -- WebSocket 路径 (若为 vless_ws)
  enabled INTEGER DEFAULT 1,               -- 是否启用 (1=启用, 0=禁用)
  created_at INTEGER NOT NULL              -- 创建时间戳
);

-- 7. 【新增】被控端代理服务运行状态与自检上报表
CREATE TABLE IF NOT EXISTS node_proxy_status (
  node_id INTEGER PRIMARY KEY,             -- 关联 node 表的 id
  status TEXT,                             -- 运行状态 (running / stopped / port_error)
  version TEXT,                            -- Xray 核心版本
  ports TEXT,                              -- 目标下发端口列表 (JSON 字符串)
  listening_ports TEXT,                    -- 实际成功监听端口列表 (JSON 字符串)
  log TEXT,                                -- 被控端诊断信息 (包括网络、防火墙、进程等快照)
  last_seen INTEGER                        -- 最后同步心跳时间戳
);

-- 8. 【新增】VIP 套餐等级表
CREATE TABLE IF NOT EXISTS proxy_tier (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  tier_key TEXT UNIQUE NOT NULL,           -- 套餐标识，如 vip1, vip2
  tier_id TEXT DEFAULT '',                 -- 别名兼容
  name TEXT NOT NULL,                      -- 套餐显示名称
  description TEXT DEFAULT '',             -- 套餐详细说明
  speed_limit_mbps INTEGER DEFAULT 0,      -- 限速限制 (0为不限)
  device_limit INTEGER DEFAULT 0,          -- 在线设备限制
  sort_order INTEGER DEFAULT 0,            -- 排序权重
  created_at INTEGER NOT NULL              -- 创建时间戳
);

-- 9. 【新增】系统公告表
CREATE TABLE IF NOT EXISTS proxy_announcement (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  title TEXT NOT NULL,                     -- 公告标题
  summary TEXT DEFAULT '',                 -- 公告概要
  content TEXT NOT NULL,                   -- 公告正文内容
  is_pinned INTEGER DEFAULT 0,             -- 是否置顶 (1=置顶, 0=正常)
  enabled INTEGER DEFAULT 1,               -- 是否生效显示
  created_at INTEGER NOT NULL,             -- 创建时间
  updated_at INTEGER NOT NULL              -- 更新时间
);

-- 10. 【新增】客户端软件下载专区表
CREATE TABLE IF NOT EXISTS proxy_app_download (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  name TEXT NOT NULL,                      -- 软件名称 (如 Clash Verge Rev)
  platform TEXT DEFAULT 'all',             -- 适用平台 (windows / android / ios / mac / all)
  version TEXT DEFAULT '',                 -- 软件版本号
  description TEXT DEFAULT '',             -- 软件说明及安装指引
  file_path TEXT DEFAULT '',               -- 本地二进制安装包存储物理路径
  file_name TEXT DEFAULT '',               -- 上传的原文件名
  file_size INTEGER DEFAULT 0,             -- 文件字节大小
  external_url TEXT DEFAULT '',            -- 官方外部备用镜像下载链接
  sort_order INTEGER DEFAULT 0,            -- 展示排序
  enabled INTEGER DEFAULT 1,               -- 是否启用展示
  created_at INTEGER NOT NULL              -- 创建时间
);
