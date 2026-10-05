import { lazy, Suspense, useCallback, useEffect, useState, useSyncExternalStore } from "react"
import { Moon, Sun, Wrench } from "lucide-react"

import { NodeCard, type LatencyProbe, type LatencyWindow, type VisibilitySettings } from "@/components/NodeCard"
import { Summary } from "@/components/Summary"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { api, groupsOf, useNodes, type Node } from "@/lib/api"

type Me = { authed: boolean; github: boolean; site_name: string; public_page: boolean }

// Split out because recharts is most of this bundle and the list page draws no
// chart. The landing page is 242 kB rather than 629 kB (77 kB gzipped against
// 188 kB), with the rest fetched immediately after it paints.
const loadDetail = () => import("@/components/NodeDetail").then((m) => ({ default: m.NodeDetail }))
const NodeDetail = lazy(loadDetail)

// `/node/{id}` is a real page: it survives a reload, can be linked to, and back
// leaves the detail view rather than the site. The hub serves index.html for any
// unknown path, so no server-side route is required.
function useNodeRoute() {
  const read = () => {
    const match = location.pathname.match(/^\/node\/(\d+)/)
    return match ? Number(match[1]) : null
  }
  const [id, setId] = useState(read)
  useEffect(() => {
    const sync = () => setId(read())
    addEventListener("popstate", sync)
    return () => removeEventListener("popstate", sync)
  }, [])
  return [
    id,
    (next: number | null) => {
      history.pushState({}, "", next === null ? "/" : `/node/${next}`)
      setId(next)
      scrollTo(0, 0)
    },
  ] as const
}

const DARK_MEDIA = matchMedia("(prefers-color-scheme: dark)")

/**
 * The visitor's own choice, or the system's while there is none. Only the toggle
 * writes the choice down: persisting the system's answer on load would pin it,
 * leaving a visitor who never touched the toggle in whichever mode their system
 * happened to be in that day. The panel at `/admin/` shares this key on one
 * origin, so it has to hold to the same rule -- one app writing on load pins the
 * others.
 *
 * The system's answer is subscribed to rather than copied into state: a flip
 * landing between the first render and the effect that would have attached the
 * listener is otherwise never heard, and the next one is a day away.
 */
function useTheme() {
  const [saved, setSaved] = useState(() => localStorage.getItem("theme"))
  const system = useSyncExternalStore(
    (notify) => {
      DARK_MEDIA.addEventListener("change", notify)
      return () => DARK_MEDIA.removeEventListener("change", notify)
    },
    () => DARK_MEDIA.matches,
  )
  const dark = saved ? saved === "dark" : system

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark)
  }, [dark])

  return [
    dark,
    () => {
      const next = dark ? "light" : "dark"
      localStorage.setItem("theme", next)
      setSaved(next)
    },
  ] as const
}

