import { useCallback, useEffect, useState } from "react"
import {
  Activity,
  ArrowUpDown,
  BarChart3,
  RefreshCw,
  Server,
  Users,
} from "lucide-react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"

export type DashboardSummary = {
  total_servers: number
  online_servers: number
  total_nodes: number
  total_users: number
  active_users: number
  online_users?: number
  total_upload_bytes: number
  total_download_bytes: number
  total_traffic_bytes: number
}

export type ServerRankingItem = {
  id: number
  name: string
  ip: string
  upload_bytes: number
  download_bytes: number
  total_bytes: number
  percentage: number
  node_count: number
  is_online: boolean
}

export type UserRankingItem = {
  id: number
  username: string
  upload_bytes: number
  download_bytes: number
  total_bytes: number
  traffic_limit_bytes: number
  percentage: number
  expires_at: number
  enabled: number
}

export type HourlyTrafficItem = {
  timestamp: number
  time: string
  upload: number
  download: number
  total: number
}

function formatBytes(bytes: number): string {
  if (!bytes || bytes <= 0) return "0 B"
  const k = 1024
  const sizes = ["B", "KB", "MB", "GB", "TB"]
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / Math.pow(k, i)).toFixed(i >= 3 ? 2 : 1)} ${sizes[i]}`
}

export function ProxyDashboard({ onNavigate }: { onNavigate?: (tab: string) => void }) {
  const [loading, setLoading] = useState(true)
  const [lastRefreshed, setLastRefreshed] = useState<Date>(new Date())

  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [serverRanking, setServerRanking] = useState<ServerRankingItem[]>([])
  const [userRanking, setUserRanking] = useState<UserRankingItem[]>([])
  const [hourlyTraffic, setHourlyTraffic] = useState<HourlyTrafficItem[]>([])

  const loadDashboard = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true)
    try {
      const res = await fetch("/api/proxy/dashboard/overview")
      const data = await res.json()
      if (data.ok) {
        setSummary(data.summary)
        
        // 优先使用服务端聚合的 server_ranking，若无则容灾降级从 node_ranking 自适应聚合并统计
        if (data.server_ranking && data.server_ranking.length > 0) {
          setServerRanking(data.server_ranking)
        } else if (data.node_ranking) {
          const map: Record<string, ServerRankingItem> = {}
          let total = 0
          for (const n of data.node_ranking) {
            const sName = n.server_name || "本机"
            if (!map[sName]) {
              map[sName] = {
                id: n.id,
                name: sName,
                ip: n.server_host || "",
                upload_bytes: 0,
                download_bytes: 0,
                total_bytes: 0,
                percentage: 0,
                node_count: 0,
                is_online: true,
              }
            }
            map[sName].upload_bytes += n.upload_bytes || 0
            map[sName].download_bytes += n.download_bytes || 0
            map[sName].total_bytes += n.total_bytes || 0
            map[sName].node_count += 1
            total += n.total_bytes || 0
          }
          const list = Object.values(map).sort((a, b) => b.total_bytes - a.total_bytes)
          for (const item of list) {
            item.percentage = total > 0 ? Math.round((item.total_bytes / total) * 1000) / 10 : 0
          }
          setServerRanking(list)
        } else {
          setServerRanking([])
        }

        setUserRanking(data.user_ranking || [])
        setHourlyTraffic(data.hourly_traffic || [])
        setLastRefreshed(new Date())
      }
    } catch {
      if (!quiet) toast.error("大盘数据加载失败，请检查网络")
    } finally {
      if (!quiet) setLoading(false)
    }
  }, [])

  useEffect(() => {
    loadDashboard()
    const timer = setInterval(() => {
      loadDashboard(true)
    }, 30000)
    return () => clearInterval(timer)
  }, [loadDashboard])

  // 计算 24 小时流量走势图坐标
  const chartMax = Math.max(...hourlyTraffic.map((h) => h.total), 1024 * 1024 * 10) // 至少 10MB 基准
  const svgWidth = 560
  const svgHeight = 140
  const paddingX = 20
  const paddingY = 20
  const innerWidth = svgWidth - paddingX * 2
  const innerHeight = svgHeight - paddingY * 2

  const points = hourlyTraffic.map((item, index) => {
    const x = paddingX + (index / Math.max(hourlyTraffic.length - 1, 1)) * innerWidth
    const y = paddingY + innerHeight - (item.total / chartMax) * innerHeight
    return { x, y, item }
  })

  const linePath = points.length > 0
    ? points.map((p, idx) => `${idx === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ")
    : ""

  const areaPath = points.length > 0
    ? `${linePath} L ${points[points.length - 1].x.toFixed(1)} ${svgHeight - paddingY} L ${points[0].x.toFixed(1)} ${svgHeight - paddingY} Z`
    : ""

  return (
    <div className="space-y-6">
      {/* 顶部标题与快速操作栏 */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-2 border-b border-border/50">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-xl sm:text-2xl font-bold tracking-tight">监控大盘与全景感知</h1>
            <Badge variant="outline" className="border-primary/30 bg-primary/10 text-primary text-xs font-medium">
              实时
            </Badge>
          </div>
          <p className="text-xs sm:text-sm text-muted-foreground mt-0.5">
            全网流量实时吞吐走势、服务器消耗排行与用户感知矩阵
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <Button
            size="sm"
            variant="ghost"
            onClick={() => loadDashboard()}
            disabled={loading}
            className="h-8 text-xs gap-1.5 text-muted-foreground hover:text-foreground"
            title={`刷新于 ${lastRefreshed.toLocaleTimeString()}`}
          >
            <RefreshCw className={`size-3.5 ${loading ? "animate-spin" : ""}`} />
            <span className="hidden sm:inline">刷新</span>
          </Button>
        </div>
      </div>

      {/* 第一行：三大核心指标卡片 */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 sm:gap-4">
        {/* 指标 1：纳管服务器与节点 */}
        <Card className="p-4 sm:p-5 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">纳管服务器与节点</span>
            <Server className="size-4 text-emerald-500" />
          </div>
          <div className="my-2">
            <div className="text-2xl sm:text-3xl font-bold tracking-tight flex items-baseline gap-2 flex-wrap">
              <span>{summary ? `${summary.online_servers} / ${summary.total_servers}` : "0 / 0"}</span>
              <span className="text-xs font-semibold px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30">
                在线服务器
              </span>
            </div>
            <div className="text-xs text-muted-foreground mt-1 truncate">
              {summary ? `共接入 ${summary.total_nodes} 个代理节点` : "加载中..."}
            </div>
          </div>
          <div className="w-full bg-muted rounded-full h-1.5 overflow-hidden">
            <div
              className="h-full bg-emerald-500 transition-all duration-500"
              style={{
                width: `${
                  summary && summary.total_servers > 0
                    ? Math.round((summary.online_servers / summary.total_servers) * 100)
                    : 100
                }%`,
              }}
            />
          </div>
        </Card>

        {/* 指标 2：全网总流量 */}
        <Card className="p-4 sm:p-5 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">全网消耗总流量</span>
            <ArrowUpDown className="size-4 text-blue-500" />
          </div>
          <div className="my-2">
            <div className="text-2xl sm:text-3xl font-bold tracking-tight truncate">
              {summary ? formatBytes(summary.total_traffic_bytes) : "0 B"}
            </div>
            <div className="text-xs text-muted-foreground mt-1 truncate">
              ↑ 上行: {summary ? formatBytes(summary.total_upload_bytes) : "0 B"} · ↓ 下行: {summary ? formatBytes(summary.total_download_bytes) : "0 B"}
            </div>
          </div>
          <div className="w-full bg-muted rounded-full h-1.5 overflow-hidden">
            <div className="h-full bg-blue-500 transition-all duration-500" style={{ width: "100%" }} />
          </div>
        </Card>

        {/* 指标 3：活跃与在线用户数 */}
        <Card className="p-4 sm:p-5 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">用户与连接状态</span>
            <Users className="size-4 text-purple-500" />
          </div>
          <div className="my-2">
            <div className="text-2xl sm:text-3xl font-bold tracking-tight flex items-baseline gap-2 flex-wrap">
              <span>{summary?.online_users ?? 0}</span>
              <span className="text-xs font-semibold px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/30">
                实时在线
              </span>
              <span className="text-xs font-normal text-muted-foreground ml-auto">
                有效 {summary ? summary.active_users : 0} / 总计 {summary ? summary.total_users : 0} 户
              </span>
            </div>
            <div className="text-xs text-muted-foreground mt-1 truncate">
              {summary ? `${summary.online_users ?? 0} 户正在连通 · ${summary.active_users} 户订阅正常` : "加载中..."}
            </div>
          </div>
          <div className="w-full bg-muted rounded-full h-1.5 overflow-hidden">
            <div
              className="h-full bg-purple-500 transition-all duration-500"
              style={{
                width: `${
                  summary && summary.total_users > 0
                    ? Math.round((summary.active_users / summary.total_users) * 100)
                    : 100
                }%`,
              }}
            />
          </div>
        </Card>
      </div>

      {/* 第二行：左右分栏（服务器消耗排行 + 24小时流量走势） */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* 左侧：服务器消耗排行榜 */}
        <Card className="p-4 sm:p-5 flex flex-col">
          <div className="flex items-center justify-between pb-3 border-b border-border/40">
            <div className="flex items-center gap-2">
              <BarChart3 className="size-4 text-primary" />
              <h2 className="text-sm font-semibold">服务器消耗排行</h2>
            </div>
            <span className="text-[11px] text-muted-foreground">
              共 {serverRanking.length} 台服务器
            </span>
          </div>

          <div className="mt-3 space-y-3 flex-1 overflow-y-auto max-h-[300px] pr-1">
            {serverRanking.length === 0 ? (
              <div className="py-12 text-center text-xs text-muted-foreground">
                暂无服务器消耗数据
              </div>
            ) : (
              serverRanking.map((srv, idx) => (
                <div key={srv.id || idx} className="space-y-1.5">
                  <div className="flex items-center justify-between text-xs gap-2">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span className={`size-4 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0 ${
                        idx === 0 ? "bg-amber-500 text-white" : idx === 1 ? "bg-slate-400 text-white" : idx === 2 ? "bg-amber-700 text-white" : "bg-muted text-muted-foreground"
                      }`}>
                        {idx + 1}
                      </span>
                      <span className="font-semibold truncate max-w-[120px] sm:max-w-[160px]" title={srv.name}>
                        {srv.name}
                      </span>
                      {srv.ip && (
                        <span className="font-mono text-[10px] text-muted-foreground truncate max-w-[110px] hidden sm:inline" title={srv.ip}>
                          {srv.ip}
                        </span>
                      )}
                      <Badge variant="outline" className={`text-[10px] px-1.5 py-0 font-normal shrink-0 ${
                        srv.is_online
                          ? "border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400"
                          : "border-muted text-muted-foreground"
                      }`}>
                        {srv.is_online ? "在线" : "离线"}
                      </Badge>
                      {srv.node_count > 0 && (
                        <span className="text-[10px] text-muted-foreground shrink-0 hidden md:inline">
                          ({srv.node_count} 节点)
                        </span>
                      )}
                    </div>
                    <div className="flex items-center gap-2 shrink-0 font-mono text-[11px]">
                      <span className="font-semibold text-foreground">{formatBytes(srv.total_bytes)}</span>
                      <span className="text-muted-foreground w-10 text-right">{srv.percentage}%</span>
                    </div>
                  </div>
                  <div className="w-full bg-muted/60 rounded-full h-1.5 overflow-hidden">
                    <div
                      className={`h-full transition-all duration-500 ${
                        idx === 0 ? "bg-primary" : "bg-primary/70"
                      }`}
                      style={{ width: `${Math.max(srv.percentage, 2)}%` }}
                    />
                  </div>
                </div>
              ))
            )}
          </div>
        </Card>

        {/* 右侧：24 小时流量走势图 (轻量原生响应式 SVG) */}
        <Card className="p-4 sm:p-5 flex flex-col justify-between">
          <div className="flex items-center justify-between pb-3 border-b border-border/40">
            <div className="flex items-center gap-2">
              <Activity className="size-4 text-emerald-500" />
              <h2 className="text-sm font-semibold">24 小时全网吞吐走势</h2>
            </div>
            <span className="text-[11px] text-muted-foreground">
              峰值: {formatBytes(chartMax)}
            </span>
          </div>

          <div className="my-auto py-2 w-full">
            <svg
              viewBox={`0 0 ${svgWidth} ${svgHeight}`}
              className="w-full h-36 sm:h-40 overflow-visible"
            >
              <defs>
                <linearGradient id="trafficGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="var(--color-primary, #3b82f6)" stopOpacity="0.3" />
                  <stop offset="100%" stopColor="var(--color-primary, #3b82f6)" stopOpacity="0.0" />
                </linearGradient>
              </defs>

              {/* 背景参考线 */}
              <line
                x1={paddingX}
                y1={paddingY}
                x2={svgWidth - paddingX}
                y2={paddingY}
                stroke="currentColor"
                strokeOpacity="0.1"
                strokeDasharray="3 3"
              />
              <line
                x1={paddingX}
                y1={paddingY + innerHeight / 2}
                x2={svgWidth - paddingX}
                y2={paddingY + innerHeight / 2}
                stroke="currentColor"
                strokeOpacity="0.1"
                strokeDasharray="3 3"
              />
              <line
                x1={paddingX}
                y1={svgHeight - paddingY}
                x2={svgWidth - paddingX}
                y2={svgHeight - paddingY}
                stroke="currentColor"
                strokeOpacity="0.2"
              />

              {/* 面积渐变与折线 */}
              {areaPath && <path d={areaPath} fill="url(#trafficGradient)" />}
              {linePath && (
                <path
                  d={linePath}
                  fill="none"
                  stroke="var(--color-primary, #3b82f6)"
                  strokeWidth="2"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              )}

              {/* 关键数据打点 */}
              {points.map((p, i) => {
                if (i % 4 === 0 || i === points.length - 1) {
                  return (
                    <circle
                      key={i}
                      cx={p.x}
                      cy={p.y}
                      r="3"
                      className="fill-background stroke-primary"
                      strokeWidth="2"
                    />
                  )
                }
                return null
              })}
            </svg>

            {/* X 轴时间刻度 */}
            <div className="flex justify-between px-2 text-[10px] text-muted-foreground mt-1">
              <span>{hourlyTraffic[0]?.time || "24h前"}</span>
              <span>{hourlyTraffic[6]?.time || "18h前"}</span>
              <span>{hourlyTraffic[12]?.time || "12h前"}</span>
              <span>{hourlyTraffic[18]?.time || "6h前"}</span>
              <span className="font-semibold text-foreground">{hourlyTraffic[hourlyTraffic.length - 1]?.time || "现在"}</span>
            </div>
          </div>

          <div className="pt-2 border-t border-border/30 flex items-center justify-between text-[11px] text-muted-foreground">
            <span>数据源：Xray / Sing-box Inbound 实时统计</span>
            <span className="text-emerald-500 font-medium">每 30 秒自动采样</span>
          </div>
        </Card>
      </div>

      {/* 第三行：活跃用户流量 Top 榜 */}
      <Card className="p-4 sm:p-5">
        <div className="flex items-center justify-between pb-3 border-b border-border/40">
          <div className="flex items-center gap-2">
            <Users className="size-4 text-sky-500" />
            <h2 className="text-sm font-semibold">用户消耗排行 Top 榜</h2>
          </div>
          {onNavigate && (
            <Button
              variant="ghost"
              size="sm"
              className="h-6 text-[11px] px-1.5 text-muted-foreground"
              onClick={() => onNavigate("/admin/users")}
            >
              用户中心 →
            </Button>
          )}
        </div>

        <div className="mt-4 space-y-3 max-h-[260px] overflow-y-auto pr-1">
          {userRanking.length === 0 ? (
            <div className="py-8 text-center text-xs text-muted-foreground">
              暂无用户流量记录
            </div>
          ) : (
            userRanking.map((u, i) => (
              <div key={u.id} className="space-y-1 text-xs">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5 truncate max-w-[160px] sm:max-w-[280px]">
                    <span className="font-mono text-muted-foreground text-[10px]">#{i + 1}</span>
                    <span className="font-medium truncate">{u.username}</span>
                    {u.enabled === 0 && (
                      <Badge variant="outline" className="border-rose-500/30 text-rose-500 text-[9px] px-1 py-0">已停用</Badge>
                    )}
                  </div>
                  <div className="font-mono text-[11px] text-muted-foreground">
                    <span className="font-semibold text-foreground">{formatBytes(u.total_bytes)}</span>
                    {u.traffic_limit_bytes > 0 && ` / ${formatBytes(u.traffic_limit_bytes)}`}
                  </div>
                </div>
                {u.traffic_limit_bytes > 0 && (
                  <div className="w-full bg-muted/60 rounded-full h-1 overflow-hidden">
                    <div
                      className={`h-full ${
                        u.percentage >= 100
                          ? "bg-rose-500"
                          : u.percentage >= 80
                          ? "bg-amber-500"
                          : "bg-emerald-500"
                      }`}
                      style={{ width: `${Math.min(u.percentage, 100)}%` }}
                    />
                  </div>
                )}
              </div>
            ))
          )}
        </div>
      </Card>
    </div>
  )
}
