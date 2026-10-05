import { ArrowDown, ArrowUp } from "lucide-react"

import { Badge } from "@/components/ui/badge"
import { Card } from "@/components/ui/card"
import { Meter } from "@/components/Meter"
import type { Node } from "@/lib/api"
import { bytes, CYCLES, daysUntil, FOREVER, money, monthlyCost, pair, percent, rate, uptime } from "@/lib/format"
import { cn } from "@/lib/utils"

// Emitted as files and fetched on first use, so a page carries only the flags its
// nodes are in rather than all 265. vite.config.ts keeps them from being inlined
// into the bundle as data URLs. The simplified set, because this theme is
// embedded in the hub binary: flag-icons' detailed emblems total 1.95 MiB against
// 174 KiB here, a difference invisible at 18 by 12 pixels.
const FLAGS = Object.fromEntries(
  Object.entries(
    import.meta.glob<string>("/node_modules/country-flag-icons/3x2/*.svg", {
      query: "?url",
      import: "default",
      eager: true,
    }),
  ).map(([path, url]) => [path.match(/([\w-]+)\.svg$/)![1], url]),
)

/**
 * This period's usage as the plan meters it. The hub computes it; the switch
 * below serves only a hub from before `month_used`.
 */
function monthUsage(node: Node): number {
  if (typeof node.month_used === "number") return node.month_used
  const { month_rx: rx, month_tx: tx } = node
  switch (node.traffic_mode) {
    case "up":
      return tx
    case "down":
      return rx
    case "max":
      return Math.max(rx, tx)
    default:
      return rx + tx
  }
}

// A node that has reported once has told the hub its shape -- cores, memory,
// disk -- and the hub retains its traffic totals whether connected or not. A node
// that never connected is the only case with nothing to show.
function deployed(node: Node) {
  return node.cpu_cores > 0 || node.mem_total > 0
}

/**
 * The dot plus how long the machine has been up, or once it is gone, how long it
 * has been absent -- the first question asked of an offline node. Both are
 * durations, so the badge keeps its shape either way.
 */
export function Status({ node }: { node: Node }) {
  const down = node.last_seen ? Date.now() / 1000 - node.last_seen : 0
  const label = node.online
    ? `在线 ${node.metrics ? uptime(node.metrics.uptime) : ""}`
    : deployed(node)
      ? `离线 ${down >= 60 ? uptime(down) : ""}`
      : "未接入"
  return (
    // Muted once it stops reporting: the figures on the page are genuine, merely
    // no longer current.
    <Badge
      variant="outline"
      className={cn("tnum shrink-0 gap-1.5 font-normal", !node.online && "text-muted-foreground")}
    >
      <span
        className={cn(
          "size-1.5 rounded-full",
          node.online ? "bg-online" : deployed(node) ? "bg-offline" : "bg-muted-foreground/40",
        )}
      />
      {label.trim()}
    </Badge>
  )
}

/** Where the machine is: its flag, or the bare code for one the set lacks. */
export function Country({ node }: { node: Node }) {
  if (!node.country) return null
  const src = FLAGS[node.country]
  if (!src) {
    return (
      <Badge variant="outline" className="shrink-0 font-normal text-muted-foreground">
        {node.country}
      </Badge>
    )
  }
  return (
    <img
      src={src}
      alt={node.country}
      title={node.country}
      className="h-3 w-4.5 shrink-0 rounded-[2px] ring-1 ring-foreground/10"
    />
  )
}


// Traffic uses the plan's own counting rule, so the bar matches the quota the
// node is billed against.
function trafficFoot(node: Node) {
  return node.traffic_limit > 0
    ? pair(monthUsage(node), node.traffic_limit)
    : `${bytes(monthUsage(node))} / ${FOREVER}`
}

export type LatencyHistoryPoint = {
  latency: number | null
  ts: number
  lost?: number
  total?: number
}

export type LatencyWindow = "1h" | "6h" | "24h"

