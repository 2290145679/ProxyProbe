import type { CSSProperties } from "react"
import { ArrowDown, ArrowUp } from "lucide-react"
import {
  siAlmalinux, siAlpinelinux, siArchlinux, siCentos, siDebian, siFedora, siLinux, siOpensuse, siRedhat,
  siRockylinux, siUbuntu, type SimpleIcon,
} from "simple-icons"

import { Badge } from "@/components/ui/badge"
import { Card } from "@/components/ui/card"
import { Meter } from "@/components/Meter"
import type { Node } from "@/lib/api"
import { bytes, daysUntil, FOREVER, osName, pair, percent, rate, uptime } from "@/lib/format"
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

// Matched against the whole release name, since "Red Hat Enterprise Linux" and
// "Raspbian GNU/Linux" do not lead with one word to key on. The distributions a
// VPS ships with; the rest take the penguin. Each logo costs 1-6 KB of entry
// bundle, so the list stays at what hosts offer.
const DISTROS: [string, SimpleIcon][] = [
  ["debian", siDebian], ["raspbian", siDebian], ["ubuntu", siUbuntu], ["alpine", siAlpinelinux],
  ["centos", siCentos], ["rocky", siRockylinux], ["almalinux", siAlmalinux], ["red hat", siRedhat],
  ["fedora", siFedora], ["arch", siArchlinux], ["opensuse", siOpensuse],
]

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

/**
 * The distribution's logo in its brand colour. Mixed toward white on the dark
 * theme, where AlmaLinux's black and CentOS's navy would otherwise vanish.
 */
function OsIcon({ os }: { os: string }) {
  const name = os.toLowerCase()
  const icon = DISTROS.find(([key]) => name.includes(key))?.[1] ?? siLinux
  return (
    <svg
      viewBox="0 0 24 24"
      aria-hidden
      style={{ "--brand": `#${icon.hex}` } as CSSProperties}
      className="size-3 shrink-0 fill-(--brand) dark:fill-[color-mix(in_oklab,var(--brand)_60%,white)]"
    >
      <path d={icon.path} />
    </svg>
  )
}

// Traffic uses the plan's own counting rule, so the bar matches the quota the
// node is billed against.
function trafficFoot(node: Node) {
  return node.traffic_limit > 0
    ? pair(monthUsage(node), node.traffic_limit)
    : `${bytes(monthUsage(node))} / ${FOREVER}`
}

export type LatencyProbe = {
  task_id: number
  name: string
  latency: number | null
  loss_rate?: number
  history?: (number | null)[]
  ts?: number
}

function getTaskDotColor(name: string, index: number): string {
  if (name.includes("联通")) return "bg-rose-500"
  if (name.includes("电信")) return "bg-blue-500"
  if (name.includes("移动")) return "bg-emerald-500"
  const fallbacks = [
    "bg-sky-500",
    "bg-amber-500",
    "bg-purple-500",
    "bg-teal-500",
    "bg-indigo-500",
    "bg-pink-500",
  ]
  return fallbacks[index % fallbacks.length]
}

function getLatencyBarColor(val: number | null | undefined): string {
  if (val === null || val === undefined) return "bg-muted/40 dark:bg-muted/20"
  if (val < 0) return "bg-rose-500"
  if (val <= 80) return "bg-emerald-500"
  if (val <= 150) return "bg-emerald-400"
  if (val <= 250) return "bg-amber-400"
  return "bg-rose-500"
}

