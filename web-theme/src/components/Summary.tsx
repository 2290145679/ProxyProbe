import { useState } from "react"
import { ArrowDownUp, CreditCard, Gauge, Server } from "lucide-react"

import { Card } from "@/components/ui/card"
import { speedHistory, type Node } from "@/lib/api"
import { bytes, convertCurrency, money, monthlyCost, rate } from "@/lib/format"
import { cn } from "@/lib/utils"
import type { VisibilitySettings } from "@/components/NodeCard"

export type CostPeriod = "monthly" | "quarterly" | "yearly"
export type TrafficScope = "today" | "total"

const COST_PERIODS: { key: CostPeriod; label: string; multiplier: number; title: string; unit: string }[] = [
  { key: "monthly", label: "月", multiplier: 1, title: "月度", unit: "/月" },
  { key: "quarterly", label: "季", multiplier: 3, title: "季度", unit: "/季" },
  { key: "yearly", label: "年", multiplier: 12, title: "年度", unit: "/年" },
]

function shortUnit(n: number): string {
  if (!n || n < 1) return "0B"
  const units = ["B", "K", "M", "G", "T", "P"]
  const i = Math.min(Math.floor(Math.log(n) / Math.log(1024)), units.length - 1)
  const v = n / 1024 ** i
  const digits = i === 0 ? 0 : v >= 100 ? 0 : v >= 10 ? 1 : 2
  return `${v.toFixed(digits)}${units[i]}`
}