export type LatencyWindowStats = {
  total: number
  lost: number
  avg: number | null
  min: number | null
  max: number | null
  loss_rate: number
  bars?: (LatencyHistoryPoint | null)[]
}

export type LatencyProbe = {
  task_id: number
  name: string
  latency: number | null
  ts?: number
  history?: LatencyHistoryPoint[]
  avg?: number | null
  min?: number | null
  max?: number | null
  loss_rate?: number | null
  lost_samples?: number | null
  total_samples?: number | null
  windows?: Record<LatencyWindow, LatencyWindowStats>
}

export function getLatencyTier(latency: number | null | undefined): {
  color: string
  bgClass: string
  borderClass: string
  textClass: string
  barClass: string
  label: string
} {
  if (latency === null || latency === undefined || latency < 0) {
    return {
      color: "#f43f5e",
      bgClass: "bg-rose-500/10 dark:bg-rose-500/20",
      borderClass: "border-rose-500/30",
      textClass: "text-rose-600 dark:text-rose-400 font-semibold",
      barClass: "bg-rose-500 dark:bg-rose-600",
      label: "超时/丢包",
    }
  }
  if (latency < 60) {
    return {
      color: "#10b981",
      bgClass: "bg-emerald-500/10 dark:bg-emerald-500/20",
      borderClass: "border-emerald-500/30",
      textClass: "text-emerald-600 dark:text-emerald-400 font-semibold",
      barClass: "bg-emerald-500 hover:bg-emerald-400 dark:bg-emerald-500 dark:hover:bg-emerald-400",
      label: "极佳 (<60ms)",
    }
  }
  if (latency <= 100) {
    return {
      color: "#06b6d4",
      bgClass: "bg-cyan-500/10 dark:bg-cyan-500/20",
      borderClass: "border-cyan-500/30",
      textClass: "text-cyan-600 dark:text-cyan-400 font-semibold",
      barClass: "bg-cyan-500 hover:bg-cyan-400 dark:bg-cyan-500 dark:hover:bg-cyan-400",
      label: "良好 (60-100ms)",
    }
  }
  if (latency <= 180) {
    return {
      color: "#f59e0b",
      bgClass: "bg-amber-500/10 dark:bg-amber-500/20",
      borderClass: "border-amber-500/30",
      textClass: "text-amber-600 dark:text-amber-400 font-semibold",
      barClass: "bg-amber-500 hover:bg-amber-400 dark:bg-amber-500 dark:hover:bg-amber-400",
      label: "一般 (100-180ms)",
    }
  }
  if (latency <= 280) {
    return {
      color: "#f97316",
      bgClass: "bg-orange-500/10 dark:bg-orange-500/20",
      borderClass: "border-orange-500/30",
      textClass: "text-orange-600 dark:text-orange-400 font-semibold",
      barClass: "bg-orange-500 hover:bg-orange-400 dark:bg-orange-500 dark:hover:bg-orange-400",
      label: "偏高 (180-280ms)",
    }
  }
  return {
    color: "#e11d48",
    bgClass: "bg-rose-500/10 dark:bg-rose-500/20",
    borderClass: "border-rose-500/30",
    textClass: "text-rose-600 dark:text-rose-400 font-semibold",
    barClass: "bg-rose-600 hover:bg-rose-500 dark:bg-rose-600 dark:hover:bg-rose-500",
    label: "拥堵 (>280ms)",
  }
}