function getLossBarColor(val: number | null | undefined): string {
  if (val === null || val === undefined) return "bg-muted/40 dark:bg-muted/20"
  if (val < 0) return "bg-rose-500"
  return "bg-emerald-500"
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
}: {
  node: Node
  onOpen: () => void
  latencies?: LatencyProbe[]
  visibilitySettings?: VisibilitySettings
}) {
  const m = node.metrics
  const showExpiry = Boolean(visibilitySettings?.is_admin || visibilitySettings?.show_expiry)
  const showTrafficLimit = Boolean(visibilitySettings?.is_admin || visibilitySettings?.show_traffic_limit)

  return (
    <Card
      onClick={onOpen}
      // min-w-0: a grid item sizes to its content unless told otherwise, and the
      // OS line below does not wrap, so on a phone the card would grow past its
      // column and scroll the page sideways. The truncate inside only takes effect
      // once the card is allowed to be narrower.
      className="min-w-0 cursor-pointer gap-0 p-4 transition-colors hover:border-ring"
      role="button"
      tabIndex={0}
      onKeyDown={(e) => (e.key === "Enter" || e.key === " ") && (e.preventDefault(), onOpen())}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex min-w-0 items-center gap-1.5">
            <h3 className="truncate font-medium">{node.name}</h3>
            <Country node={node} />
          </div>
          <p className="mt-1 flex min-w-0 items-center gap-1 text-xs text-muted-foreground">
            {node.os && <OsIcon os={node.os} />}
            <span className="truncate">
              {node.os ? osName(node.os) : "等待首次上报"}
              {node.virt && node.virt !== "none" ? ` · ${node.virt}` : ""}
              {node.arch ? ` · ${node.arch}` : ""}
            </span>
          </p>
        </div>
        {/* State right, identity left, one line each. */}
        <div className="flex shrink-0 flex-col items-end gap-1">
          <Status node={node} />
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

          {/* 探针卡片直观展示已配置的网络延迟与丢包率 */}
          {latencies && latencies.length > 0 && (() => {
            const isThreeNets = latencies.some((l) => /联通|电信|移动/.test(l.name))
            const subtitle = isThreeNets ? "三网" : "监控点"

            return (
              <div className="mt-3 grid grid-cols-2 gap-3 sm:gap-4 border-t border-border/40 pt-2.5 text-xs">
                {/* 延迟 */}
                <div className="flex flex-col min-w-0">
                  <div className="flex items-center justify-between text-muted-foreground mb-1.5 leading-none">
                    <span className="font-semibold text-foreground text-xs">延迟</span>
                    <span className="text-[11px] text-muted-foreground/80">{subtitle}</span>
                  </div>
                  <div className="flex flex-col gap-2">
                    {latencies.map((p, idx) => {
                      const hasData = typeof p.latency === "number"
                      const isTimeout = typeof p.latency === "number" && p.latency < 0
                      const lat = p.latency ?? 0
                      const tone = !hasData
                        ? "text-muted-foreground"
                        : isTimeout
                          ? "text-rose-600 dark:text-rose-400 font-bold"
                          : lat <= 80
                            ? "text-emerald-600 dark:text-emerald-400 font-bold"
                            : lat <= 150
                              ? "text-emerald-500 dark:text-emerald-400 font-bold"
                              : lat <= 250
                                ? "text-amber-600 dark:text-amber-400 font-bold"
                                : "text-rose-600 dark:text-rose-400 font-bold"

                      const paddedHistory = [
                        ...Array(Math.max(0, 20 - (p.history?.length || 0))).fill(null),
                        ...(p.history || []),
                      ].slice(-20)

                      return (
                        <div key={p.task_id} className="space-y-1">
                          <div className="flex items-center justify-between text-xs leading-none">
                            <div className="flex items-center gap-1.5 min-w-0">
                              <span className={cn("size-1.5 rounded-full shrink-0", getTaskDotColor(p.name, idx))} />
                              <span className="truncate text-muted-foreground text-[11px]">{p.name}</span>
                            </div>
                            <span className={cn("font-mono text-[11px] shrink-0", tone)}>
                              {!hasData ? "—" : isTimeout ? "超时" : `${lat} ms`}
                            </span>
                          </div>
                          <div className="flex items-center gap-[2px] h-1.5 w-full">
                            {paddedHistory.map((val, i) => (
                              <div
                                key={i}
                                className={cn(
                                  "h-full flex-1 rounded-[1px] transition-colors",
                                  getLatencyBarColor(val)
                                )}
                                title={
                                  val === null || val === undefined
                                    ? "无数据"
                                    : val < 0
                                      ? "超时 / 丢包"
                                      : `${val} ms`
                                }
                              />
                            ))}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>

                {/* 丢包 */}
                <div className="flex flex-col min-w-0">
                  <div className="flex items-center justify-between text-muted-foreground mb-1.5 leading-none">
                    <span className="font-semibold text-foreground text-xs">丢包</span>
                    <span className="text-[11px] text-muted-foreground/80">{subtitle}</span>
                  </div>
                  <div className="flex flex-col gap-2">
                    {latencies.map((p, idx) => {
                      const hasData = typeof p.latency === "number" || typeof p.loss_rate === "number"
                      const lossRate = p.loss_rate ?? 0
                      const lossTone = !hasData
                        ? "text-muted-foreground"
                        : lossRate === 0
                          ? "text-muted-foreground"
                          : lossRate < 10
                            ? "text-amber-600 dark:text-amber-400 font-bold"
                            : "text-rose-600 dark:text-rose-400 font-bold"

                      const paddedHistory = [
                        ...Array(Math.max(0, 20 - (p.history?.length || 0))).fill(null),
                        ...(p.history || []),
                      ].slice(-20)

                      return (
                        <div key={p.task_id} className="space-y-1">
                          <div className="flex items-center justify-between text-xs leading-none">
                            <div className="flex items-center gap-1.5 min-w-0">
                              <span className={cn("size-1.5 rounded-full shrink-0", getTaskDotColor(p.name, idx))} />
                              <span className="truncate text-muted-foreground text-[11px]">{p.name}</span>
                            </div>
                            <span className={cn("font-mono text-[11px] shrink-0", lossTone)}>
                              {!hasData ? "—" : `${lossRate.toFixed(1)}%`}
                            </span>
                          </div>
                          <div className="flex items-center gap-[2px] h-1.5 w-full">
                            {paddedHistory.map((val, i) => (
                              <div
                                key={i}
                                className={cn(
                                  "h-full flex-1 rounded-[1px] transition-colors",
                                  getLossBarColor(val)
                                )}
                                title={
                                  val === null || val === undefined
                                    ? "无数据"
                                    : val < 0
                                      ? "丢包"
                                      : `正常 (${val} ms)`
                                }
                              />
                            ))}
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>
              </div>
            )
          })()}
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
