import { useCallback, useEffect, useState } from "react"
import {
  Activity,
  AlertTriangle,
  ArrowUpDown,
  BarChart3,
  CheckCircle2,
  Layers,
  RefreshCw,
  Users,
  Wifi,
  XCircle,
} from "lucide-react"
import { toast } from "sonner"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select"

export type DashboardSummary = {
  total_servers: number
  online_servers: number
  total_nodes: number
  healthy_nodes: number
  unhealthy_nodes: number
  total_users: number
  active_users: number
  online_users?: number
  total_upload_bytes: number
  total_download_bytes: number
  total_traffic_bytes: number
  avg_latency_ms: number
  best_node: string | null
  best_latency_ms: number
  tg_bot_active: boolean
  inspection_interval_minutes?: number
}

export type NodeRankingItem = {
  id: number
  name: string
  server_name: string
  protocol: string
  port: number
  upload_bytes: number
  download_bytes: number
  total_bytes: number
  percentage: number
  last_check_status: string
  last_check_latency: number
  last_check_time: number
  last_check_error: string
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

export type ProtocolItem = {
  protocol: string
  count: number
  percentage: number
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

function formatRelativeTime(ts: number): string {
  if (!ts) return "未检测"
  const diff = Math.floor(Date.now() / 1000) - ts
  if (diff < 60) return "刚刚"
  if (diff < 3600) return `${Math.floor(diff / 60)} 分钟前`
  if (diff < 86400) return `${Math.floor(diff / 3600)} 小时前`
  return `${Math.floor(diff / 86400)} 天前`
}

function protocolBadge(proto: string) {
  switch (proto) {
    case "vless_reality":
      return <Badge variant="outline" className="border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 text-[10px] px-1.5 py-0 font-normal">Reality</Badge>
    case "vless_reality_xhttp":
      return <Badge variant="outline" className="border-teal-500/30 bg-teal-500/10 text-teal-600 dark:text-teal-400 text-[10px] px-1.5 py-0 font-normal">Reality xHTTP</Badge>
    case "anytls":
      return <Badge variant="outline" className="border-cyan-500/30 bg-cyan-500/10 text-cyan-600 dark:text-cyan-400 text-[10px] px-1.5 py-0 font-normal">AnyTLS</Badge>
    case "hysteria2":
      return <Badge variant="outline" className="border-purple-500/30 bg-purple-500/10 text-purple-600 dark:text-purple-400 text-[10px] px-1.5 py-0 font-normal">Hysteria 2</Badge>
    case "trojan":
      return <Badge variant="outline" className="border-sky-500/30 bg-sky-500/10 text-sky-600 dark:text-sky-400 text-[10px] px-1.5 py-0 font-normal">Trojan</Badge>
    case "ss2022":
      return <Badge variant="outline" className="border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400 text-[10px] px-1.5 py-0 font-normal">SS 2022</Badge>
    case "socks5":
      return <Badge variant="outline" className="border-blue-500/30 bg-blue-500/10 text-blue-600 dark:text-blue-400 text-[10px] px-1.5 py-0 font-normal">SOCKS 5</Badge>
    case "vmess_ws":
      return <Badge variant="outline" className="border-indigo-500/30 bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 text-[10px] px-1.5 py-0 font-normal">VMess WS</Badge>
    default:
      return <Badge variant="outline" className="text-[10px] px-1.5 py-0 font-normal">{proto}</Badge>
  }
}

export function ProxyDashboard({ onNavigate }: { onNavigate?: (tab: string) => void }) {
  const [loading, setLoading] = useState(true)
  const [checkingAll, setCheckingAll] = useState(false)
  const [testingId, setTestingId] = useState<number | null>(null)
  const [lastRefreshed, setLastRefreshed] = useState<Date>(new Date())
  const [showUnhealthyDialog, setShowUnhealthyDialog] = useState(false)
  const [inspectionInterval, setInspectionInterval] = useState(10)

  const [summary, setSummary] = useState<DashboardSummary | null>(null)
  const [nodeRanking, setNodeRanking] = useState<NodeRankingItem[]>([])
  const [userRanking, setUserRanking] = useState<UserRankingItem[]>([])
  const [protocolDist, setProtocolDist] = useState<ProtocolItem[]>([])
  const [hourlyTraffic, setHourlyTraffic] = useState<HourlyTrafficItem[]>([])

  const loadDashboard = useCallback(async (quiet = false) => {
    if (!quiet) setLoading(true)
    try {
      const res = await fetch("/api/proxy/dashboard/overview")
      const data = await res.json()
      if (data.ok) {
        setSummary(data.summary)
        if (data.summary?.inspection_interval_minutes) {
          setInspectionInterval(data.summary.inspection_interval_minutes)
        }
        setNodeRanking(data.node_ranking || [])
        setUserRanking(data.user_ranking || [])
        setProtocolDist(data.protocol_distribution || [])
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

  // 一键全网并发连通性测试
  const handleSweepCheck = async () => {
    setCheckingAll(true)
    try {
      const res = await fetch("/api/proxy/dashboard/check-health", { method: "POST" })
      const data = await res.json()
      if (data.ok) {
        const results = data.results || []
        const okCount = results.filter((r: { ok: boolean }) => r.ok).length
        const total = results.length
        if (total === 0) {
          toast.info("暂无可巡检的启用节点")
        } else if (okCount === total) {
          toast.success(`全网巡检完成：全部 ${total} 个节点连通握手正常！`)
        } else {
          toast.warning(`全网巡检完成：${okCount} 正常，${total - okCount} 个节点握手失败`)
        }
        loadDashboard(true)
      } else {
        toast.error(data.error || "全网巡检失败")
      }
    } catch {
      toast.error("巡检请求超时或网络异常")
    } finally {
      setCheckingAll(false)
    }
  }

  // 单节点独立测试
  const handleSingleTest = async (nodeId: number) => {
    setTestingId(nodeId)
    try {
      const res = await fetch(`/api/proxy/nodes/${nodeId}/test`)
      const data = await res.json()
      if (data.ok) {
        toast.success(data.message || `测试通过 (延迟 ~${data.latency_ms}ms)`)
      } else {
        toast.error(data.message || "握手测试未通过")
      }
      loadDashboard(true)
    } catch {
      toast.error("网络请求测试失败")
    } finally {
      setTestingId(null)
    }
  }

  // 修改巡检周期
  const handleUpdateInterval = async (val: string) => {
    const mins = parseInt(val) || 10
    setInspectionInterval(mins)
    try {
      const res = await fetch("/api/proxy/dashboard/check-interval", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ interval_minutes: mins }),
      })
      const d = await res.json()
      if (d.ok) {
        toast.success(`静默巡检周期已更新为每 ${mins} 分钟一次`)
      } else {
        toast.error(d.message || "设置巡检周期失败")
      }
    } catch {
      toast.error("网络请求错误")
    }
  }

  const unhealthyNodes = nodeRanking.filter(n => n.last_check_status && n.last_check_status !== "ok")

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
            全网节点实时连通性探测、流量消耗分布与服务器感知矩阵
          </p>
        </div>

        <div className="flex items-center gap-2 shrink-0">
          <Button
            size="sm"
            variant="outline"
            onClick={handleSweepCheck}
            disabled={checkingAll || loading}
            className="h-8 text-xs gap-1.5"
          >
            <Activity className={`size-3.5 ${checkingAll ? "animate-spin text-primary" : "text-emerald-500"}`} />
            {checkingAll ? "全网巡检中..." : "一键全网巡检"}
          </Button>

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
        {/* 指标 1：节点健康度 */}
        <Card className="p-4 sm:p-5 flex flex-col justify-between">
          <div className="flex items-center justify-between">
            <span className="text-xs font-medium text-muted-foreground">全网节点健康度</span>
            {summary && summary.unhealthy_nodes === 0 && summary.total_nodes > 0 ? (
              <CheckCircle2 className="size-4 text-emerald-500" />
            ) : (
              <button
                type="button"
                onClick={() => setShowUnhealthyDialog(true)}
                className="p-1 -m-1 rounded-md text-amber-500 hover:bg-amber-500/10 transition-colors flex items-center gap-1 cursor-pointer"
                title="点击查看异常节点详情与排查报告"
              >
                <AlertTriangle className="size-4 text-amber-500 animate-pulse" />
                <span className="text-[11px] font-semibold text-amber-600 dark:text-amber-400 underline decoration-dotted">查看详情</span>
              </button>
            )}
          </div>
          <div className="my-2">
            <div className="text-2xl sm:text-3xl font-bold tracking-tight">
              {summary && summary.total_nodes > 0
                ? `${Math.round((summary.healthy_nodes / summary.total_nodes) * 100)}%`
                : "100%"}
            </div>
            <div className="text-xs text-muted-foreground mt-1 flex items-center gap-1.5 flex-wrap">
              <span>{summary ? `${summary.healthy_nodes} / ${summary.total_nodes} 节点握手正常` : "加载中..."}</span>
              {summary && summary.unhealthy_nodes > 0 && (
                <button
                  type="button"
                  onClick={() => setShowUnhealthyDialog(true)}
                  className="text-destructive font-medium hover:underline cursor-pointer transition-colors"
                  title="点击查看异常节点清单"
                >
                  ({summary.unhealthy_nodes} 个异常)
                </button>
              )}
            </div>
          </div>
          <div className="w-full bg-muted rounded-full h-1.5 overflow-hidden">
            <div
              className={`h-full transition-all duration-500 ${
                summary && summary.unhealthy_nodes === 0 ? "bg-emerald-500" : "bg-amber-500"
              }`}
              style={{
                width: `${
                  summary && summary.total_nodes > 0
                    ? Math.round((summary.healthy_nodes / summary.total_nodes) * 100)
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

      {/* 第二行：左右分栏（节点流量排行 + 24小时流量趋势） */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* 左侧：节点流量消耗排行榜 */}
        <Card className="p-4 sm:p-5 flex flex-col">
          <div className="flex items-center justify-between pb-3 border-b border-border/40">
            <div className="flex items-center gap-2">
              <BarChart3 className="size-4 text-primary" />
              <h2 className="text-sm font-semibold">节点流量消耗排行</h2>
            </div>
            <span className="text-[11px] text-muted-foreground">
              累计共 {nodeRanking.length} 个节点
            </span>
          </div>

          <div className="mt-3 space-y-3 flex-1 overflow-y-auto max-h-[300px] pr-1">
            {nodeRanking.length === 0 ? (
              <div className="py-12 text-center text-xs text-muted-foreground">
                暂无节点流量消耗数据
              </div>
            ) : (
              nodeRanking.map((node, idx) => (
                <div key={node.id} className="space-y-1.5">
                  <div className="flex items-center justify-between text-xs gap-2">
                    <div className="flex items-center gap-1.5 min-w-0">
                      <span className={`size-4 rounded-full flex items-center justify-center text-[10px] font-bold shrink-0 ${
                        idx === 0 ? "bg-amber-500 text-white" : idx === 1 ? "bg-slate-400 text-white" : idx === 2 ? "bg-amber-700 text-white" : "bg-muted text-muted-foreground"
                      }`}>
                        {idx + 1}
                      </span>
                      <span className="font-medium truncate max-w-[140px] sm:max-w-[200px]" title={node.name}>
                        {node.name}
                      </span>
                      {protocolBadge(node.protocol)}
                    </div>
                    <div className="flex items-center gap-2 shrink-0 font-mono text-[11px]">
                      <span className="font-semibold text-foreground">{formatBytes(node.total_bytes)}</span>
                      <span className="text-muted-foreground w-10 text-right">{node.percentage}%</span>
                    </div>
                  </div>
                  <div className="w-full bg-muted/60 rounded-full h-1.5 overflow-hidden">
                    <div
                      className={`h-full transition-all duration-500 ${
                        idx === 0 ? "bg-primary" : "bg-primary/70"
                      }`}
                      style={{ width: `${Math.max(node.percentage, 2)}%` }}
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

      {/* 第三行：左右分栏（协议分布矩阵 + 活跃用户流量 Top 榜） */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* 左侧：协议分布矩阵 */}
        <Card className="p-4 sm:p-5">
          <div className="flex items-center justify-between pb-3 border-b border-border/40">
            <div className="flex items-center gap-2">
              <Layers className="size-4 text-purple-500" />
              <h2 className="text-sm font-semibold">协议分布与结构矩阵</h2>
            </div>
            <span className="text-[11px] text-muted-foreground">
              共 {protocolDist.length} 类协议
            </span>
          </div>

          <div className="mt-4 space-y-3">
            {protocolDist.length === 0 ? (
              <div className="py-8 text-center text-xs text-muted-foreground">
                暂无节点数据
              </div>
            ) : (
              protocolDist.map((item) => (
                <div key={item.protocol} className="space-y-1">
                  <div className="flex items-center justify-between text-xs">
                    <div className="flex items-center gap-2">
                      {protocolBadge(item.protocol)}
                      <span className="text-muted-foreground font-mono">{item.count} 个节点</span>
                    </div>
                    <span className="font-medium">{item.percentage}%</span>
                  </div>
                  <div className="w-full bg-muted/60 rounded-full h-1.5 overflow-hidden">
                    <div
                      className="h-full bg-purple-500 transition-all duration-500"
                      style={{ width: `${Math.max(item.percentage, 3)}%` }}
                    />
                  </div>
                </div>
              ))
            )}
          </div>
        </Card>

        {/* 右侧：活跃用户流量 Top 榜 */}
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

          <div className="mt-4 space-y-3 max-h-[220px] overflow-y-auto pr-1">
            {userRanking.length === 0 ? (
              <div className="py-8 text-center text-xs text-muted-foreground">
                暂无用户流量记录
              </div>
            ) : (
              userRanking.map((u, i) => (
                <div key={u.id} className="space-y-1 text-xs">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5 truncate max-w-[160px]">
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

      {/* 第四行：节点实时感知健康状态矩阵 */}
      <Card className="p-4 sm:p-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-3 border-b border-border/40">
          <div className="flex items-center gap-2">
            <Wifi className="size-4 text-emerald-500" />
            <h2 className="text-sm font-semibold">节点全景感知与连通性矩阵</h2>
          </div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <span>后台静默自动巡检周期：</span>
            <Select
              value={String(inspectionInterval)}
              onValueChange={handleUpdateInterval}
            >
              <SelectTrigger className="h-7 text-xs w-28 font-medium">
                <SelectValue placeholder="选择周期" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="1">1 分钟</SelectItem>
                <SelectItem value="3">3 分钟</SelectItem>
                <SelectItem value="5">5 分钟</SelectItem>
                <SelectItem value="10">10 分钟 (默认)</SelectItem>
                <SelectItem value="15">15 分钟</SelectItem>
                <SelectItem value="30">30 分钟</SelectItem>
                <SelectItem value="60">60 分钟</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </div>

        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-xs text-left">
            <thead>
              <tr className="border-b border-border/40 text-muted-foreground">
                <th className="py-2 px-2 font-medium">节点名称</th>
                <th className="py-2 px-2 font-medium">所属服务器</th>
                <th className="py-2 px-2 font-medium">协议 / 端口</th>
                <th className="py-2 px-2 font-medium">连通性状态</th>
                <th className="py-2 px-2 font-medium">最近感知时间</th>
                <th className="py-2 px-2 font-medium text-right">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border/30">
              {nodeRanking.length === 0 ? (
                <tr>
                  <td colSpan={6} className="py-8 text-center text-muted-foreground">
                    暂无代理节点
                  </td>
                </tr>
              ) : (
                nodeRanking.map((node) => {
                  const isTesting = testingId === node.id
                  const isOk = node.last_check_status === "ok"
                  const isFail = node.last_check_status === "fail"

                  return (
                    <tr key={node.id} className="hover:bg-muted/30 transition-colors">
                      <td className="py-2.5 px-2 font-medium max-w-[180px] truncate" title={node.name}>
                        {node.name}
                      </td>
                      <td className="py-2.5 px-2 text-muted-foreground max-w-[120px] truncate">
                        {node.server_name}
                      </td>
                      <td className="py-2.5 px-2">
                        <div className="flex items-center gap-1.5">
                          {protocolBadge(node.protocol)}
                          <span className="font-mono text-[11px] text-muted-foreground">:{node.port}</span>
                        </div>
                      </td>
                      <td className="py-2.5 px-2">
                        {isTesting ? (
                          <span className="inline-flex items-center gap-1 text-primary">
                            <RefreshCw className="size-3 animate-spin" />
                            <span>握手测速中...</span>
                          </span>
                        ) : isOk ? (
                          <span className="inline-flex items-center gap-1.5 text-emerald-600 dark:text-emerald-400 font-medium">
                            <span className="size-1.5 rounded-full bg-emerald-500 animate-pulse" />
                            连通正常
                            <span className="font-mono text-[11px]">({node.last_check_latency}ms)</span>
                          </span>
                        ) : isFail ? (
                          <span className="inline-flex items-center gap-1 text-destructive font-medium" title={node.last_check_error}>
                            <XCircle className="size-3.5 shrink-0" />
                            <span className="truncate max-w-[140px] sm:max-w-[200px]">
                              {node.last_check_error || "连通失败"}
                            </span>
                          </span>
                        ) : (
                          <span className="text-muted-foreground">未检测</span>
                        )}
                      </td>
                      <td className="py-2.5 px-2 text-muted-foreground font-mono text-[11px]">
                        {formatRelativeTime(node.last_check_time)}
                      </td>
                      <td className="py-2.5 px-2 text-right">
                        <Button
                          variant="ghost"
                          size="sm"
                          disabled={isTesting || checkingAll}
                          onClick={() => handleSingleTest(node.id)}
                          className="h-6 px-2 text-[11px] gap-1 hover:bg-muted"
                        >
                          <RefreshCw className={`size-3 ${isTesting ? "animate-spin" : ""}`} />
                          <span>测试</span>
                        </Button>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </Card>

      {/* 异常节点清单弹窗 */}
      <Dialog open={showUnhealthyDialog} onOpenChange={setShowUnhealthyDialog}>
        <DialogContent className="max-w-xl max-h-[80vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base font-bold text-destructive">
              <AlertTriangle className="size-5 text-amber-500" />
              全网异常节点检测清单 ({unhealthyNodes.length} 个)
            </DialogTitle>
            <DialogDescription className="text-xs text-muted-foreground">
              以下节点在最近一次连通性感知巡检中握手失败或响应超时。
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-2.5 py-2">
            {unhealthyNodes.length === 0 ? (
              <div className="text-center py-8 text-xs text-muted-foreground">
                <CheckCircle2 className="size-8 text-emerald-500 mx-auto mb-2 opacity-80" />
                当前暂无异常节点，全部代理节点握手测试均畅通！
              </div>
            ) : (
              unhealthyNodes.map((n) => (
                <div key={n.id} className="p-3 rounded-lg border border-destructive/20 bg-destructive/5 space-y-2">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-xs text-foreground">{n.name}</span>
                      {protocolBadge(n.protocol)}
                    </div>
                    <Badge variant="destructive" className="text-[10px] px-1.5 py-0">连接异常</Badge>
                  </div>
                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
                    <span>所属服务器: <strong className="text-foreground">{n.server_name}</strong></span>
                    <span>端口: <code className="font-mono">{n.port}</code></span>
                    <span>最近检测: {formatRelativeTime(n.last_check_time)}</span>
                  </div>
                  <div className="text-xs font-mono bg-destructive/10 text-destructive rounded p-2 text-[11px] break-all">
                    ⚠️ 失败原因: {n.last_check_error || "TCP/TLS 握手超时或对端拒绝连接"}
                  </div>
                  <div className="flex justify-end gap-2 pt-1">
                    <Button
                      variant="outline"
                      size="sm"
                      className="h-7 text-xs"
                      disabled={testingId === n.id}
                      onClick={() => handleSingleTest(n.id)}
                    >
                      <RefreshCw className={`size-3 mr-1 ${testingId === n.id ? "animate-spin" : ""}`} />
                      {testingId === n.id ? "探测中..." : "重新探测"}
                    </Button>
                  </div>
                </div>
              ))
            )}
          </div>

          <div className="flex justify-between items-center pt-2 border-t">
            {onNavigate && (
              <Button
                variant="secondary"
                size="sm"
                className="text-xs h-8"
                onClick={() => {
                  setShowUnhealthyDialog(false)
                  onNavigate("/admin/proxy")
                }}
              >
                前往代理节点管理 →
              </Button>
            )}
            <Button
              variant="outline"
              size="sm"
              className="text-xs h-8 ml-auto"
              onClick={() => setShowUnhealthyDialog(false)}
            >
              关闭
            </Button>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