export function getBarPointTier(pt: LatencyHistoryPoint | null | undefined): {
  color: string
  bgClass: string
  borderClass: string
  textClass: string
  barClass: string
  label: string
} {
  if (!pt) {
    return {
      color: "#9ca3af",
      bgClass: "bg-muted/30",
      borderClass: "border-border",
      textClass: "text-muted-foreground",
      barClass: "bg-muted/40",
      label: "尚无检测采样",
    }
  }

  const isFullLoss = pt.latency === null || pt.latency === undefined || pt.latency < 0
  const tot = pt.total ?? 1
  const lost = pt.lost ?? (isFullLoss ? 1 : 0)
  const lossRate = tot > 0 ? (lost / tot) * 100 : (isFullLoss ? 100 : 0)

  // 1. 如果当前时间桶全部丢包 (100% loss)
  if (isFullLoss || lossRate >= 99.9) {
    return {
      color: "#f43f5e",
      bgClass: "bg-rose-500/10 dark:bg-rose-500/20",
      borderClass: "border-rose-500/30",
      textClass: "text-rose-600 dark:text-rose-400 font-semibold",
      barClass: "bg-rose-500 dark:bg-rose-600",
      label: "全丢包 (100%)",
    }
  }

  // 2. 如果当前时间桶出现严重丢包 (>= 50% loss)
  if (lossRate >= 50) {
    return {
      color: "#f43f5e",
      bgClass: "bg-rose-500/10 dark:bg-rose-500/20",
      borderClass: "border-rose-500/30",
      textClass: "text-rose-600 dark:text-rose-400 font-semibold",
      barClass: "bg-rose-500 hover:bg-rose-400 dark:bg-rose-600 dark:hover:bg-rose-500",
      label: `严重丢包 (${Math.round(lossRate)}%)`,
    }
  }

  // 3. 如果当前时间桶出现较高丢包 (>= 20% loss)
  if (lossRate >= 20) {
    return {
      color: "#f97316",
      bgClass: "bg-orange-500/10 dark:bg-orange-500/20",
      borderClass: "border-orange-500/30",
      textClass: "text-orange-600 dark:text-orange-400 font-semibold",
      barClass: "bg-orange-500 hover:bg-orange-400 dark:bg-orange-500 dark:hover:bg-orange-400",
      label: `较高丢包 (${Math.round(lossRate)}%)`,
    }
  }

  // 4. 如果当前时间桶出现轻度丢包 (>= 5% loss)
  if (lossRate >= 5) {
    return {
      color: "#f59e0b",
      bgClass: "bg-amber-500/10 dark:bg-amber-500/20",
      borderClass: "border-amber-500/30",
      textClass: "text-amber-600 dark:text-amber-400 font-semibold",
      barClass: "bg-amber-500 hover:bg-amber-400 dark:bg-amber-500 dark:hover:bg-amber-400",
      label: `轻度丢包 (${Math.round(lossRate)}%)`,
    }
  }

  // 5. 丢包率极低或无丢包 (< 5% loss)，按平均延迟评级
  return getLatencyTier(pt.latency)
}

function getIspTheme(name: string) {
  if (name.includes("移动")) {
    return {
      badge: "bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/25",
      dot: "bg-blue-500",
    }
  }
  if (name.includes("联通")) {
    return {
      badge: "bg-orange-500/10 text-orange-600 dark:text-orange-400 border-orange-500/25",
      dot: "bg-orange-500",
    }
  }
  if (name.includes("电信")) {
    return {
      badge: "bg-sky-500/10 text-sky-600 dark:text-sky-400 border-sky-500/25",
      dot: "bg-sky-500",
    }
  }
  return {
    badge: "bg-muted text-muted-foreground border-border",
    dot: "bg-muted-foreground",
  }
}

function formatLatencyTime(ts?: number, window?: LatencyWindow): string {
  if (!ts) return "—"
  const d = new Date(ts * 1000)
  if (window === "24h") {
    return `${d.getMonth() + 1}/${d.getDate()} ${d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}`
  }
  return d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })
}

export type VisibilitySettings = {
  show_price: boolean
  show_expiry: boolean
  show_traffic_limit: boolean
  is_admin: boolean
}

// No date means nothing expires: a permanent host, or one with no renewal set. A
// blank corner asserts neither. The days are the hub's count: it renews an online
// node by its own calendar, and counting on the visitor's would show the node
// expired for hours before that. Only a hub from before `expires_in` leaves the
// count to the browser.
function Expiry({ node, show }: { node: Node; show: boolean }) {
  if (!show) return null
  const days = node.expires_in !== undefined ? node.expires_in : daysUntil(node.expires_at)
  if (days === null) return <span className="text-xs text-muted-foreground" title="永不到期">{FOREVER}</span>
  const tone = days < 0 ? "text-destructive" : days <= 7 ? "text-warn" : "text-muted-foreground"
  return (
    <span className={cn("tnum text-xs", tone)}>
      {days < 0 ? `已过期 ${-days} 天` : `${days} 天后到期`}
    </span>
  )
}