export default function App() {
  const [dark, toggleTheme] = useTheme()
  const [me, setMe] = useState<Me | null>(null)
  const [meError, setMeError] = useState("")
  const { nodes, error, closed } = useNodes()
  const [open, go] = useNodeRoute()
  // The list's group tab, held here so it survives a visit to a node's page.
  const [group, setGroup] = useState<string | null>(null)

  const loadMe = useCallback(() => {
    return api<Me>("/me")
      .then((next) => { setMe(next); setMeError("") })
      .catch((e: Error) => setMeError(e.message))
  }, [])

  useEffect(() => {
    loadMe()
    // Warmed here rather than left to Suspense, which requests the chunk only
    // once a render reaches the detail view, itself waiting on /me. Without this
    // the split trades its first paint for a full-page skeleton over the first
    // node opened: 2.6s click-to-chart on 4G against 1.4s unsplit, 1.7s warm.
    void loadDetail()
  }, [loadMe])

  // The status page was closed while this tab was open. `me` holds whatever it
  // reported at load, so it is re-queried; the effect below then directs an
  // anonymous visitor to the panel rather than leaving them on a list that
  // stopped updating with only a red line to explain it.
  useEffect(() => {
    if (closed) void loadMe()
  }, [closed, loadMe])

  useEffect(() => {
    if (me && !me.public_page && !me.authed) location.href = "/admin/"
  }, [me])

  const [probeStatus, setProbeStatus] = useState<{
    is_admin?: boolean
    settings: {
      public_show_price: boolean
      public_show_expiry: boolean
      public_show_traffic_limit: boolean
      total_cost_currency?: string
    }
    latencies: Record<string, LatencyProbe[]>
  } | null>(null)

  const [latencyWindow, setLatencyWindow] = useState<LatencyWindow>(() => {
    try {
      return (localStorage.getItem("probe_latency_window") as LatencyWindow) || "1h"
    } catch {
      return "1h"
    }
  })

  const handleLatencyWindowChange = useCallback((w: LatencyWindow) => {
    setLatencyWindow(w)
    try {
      localStorage.setItem("probe_latency_window", w)
    } catch {}
  }, [])

  const loadProbeStatus = useCallback(() => {
    fetch("/api/proxy/probe/public-status")
      .then((r) => r.json())
      .then((data) => {
        if (data.ok) {
          setProbeStatus(data)
        }
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    loadProbeStatus()
    const timer = setInterval(loadProbeStatus, 15000)
    return () => clearInterval(timer)
  }, [loadProbeStatus])

  const isTrueAdmin = Boolean(probeStatus?.is_admin)
  const visibilitySettings: VisibilitySettings = {
    // 续费价格：公开展示开关开启或超级管理员登录时展示
    show_price: Boolean(probeStatus ? (probeStatus.settings?.public_show_price || isTrueAdmin) : true),
    show_expiry: Boolean(probeStatus?.settings?.public_show_expiry),
    show_traffic_limit: Boolean(probeStatus?.settings?.public_show_traffic_limit),
    is_admin: isTrueAdmin,
  }

  const sorted = [...(nodes ?? [])].sort((a, b) => a.sort - b.sort || a.id - b.id)
  const selected = sorted.find((n) => n.id === open)

  // `/node/{id}` is a page people bookmark and share, so the tab needs the node's
  // name. The site name rather than a fixed string, since the hub lets an operator
  // rename the site.
  useEffect(() => {
    document.title = [selected?.name, me?.site_name || "Monitor"].filter(Boolean).join(" · ")
  }, [selected?.name, me?.site_name])

  // Only while there is nothing else to show. Once `me` has loaded, a later
  // failure belongs beside the page rather than over it.
  if (!me) return (
    <div className="grid min-h-svh place-items-center p-6 text-sm text-muted-foreground">
      {meError ? <div className="space-y-3 text-center"><p role="alert">加载失败：{meError}</p><Button onClick={loadMe}>重试</Button></div> : "加载中…"}
    </div>
  )

  // The status page is closed and nobody is signed in: redirect to the panel.
  if (!me.public_page && !me.authed) return null

  return (
    <div className="min-h-svh">
      <header className="sticky top-0 z-10 border-b bg-background/80 backdrop-blur">
        <div className="mx-auto flex max-w-[1400px] items-center gap-3 px-4 py-3 sm:px-6">
          {/* The site name is the way back to the list, so a node page needs
              no back button of its own. */}
          <button className="font-semibold transition-opacity hover:opacity-70" onClick={() => go(null)}>
            {me.site_name || "Monitor"}
          </button>
          <div className="flex-1" />
          {/* The panel is a separate app built into the hub, not part of this
              theme, so this is a navigation rather than a route. */}
          <Button variant="ghost" size="sm" asChild>
            <a href="/admin/">
              <Wrench /> {me.authed ? "进入后台" : "登录"}
            </a>
          </Button>
          <Button variant="ghost" size="icon" onClick={toggleTheme} title="切换主题">
            {dark ? <Sun /> : <Moon />}
          </Button>
        </div>
      </header>

      <main className="mx-auto max-w-[1400px] space-y-5 px-4 py-4 sm:px-6">
        {error && <p className="text-sm text-destructive">{error}</p>}

        {open !== null ? (
          !nodes ? (
            <Skeleton className="h-96" />
          ) : selected ? (
            <Suspense fallback={<Skeleton className="h-96" />}>
              <NodeDetail node={selected} visibilitySettings={visibilitySettings} />
            </Suspense>
          ) : (
            <p className="py-16 text-center text-sm text-muted-foreground">
              节点不存在或未公开。<button className="underline" onClick={() => go(null)}>返回列表</button>
            </p>
          )
        ) : !nodes ? (
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-72" />
            ))}
          </div>
        ) : (
          <NodeList
            nodes={sorted}
            group={group}
            onGroup={setGroup}
            onOpen={go}
            latencies={probeStatus?.latencies}
            visibilitySettings={visibilitySettings}
            latencyWindow={latencyWindow}
            onLatencyWindowChange={handleLatencyWindowChange}
            targetCurrency={probeStatus?.settings?.total_cost_currency || "CNY"}
          />
        )}
      </main>
    </div>
  )
}