function shortSpeed(n: number): string {
  if (!n || n < 1) return "0B/s"
  if (n < 1024) return `${n.toFixed(0)}B/s`
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(n >= 100 * 1024 ? 0 : 1)}K/s`
  return `${(n / 1024 / 1024).toFixed(1)}M/s`
}

function Tile({
  icon: Icon,
  label,
  right,
  children,
  className,
}: {
  icon: typeof Server
  label: React.ReactNode
  right?: React.ReactNode
  children: React.ReactNode
  className?: string
}) {
  return (
    <Card className={cn("flex flex-col justify-between gap-0 p-3 sm:p-3.5 min-h-[108px] sm:min-h-[114px] overflow-hidden", className)}>
      <div className="flex items-center justify-between text-xs text-muted-foreground gap-1 min-w-0">
        <div className="flex items-center gap-1.5 shrink-0 min-w-0">
          <Icon className="size-3.5 shrink-0 text-muted-foreground/80" />
          <span className="font-medium text-foreground/80 whitespace-nowrap">{label}</span>
        </div>
        {right}
      </div>
      {children}
    </Card>
  )
}

/**
 * A bare polyline with no axes or tooltips: at this size only the shape is
 * legible, and recharts would bring a full chart's machinery for it. Series share
 * one scale so the two throughput lines remain comparable.
 */
function Spark({ series }: { series: { values: number[]; className: string }[] }) {
  const top = Math.max(...series.flatMap((s) => s.values), 1)
  const width = Math.max(...series.map((s) => s.values.length), 2) - 1
  return (
    <svg viewBox="0 0 100 20" preserveAspectRatio="none" className="h-4.5 w-full mt-1.5 opacity-80" aria-hidden>
      {series.map((s, i) => (
        <polyline
          key={i}
          className={s.className}
          fill="none"
          stroke="currentColor"
          strokeWidth={1.25}
          vectorEffect="non-scaling-stroke"
          points={s.values.map((v, x) => `${(x / width) * 100},${19 - (v / top) * 18}`).join(" ")}
        />
      ))}
    </svg>
  )
}

/** `group` picks the throughput series: null for every node, else the tab's group. */
export function Summary({
  nodes,
  group,
  visibilitySettings,
  targetCurrency = "CNY",
}: {
  nodes: Node[]
  group: string | null
  visibilitySettings?: VisibilitySettings
  targetCurrency?: string
}) {
  const online = nodes.filter((n) => n.online)
  const sum = (pick: (n: Node) => number) => nodes.reduce((total, n) => total + pick(n), 0)

  const showPrice = Boolean(
    visibilitySettings
      ? visibilitySettings.is_admin || visibilitySettings.show_price
      : true,
  )

  // 费用周期切换 (月 / 季 / 年)
  const [costPeriod, setCostPeriod] = useState<CostPeriod>(() => {
    try {
      return (localStorage.getItem("probe_cost_period") as CostPeriod) || "monthly"
    } catch {
      return "monthly"
    }
  })

  const handleCostPeriodChange = (p: CostPeriod) => {
    setCostPeriod(p)
    try {
      localStorage.setItem("probe_cost_period", p)
    } catch {}
  }

  // 流量范围切换 (今日 / 累计)
  const [trafficScope, setTrafficScope] = useState<TrafficScope>(() => {
    try {
      return (localStorage.getItem("probe_traffic_scope") as TrafficScope) || "today"
    } catch {
      return "today"
    }
  })

  const handleTrafficScopeChange = (s: TrafficScope) => {
    setTrafficScope(s)
    try {
      localStorage.setItem("probe_traffic_scope", s)
    } catch {}
  }

  const activePeriodConfig = COST_PERIODS.find((p) => p.key === costPeriod) ?? COST_PERIODS[0]

  // 计算统一折算后的总费用（默认人民币 CNY，或后台设置货币）
  let totalConvertedCost = 0
  let payingCount = 0
  const originalCurrencyTotals: Record<string, number> = {}

  for (const n of nodes) {
    if (typeof n.price === "number" && n.price > 0) {
      payingCount++
      const mCost = monthlyCost(n.price, n.billing_cycle || "monthly")
      const periodCost = mCost * activePeriodConfig.multiplier
      const nodeCur = n.currency || "CNY"
      
      originalCurrencyTotals[nodeCur] = (originalCurrencyTotals[nodeCur] || 0) + periodCost
      // 统一折算至目标货币单位 (如 CNY)
      const convertedCost = convertCurrency(periodCost, nodeCur, targetCurrency)
      totalConvertedCost += convertedCost
    }
  }

  // 构建详细 Tooltip
  const originalParts = Object.keys(originalCurrencyTotals).map(
    (cur) => money(originalCurrencyTotals[cur], cur),
  )
  const tooltipOriginal = originalParts.length > 0 ? originalParts.join(" + ") : "免费"
  const costTooltip = `折合${targetCurrency === "CNY" ? "人民币" : targetCurrency} · 原币种合计: ${tooltipOriginal} (共 ${payingCount} 台计费服务器)`

  // 流量数据
  const todayRx = sum((n) => n.day_rx)
  const todayTx = sum((n) => n.day_tx)
  const todayTotal = todayRx + todayTx

  const totalRx = sum((n) => n.total_rx)
  const totalTx = sum((n) => n.total_tx)
  const allTotal = totalRx + totalTx

  const activeTrafficTotal = trafficScope === "today" ? todayTotal : allTotal
  const activeTrafficRx = trafficScope === "today" ? todayRx : totalRx
  const activeTrafficTx = trafficScope === "today" ? todayTx : totalTx

  // 网速数据
  const history = speedHistory.get(group) ?? []
  const now = history.at(-1) ?? { rx: 0, tx: 0 }
  const totalSpeed = now.rx + now.tx

  return (
    <div
      className={cn(
        "grid grid-cols-2 gap-2 sm:gap-3",
        showPrice ? "lg:grid-cols-4" : "lg:grid-cols-3",
      )}
    >
      {/* 1. 节点状态 */}
      <Tile icon={Server} label="节点">
        <div className="tnum mt-1 text-xl sm:text-2xl font-bold font-mono tracking-tight">
          {online.length} <span className="text-muted-foreground/60 text-lg font-normal">/</span> {nodes.length}
        </div>
        <div className="mt-auto pt-1 text-[11px] sm:text-xs text-muted-foreground truncate">
          {nodes.length - online.length > 0 ? (
            <span className="text-rose-500/90 dark:text-rose-400 font-medium">
              {nodes.length - online.length} 台离线
            </span>
          ) : (
            <span className="text-emerald-600 dark:text-emerald-400">全部在线</span>
          )}
        </div>
      </Tile>

      {/* 2. 服务器总费用 (药丸切换 + 统一货币计算) */}
      {showPrice && (
        <Tile
          icon={CreditCard}
          label={<><span className="hidden sm:inline">服务器</span>费用</>}
          right={
            <div className="inline-flex items-center rounded-full bg-muted/70 p-0.5 border border-border/40 text-[9px] sm:text-[10px] shrink-0">
              {COST_PERIODS.map((p) => (
                <button
                  key={p.key}
                  type="button"
                  onClick={() => handleCostPeriodChange(p.key)}
                  className={cn(
                    "cursor-pointer rounded-full px-1.5 py-0.5 sm:px-2 font-medium leading-none transition-all",
                    costPeriod === p.key
                      ? "bg-background font-semibold text-foreground shadow-xs ring-1 ring-border/50"
                      : "text-muted-foreground hover:text-foreground",
                  )}
                  title={`按${p.title}统计总费用`}
                >
                  {p.label}
                </button>
              ))}
            </div>
          }
        >
          <div
            className="tnum mt-1 truncate text-xl sm:text-2xl font-bold font-mono tracking-tight text-foreground flex items-baseline gap-1"
            title={costTooltip}
          >
            <span>{money(totalConvertedCost, targetCurrency)}</span>
            <span className="text-[11px] sm:text-xs font-normal text-muted-foreground">
              {activePeriodConfig.unit}
            </span>
          </div>
          <div className="mt-auto pt-1 text-[11px] sm:text-xs text-muted-foreground truncate" title={costTooltip}>
            {payingCount > 0 ? (
              <span>
                {payingCount} 台计费
                <span className="hidden sm:inline"> · 折合{targetCurrency === "CNY" ? "人民币" : targetCurrency}</span>
              </span>
            ) : (
              "全部免费"
            )}
          </div>
        </Tile>
      )}

      {/* 3. 流量统计 (响应式标题 + 今日/累计药丸切换) */}
      <Tile
        icon={ArrowDownUp}
        label={<>流量<span className="hidden sm:inline">统计</span></>}
        right={
          <div className="inline-flex items-center rounded-full bg-muted/70 p-0.5 border border-border/40 text-[9px] sm:text-[10px] shrink-0">
            {(
              [
                { key: "today", label: "今日" },
                { key: "total", label: "累计" },
              ] as const
            ).map((s) => (
              <button
                key={s.key}
                type="button"
                onClick={() => handleTrafficScopeChange(s.key)}
                className={cn(
                  "cursor-pointer rounded-full px-1.5 py-0.5 sm:px-2 font-medium leading-none transition-all",
                  trafficScope === s.key
                    ? "bg-background font-semibold text-foreground shadow-xs ring-1 ring-border/50"
                    : "text-muted-foreground hover:text-foreground",
                )}
                title={`查看${s.label}流量`}
              >
                {s.label}
              </button>
            ))}
          </div>
        }
      >
        <div className="tnum mt-1 text-xl sm:text-2xl font-bold font-mono tracking-tight">
          {bytes(activeTrafficTotal)}
        </div>
        <div
          className="mt-auto pt-1 text-[11px] sm:text-xs text-muted-foreground flex items-center gap-1.5 whitespace-nowrap"
          title={`${trafficScope === "today" ? "今日" : "累计"}下载: ${bytes(activeTrafficRx)} · 上传: ${bytes(activeTrafficTx)}`}
        >
          <span>↓ {shortUnit(activeTrafficRx)}</span>
          <span className="text-muted-foreground/40">·</span>
          <span>↑ {shortUnit(activeTrafficTx)}</span>
        </div>
      </Tile>

      {/* 4. 实时网速 (响应式标题 + 紧凑速率 + 曲线波动) */}
      <Tile icon={Gauge} label={<><span className="hidden sm:inline">实时</span>网速</>}>
        <div className="tnum mt-1 text-xl sm:text-2xl font-bold font-mono tracking-tight">
          {rate(totalSpeed)}
        </div>
        <div className="mt-auto flex flex-col justify-end pt-1">
          <div
            className="text-[11px] sm:text-xs text-muted-foreground flex items-center gap-1.5 whitespace-nowrap"
            title={`实时下载: ${rate(now.rx)} · 实时上传: ${rate(now.tx)}`}
          >
            <span>↓ {shortSpeed(now.rx)}</span>
            <span className="text-muted-foreground/40">·</span>
            <span>↑ {shortSpeed(now.tx)}</span>
          </div>
          <Spark
            series={[
              { values: history.map((s) => s.rx), className: "text-foreground" },
              { values: history.map((s) => s.tx), className: "text-muted-foreground" },
            ]}
          />
        </div>
      </Tile>
    </div>
  )
}