export function NodeCard({
  node,
  onOpen,
  latencies,
  visibilitySettings,
  latencyWindow = "1h",
  onLatencyWindowChange,
}: {
  node: Node
  onOpen: () => void
  latencies?: LatencyProbe[]
  visibilitySettings?: VisibilitySettings
  latencyWindow?: LatencyWindow
  onLatencyWindowChange?: (w: LatencyWindow) => void
}) {
  const m = node.metrics
  const showExpiry = Boolean(visibilitySettings?.is_admin || visibilitySettings?.show_expiry)
  const showTrafficLimit = Boolean(visibilitySettings?.is_admin || visibilitySettings?.show_traffic_limit)
  const showPrice = Boolean(
    visibilitySettings
      ? visibilitySettings.is_admin || visibilitySettings.show_price
      : true
  )

  const down = node.last_seen ? Date.now() / 1000 - node.last_seen : 0
  const uptimeLabel = node.online
    ? `在线 ${node.metrics ? uptime(node.metrics.uptime) : "运行中"}`
    : deployed(node)
      ? `离线 ${down >= 60 ? uptime(down) : "刚刚"}`
      : "等待首次上报"

  const price = typeof node.price === "number" ? node.price : 0
  const currency = node.currency || "CNY"
  const cycleKey = node.billing_cycle || "monthly"
  const cycleName = CYCLES[cycleKey] ?? cycleKey
  const mCost = monthlyCost(price, cycleKey)

  let priceText = ""
  let priceTooltip = ""
  if (showPrice) {
    if (price > 0) {
      priceText = `${money(price, currency)}/${cycleName}`
      priceTooltip = `续费周期: ${cycleName} (${money(price, currency)})`
      if (cycleKey !== "monthly" && mCost > 0) {
        priceTooltip += ` · 折合 ${money(mCost, currency)}/月`
      }
    } else {
      priceText = "免费"
      priceTooltip = "免费服务器"
    }
  }

  return (
    <Card
      onClick={onOpen}
      // min-w-0: a grid item sizes to its content unless told otherwise, and the
      // title line below truncates nicely so the card never overflows its column.
      className="min-w-0 cursor-pointer gap-0 p-4 transition-colors hover:border-ring"
      role="button"
      tabIndex={0}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onOpen())}
    >
      <div className="flex flex-col gap-1.5">
        {/* 第一行：左侧为服务器名称与国家图标，右侧为运行状态指示徽章 */}
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 items-center gap-1.5">
            <h3 className="truncate font-medium">{node.name}</h3>
            <Country node={node} />
          </div>
          {node.online ? (
            <Badge
              variant="outline"
              className="shrink-0 gap-1.5 border-emerald-500/30 bg-emerald-500/10 text-xs font-normal text-emerald-600 dark:text-emerald-400"
            >
              <span className="size-1.5 rounded-full bg-emerald-500" />
              运行中
            </Badge>
          ) : deployed(node) ? (
            <Badge
              variant="outline"
              className="shrink-0 gap-1.5 border-rose-500/30 bg-rose-500/10 text-xs font-normal text-rose-600 dark:text-rose-400"
            >
              <span className="size-1.5 rounded-full bg-rose-500" />
              已离线
            </Badge>
          ) : (
            <Badge variant="outline" className="shrink-0 gap-1.5 text-xs font-normal text-muted-foreground">
              <span className="size-1.5 rounded-full bg-muted-foreground/40" />
              未接入
            </Badge>
          )}
        </div>

        {/* 第二行：左侧为在线时长与服务器费用，右侧为到期倒计时 */}
        <div className="flex items-center justify-between gap-2 text-xs text-muted-foreground">
          <div className="flex min-w-0 items-center gap-1.5 truncate">
            <span className="truncate" title={uptimeLabel}>
              {uptimeLabel}
            </span>
            {showPrice && (
              <>
                <span className="text-muted-foreground/60">·</span>
                <span
                  className={cn(
                    "shrink-0 font-medium",
                    price > 0 ? "text-foreground/90 font-mono" : "text-muted-foreground"
                  )}
                  title={priceTooltip}
                >
                  {priceText}
                </span>
              </>
            )}
          </div>
          <Expiry node={node} show={showExpiry} />
        </div>
      </div>

      {/* One layout for both states: a disconnected node still knows its
          cores, memory, disk size and traffic totals, and showing those with
          the live figures blank beats a stretched card with one line in it. */}
      {deployed(node) ? (
        <>
          <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-4">
            {/* The core count belongs beside the word CPU: it is what the
                percentage and the load averages are both measured against. */}
            <Meter
              label={`CPU ${node.cpu_cores} 核`}
              pct={m ? m.cpu : null}
              foot={m ? m.load.map((n) => n.toFixed(2)).join(" ") : "—"}
            />
            <Meter
              label="内存"
              pct={m ? percent(m.mem_used, m.mem_total) : null}
              foot={m ? pair(m.mem_used, m.mem_total) : bytes(node.mem_total)}
            />
            <Meter
              label="硬盘"
              pct={m ? percent(m.disk_used, m.disk_total) : null}
              foot={m ? pair(m.disk_used, m.disk_total) : bytes(node.disk_total)}
            />
            <Meter
              label="流量"
              pct={showTrafficLimit && node.traffic_limit > 0 ? percent(monthUsage(node), node.traffic_limit) : null}
              empty={FOREVER}
              foot={showTrafficLimit ? trafficFoot(node) : `${bytes(monthUsage(node))} (已用)`}
            />
          </div>

          <div className="mt-4 grid grid-cols-2 gap-x-4 gap-y-2 border-t pt-4 text-xs">
            <span className="tnum inline-flex items-center gap-1.5">
              <ArrowDown className="size-3 text-muted-foreground" />
              {m ? rate(m.net_rx) : "—"}
            </span>
            <span className="tnum inline-flex items-center gap-1.5">
              <ArrowUp className="size-3 text-muted-foreground" />
              {m ? rate(m.net_tx) : "—"}
            </span>
            <span className="tnum inline-flex items-center gap-1.5 text-muted-foreground">
              <ArrowDown className="size-3" />
              {bytes(node.total_rx)}
            </span>
            <span className="tnum inline-flex items-center gap-1.5 text-muted-foreground">
              <ArrowUp className="size-3" />
              {bytes(node.total_tx)}
            </span>
          </div>

          {/* 探针卡片直观展示已配置的网络延迟与近期波动走势 */}
          {latencies && latencies.length > 0 && (
            <div className="mt-3.5 border-t pt-2.5 text-xs">
              {/* 头部标题、实时采样说明与延迟颜色图例 */}
              <div className="flex items-center justify-between gap-1 mb-2">
                <div className="flex items-center gap-1.5 font-medium text-foreground/90">
                  <span className="relative flex h-2 w-2 shrink-0">
                    <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75" />
                    <span className="relative inline-flex rounded-full h-2 w-2 bg-emerald-500" />
                  </span>
                  <span className="text-[11px] sm:text-xs">网络延迟</span>
                  <span className="text-[10px] text-muted-foreground font-normal">
                    (60s采样)
                  </span>
                </div>
                {/* 1h / 6h / 24h 切换胶囊 */}
                <div
                  className="inline-flex items-center p-0.5 rounded-md bg-muted/70 dark:bg-muted/40 border border-border/50 text-[10px] select-none"
                  onClick={(e) => e.stopPropagation()}
                >
                  {(["1h", "6h", "24h"] as const).map((w) => (
                    <button
                      key={w}
                      type="button"
                      onClick={() => onLatencyWindowChange?.(w)}
                      className={cn(
                        "px-1.5 py-0.5 rounded-[4px] font-mono leading-none transition-all cursor-pointer",
                        latencyWindow === w
                          ? "bg-background text-foreground shadow-2xs font-semibold ring-1 ring-border/50"
                          : "text-muted-foreground hover:text-foreground"
                      )}
                      title={`切换统计周期至近 ${w === "1h" ? "1 小时" : w === "6h" ? "6 小时" : "24 小时"}`}
                    >
                      {w}
                    </button>
                  ))}
                </div>
              </div>

              {/* 每个监控接口的实时延迟与历史波动条 */}
              {(() => {
                const windowLabel = latencyWindow === "1h" ? "1 小时" : latencyWindow === "6h" ? "6 小时" : "24 小时"
                const unitLabel = latencyWindow === "1h" ? "2分钟" : latencyWindow === "6h" ? "12分钟" : "1小时"
                return (
                  <div className="space-y-1.5" onClick={(e) => e.stopPropagation()}>
                    {latencies.map((p) => {
                  const isTimeout = p.latency === null || p.latency === undefined || p.latency < 0
                  const lat = p.latency ?? 0
                  const currentTier = getLatencyTier(p.latency)
                  const isp = getIspTheme(p.name)
                  const hist = p.history || []

                  // 获取当前选定时间窗口的统计数据 (1h / 6h / 24h)
                  const win = p.windows?.[latencyWindow]
                  const winAvg = win ? win.avg : p.avg
                  const winMin = win ? win.min : p.min
                  const winMax = win ? win.max : p.max
                  const winTotal = win ? win.total : (p.total_samples ?? hist.length)
                  const winLost = win ? win.lost : (p.lost_samples ?? hist.filter((h) => h.latency === null || h.latency === undefined || h.latency < 0).length)
                  const winLossRate = win ? win.loss_rate : (winTotal > 0 ? Math.round((winLost / winTotal) * 100) : 0)

                  const windowLabel = latencyWindow === "1h" ? "1 小时" : latencyWindow === "6h" ? "6 小时" : "24 小时"

                  // 格式化当前窗口丢包率显示文案：
                  let lossDisplay = "0%"
                  if (winLossRate > 0 && winLossRate < 1) {
                    lossDisplay = "<1%"
                  } else if (winLossRate >= 1) {
                    lossDisplay = `${winLossRate % 1 === 0 ? winLossRate : winLossRate.toFixed(1)}%`
                  }

                  const lossTone =
                    winLossRate <= 0
                      ? "text-muted-foreground/80"
                      : winLossRate < 10
                        ? "text-amber-500 dark:text-amber-400 font-medium"
                        : "text-rose-500 dark:text-rose-400 font-semibold"

                  const totalSlots = 20
                  const paddedHist: (LatencyHistoryPoint | null)[] = []
                  if (hist.length < totalSlots) {
                    for (let i = 0; i < totalSlots - hist.length; i++) {
                      paddedHist.push(null)
                    }
                  }
                  for (const pt of hist.slice(-totalSlots)) {
                    paddedHist.push(pt)
                  }

                  const activeBars: (LatencyHistoryPoint | null)[] = win?.bars && win.bars.length > 0 ? win.bars : paddedHist
                  const unitLabel = latencyWindow === "1h" ? "2分钟" : latencyWindow === "6h" ? "12分钟" : "1小时"

                  return (
                    <div
                      key={p.task_id}
                      className="rounded-md bg-muted/25 dark:bg-muted/15 border border-border/40 p-1.5 hover:bg-muted/40 transition-colors"
                    >
                      {/* 首行：接口名称 + 历史均值 + 丢包率 + 实时延迟徽章 */}
                      <div className="flex items-center justify-between gap-1 text-[11px] leading-tight mb-1">
                        <div className="flex items-center gap-1.5 min-w-0">
                          <span className={cn("px-1.5 py-0.5 rounded text-[10px] font-medium shrink-0 border", isp.badge)}>
                            {p.name}
                          </span>
                          {winAvg !== undefined && winAvg !== null && (
                            <span
                              className="text-[10px] text-muted-foreground truncate"
                              title={`近 ${windowLabel}延迟波动: 最低 ${winMin ?? '-'}ms / 最高 ${winMax ?? '-'}ms / 平均 ${winAvg}ms`}
                            >
                              均值 {winAvg}ms
                            </span>
                          )}
                          <span
                            className={cn(
                              "text-[10px] shrink-0 font-mono transition-colors",
                              lossTone
                            )}
                            title={`近 ${windowLabel}共检测 ${winTotal} 次，超时/丢包 ${winLost} 次，丢包率 ${lossDisplay}`}
                          >
                            · 丢包 {lossDisplay}
                          </span>
                        </div>

                        {/* 实时延迟胶囊 */}
                        <div
                          className={cn(
                            "inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] sm:text-[11px] font-mono border shrink-0 transition-colors shadow-2xs",
                            currentTier.bgClass,
                            currentTier.borderClass,
                            currentTier.textClass
                          )}
                          title={isTimeout ? `${p.name}: 当前连接超时/丢包` : `${p.name}: 实时延迟 ${lat}ms (${currentTier.label})`}
                        >
                          <span className="size-1.5 rounded-full animate-pulse" style={{ backgroundColor: currentTier.color }} />
                          <span>{isTimeout ? "超时" : `${lat} ms`}</span>
                        </div>
                      </div>

                      {/* 次行：当前周期延迟波动走势条 */}
                      <div
                        className="flex items-center gap-[2px] w-full h-3 pt-0.5"
                        title={`近${windowLabel}延迟波动走势（共 ${activeBars.length} 格，每格 ${unitLabel}）`}
                      >
                        {activeBars.map((pt, idx) => {
                          if (!pt) {
                            return (
                              <div
                                key={idx}
                                className="flex-1 h-full rounded-[1px] bg-muted/40"
                                title="尚无检测采样"
                              />
                            )
                          }
                          const ptTier = getBarPointTier(pt)
                          const isLoss = pt.latency === null || pt.latency < 0
                          
                          let tooltipText = `时间: ${formatLatencyTime(pt.ts, latencyWindow)} (${unitLabel})`
                          if (ptTier.label.includes("丢包") || ptTier.label.includes("超时")) {
                            tooltipText += ` | 状态: ${ptTier.label}`
                            if (!isLoss && pt.latency !== null) {
                              tooltipText += ` · 延迟: ${pt.latency}ms`
                            }
                          } else {
                            tooltipText += ` | 延迟: ${pt.latency}ms (${ptTier.label})`
                          }
                          if (pt.total && pt.total > 1) {
                            tooltipText += ` · 采样: 成功 ${pt.total - (pt.lost || 0)}/丢包 ${pt.lost || 0} (共 ${pt.total} 次)`
                          }

                          return (
                            <div
                              key={idx}
                              className={cn(
                                "flex-1 h-full rounded-[1px] transition-all duration-150 hover:scale-y-125 hover:brightness-125 cursor-pointer",
                                ptTier.barClass
                              )}
                              title={tooltipText}
                            />
                          )
                        })}
                      </div>
                    </div>
                  )
                })}

                {/* 走势条时间跨度动态提示 */}
                <div className="flex items-center justify-between text-[9px] text-muted-foreground/60 px-0.5 font-mono select-none">
                  <span>← {windowLabel}前</span>
                  <span>波动走势（每格{unitLabel}）</span>
                  <span>刚刚 →</span>
                </div>
              </div>
            )
          })()}
        </div>
      )}
        </>
      ) : (
        /* Never connected: nothing to plot, so the card stays short rather than
           padding out to match its neighbours. */
        <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
          还没有接入。在后台生成安装命令并执行一次。
        </p>
      )}
    </Card>
  )
}