// Group tabs appear only once the operator has grouped something, so a hub
// without groups keeps the page it always had. The summary follows the tab.
function NodeList({
  nodes,
  group,
  onGroup,
  onOpen,
  latencies,
  visibilitySettings,
  latencyWindow,
  onLatencyWindowChange,
  targetCurrency,
}: {
  nodes: Node[]
  /** null is every node, "" the ungrouped. */
  group: string | null
  onGroup: (group: string | null) => void
  onOpen: (id: number) => void
  latencies?: Record<string, LatencyProbe[]>
  visibilitySettings?: VisibilitySettings
  latencyWindow?: LatencyWindow
  onLatencyWindowChange?: (w: LatencyWindow) => void
  targetCurrency?: string
}) {
  const groups = groupsOf(nodes)
  const ungrouped = nodes.filter((n) => !n.group).length
  // A tab that has since emptied or been renamed -- 未分组 included -- falls back
  // to every node rather than to an empty page, and is forgotten, so a later
  // group of the same name does not take the page over.
  const current = group === null || (group === "" ? ungrouped > 0 : groups.includes(group)) ? group : null
  useEffect(() => {
    if (current !== group) onGroup(current)
  }, [current, group, onGroup])
  const shown = current === null ? nodes : nodes.filter((n) => (n.group ?? "") === current)
  const tabs = [
    [null, "全部", nodes.length] as const,
    ...groups.map((g) => [g, g, nodes.filter((n) => n.group === g).length] as const),
    ...(ungrouped ? [["", "未分组", ungrouped] as const] : []),
  ]
  return (
    <>
      {groups.length > 0 && (
        <div role="group" aria-label="分组" className="-mx-1 flex gap-1 overflow-x-auto px-1 pb-1">
          {tabs.map(([value, label, count]) => (
            <Button
              // Group names are free text, so they carry a prefix no key of
              // the 全部 tab can share.
              key={value === null ? "*" : `=${value}`}
              aria-pressed={current === value}
              size="sm"
              variant={current === value ? "secondary" : "ghost"}
              className="shrink-0"
              onClick={() => onGroup(value)}
            >
              {label}
              <span className="tnum text-muted-foreground">{count}</span>
            </Button>
          ))}
        </div>
      )}
      <Summary nodes={shown} group={current} visibilitySettings={visibilitySettings} targetCurrency={targetCurrency} />
      {nodes.length === 0 ? (
        <p className="py-16 text-center text-sm text-muted-foreground">还没有节点</p>
      ) : (
        <div className="grid items-start gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {shown.map((n) => (
            <NodeCard
              key={n.id}
              node={n}
              onOpen={() => onOpen(n.id)}
              latencies={latencies?.[String(n.id)]}
              visibilitySettings={visibilitySettings}
              latencyWindow={latencyWindow}
              onLatencyWindowChange={onLatencyWindowChange}
            />
          ))}
        </div>
      )}
    </>
  )
}
