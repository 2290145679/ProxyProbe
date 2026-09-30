import { useEffect, useRef, useState } from "react"
import { flushSync } from "react-dom"
import { BarChart3, Bell, Bot, CalendarClock, Check, CheckCircle, ChevronRight, Copy, CreditCard, Database, Download, Globe, GripVertical, KeyRound, Mail, Megaphone, PackageCheck, Pencil, Plus, Radio, RefreshCw, Rocket, Search, Send, Server, Settings, Shield, SlidersHorizontal, Sparkles, Trash2, Upload, Users, XCircle } from "lucide-react"
import { toast } from "sonner"
import { copyToClipboard } from "@/lib/clipboard"

import { ProxyDashboard } from "./ProxyDashboard"
import { ProxyNodes } from "./ProxyNodes"
import { ProxyUsers } from "./ProxyUsers"
import { ProxyRules } from "./ProxyRules"
import { LicenseManager } from "./LicenseManager"
import type { UpdateInfo } from "./UpdateDialog"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Switch } from "@/components/ui/switch"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import { addresses, api, badIfaceName, changes, currentIface, GIB, ifaceChoice, ifaceSpec, provisioningSite, trafficCorrection, upload, type IfaceChoice, type Node, type PingTask, type Source } from "@/lib/api"
import { bytes, CYCLES, FOREVER, money, uptime } from "@/lib/format"

// Counters the panel can correct after migration or an accounting error.
const TRAFFIC_FIELDS = [
  ["total_rx", "累计下行"],
  ["total_tx", "累计上行"],
  ["month_rx", "本月下行"],
  ["month_tx", "本月上行"],
] as const
const TRAFFIC_MODES: Record<string, string> = {
  sum: "上下行相加",
  max: "取较大值",
  up: "仅上行",
  down: "仅下行",
}

// Reordering uses the browser's view transitions, so displaced rows slide.
// Browsers without support jump instead.
function animate(update: () => void) {
  if (document.startViewTransition) document.startViewTransition(() => flushSync(update))
  else update()
}

async function copy(text: string) {
  const ok = await copyToClipboard(text)
  if (ok) {
    toast.success("已复制")
  } else {
    toast.error("复制失败，请手动选中文本复制")
  }
}

const SOURCES: Record<Source, string> = {
  manual: "手动填写",
  interface: "网卡地址",
  exit: "hub 看到的出口，不在节点网卡上（NAT 或代理）",
  connection: "hub 看到的连接地址",
}

// The address a node is reached by, one per family, each click-to-copy: pasting
// one into an ssh command is why they are shown. Where each came from is in the
// tooltip, keeping the column to addresses alone.
function Addresses({ node }: { node: Node }) {
  const list = addresses(node)
  if (!list.length) return <span className="text-sm text-muted-foreground">—</span>
  return (
    <div className="flex flex-col items-start gap-y-0.5">
      {list.map(({ address, source }) => (
        <button
          key={address}
          type="button"
          onClick={() => copy(address)}
          title={`${SOURCES[source]}。点击复制`}
          className="tnum group inline-flex items-center gap-1 text-sm hover:text-foreground"
        >
          {address}
          <Copy className="size-3 shrink-0 opacity-0 transition-opacity group-hover:opacity-100" />
        </button>
      ))}
    </div>
  )
}

// Name, address and country: what a node is looked up by, in every node list.
function searchNodes(nodes: Node[], query: string) {
  const needle = query.trim().toLowerCase()
  if (!needle) return nodes
  return nodes.filter((n) =>
    [n.name, n.ip, n.ipv4, n.ipv6, n.ipv4_pin, n.ipv6_pin, n.country].some((v) => v?.toLowerCase().includes(needle)))
}

function NodeSearch({ value, onChange, className = "" }: { value: string; onChange: (value: string) => void; className?: string }) {
  return (
    <div className={`relative ${className}`}>
      <Search className="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground" />
      <Input className="pl-8" placeholder="名称/地址/地区" aria-label="搜索服务器" value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  )
}

// Ticks nodes in a searchable grid. 全选 and 全不选 act on the rows in view, so a
// search narrows what they touch: search JP, then 全选. Offline nodes are dimmed
// but remain selectable.
function NodePicker({ nodes, chosen, onPick, disabled = false }: {
  nodes: Node[]
  chosen: Set<number>
  onPick: (list: Node[], on: boolean) => void
  disabled?: boolean
}) {
  const [query, setQuery] = useState("")
  // The unfiltered list's height, held as its floor: in a centred dialog a
  // shrinking list would move the search box out from under the cursor.
  const [listHeight, setListHeight] = useState(0)
  const visible = searchNodes(nodes, query)
  const visibleChosen = visible.filter((n) => chosen.has(n.id)).length
  return (
    <div className="rounded-lg border">
      <div className="flex items-center gap-1 border-b p-2">
        <NodeSearch className="min-w-0 flex-1" value={query} onChange={setQuery} />
        <Button size="sm" variant="ghost" className="px-2.5" disabled={disabled || visibleChosen === visible.length} onClick={() => onPick(visible, true)}>全选</Button>
        <Button size="sm" variant="ghost" className="px-2.5" disabled={disabled || visibleChosen === 0} onClick={() => onPick(visible, false)}>全不选</Button>
      </div>
      {/* Three columns keep a few dozen nodes within one scroll. */}
      <div
        ref={(el) => { if (el && !listHeight) setListHeight(el.offsetHeight) }}
        // Capped like the height itself, which a min-height would otherwise
        // override once the viewport shrinks.
        style={{ minHeight: listHeight ? `min(${listHeight}px, 16rem, 40dvh)` : undefined }}
        className="grid max-h-[min(16rem,40dvh)] grid-cols-2 content-start gap-0.5 overflow-y-auto p-1.5 sm:grid-cols-3"
      >
        {visible.map((n) => (
          <label key={n.id} title={n.name} className="flex min-w-0 cursor-pointer items-center gap-2 rounded-md px-2 py-1.5 text-sm hover:bg-muted">
            <input type="checkbox" checked={chosen.has(n.id)} disabled={disabled} onChange={(e) => onPick([n], e.target.checked)} className="shrink-0 accent-primary" />
            <span className={`truncate ${n.online ? "" : "text-muted-foreground"}`}>{n.name}</span>
            {n.country && <span className="ml-auto shrink-0 text-xs text-muted-foreground">{n.country}</span>}
          </label>
        ))}
        {!visible.length && (
          <p className="col-span-full p-2 text-xs text-muted-foreground">{nodes.length ? "没有匹配的服务器" : "先添加服务器"}</p>
        )}
      </div>
    </div>
  )
}

// Every command the panel hands out. break-all because a token has no spaces to
// wrap at.
function Command({ className = "", children }: { className?: string; children: React.ReactNode }) {
  return (
    <pre className={`overflow-auto whitespace-pre-wrap break-all rounded-lg border bg-muted/40 p-3 text-xs leading-relaxed select-all ${className}`}>
      {children}
    </pre>
  )
}

function Field({ label, hint, className = "", children }: { label: string; hint?: string; className?: string; children: React.ReactNode }) {
  return (
    <div className={`space-y-2 ${className}`}>
      <Label className="text-sm font-medium">{label}</Label>
      {children}
      {hint && <p className="text-xs leading-relaxed text-muted-foreground">{hint}</p>}
    </div>
  )
}

// A titled option with its control at the right. `toggle` makes the whole row a
// label, so a click anywhere flips the Switch it holds; `below` opens beneath it
// in the same card.
function OptionRow({ title, hint, toggle = false, below, children }: {
  title: React.ReactNode
  hint?: React.ReactNode
  toggle?: boolean
  below?: React.ReactNode
  children: React.ReactNode
}) {
  const Row = toggle ? "label" : "div"
  return (
    <div className="flex flex-col rounded-lg border bg-muted/30 text-sm">
      {/* flex-1: stretched by a grid, the row fills the card and stays clickable. */}
      <Row className={`flex flex-1 items-center justify-between gap-4 px-3 py-2.5 ${toggle ? "cursor-pointer" : ""}`}>
        <span>
          <span className="block font-medium">{title}</span>
          {hint && <span className="mt-0.5 block text-xs text-muted-foreground">{hint}</span>}
        </span>
        {children}
      </Row>
      {below && <div className="border-t px-3 pt-3 pb-3.5">{below}</div>}
    </div>
  )
}


function ConfirmDialog({ title, description, confirmLabel, busy = false, onClose, onConfirm, children }: {
  title: string
  description: string
  confirmLabel: string
  busy?: boolean
  onClose: () => void
  onConfirm: () => void
  children?: React.ReactNode
}) {
  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription className="leading-relaxed">{description}</DialogDescription>
        </DialogHeader>
        {children}
        <DialogFooter className="border-t pt-4">
          <Button variant="ghost" onClick={onClose}>取消</Button>
          <Button variant="destructive" onClick={onConfirm} disabled={busy}>{confirmLabel}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export type CoreOptions = {
  xray: boolean
  singbox: boolean
  realm: boolean
}

export const DEFAULT_CORE_OPTIONS: CoreOptions = {
  xray: true,
  singbox: true,
  realm: false,
}

export function coreFlags(cores: CoreOptions): string[] {
  if (!cores.xray && !cores.singbox && !cores.realm) {
    return ["--no-proxy"]
  }
  const flags: string[] = []
  if (cores.xray) flags.push("--xray")
  else flags.push("--no-xray")

  if (cores.singbox) flags.push("--singbox")
  else flags.push("--no-singbox")

  if (cores.realm) flags.push("--realm")
  else flags.push("--no-realm")

  return flags
}

function scriptCommand(site: string, args: (site: string) => string[]) {
  site = provisioningSite(site)
  return site && `curl -fsSL ${site}/install.sh | sh -s -- ${args(site).join(" ")}`
}

function ifaceArg(iface: string | undefined) {
  return iface === undefined ? [] : [`--iface ${iface || "''"}`]
}

function installCommand(
  site: string,
  token: string,
  seconds: number,
  iface: string | undefined,
  cores: CoreOptions = DEFAULT_CORE_OPTIONS,
  noMonitor: boolean = false,
) {
  site = provisioningSite(site)
  if (noMonitor) {
    const flags = coreFlags(cores)
    return site && `curl -fsSL ${site}/proxy-agent.sh | bash -s -- --server ${site}${site.startsWith("http://") ? " --insecure" : ""} --token ${token} ${flags.join(" ")}`
  }
  return scriptCommand(site, (s) => [
    `--server ${s}`,
    ...(s.startsWith("http://") ? ["--insecure"] : []),
    `--token ${token}`,
    `--interval ${seconds}`,
    ...ifaceArg(iface),
    ...coreFlags(cores),
  ])
}

function registerCommand(
  site: string,
  key: string,
  iface: string | undefined,
  cores: CoreOptions = DEFAULT_CORE_OPTIONS,
  noMonitor: boolean = false,
) {
  site = provisioningSite(site)
  if (noMonitor) {
    const flags = coreFlags(cores)
    return scriptCommand(site, (s) => [
      `--server ${s}`,
      ...(s.startsWith("http://") ? ["--insecure"] : []),
      `--register ${key}`,
      `--no-monitor`,
      ...flags,
    ])
  }
  return scriptCommand(site, (s) => [
    `--server ${s}`,
    ...(s.startsWith("http://") ? ["--insecure"] : []),
    `--register ${key}`,
    ...ifaceArg(iface),
    ...coreFlags(cores),
  ])
}

function uninstallCommand(site: string) {
  return scriptCommand(site, () => ["--uninstall"])
}

function InstallModeSelector({
  onlyProxy,
  onChange,
}: {
  onlyProxy: boolean
  onChange: (onlyProxy: boolean) => void
}) {
  return (
    <div className="rounded-lg border bg-muted/20 p-3 space-y-2">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold">安装模式</span>
          {onlyProxy ? (
            <Badge variant="secondary" className="text-[10px] px-1.5 bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border-indigo-500/20 font-medium">
              纯代理模式 (免装探针)
            </Badge>
          ) : (
            <Badge variant="secondary" className="text-[10px] px-1.5 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20 font-medium">
              全功能模式 (探针监控 + 代理节点)
            </Badge>
          )}
        </div>
        <div className="flex items-center gap-1.5">
          <span className="text-[11px] text-muted-foreground font-medium">免装探针</span>
          <Switch checked={onlyProxy} onCheckedChange={onChange} />
        </div>
      </div>
      <p className="text-[11px] text-muted-foreground leading-relaxed">
        {onlyProxy
          ? "仅部署代理核心与节点管理守护，零系统监控，不采集 CPU/内存/进程，适合低配玩具机或注重隐私者。"
          : "同时部署探针监控与代理核心，提供实时 CPU/内存/网络/磁盘硬件性能监控与多协议节点纳管。"}
      </p>
    </div>
  )
}

function CoreOptionsSelector({
  cores,
  onChange,
  onlyProxy = false,
}: {
  cores: CoreOptions
  onChange: (cores: CoreOptions) => void
  onlyProxy?: boolean
}) {
  const isNone = !cores.xray && !cores.singbox && !cores.realm

  return (
    <div className="space-y-2.5">
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-semibold uppercase tracking-wider text-muted-foreground">
          代理核心安装选项
        </h4>
        {isNone && (
          <Badge variant="outline" className="text-[10px] text-amber-600 dark:text-amber-400 border-amber-500/30 bg-amber-500/10">
            {onlyProxy ? "警告：纯代理模式请至少勾选一种代理核心" : "仅探针监控（不安装任何代理核心）"}
          </Badge>
        )}
      </div>

      <div className="space-y-2">
        <OptionRow
          title="Xray-Core 核心"
          hint="支持 VLESS (Reality/XHTTP)、VMess、Trojan、Shadowsocks 等主流协议"
          toggle
        >
          <Switch
            checked={cores.xray}
            onCheckedChange={(v) => onChange({ ...cores, xray: v })}
          />
        </OptionRow>

        <OptionRow
          title="Sing-box 核心"
          hint="支持 Hysteria 2、TUIC 等高性能 UDP 协议"
          toggle
        >
          <Switch
            checked={cores.singbox}
            onCheckedChange={(v) => onChange({ ...cores, singbox: v })}
          />
        </OptionRow>

        <OptionRow
          title="Realm 端口转发核心"
          hint="支持 TCP/UDP 双向转发，用于中转落地节点搭建"
          toggle
        >
          <Switch
            checked={cores.realm}
            onCheckedChange={(v) => onChange({ ...cores, realm: v })}
          />
        </OptionRow>
      </div>

      <p className="text-[11px] text-muted-foreground leading-relaxed">
        💡 提示：若该服务器仅用来加入探针监控、不用作代理节点，可将上述核心全部关闭，生成的安装指令将仅部署监控探针。
      </p>
    </div>
  )
}

function CreateNode({
  site,
  onClose,
  onSaved,
}: {
  site: string
  onClose: () => void
  onSaved: () => void
}) {
  const [name, setName] = useState("")
  const [cores, setCores] = useState<CoreOptions>(DEFAULT_CORE_OPTIONS)
  const [onlyProxy, setOnlyProxy] = useState(false)
  const [saving, setSaving] = useState(false)
  const [createdInfo, setCreatedInfo] = useState<{ id: number; token: string; name: string } | null>(null)

  const [copied, setCopied] = useState(false)

  const handleCopy = async () => {
    if (!command) return
    await copy(command)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  async function save(e: React.FormEvent) {
    e.preventDefault()
    if (!name.trim()) return toast.error("请填写服务器名称")
    setSaving(true)
    try {
      const res = await api<{ id: number }>("/nodes", {
        method: "POST",
        body: JSON.stringify({ name: name.trim() }),
      })
      toast.success("服务器已创建！")
      onSaved()
      try {
        const tokenRes = await api<{ token: string }>(`/nodes/${res.id}/token`, { method: "POST" })
        setCreatedInfo({ id: res.id, token: tokenRes.token, name: name.trim() })
      } catch {
        onClose()
      }
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const command = createdInfo
    ? installCommand(site, createdInfo.token, 1, undefined, cores, onlyProxy)
    : ""

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent onOpenAutoFocus={(e) => e.preventDefault()} className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{createdInfo ? `部署服务器「${createdInfo.name}」` : "添加服务器"}</DialogTitle>
          <DialogDescription>
            {createdInfo
              ? "服务器已成功添加。请在目标服务器终端复制并执行以下命令完成部署："
              : "配置服务器名称与安装模式，按需选择代理核心："}
          </DialogDescription>
        </DialogHeader>

        {!createdInfo ? (
          <form className="space-y-4" onSubmit={save}>
            <Field label="服务器名称">
              <Input
                autoFocus
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="例如：香港 · 甲商家 或 HK-Node-01"
              />
            </Field>

            <InstallModeSelector onlyProxy={onlyProxy} onChange={setOnlyProxy} />
            <CoreOptionsSelector cores={cores} onChange={setCores} onlyProxy={onlyProxy} />

            <DialogFooter className="border-t pt-4">
              <Button type="button" variant="ghost" onClick={onClose}>取消</Button>
              <Button type="submit" disabled={saving}>
                {saving ? "创建中..." : "创建并生成安装命令"}
              </Button>
            </DialogFooter>
          </form>
        ) : (
          <div className="space-y-4">
            <InstallModeSelector onlyProxy={onlyProxy} onChange={setOnlyProxy} />
            <CoreOptionsSelector cores={cores} onChange={setCores} onlyProxy={onlyProxy} />

            <div className="space-y-2 border-t pt-3">
              <div className="flex items-center justify-between">
                <h4 className="text-xs font-medium text-muted-foreground">一键安装命令</h4>
                <button
                  type="button"
                  onClick={handleCopy}
                  className="text-xs text-primary hover:underline flex items-center gap-1 font-medium transition-colors"
                >
                  {copied ? <Check className="size-3.5 text-emerald-500" /> : <Copy className="size-3.5" />}
                  {copied ? <span className="text-emerald-600 dark:text-emerald-400 font-semibold">已复制命令</span> : "点击复制"}
                </button>
              </div>
              <div 
                className="relative group cursor-pointer"
                onClick={handleCopy}
                title="点击直接复制命令"
              >
                <Command className="max-h-40 min-h-24 hover:border-primary/50 transition-colors select-all">
                  {command}
                </Command>
              </div>
            </div>

            <DialogFooter className="border-t pt-4">
              <Button variant="ghost" onClick={onClose}>完成</Button>
              <Button 
                onClick={handleCopy}
                className={copied ? "bg-emerald-600 hover:bg-emerald-700 text-white font-medium" : ""}
              >
                {copied ? <Check className="size-4 text-white" /> : <Copy className="size-4" />}
                {copied ? "已复制安装命令" : "复制安装命令"}
              </Button>
            </DialogFooter>
          </div>
        )}
      </DialogContent>
    </Dialog>
  )
}

function NodeForm({ node, onClose, onSaved }: {
  node: Node
  onClose: () => void
  onSaved: () => void
}) {
  const [form, setForm] = useState(node)
  const [limitGib, setLimitGib] = useState(String(node.traffic_limit / GIB || ""))
  const [saving, setSaving] = useState(false)
  const gib = (bytes: number) => String(Number((bytes / GIB).toFixed(3)))
  const [traffic, setTraffic] = useState(() =>
    Object.fromEntries(TRAFFIC_FIELDS.map(([k]) => [k, gib(node[k])])) as Record<string, string>,
  )
  // Compared as entered rather than as bytes: rounding to GB would read as an
  // edit and zero a node that has transferred a few MB.
  const pristine = useRef(traffic)
  const set = <K extends keyof Node>(k: K, v: Node[K]) => setForm((f) => ({ ...f, [k]: v }))
  // What each address box falls back to when left empty.
  const automatic = (v6: boolean) =>
    addresses({ ...node, ipv4_pin: "", ipv6_pin: "" }).find((a) => a.address.includes(":") === v6)?.address ?? "无"

  async function save() {
    if (!form.name.trim()) return toast.error("请填写服务器名称")
    const patch = changes(node, {
      name: form.name.trim(),
      public: form.public,
      remark: form.remark,
      traffic_mode: form.traffic_mode,
      traffic_limit: Math.round(Number(limitGib) * GIB),
      traffic_reset_day: Math.min(31, Math.max(1, Math.round(Number(form.traffic_reset_day) || 1))),
      notify: !!form.notify,
      ipv4_pin: (form.ipv4_pin ?? "").trim(),
      ipv6_pin: (form.ipv6_pin ?? "").trim(),
      country_pin: (form.country_pin ?? "").trim().toUpperCase(),
    })
    const correction = trafficCorrection(pristine.current, traffic)
    if ([patch.traffic_limit, ...Object.values(correction)].some((v) => v !== undefined && (!Number.isSafeInteger(v) || v < 0))) {
      return toast.error("流量必须是有效的非负数，且不能超出精确计数范围")
    }
    setSaving(true)
    try {
      // The correction belongs to the new reset period, so its day is saved
      // first.
      if (Object.keys(patch).length) {
        await api(`/nodes/${node.id}`, { method: "PUT", body: JSON.stringify(patch) })
      }
      if (Object.keys(correction).length) {
        await api(`/nodes/${node.id}/traffic`, {
          method: "PUT",
          body: JSON.stringify(correction),
        })
      }
      toast.success("服务器设置已保存")
      onClose()
      onSaved()
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent onOpenAutoFocus={(e) => e.preventDefault()} className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{node.name}</DialogTitle>
        </DialogHeader>
        <div className="space-y-6">
          <section className="space-y-4">
            <div className="grid gap-4 sm:grid-cols-2">
              <Field label="名称">
                <Input value={form.name} onChange={(e) => set("name", e.target.value)} />
              </Field>
              <Field label="备注">
                <Input value={form.remark ?? ""} onChange={(e) => set("remark", e.target.value)} placeholder="商家、用途，仅管理员可见" />
              </Field>
            </div>
            <div className="grid gap-3 sm:grid-cols-2">
              <OptionRow title="公开显示" hint="关闭后只在管理后台可见" toggle>
                <Switch checked={form.public} onCheckedChange={(v) => set("public", v)} />
              </OptionRow>
              <OptionRow title="离线通知" hint="掉线超过宽限期、恢复时各推一条" toggle>
                <Switch checked={!!form.notify} onCheckedChange={(v) => set("notify", v)} />
              </OptionRow>
            </div>
          </section>
          <section className="space-y-3 border-t pt-5">
            <h3 className="text-sm font-medium">流量</h3>
            <div className="grid gap-4 sm:grid-cols-3">
              <Field label="每月额度 (GB)" hint="留空或 0 不限">
                <Input type="number" value={limitGib} onChange={(e) => setLimitGib(e.target.value)} placeholder="1024" />
              </Field>
              <Field label="计算方式">
                <Select value={form.traffic_mode} onValueChange={(v) => set("traffic_mode", v)}>
                  <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                  <SelectContent>
                    {Object.entries(TRAFFIC_MODES).map(([k, v]) => (
                      <SelectItem key={k} value={k}>{v}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </Field>
              <Field label="每月重置日" hint="1–31，改后本月重算，总量不变">
                <Input type="number" min={1} max={31} value={form.traffic_reset_day} onChange={(e) => set("traffic_reset_day", Number(e.target.value))} />
              </Field>
            </div>
            <details className="rounded-lg border bg-muted/30 px-3 py-2.5">
              <summary className="cursor-pointer text-sm font-medium">流量校正</summary>
              <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                按 GB 填入需要校正的值，未修改的计数器继续正常累计。
              </p>
              <div className="mt-3 grid gap-4 sm:grid-cols-2">
                {TRAFFIC_FIELDS.map(([key, label]) => (
                  <Field key={key} label={`${label} (GB)`}>
                    <Input
                      type="number"
                      step="0.001"
                      value={traffic[key]}
                      onChange={(e) => setTraffic((t) => ({ ...t, [key]: e.target.value }))}
                    />
                  </Field>
                ))}
              </div>
            </details>
          </section>
          <section className="space-y-3 border-t pt-5">
            <h3 className="text-sm font-medium">地址与地区</h3>
            <div className="grid gap-4 sm:grid-cols-[1fr_1.4fr_6rem]">
              <Field label="IPv4">
                <Input value={form.ipv4_pin ?? ""} onChange={(e) => set("ipv4_pin", e.target.value)} placeholder={`自动：${automatic(false)}`} />
              </Field>
              <Field label="IPv6">
                <Input value={form.ipv6_pin ?? ""} onChange={(e) => set("ipv6_pin", e.target.value)} placeholder={`自动：${automatic(true)}`} />
              </Field>
              <Field label="国家/地区">
                <Input
                  value={form.country_pin ?? ""}
                  maxLength={2}
                  onChange={(e) => set("country_pin", e.target.value.toUpperCase())}
                  placeholder={`自动：${node.country_auto || "无"}`}
                />
              </Field>
            </div>
            <p className="text-xs leading-relaxed text-muted-foreground">
              留空为自动。国家/地区填两位代码，如 CN；手填的值会一直显示，IP 变了要自己改。
            </p>
          </section>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>取消</Button>
          <Button onClick={save} disabled={saving}>保存</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function BillingForm({ node, onClose, onSaved }: {
  node: Node
  onClose: () => void
  onSaved: () => void
}) {
  const [form, setForm] = useState(node)
  // Text rather than a number: a numeric state cannot represent an empty field,
  // so clearing it would snap back to 0 mid-entry. Empty means free.
  const [price, setPrice] = useState(node.price > 0 ? String(node.price) : "")
  const [saving, setSaving] = useState(false)
  const set = <K extends keyof Node>(k: K, v: Node[K]) => setForm((f) => ({ ...f, [k]: v }))

  async function save() {
    setSaving(true)
    try {
      await api(`/nodes/${node.id}`, {
        method: "PUT",
        body: JSON.stringify(changes(node, {
          price: Math.max(0, Number(price) || 0),
          currency: form.currency,
          billing_cycle: form.billing_cycle,
          expires_at: form.expires_at || null,
        })),
      })
      toast.success("续费设置已保存")
      onClose()
      onSaved()
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent onOpenAutoFocus={(e) => e.preventDefault()} className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{node.name}</DialogTitle>
        </DialogHeader>
        <div className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="价格" hint="留空或 0 为免费">
              <Input
                type="number"
                min="0"
                step="0.01"
                value={price}
                onChange={(e) => setPrice(e.target.value)}
                placeholder="免费"
              />
            </Field>
            <Field label="货币">
              <Select value={form.currency} onValueChange={(v) => set("currency", v)}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {["USD", "CNY", "EUR", "GBP", "JPY"].map((c) => (
                    <SelectItem key={c} value={c}>{c}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
          </div>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="付款周期">
              <Select value={form.billing_cycle} onValueChange={(v) => set("billing_cycle", v)}>
                <SelectTrigger className="w-full"><SelectValue /></SelectTrigger>
                <SelectContent>
                  {Object.entries(CYCLES).map(([k, v]) => (
                    <SelectItem key={k} value={k}>{v}</SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </Field>
            <Field label="到期时间">
              <Input type="date" value={form.expires_at ?? ""} onChange={(e) => set("expires_at", e.target.value)} />
            </Field>
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>取消</Button>
          <Button onClick={save} disabled={saving}>保存</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}



// The window lives on the hub; this reads it back and counts down, which is also
// what makes an expired one disappear from the panel without interaction.
function useRegisterWindow() {
  const [key, setKey] = useState("")
  const [until, setUntil] = useState(0)
  const [now, setNow] = useState(() => Math.floor(Date.now() / 1000))

  useEffect(() => {
    api<Settings>("/settings")
      .then((s) => { setKey(String(s.register_key ?? "")); setUntil(Number(s.register_until ?? 0)) })
      .catch(() => {})
    const timer = setInterval(() => setNow(Math.floor(Date.now() / 1000)), 1000)
    return () => clearInterval(timer)
  }, [])

  return {
    key,
    left: key === "" ? 0 : Math.max(0, until - now),
    async open() {
      try {
        const w = await api<{ register_key: string; register_until: string }>("/register-window", { method: "POST" })
        setKey(w.register_key)
        setUntil(Number(w.register_until))
      } catch (e) {
        toast.error((e as Error).message)
      }
    },
    async close() {
      try {
        await api("/register-window", { method: "DELETE" })
        setKey("")
        setUntil(0)
        toast.success("注册窗口已关闭")
      } catch (e) {
        toast.error((e as Error).message)
      }
    },
  }
}

function RegisterDialog({ site, reg, onClose }: {
  site: string
  reg: ReturnType<typeof useRegisterWindow>
  onClose: () => void
}) {
  const [cores, setCores] = useState<CoreOptions>(DEFAULT_CORE_OPTIONS)
  const [onlyProxy, setOnlyProxy] = useState(false)
  const iface = useIfaceOption(undefined)
  const command = reg.left > 0 && iface.valid ? registerCommand(site, reg.key, iface.flag, cores, onlyProxy) : ""
  const clock = `${Math.floor(reg.left / 60)}:${String(reg.left % 60).padStart(2, "0")}`

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent onOpenAutoFocus={(e) => e.preventDefault()} className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>批量添加服务器</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          {/* One string: JSX turns a line break inside CJK text into a visible space. */}
          <p className="text-sm text-muted-foreground">
            {"开一个一小时的注册窗口。期间这条命令在任意机器上跑一次，那台机器就会自己出现在列表里，" +
              "名字取自它的 hostname。命令里没有任何一台机器的凭证，可以直接进循环。"}
          </p>
          <InstallModeSelector onlyProxy={onlyProxy} onChange={setOnlyProxy} />
          <CoreOptionsSelector cores={cores} onChange={setCores} onlyProxy={onlyProxy} />
          {!onlyProxy ? (
            <section className="space-y-3">
              <h3 className="text-sm font-medium">网络选项</h3>
              <IfaceOption option={iface} batch />
            </section>
          ) : (
            <div className="rounded-md border border-dashed p-2.5 text-xs text-muted-foreground bg-muted/10 flex items-center justify-between">
              <span>已启用纯代理模式</span>
              <Badge variant="outline" className="text-[10px] text-indigo-500 border-indigo-500/30">自动跳过探针服务安装</Badge>
            </div>
          )}
          {reg.left > 0 ? (
            <section className="space-y-2 border-t pt-5">
              <h3 className="text-sm font-medium">安装命令</h3>
              <Command className={`max-h-40 min-h-24 ${command ? "" : "text-muted-foreground"}`}>
                {command || "网卡名有误，改正后显示命令"}
              </Command>
              <OptionRow title={`窗口 ${clock} 后自动关闭`} hint="到点自动失效，装完了也可以现在就关">
                <Button variant="outline" size="sm" onClick={reg.close}>立即关闭</Button>
              </OptionRow>
            </section>
          ) : (
            <Button onClick={reg.open}>开启一小时窗口</Button>
          )}
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>关闭</Button>
          <Button onClick={() => copy(command)} disabled={!command}>
            <Copy className="size-4" /> 复制
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

// The `--iface` part of an install command. Off leaves the flag out, and
// install.sh then keeps whatever the machine already has; on with both lists
// empty passes '' and restores the default rules. It opens on for a node whose
// agent reports a list, so reinstalling from here repeats that list rather than
// relying on the machine to remember it.
function useIfaceOption(current: string | undefined) {
  const [on, setOn] = useState(!!current)
  const [choice, setChoice] = useState<IfaceChoice>(() => ifaceChoice(current ?? ""))
  const bad = on ? badIfaceName(choice) : undefined
  const spec = ifaceSpec(choice)
  return { on, setOn, choice, setChoice, current, bad, valid: !bad, flag: on && spec !== null ? spec : undefined }
}

function describeIface(spec: string) {
  const { only, skip } = ifaceChoice(spec)
  const parts = [only && `只统计 ${only.replaceAll(",", "、")}`, skip && `不统计 ${skip.replaceAll(",", "、")}`]
  return parts.filter(Boolean).join("；") || "默认规则"
}

function IfaceOption({ option, batch = false }: { option: ReturnType<typeof useIfaceOption>; batch?: boolean }) {
  const { on, setOn, choice, setChoice, current, bad } = option
  const field = (list: keyof IfaceChoice, label: string, placeholder: string) => (
    <Field label={label}>
      <Input
        value={choice[list]}
        onChange={(e) => setChoice({ ...choice, [list]: e.target.value })}
        placeholder={placeholder}
        spellCheck={false}
        aria-invalid={bad?.list === list}
        className="bg-background font-mono text-xs"
      />
    </Field>
  )
  const hint = on
    ? batch ? "每台机器都按这里的设置统计" : "覆盖这台机器原有的设置"
    : batch ? "关闭时各台机器沿用原有设置，新机器按默认规则" : "关闭时沿用机器上原有的设置，转发流量的机器才需要指定"
  return (
    <OptionRow
      title="指定统计的网卡"
      hint={<>{hint}{current !== undefined && <span className="mt-0.5 block">当前：{describeIface(current)}</span>}</>}
      toggle
      below={on && (
        <div className="space-y-2.5">
          <div className="grid gap-3 sm:grid-cols-2">
            {field("only", "只统计", "如 WAN 口 eth1 或 pppoe-wan")}
            {field("skip", "不统计", "如 LAN 口 eth0")}
          </div>
          <p className={`text-xs leading-relaxed ${bad ? "text-destructive" : "text-muted-foreground"}`}>
            {bad
              ? `「${bad.name}」不是有效的网卡名：写完整的名字，多个用逗号分隔`
              : "写完整的网卡名，多个用逗号分隔。两项都留空即恢复默认规则。"}
          </p>
        </div>
      )}
    >
      <Switch checked={on} onCheckedChange={setOn} />
    </OptionRow>
  )
}

function InstallDialog({ node, site, onClose, onRotated }: {
  node: Node
  site: string
  onClose: () => void
  onRotated: () => void
}) {
  const [token, setToken] = useState(node.token ?? "")
  const [interval, setInterval] = useState("1")
  const [rotating, setRotating] = useState(false)
  const [confirmRotate, setConfirmRotate] = useState(false)
  const [cores, setCores] = useState<CoreOptions>(DEFAULT_CORE_OPTIONS)
  const [onlyProxy, setOnlyProxy] = useState(false)
  const iface = useIfaceOption(currentIface(node))

  const seconds = Math.min(3600, Math.max(1, Math.round(Number(interval) || 1)))
  const command = token && iface.valid ? installCommand(site, token, seconds, iface.flag, cores, onlyProxy) : ""

  async function rotate() {
    setRotating(true)
    try {
      const fresh = await api<{ token: string }>(`/nodes/${node.id}/token`, { method: "POST" })
      setToken(fresh.token)
      setConfirmRotate(false)
      toast.success("凭证已换发，需用新命令重装")
      onRotated()
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setRotating(false)
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent onOpenAutoFocus={(e) => e.preventDefault()} className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{node.name}</DialogTitle>
          <DialogDescription>
            调整安装选项以生成定制安装命令：
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <InstallModeSelector onlyProxy={onlyProxy} onChange={setOnlyProxy} />
          <CoreOptionsSelector cores={cores} onChange={setCores} onlyProxy={onlyProxy} />

          {!onlyProxy ? (
            <section className="space-y-3">
              <h3 className="text-sm font-medium">探针监控选项</h3>
              <OptionRow title="上报间隔" hint="1–3600 秒，默认 1 秒">
                <span className="flex shrink-0 items-center gap-2 text-muted-foreground">
                  <Input
                    inputMode="numeric"
                    value={interval}
                    onChange={(e) => setInterval(e.target.value.replace(/\D/g, ""))}
                    aria-label="上报间隔（秒）"
                    className="tnum h-8 w-20 bg-background text-right"
                  />
                  秒
                </span>
              </OptionRow>
              <IfaceOption option={iface} />
            </section>
          ) : (
            <div className="rounded-md border border-dashed p-2.5 text-xs text-muted-foreground bg-muted/10 flex items-center justify-between">
              <span>已启用纯代理模式</span>
              <Badge variant="outline" className="text-[10px] text-indigo-500 border-indigo-500/30">无需配置探针上报参数</Badge>
            </div>
          )}

          <section className="space-y-2 border-t pt-5">
            <h3 className="text-sm font-medium">安装命令</h3>
            <Command className={`max-h-40 min-h-24 ${command ? "" : "text-muted-foreground"}`}>
              {command || (token ? "网卡名有误，改正后显示命令" : "旧版本创建的凭证不可读取，换发后显示")}
            </Command>
          </section>
          <OptionRow title="换发凭证" hint="旧凭证立即作废，agent 掉线，需用新命令重装">
            <Button variant="outline" size="sm" disabled={rotating} onClick={() => setConfirmRotate(true)}>
              换发
            </Button>
          </OptionRow>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>关闭</Button>
          <Button onClick={() => copy(command)} disabled={!command}>
            <Copy className="size-4" /> 复制
          </Button>
        </DialogFooter>
      </DialogContent>
      {confirmRotate && (
        <ConfirmDialog
          title={`给「${node.name}」换发凭证？`}
          description="旧凭证立即作废，agent 掉线，必须用新命令重装。仅在凭证可能泄露时使用。"
          confirmLabel="换发凭证"
          busy={rotating}
          onClose={() => setConfirmRotate(false)}
          onConfirm={rotate}
        />
      )}
    </Dialog>
  )
}

function ServerDisplaySettingsDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [settings, setSettings] = useState({
    public_show_price: false,
    public_show_expiry: false,
    public_show_traffic_limit: false,
  })

  useEffect(() => {
    if (open) {
      setLoading(true)
      fetch("/api/proxy/settings/display")
        .then((r) => r.json())
        .then((data) => {
          if (data.ok) {
            setSettings({
              public_show_price: !!data.public_show_price,
              public_show_expiry: !!data.public_show_expiry,
              public_show_traffic_limit: !!data.public_show_traffic_limit,
            })
          }
        })
        .catch(() => {})
        .finally(() => setLoading(false))
    }
  }, [open])

  const handleSave = async () => {
    setSaving(true)
    try {
      const res = await fetch("/api/proxy/settings/display", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
      })
      const data = await res.json()
      if (data.ok) {
        toast.success(data.message || "展示权限设置已保存")
        onOpenChange(false)
      } else {
        toast.error(data.message || "保存失败")
      }
    } catch {
      toast.error("网络请求失败")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[94vw] max-w-md sm:max-w-lg p-4 sm:p-6 space-y-4 max-h-[88vh] overflow-y-auto overflow-x-hidden">
        <DialogHeader>
          <DialogTitle className="text-base sm:text-lg font-bold flex items-center gap-2">
            <Shield className="size-5 text-primary" />
            <span>服务器公开信息展示权限</span>
          </DialogTitle>
          <DialogDescription className="text-xs leading-relaxed">
            选择向公开探针主页展示哪些数据。关闭后相应数据仅管理员可见，访客与已登录客户均不可见，保护服务器成本与配额隐私。
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 pt-1">
          <div className="flex items-start justify-between gap-3 p-3 rounded-lg border bg-muted/20">
            <div className="space-y-0.5 min-w-0 pr-2">
              <span className="text-xs font-semibold flex items-center gap-1.5">
                💰 展示服务器续费价格
              </span>
              <p className="text-[11px] text-muted-foreground leading-snug">
                默认关闭（严格仅超级管理员登录可见；访客与已登录客户均不可见，彻底保护续费成本隐私）。
              </p>
            </div>
            <Switch
              checked={settings.public_show_price}
              onCheckedChange={(v) => setSettings((s) => ({ ...s, public_show_price: v }))}
              disabled={loading || saving}
              className="shrink-0 mt-0.5"
            />
          </div>

          <div className="flex items-start justify-between gap-3 p-3 rounded-lg border bg-muted/20">
            <div className="space-y-0.5 min-w-0 pr-2">
              <span className="text-xs font-semibold flex items-center gap-1.5">
                ⏳ 展示到期与剩余时间
              </span>
              <p className="text-[11px] text-muted-foreground leading-snug">
                开启后，公开卡片展示到期时间与剩余可用天数；关闭后仅管理员登录可见。
              </p>
            </div>
            <Switch
              checked={settings.public_show_expiry}
              onCheckedChange={(v) => setSettings((s) => ({ ...s, public_show_expiry: v }))}
              disabled={loading || saving}
              className="shrink-0 mt-0.5"
            />
          </div>

          <div className="flex items-start justify-between gap-3 p-3 rounded-lg border bg-muted/20">
            <div className="space-y-0.5 min-w-0 pr-2">
              <span className="text-xs font-semibold flex items-center gap-1.5">
                📊 展示流量限额与剩余流量
              </span>
              <p className="text-[11px] text-muted-foreground leading-snug">
                开启后，公开卡片展示月度限额与剩余比例；关闭后卡片仅显示已用流量（隐藏限额与剩余量）。
              </p>
            </div>
            <Switch
              checked={settings.public_show_traffic_limit}
              onCheckedChange={(v) => setSettings((s) => ({ ...s, public_show_traffic_limit: v }))}
              disabled={loading || saving}
              className="shrink-0 mt-0.5"
            />
          </div>
        </div>

        <DialogFooter className="flex flex-row justify-end gap-2 pt-2">
          <Button variant="outline" size="sm" onClick={() => onOpenChange(false)} disabled={saving} className="text-xs">
            取消
          </Button>
          <Button size="sm" onClick={handleSave} disabled={loading || saving} className="text-xs">
            {saving ? "保存中…" : "保存权限设置"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Nodes({ nodes, refresh, site, refusal }: { nodes: Node[]; refresh: () => void; site: string; refusal: string }) {
  const [displaySettingsOpen, setDisplaySettingsOpen] = useState(false)
  const [licenseStatus, setLicenseStatus] = useState<any>(() => {
    try {
      return JSON.parse(localStorage.getItem("proxyprobe_license_status") || "null")
    } catch {
      return null
    }
  })
  const [creating, setCreating] = useState(false)
  const [editing, setEditing] = useState<Node | null>(null)
  const [billing, setBilling] = useState<Node | null>(null)
  const [installing, setInstalling] = useState<Node | null>(null)
  const [registering, setRegistering] = useState(false)
  const reg = useRegisterWindow()
  const [deleting, setDeleting] = useState<Node | null>(null)
  const [removing, setRemoving] = useState(false)
  const [manualOrder, setManualOrder] = useState<number[]>([])
  const [query, setQuery] = useState("")
  const [dragging, setDragging] = useState<number | null>(null)
  const orderBeforeDrag = useRef<number[]>([])

  const [proxyOnlineMap, setProxyOnlineMap] = useState<Record<number, boolean>>({})

  useEffect(() => {
    fetch("/api/proxy/license/status")
      .then(r => r.json())
      .then(d => {
        setLicenseStatus(d)
        try { localStorage.setItem("proxyprobe_license_status", JSON.stringify(d)) } catch {}
      })
      .catch(() => {})

    fetch("/api/proxy/servers")
      .then(r => r.json())
      .then(d => {
        if (d.servers && Array.isArray(d.servers)) {
          const map: Record<number, boolean> = {}
          d.servers.forEach((s: any) => {
            if (s.proxy_online) map[s.id] = true
          })
          setProxyOnlineMap(map)
        }
      })
      .catch(() => {})
  }, [nodes])
  const byId = new Map(nodes.map((node) => [node.id, node]))
  const orderedIds = new Set(manualOrder)
  const order = [
    ...manualOrder.map((id) => byId.get(id)).filter((node): node is Node => Boolean(node)),
    ...nodes.filter((node) => !orderedIds.has(node.id)),
  ]
  // `order` itself stays whole, because the order sent on drop is the order of
  // every node.
  const visible = searchNodes(order, query)
  const searching = query.trim() !== ""
  const uninstall = refusal ? "" : uninstallCommand(site)

  async function remove() {
    if (!deleting) return
    setRemoving(true)
    try {
      await api(`/nodes/${deleting.id}`, { method: "DELETE" })
      try {
        await fetch(`/api/proxy/servers/${deleting.id}`, {
          method: "DELETE",
          headers: {
            "Authorization": `Bearer ${localStorage.getItem("token") || ""}`,
            "X-Auth-Token": localStorage.getItem("token") || ""
          }
        })
      } catch (err) {
        console.warn("Cascade proxy server cleanup notice:", err)
      }
      toast.success("已彻底删除服务器及所有关联数据")
      setDeleting(null)
      refresh()
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setRemoving(false)
    }
  }

  // Rows are displaced while the pointer is down; the order is saved on drop.
  function move(from: number, to: number) {
    if (from < 0 || to < 0 || to >= order.length || from === to) return
    const next = [...order]
    next.splice(to, 0, ...next.splice(from, 1))
    const ids = next.map((node) => node.id)
    animate(() => setManualOrder(ids))
    return ids
  }

  // Dropped outside the table or cancelled with Escape: the order is restored.
  function cancel() {
    setDragging(null)
    const rollback = orderBeforeDrag.current
    if (rollback.length) animate(() => setManualOrder(rollback))
  }

  function save(ids: number[]) {
    setDragging(null)
    const rollback = orderBeforeDrag.current
    if (!rollback.length || ids.join() === rollback.join()) return
    orderBeforeDrag.current = ids
    api("/nodes/order", { method: "PUT", body: JSON.stringify({ ids }) }).then(refresh, (e: Error) => {
      setManualOrder(rollback)
      toast.error(e.message)
    })
  }

  return (
    <div className="space-y-4">
      {licenseStatus && (
        <div className="rounded-xl border border-muted bg-muted/30 p-3 text-xs text-muted-foreground flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2 shadow-sm">
          <div className="flex items-center gap-2">
            <span className={`px-2 py-0.5 rounded text-[10px] font-semibold ${licenseStatus.active ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20" : "bg-amber-500/10 text-amber-600 border border-amber-500/20"}`}>
              {licenseStatus.plan_name || (licenseStatus.active ? "商业版" : "免费体验版")}
            </span>
            <span>
              已纳管服务器：<strong>{nodes.length} 台</strong>
              <span className="text-emerald-600 dark:text-emerald-400 font-medium ml-1.5">(基础探针无限纳管)</span>
            </span>
          </div>
          <span className="text-muted-foreground font-medium shrink-0">
            探针基础功能终身免费；商业授权按代理节点与客户端用户配额授权
          </span>
        </div>
      )}
      {refusal && <p className="text-sm text-muted-foreground">{refusal}</p>}
      <div className="flex flex-wrap items-center justify-end gap-2">
        <NodeSearch className="mr-auto w-full sm:w-64" value={query} onChange={setQuery} />
        <Button
          variant="outline"
          size="icon"
          onClick={() => setDisplaySettingsOpen(true)}
          className="size-9 shrink-0 text-muted-foreground hover:text-foreground"
          title="服务器公开信息展示权限（访客视图控制）"
          aria-label="服务器公开信息展示权限"
        >
          <Settings className="size-4" />
        </Button>
        {/* An open window is visible from the list itself, so nobody has to
            remember they left one open. */}
        <Button 
          variant="outline" 
          disabled={!!refusal} 
          onClick={() => {
            if (licenseStatus?.type === "revoked") {
              toast.error("当前商业许可证已被授权中心吊销冻结，禁止添加服务器！")
              return
            }
            setRegistering(true)
          }}
        >
          <Server /> 批量添加{reg.left > 0 && ` · ${Math.ceil(reg.left / 60)} 分`}
        </Button>
        <Button 
          disabled={!!refusal} 
          onClick={() => {
            if (licenseStatus?.type === "revoked") {
              toast.error("当前商业许可证已被授权中心吊销冻结，禁止添加服务器！")
              return
            }
            setCreating(true)
          }}
        >
          <Plus /> 添加服务器
        </Button>
      </div>

      <Card className="overflow-x-auto p-0">
        <Table>
          <TableHeader>
            {/* Percentages, or the address column swallows every spare pixel
                and pushes status across the table. */}
            <TableRow>
              <TableHead className="w-[20%]">名称</TableHead>
              <TableHead className="w-[22%]">IP</TableHead>
              <TableHead className="w-[12%]">状态</TableHead>
              <TableHead className="w-[16%]">流量</TableHead>
              <TableHead className="w-[10%]">价格</TableHead>
              <TableHead className="w-[12%]">到期</TableHead>
              <TableHead className="text-right">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {visible.map((n, index) => (
              <TableRow
                key={n.id}
                style={{ viewTransitionName: `node-${n.id}` }}
                data-dragging={dragging === n.id || undefined}
                className="transition-opacity data-[dragging]:opacity-40"
                onDragOver={(e) => { e.preventDefault(); e.dataTransfer.dropEffect = "move" }}
                onDragEnter={() => dragging !== null && move(order.findIndex((node) => node.id === dragging), index)}
                onDrop={(e) => { e.preventDefault(); save(order.map((node) => node.id)) }}
              >
                <TableCell>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      draggable={!searching}
                      // A drop sends the order of every node, and a filtered list
                      // offers only its own rows to drop onto, so the index below
                      // is the full one exactly while nothing is filtered out.
                      disabled={searching}
                      className="cursor-grab touch-none rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground active:cursor-grabbing disabled:cursor-default disabled:opacity-40 disabled:hover:bg-transparent"
                      title={searching ? "清空搜索后可拖动排序" : "拖动排序"}
                      aria-label={`拖动 ${n.name} 排序`}
                      onDragStart={(e) => {
                        orderBeforeDrag.current = order.map((node) => node.id)
                        setDragging(n.id)
                        e.dataTransfer.effectAllowed = "move"
                        // Firefox refuses to start a drag without a payload.
                        e.dataTransfer.setData("text/plain", String(n.id))
                      }}
                      onDragEnd={(e) => (e.dataTransfer.dropEffect === "none" ? cancel() : save(order.map((node) => node.id)))}
                      onKeyDown={(e) => {
                        const delta = e.key === "ArrowUp" ? -1 : e.key === "ArrowDown" ? 1 : 0
                        if (!delta) return
                        e.preventDefault()
                        orderBeforeDrag.current = order.map((node) => node.id)
                        const ids = move(index, index + delta)
                        if (ids) save(ids)
                      }}
                    >
                      <GripVertical className="size-4" />
                    </button>
                    <div className="min-w-0 font-medium">{n.name}</div>
                    {n.country && (
                      <Badge
                        variant="outline"
                        title={n.country_pin ? "手动指定" : undefined}
                        className="shrink-0 font-normal text-muted-foreground"
                      >
                        {n.country}
                      </Badge>
                    )}
                  </div>
                </TableCell>
                {/* Addresses live only here, never on the public page. */}
                <TableCell>
                  <Addresses node={n} />
                </TableCell>
                <TableCell>
                  {n.online ? (
                    <Badge variant="default" className="font-normal">
                      在线
                    </Badge>
                  ) : proxyOnlineMap[n.id] ? (
                    <Badge className="font-normal bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border border-indigo-500/20" title="该服务器未安装探针监控，但代理核心与守护程序正常在线运行">
                      纯代理在线
                    </Badge>
                  ) : (
                    <Badge variant="secondary" className="font-normal">
                      离线
                    </Badge>
                  )}
                  {!n.public && <Badge variant="outline" className="ml-1 font-normal">不公开</Badge>}
                  {/* Under the badge, not inside it: the column is a tenth of
                      the table and the three do not share one line. */}
                  {!n.online && !proxyOnlineMap[n.id] && n.last_seen > 0 && Date.now() / 1000 - n.last_seen >= 60 && (
                    <div className="tnum mt-1 text-xs text-muted-foreground">
                      {uptime(Date.now() / 1000 - n.last_seen)}
                    </div>
                  )}
                </TableCell>
                {/* Counted by the node's own billing rule, as on the public
                    page. */}
                <TableCell className="tnum text-sm">
                  {bytes(n.month_used)}
                  <span className="text-muted-foreground">
                    {" / "}{n.traffic_limit > 0 ? bytes(n.traffic_limit) : FOREVER}
                  </span>
                </TableCell>
                <TableCell className="tnum text-sm">
                  {n.price > 0 ? money(n.price, n.currency) : "免费"}
                </TableCell>
                <TableCell className="text-sm">{n.expires_at || FOREVER}</TableCell>
                <TableCell className="text-right whitespace-nowrap">
                  <Button variant="ghost" size="icon" disabled={!!refusal} onClick={() => setInstalling(n)} title="安装 Agent" aria-label="安装 Agent">
                    <Download />
                  </Button>
                  <Button variant="ghost" size="icon" onClick={() => setEditing(n)} title="编辑服务器" aria-label="编辑服务器">
                    <Pencil />
                  </Button>
                  <Button variant="ghost" size="icon" onClick={() => setBilling(n)} title="续费设置" aria-label="续费设置">
                    <CalendarClock />
                  </Button>
                  <Button variant="ghost" size="icon" onClick={() => setDeleting(n)} title="删除服务器" aria-label="删除服务器">
                    <Trash2 className="text-destructive" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {nodes.length === 0 && (
              <TableRow>
                <TableCell colSpan={7} className="py-10 text-center text-sm text-muted-foreground">
                  还没有服务器，右上角添加
                </TableCell>
              </TableRow>
            )}
            {searching && nodes.length > 0 && !visible.length && (
              <TableRow>
                <TableCell colSpan={7} className="py-10 text-center text-sm text-muted-foreground">
                  没有匹配的服务器
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Card>

      {creating && (
        <CreateNode
          site={site}
          onClose={() => setCreating(false)}
          onSaved={refresh}
        />
      )}
      {editing && (
        <NodeForm
          node={editing}
          onClose={() => setEditing(null)}
          onSaved={refresh}
        />
      )}
      {billing && (
        <BillingForm node={billing} onClose={() => setBilling(null)} onSaved={refresh} />
      )}
      {registering && <RegisterDialog site={site} reg={reg} onClose={() => { setRegistering(false); refresh() }} />}

      {installing && (
        <InstallDialog
          node={installing}
          site={site}
          onClose={() => setInstalling(null)}
          onRotated={refresh}
        />
      )}
      {deleting && (
        <ConfirmDialog
          title={`删除服务器「${deleting.name}」？`}
          description="历史指标、流量记录和凭证一并删除，不可恢复。"
          confirmLabel="删除服务器"
          busy={removing}
          onClose={() => setDeleting(null)}
          onConfirm={remove}
        >
          {/* Deleting the node leaves the agent running on the machine, retrying
              with a token the hub no longer accepts. */}
          {uninstall && (
            <div className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <Label className="text-sm font-medium">卸载 agent</Label>
                <Button variant="ghost" size="sm" onClick={() => copy(uninstall)}>
                  <Copy className="size-4" /> 复制
                </Button>
              </div>
              <Command>{uninstall}</Command>
              <p className="text-xs text-muted-foreground">
                在这台机器上以 root 执行，停止 agent，删除二进制、env 文件和服务文件。
              </p>
            </div>
          )}
        </ConfirmDialog>
      )}

      <ServerDisplaySettingsDialog
        open={displaySettingsOpen}
        onOpenChange={setDisplaySettingsOpen}
      />
    </div>
  )
}

function PingForm({ task, nodes, onClose, onSaved }: {
  task: Partial<PingTask>
  nodes: Node[]
  onClose: () => void
  onSaved: () => void
}) {
  const [form, setForm] = useState(task)
  const [saving, setSaving] = useState(false)
  // The assignments as the hub holds them, as far as this dialog can tell: those
  // loaded, plus any node that registers while it is open, which an auto_join
  // probe takes at once. Shown ticked, so unticking one removes it.
  const base = useRef(task.nodes ?? [])
  const seen = useRef(new Set(nodes.map((n) => n.id)))
  useEffect(() => {
    const fresh = nodes.filter((n) => !seen.current.has(n.id)).map((n) => n.id)
    for (const id of fresh) seen.current.add(id)
    if (!task.auto_join || !fresh.length) return
    base.current = [...base.current, ...fresh]
    setForm((f) => ({ ...f, nodes: [...(f.nodes ?? []), ...fresh] }))
  }, [nodes, task.auto_join])
  const chosen = new Set(form.nodes)
  // Counted against the live list: `form.nodes` can still name a node deleted
  // since the probes were loaded.
  const chosenCount = nodes.filter((n) => chosen.has(n.id)).length

  const pick = (list: Node[], on: boolean) =>
    setForm((f) => {
      const next = new Set(f.nodes)
      for (const n of list) {
        if (on) next.add(n.id)
        else next.delete(n.id)
      }
      return { ...f, nodes: [...next] }
    })

  async function save() {
    if (!form.name?.trim() || !form.target?.trim()) return toast.error("请填写名称和目标")
    setSaving(true)
    try {
      // `base` limits the save to what was ticked or unticked here; a node that
      // joined through auto_join while the dialog was open keeps its assignment.
      await api("/ping-tasks", { method: "POST", body: JSON.stringify(task.id ? { ...form, base: base.current } : form) })
      toast.success("已保存，正在下发")
      onClose()
      onSaved()
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open onOpenChange={(open) => !open && onClose()}>
      <DialogContent onOpenAutoFocus={(e) => e.preventDefault()} className="sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>{task.id ? "编辑监控" : "添加监控"}</DialogTitle>
        </DialogHeader>
        <div className="space-y-6">
          {/* On a phone the name takes the first row and the target shares the
              second with the interval, so the tab order matches the screen. */}
          <section className="grid grid-cols-[1fr_6rem] gap-4 sm:grid-cols-[1fr_1.4fr_6rem]">
            <Field label="名称" className="col-span-full sm:col-span-1">
              {/* A new monitor starts empty, so the cursor belongs here;
                  editing an existing one starts with nothing selected. */}
              <Input autoFocus={!task.id} value={form.name ?? ""} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="Cloudflare" />
            </Field>
            <Field label="目标地址" hint="host:port，每个节点各自 TCP 连接">
              <Input value={form.target ?? ""} onChange={(e) => setForm({ ...form, target: e.target.value })} placeholder="1.1.1.1:443" />
            </Field>
            <Field label="间隔（秒）" hint="5–3600">
              {/* An emptied number box reads back as "", and Number("") is 0,
                  which the hub refuses. */}
              <Input type="number" min="5" max="3600" value={form.interval ?? 60} onChange={(e) => setForm({ ...form, interval: Number(e.target.value) || 60 })} />
            </Field>
          </section>
          <section className="space-y-3 border-t pt-5">
            <div className="flex items-baseline justify-between gap-2">
              <h3 className="text-sm font-medium">运行服务器</h3>
              <span className="tnum text-xs text-muted-foreground">已选 {chosenCount} / {nodes.length}</span>
            </div>
            <NodePicker nodes={nodes} chosen={chosen} onPick={pick} />
            <OptionRow title="新服务器自动加入" hint="以后添加的服务器自动运行此监控" toggle>
              <Switch checked={!!form.auto_join} onCheckedChange={(v) => setForm({ ...form, auto_join: v })} />
            </OptionRow>
          </section>
        </div>
        <DialogFooter>
          <Button variant="ghost" onClick={onClose}>取消</Button>
          <Button onClick={save} disabled={saving}>保存</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Ping({ nodes }: { nodes: Node[] }) {
  const [tasks, setTasks] = useState<PingTask[]>([])
  const [editing, setEditing] = useState<Partial<PingTask> | null>(null)
  const [deleting, setDeleting] = useState<PingTask | null>(null)
  const [removing, setRemoving] = useState(false)

  const load = () => api<{ tasks: PingTask[] }>("/ping-tasks").then((d) => setTasks(d.tasks)).catch(() => {})
  // A node added or removed changes assignments on the hub: auto_join adds, a
  // deletion cascades.
  useEffect(() => { load() }, [nodes.length])

  async function remove() {
    if (!deleting) return
    setRemoving(true)
    try {
      await api(`/ping-tasks/${deleting.id}`, { method: "DELETE" })
      toast.success("监控已删除")
      setDeleting(null)
      load()
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setRemoving(false)
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button onClick={() => setEditing({ name: "", target: "", interval: 60, nodes: nodes.map((n) => n.id), auto_join: true })}>
          <Plus /> 添加监控
        </Button>
      </div>

      <Card className="overflow-x-auto p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[22%]">名称</TableHead>
              <TableHead className="w-[34%]">目标</TableHead>
              <TableHead className="w-[10%]">间隔</TableHead>
              <TableHead className="w-[22%]">服务器</TableHead>
              <TableHead className="text-right">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {tasks.map((t) => (
              <TableRow key={t.id}>
                <TableCell className="font-medium">{t.name}</TableCell>
                <TableCell className="tnum text-sm">{t.target}</TableCell>
                <TableCell className="tnum text-sm">{t.interval}s</TableCell>
                <TableCell className="text-sm whitespace-nowrap text-muted-foreground">
                  {t.nodes.length > 0 && t.nodes.length === nodes.length ? "全部" : `${t.nodes.length} 个`}
                  {t.auto_join && <Badge variant="outline" className="ml-2 font-normal">自动加入</Badge>}
                </TableCell>
                <TableCell className="text-right whitespace-nowrap">
                  <Button variant="ghost" size="icon" onClick={() => setEditing(t)} title="编辑监控" aria-label="编辑监控"><Pencil /></Button>
                  <Button variant="ghost" size="icon" onClick={() => setDeleting(t)} title="删除监控" aria-label="删除监控">
                    <Trash2 className="text-destructive" />
                  </Button>
                </TableCell>
              </TableRow>
            ))}
            {tasks.length === 0 && (
              <TableRow>
                <TableCell colSpan={5} className="py-10 text-center text-sm text-muted-foreground">
                  还没有延迟监控。每台服务器独立 TCP 连接目标端口并上报耗时。
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Card>

      {editing && <PingForm task={editing} nodes={nodes} onClose={() => setEditing(null)} onSaved={load} />}
      {deleting && (
        <ConfirmDialog
          title={`删除监控「${deleting.name}」？`}
          description="该监控及其历史延迟记录一并删除，不可恢复。"
          confirmLabel="删除监控"
          busy={removing}
          onClose={() => setDeleting(null)}
          onConfirm={remove}
        />
      )}
    </div>
  )
}



type Settings = Record<string, string | boolean>

// Two pages write settings, and each loads only what it displays.
function useSettings() {
  const [s, setS] = useState<Settings | null>(null)
  useEffect(() => { api<Settings>("/settings").then(setS).catch(() => {}) }, [])
  return {
    s,
    set: (k: string, v: string) => setS((old) => ({ ...(old ?? {}), [k]: v })),
    save: async (patch: Record<string, string>) => {
      try {
        await api("/settings", { method: "PUT", body: JSON.stringify(patch) })
        toast.success("已保存")
        // Only the saved keys and the `*_set` flags are taken from the hub: a
        // credential comes back as a flag, so the typed value must not linger,
        // while another card's unsaved edits on the same page must survive.
        const fresh = await api<Settings>("/settings")
        setS((old) => {
          const next = { ...old }
          for (const key of Object.keys(patch)) next[key] = fresh[key]
          for (const [key, value] of Object.entries(fresh)) if (key.endsWith("_set")) next[key] = value
          return next
        })
      } catch (e) {
        toast.error((e as Error).message)
      }
    },
  }
}


function SettingsTab({
  updateInfo,
  onOpenUpdateDialog,
}: {
  updateInfo?: UpdateInfo | null
  onOpenUpdateDialog?: () => void
}) {
  const { s, set, save } = useSettings()
  if (!s) return null

  return (
    <div className="space-y-4">
      {/* 系统版本与在线更新卡片 */}
      <Card className="gap-4 p-5">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b pb-4">
          <div className="space-y-1">
            <h3 className="text-sm font-bold flex items-center gap-2">
              <Sparkles className="size-4 text-amber-500" /> 系统版本与在线更新
            </h3>
            <p className="text-xs text-muted-foreground">
              当前版本：<code className="text-primary font-mono font-semibold">{updateInfo?.current_version || "v2.5.3"}</code>
              {updateInfo?.has_update ? (
                <span className="ml-2 text-amber-600 dark:text-amber-400 font-semibold">
                  (🔥 发现最新版本 {updateInfo.latest_version})
                </span>
              ) : (
                <span className="ml-2 text-emerald-600 dark:text-emerald-400">
                  (已是最新版)
                </span>
              )}
            </p>
          </div>
          {onOpenUpdateDialog && (
            <Button
              size="sm"
              variant={updateInfo?.has_update ? "default" : "outline"}
              onClick={onOpenUpdateDialog}
              className="text-xs gap-1.5 h-8 shrink-0 self-start sm:self-auto"
            >
              {updateInfo?.has_update ? (
                <>
                  <Rocket className="size-3.5" /> 立即升级系统
                </>
              ) : (
                <>
                  <RefreshCw className="size-3.5" /> 检查更新
                </>
              )}
            </Button>
          )}
        </div>
        <p className="text-xs text-muted-foreground leading-relaxed">
          系统支持全自动在线无损热升级（零停机、历史配置与数据库完全保留），亦可在 SSH 终端输入 <code>hhub upgrade</code> 快速完成更新。
        </p>
      </Card>

      <Card className="gap-4 p-5">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="站点名称">
            <Input value={String(s.site_name ?? "")} onChange={(e) => set("site_name", e.target.value)} placeholder="HHUB" />
          </Field>
          <Field label="历史数据保留天数" hint="超出的明细自动清理，累计流量不受影响">
            <Input
              type="number"
              value={String(s.retention_days ?? "")}
              onChange={(e) => set("retention_days", e.target.value)}
              placeholder="7"
            />
          </Field>
          <Field
            label="GitHub 代理"
            hint="留空直连。仅在 hub 自己拉不到 GitHub Release 时填。这个地址返回的字节会被安装到每一台节点上，只填信得过的镜像"
          >
            <Input
              value={String(s.github_proxy ?? "")}
              onChange={(e) => set("github_proxy", e.target.value)}
              placeholder="https://ghfast.top"
            />
          </Field>
        </div>
        {/* 不是 <label>：点文字不该切换开关，只有开关自己可点。
            aria-labelledby 保住读屏软件那边的关联。 */}
        <div className="flex items-center gap-2 text-sm">
          <Switch
            aria-labelledby="public-page-label"
            checked={s.public_page !== "off"}
            onCheckedChange={(v) => set("public_page", v ? "on" : "off")}
          />
          <span id="public-page-label">开放公开状态页，关闭后所有页面需登录</span>
        </div>
        <div>
          <Button
            size="sm"
            onClick={() =>
              save({
                site_name: String(s.site_name ?? ""),
                // `||` rather than `??`: the hub returns "" for an unset key
                // rather than null, and "" is the one value this key's write path
                // refuses.
                retention_days: String(s.retention_days || "7"),
                github_proxy: String(s.github_proxy ?? ""),
                public_page: s.public_page === "off" ? "off" : "on",
              })
            }
          >
            保存站点设置
          </Button>
        </div>
      </Card>

      {/* 客户端软件下载与上传专区设置 */}
      <ClientAppsSettingsCard />

      {/* 客服支持与 Telegram 联系渠道设置 */}
      <TelegramSupportSettingsCard />

      {/* 用户邮箱注册与 SMTP 邮件发信服务设置 */}
      <SmtpSettingsCard />
    </div>
  )
}

function VipTierSettingsCard() {
  const [tiers, setTiers] = useState<any[]>([])
  const [createOpen, setCreateOpen] = useState(false)
  const [editingTier, setEditingTier] = useState<any | null>(null)
  const [form, setForm] = useState({
    tier_id: "",
    name: "",
    price_monthly: "0",
    price_quarterly: "0",
    price_yearly: "0",
    traffic_gb: "200",
    device_limit: "0",
    description: "",
  })
  const [saving, setSaving] = useState(false)

  const loadTiers = async () => {
    try {
      const res = await fetch("/api/proxy/tiers")
      const d = await res.json()
      if (d.ok && Array.isArray(d.tiers)) setTiers(d.tiers)
    } catch {}
  }

  useEffect(() => { loadTiers() }, [])

  const handleOpenCreate = () => {
    setEditingTier(null)
    setForm({ tier_id: "", name: "", price_monthly: "0", price_quarterly: "0", price_yearly: "0", traffic_gb: "200", device_limit: "0", description: "" })
    setCreateOpen(true)
  }

  const handleEdit = (t: any) => {
    setEditingTier(t)
    setForm({
      tier_id: t.tier_id || t.tier_key || "",
      name: t.name || "",
      price_monthly: String(t.price_monthly ?? 0),
      price_quarterly: String(t.price_quarterly ?? (t.price_monthly ? Math.round(t.price_monthly * 3 * 0.9) : 0)),
      price_yearly: String(t.price_yearly ?? (t.price_monthly ? Math.round(t.price_monthly * 12 * 0.8) : 0)),
      traffic_gb: String(t.traffic_gb ?? 200),
      device_limit: String(t.device_limit ?? 0),
      description: t.description || "",
    })
    setCreateOpen(true)
  }

  const handleSaveTier = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    try {
      const payload: any = {
        tier_id: form.tier_id.trim().toLowerCase(),
        name: form.name.trim(),
        price_monthly: parseFloat(form.price_monthly) || 0,
        price_quarterly: parseFloat(form.price_quarterly) || 0,
        price_yearly: parseFloat(form.price_yearly) || 0,
        traffic_gb: parseFloat(form.traffic_gb) || 0,
        device_limit: parseInt(form.device_limit) || 0,
        description: form.description.trim(),
      }
      if (editingTier) {
        payload.id = editingTier.id
      }
      const res = await fetch("/api/proxy/tiers", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
      const d = await res.json()
      if (d.ok) {
        toast.success(d.message || (editingTier ? "VIP 套餐修改成功！" : "VIP 套餐添加成功！"))
        setCreateOpen(false)
        setEditingTier(null)
        setForm({ tier_id: "", name: "", price_monthly: "0", price_quarterly: "0", price_yearly: "0", traffic_gb: "200", device_limit: "0", description: "" })
        loadTiers()
      } else {
        toast.error(d.message || "操作失败")
      }
    } catch {
      toast.error("网络请求错误")
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id: number, name: string) => {
    if (!confirm(`确定要删除 VIP 套餐【${name}】吗？`)) return
    try {
      const res = await fetch(`/api/proxy/tiers/${id}`, { method: "DELETE" })
      const d = await res.json()
      if (d.ok) {
        toast.success("VIP 套餐已删除")
        loadTiers()
      } else {
        toast.error(d.message || "删除失败")
      }
    } catch {
      toast.error("网络请求错误")
    }
  }

  return (
    <Card className="gap-4 p-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b pb-4">
        <div className="space-y-1">
          <h3 className="text-sm font-bold flex items-center gap-2">
            <Sparkles className="size-4 text-amber-500" /> VIP 等级套餐与节点物理隔离
          </h3>
          <p className="text-xs text-muted-foreground">
            自定义 VIP 权限等级（如 vip1, vip2）。在节点上标记对应等级后，只有该等级的用户可以获取与订阅，不同等级节点物理隔离不可见。
          </p>
        </div>
        <Button size="sm" onClick={handleOpenCreate} className="gap-1.5 text-xs h-8">
          <Plus className="size-3.5" /> 添加 VIP 套餐
        </Button>
      </div>

      <div className="pt-2">
        {tiers.length === 0 ? (
          <div className="p-6 text-center text-xs text-muted-foreground">
            暂未添加自定义 VIP 套餐，默认所有节点全员可访问。
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
            {tiers.map((t) => (
              <div key={t.id} className="p-3.5 rounded-lg border bg-muted/20 space-y-2 flex flex-col justify-between">
                <div className="space-y-1">
                  <div className="flex items-center justify-between">
                    <Badge className="bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/30 uppercase font-mono font-bold text-xs">
                      {t.tier_id}
                    </Badge>
                    <span className="font-semibold text-xs text-foreground">{t.name}</span>
                  </div>
                  {t.description && (
                    <p className="text-[11px] text-muted-foreground line-clamp-2">{t.description}</p>
                  )}
                  <div className="flex items-center gap-2 text-[11px] text-muted-foreground font-mono pt-1">
                    <span>流量: {t.traffic_gb > 0 ? `${t.traffic_gb}GB` : "不限"}</span>
                    <span>·</span>
                    <span>设备: {t.device_limit > 0 ? `${t.device_limit}台` : "不限"}</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-[11px] text-emerald-600 dark:text-emerald-400 font-mono font-semibold pt-1">
                    <span>月付: ￥{t.price_monthly ?? 0}</span>
                    <span>·</span>
                    <span>季付: ￥{t.price_quarterly ?? (t.price_monthly ? (t.price_monthly * 3 * 0.9).toFixed(0) : 0)}</span>
                    <span>·</span>
                    <span>年付: ￥{t.price_yearly ?? (t.price_monthly ? (t.price_monthly * 12 * 0.8).toFixed(0) : 0)}</span>
                  </div>
                </div>
                <div className="flex justify-end gap-1 pt-2 border-t">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleEdit(t)}
                    className="h-6 px-2 text-primary hover:text-primary hover:bg-primary/10 text-[11px] gap-1"
                  >
                    <Pencil className="size-3" /> 编辑
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleDelete(t.id, t.name)}
                    className="h-6 px-2 text-rose-500 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/30 text-[11px] gap-1"
                  >
                    <Trash2 className="size-3" /> 删除
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <Dialog open={createOpen} onOpenChange={(open) => {
        setCreateOpen(open)
        if (!open) setEditingTier(null)
      }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="text-base font-bold flex items-center gap-2">
              {editingTier ? (
                <>
                  <Pencil className="size-4 text-primary" /> 编辑 VIP 等级套餐
                </>
              ) : (
                <>
                  <Plus className="size-4 text-primary" /> 新增 VIP 等级套餐
                </>
              )}
            </DialogTitle>
            <DialogDescription className="text-xs">
              {editingTier ? "修改 VIP 权限等级、售价、流量配额及说明描述。" : "定义 VIP 标识与售价，创建后可在节点管理中标记节点权限，并分配给目标用户。"}
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleSaveTier} className="space-y-4 py-2">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-xs">套餐标识 (英文数字代号)</Label>
                <Input
                  className="text-xs h-9 font-mono"
                  placeholder="如: vip1, vip2"
                  value={form.tier_id}
                  onChange={e => setForm(prev => ({ ...prev, tier_id: e.target.value }))}
                  required
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">展示名称</Label>
                <Input
                  className="text-xs h-9"
                  placeholder="如: VIP1 黄金会员"
                  value={form.name}
                  onChange={e => setForm(prev => ({ ...prev, name: e.target.value }))}
                  required
                />
              </div>
            </div>

            <div className="grid grid-cols-3 gap-2">
              <div className="space-y-1.5">
                <Label className="text-xs">月付价格 (元)</Label>
                <Input
                  type="number"
                  min="0"
                  step="0.01"
                  className="text-xs h-9 font-mono"
                  placeholder="0.00"
                  value={form.price_monthly}
                  onChange={e => setForm(prev => ({ ...prev, price_monthly: e.target.value }))}
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">季付价格 (元)</Label>
                <Input
                  type="number"
                  min="0"
                  step="0.01"
                  className="text-xs h-9 font-mono"
                  placeholder="0.00"
                  value={form.price_quarterly}
                  onChange={e => setForm(prev => ({ ...prev, price_quarterly: e.target.value }))}
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">年付价格 (元)</Label>
                <Input
                  type="number"
                  min="0"
                  step="0.01"
                  className="text-xs h-9 font-mono"
                  placeholder="0.00"
                  value={form.price_yearly}
                  onChange={e => setForm(prev => ({ ...prev, price_yearly: e.target.value }))}
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-xs">默认流量配额 (GB)</Label>
                <Input
                  type="number"
                  min="0"
                  className="text-xs h-9 font-mono"
                  value={form.traffic_gb}
                  onChange={e => setForm(prev => ({ ...prev, traffic_gb: e.target.value }))}
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">允许同时在线设备 (台)</Label>
                <Input
                  type="number"
                  min="0"
                  className="text-xs h-9 font-mono"
                  value={form.device_limit}
                  onChange={e => setForm(prev => ({ ...prev, device_limit: e.target.value }))}
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs">套餐说明描述 (可选)</Label>
              <Input
                className="text-xs h-9"
                placeholder="如: 包含香港/日本节点，高速低延迟"
                value={form.description}
                onChange={e => setForm(prev => ({ ...prev, description: e.target.value }))}
              />
            </div>

            <DialogFooter className="pt-2">
              <Button type="button" variant="outline" size="sm" onClick={() => setCreateOpen(false)} className="h-8 text-xs">
                取消
              </Button>
              <Button type="submit" size="sm" disabled={saving} className="h-8 text-xs">
                {saving ? "保存中..." : (editingTier ? "保存修改" : "确认添加")}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </Card>
  )
}

function PaymentGatewaySettingsCard() {
  const [enabled, setEnabled] = useState(false)
  const [usdtTrc20, setUsdtTrc20] = useState("")
  const [alipayQr, setAlipayQr] = useState("")
  const [wechatQr, setWechatQr] = useState("")
  const [tgSupport, setTgSupport] = useState("")
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    fetch("/api/proxy/settings/payment")
      .then(r => r.json())
      .then(d => {
        if (d.ok) {
          setEnabled(Boolean(d.enabled))
          setUsdtTrc20(d.usdt_trc20 || "")
          setAlipayQr(d.alipay_qr || "")
          setWechatQr(d.wechat_qr || "")
          setTgSupport(d.tg_support || "")
        }
      })
      .catch(() => {})
  }, [])

  const handleSave = async () => {
    setSaving(true)
    try {
      const res = await fetch("/api/proxy/settings/payment", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          enabled,
          usdt_trc20: usdtTrc20.trim(),
          alipay_qr: alipayQr.trim(),
          wechat_qr: wechatQr.trim(),
          tg_support: tgSupport.trim(),
        }),
      })
      const d = await res.json()
      if (d.ok) {
        toast.success(d.message || "支付网关设置已保存")
      } else {
        toast.error(d.message || "保存失败")
      }
    } catch {
      toast.error("网络请求错误")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card className="gap-4 p-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b pb-4">
        <div className="space-y-1">
          <h3 className="text-sm font-bold flex items-center gap-2">
            <CreditCard className="size-4 text-emerald-500" /> 支付入口与收款网关配置
          </h3>
          <p className="text-xs text-muted-foreground">
            配置客户端用户选购/续费套餐时的外部收款渠道（USDT TRC20 钱包地址、微信/支付宝收款二维码图片或链接、Telegram 咨询直达）。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Switch
            checked={enabled}
            onCheckedChange={setEnabled}
            aria-label="启用支付入口"
          />
          <span className={`text-xs font-semibold ${enabled ? "text-emerald-600 dark:text-emerald-400" : "text-muted-foreground"}`}>
            {enabled ? "收款入口已启用" : "已关闭收款"}
          </span>
        </div>
      </div>

      <div className="space-y-4 pt-2">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label className="text-xs font-semibold">USDT (TRC20) 收款钱包地址</Label>
            <Input
              className="text-xs h-9 font-mono"
              placeholder="如: Txxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"
              value={usdtTrc20}
              onChange={e => setUsdtTrc20(e.target.value)}
            />
            <p className="text-[11px] text-muted-foreground">用户选购套餐时可直接复制此地址进行波场转账</p>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs font-semibold">Telegram 人工客服 / 支付联络</Label>
            <Input
              className="text-xs h-9"
              placeholder="如: https://t.me/your_admin"
              value={tgSupport}
              onChange={e => setTgSupport(e.target.value)}
            />
            <p className="text-[11px] text-muted-foreground">用户支付时一键直达客服快速核单开通</p>
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-1.5">
            <Label className="text-xs font-semibold">支付宝收款二维码 (图片 URL 或 Base64)</Label>
            <Input
              className="text-xs h-9"
              placeholder="https://... 或 data:image/png;base64,..."
              value={alipayQr}
              onChange={e => setAlipayQr(e.target.value)}
            />
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs font-semibold">微信支付收款二维码 (图片 URL 或 Base64)</Label>
            <Input
              className="text-xs h-9"
              placeholder="https://... 或 data:image/png;base64,..."
              value={wechatQr}
              onChange={e => setWechatQr(e.target.value)}
            />
          </div>
        </div>

        <div className="flex justify-end pt-2">
          <Button size="sm" onClick={handleSave} disabled={saving} className="text-xs h-8">
            {saving ? "保存中..." : "保存支付入口设置"}
          </Button>
        </div>
      </div>
    </Card>
  )
}

function OrdersTable() {
  const [orders, setOrders] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [statusFilter, setStatusFilter] = useState<string>("all")

  const loadOrders = async () => {
    setLoading(true)
    try {
      const res = await fetch("/api/proxy/orders")
      const d = await res.json()
      if (d.ok && Array.isArray(d.orders)) {
        setOrders(d.orders)
      }
    } catch {
      toast.error("加载订单记录失败")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadOrders()
  }, [])

  const handleComplete = async (orderId: number) => {
    if (!confirm(`确认审核通过订单 #${orderId} 吗？系统将自动升级该用户的 VIP 等级并顺延有效期。`)) return
    try {
      const res = await fetch(`/api/proxy/orders/${orderId}/complete`, { method: "POST" })
      const d = await res.json()
      if (d.ok) {
        toast.success(d.message || "订单审核通过，服务已生效！")
        loadOrders()
      } else {
        toast.error(d.message || "操作失败")
      }
    } catch {
      toast.error("网络请求错误")
    }
  }

  const handleReject = async (orderId: number) => {
    if (!confirm(`确认驳回订单 #${orderId} 吗？`)) return
    try {
      const res = await fetch(`/api/proxy/orders/${orderId}/reject`, { method: "POST" })
      const d = await res.json()
      if (d.ok) {
        toast.success(d.message || "订单已驳回")
        loadOrders()
      } else {
        toast.error(d.message || "操作失败")
      }
    } catch {
      toast.error("网络请求错误")
    }
  }

  const handleDelete = async (orderId: number) => {
    if (!confirm(`确认彻底删除订单 #${orderId} 吗？`)) return
    try {
      const res = await fetch(`/api/proxy/orders/${orderId}`, { method: "DELETE" })
      const d = await res.json()
      if (d.ok) {
        toast.success(d.message || "订单已删除")
        loadOrders()
      } else {
        toast.error(d.message || "删除失败")
      }
    } catch {
      toast.error("网络请求错误")
    }
  }

  const filteredOrders = orders.filter(o => {
    if (statusFilter === "all") return true
    return o.status === statusFilter
  })

  return (
    <Card className="gap-4 p-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b pb-4">
        <div className="space-y-1">
          <h3 className="text-sm font-bold flex items-center gap-2">
            <PackageCheck className="size-4 text-primary" /> 用户订购与支付记录 ({filteredOrders.length})
          </h3>
          <p className="text-xs text-muted-foreground">
            管理全站用户的 VIP 套餐购买、续费订单以及支付审核状态。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Select value={statusFilter} onValueChange={setStatusFilter}>
            <SelectTrigger className="h-8 text-xs w-28">
              <SelectValue placeholder="筛选状态" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">全部订单</SelectItem>
              <SelectItem value="pending">待审核</SelectItem>
              <SelectItem value="completed">已生效</SelectItem>
              <SelectItem value="rejected">已驳回</SelectItem>
            </SelectContent>
          </Select>
          <Button variant="outline" size="sm" onClick={loadOrders} className="h-8 text-xs gap-1">
            <RefreshCw className={`size-3 ${loading ? "animate-spin" : ""}`} /> 刷新
          </Button>
        </div>
      </div>

      <div className="overflow-x-auto pt-2">
        {filteredOrders.length === 0 ? (
          <div className="p-8 text-center text-xs text-muted-foreground">
            暂无相关支付订购记录
          </div>
        ) : (
          <table className="w-full text-left text-xs">
            <thead className="bg-muted/50 border-b text-muted-foreground">
              <tr>
                <th className="py-2.5 px-3 font-semibold">单号</th>
                <th className="py-2.5 px-3 font-semibold">用户</th>
                <th className="py-2.5 px-3 font-semibold">套餐</th>
                <th className="py-2.5 px-3 font-semibold">周期</th>
                <th className="py-2.5 px-3 font-semibold">金额</th>
                <th className="py-2.5 px-3 font-semibold">方式</th>
                <th className="py-2.5 px-3 font-semibold">转账单号 / 附言</th>
                <th className="py-2.5 px-3 font-semibold">状态</th>
                <th className="py-2.5 px-3 font-semibold">创建时间</th>
                <th className="py-2.5 px-3 font-semibold text-right">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {filteredOrders.map(o => (
                <tr key={o.id} className="hover:bg-muted/30 transition-colors">
                  <td className="py-3 px-3 font-mono text-muted-foreground text-[11px]">#{o.id}</td>
                  <td className="py-3 px-3 font-semibold text-foreground">{o.username}</td>
                  <td className="py-3 px-3 uppercase font-mono font-bold text-amber-600 dark:text-amber-400">
                    {o.tier_key}
                  </td>
                  <td className="py-3 px-3 font-medium">
                    {o.period === "yearly" ? "年付" : o.period === "quarterly" ? "季付" : "月付"}
                  </td>
                  <td className="py-3 px-3 font-mono font-bold text-emerald-600 dark:text-emerald-400">
                    ￥{Number(o.amount || 0).toFixed(2)}
                  </td>
                  <td className="py-3 px-3 font-mono text-[11px]">
                    {o.pay_method === "balance" ? "余额扣款" : o.pay_method}
                  </td>
                  <td className="py-3 px-3 text-muted-foreground max-w-[150px] truncate" title={o.note}>
                    {o.note || "-"}
                  </td>
                  <td className="py-3 px-3">
                    {o.status === "completed" && (
                      <Badge className="bg-emerald-500/10 text-emerald-600 border border-emerald-500/20 text-[10px]">
                        已生效
                      </Badge>
                    )}
                    {o.status === "pending" && (
                      <Badge className="bg-amber-500/10 text-amber-600 border border-amber-500/20 text-[10px]">
                        待审核
                      </Badge>
                    )}
                    {o.status === "rejected" && (
                      <Badge variant="destructive" className="text-[10px]">
                        已驳回
                      </Badge>
                    )}
                  </td>
                  <td className="py-3 px-3 text-muted-foreground font-mono text-[11px]">
                    {o.created_at ? new Date(o.created_at * 1000).toLocaleString() : "-"}
                  </td>
                  <td className="py-3 px-3 text-right">
                    <div className="flex items-center justify-end gap-1">
                      {o.status === "pending" && (
                        <>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 px-2 text-xs text-emerald-600 hover:text-emerald-700 hover:bg-emerald-50 dark:hover:bg-emerald-950/30 gap-1"
                            onClick={() => handleComplete(o.id)}
                            title="通过并生效"
                          >
                            <CheckCircle className="size-3.5" /> 通过
                          </Button>
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 px-2 text-xs text-amber-600 hover:text-amber-700 hover:bg-amber-50 dark:hover:bg-amber-950/30 gap-1"
                            onClick={() => handleReject(o.id)}
                            title="驳回订单"
                          >
                            <XCircle className="size-3.5" /> 驳回
                          </Button>
                        </>
                      )}
                      <Button
                        variant="ghost"
                        size="sm"
                        className="h-7 px-1.5 text-xs text-destructive hover:bg-destructive/10"
                        onClick={() => handleDelete(o.id)}
                        title="删除记录"
                      >
                        <Trash2 className="size-3.5" />
                      </Button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </Card>
  )
}

function TiersManagementTab() {
  return (
    <div className="space-y-4">
      <VipTierSettingsCard />
      <PaymentGatewaySettingsCard />
      <OrdersTable />
    </div>
  )
}

function AnnouncementsTab() {
  return (
    <div className="space-y-4">
      <AnnouncementSettingsCard />
      <GlobalNotificationSettingsCard />
    </div>
  )
}

function ServerExpirySettingsCard() {
  const [enabled, setEnabled] = useState(false)
  const [remindDays, setRemindDays] = useState(3)
  const [saving, setSaving] = useState(false)
  const [testing, setTesting] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch("/api/proxy/settings/server-expiry")
      .then(r => r.json())
      .then(d => {
        if (d.ok) {
          setEnabled(Boolean(d.enabled))
          if (d.remind_days_before !== undefined) setRemindDays(d.remind_days_before)
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const handleSave = async () => {
    setSaving(true)
    try {
      const res = await fetch("/api/proxy/settings/server-expiry", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          enabled: enabled ? 1 : 0,
          remind_days_before: parseInt(String(remindDays)) || 3,
        }),
      })
      const d = await res.json()
      if (d.ok) toast.success(d.message || "服务器到期提醒设置已保存")
      else toast.error(d.message || "保存失败")
    } catch {
      toast.error("网络请求错误")
    } finally {
      setSaving(false)
    }
  }

  const handleTestNotify = async () => {
    setTesting(true)
    try {
      const res = await fetch("/api/proxy/server-expiry/test-notify", { method: "POST" })
      const d = await res.json()
      if (d.ok) toast.success(d.message || "已执行到期检测与 TG 推送！")
      else toast.error(d.message || "推送未成功，请检查 TG Bot 配置")
    } catch {
      toast.error("网络请求错误")
    } finally {
      setTesting(false)
    }
  }

  return (
    <Card className="gap-4 p-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b pb-4">
        <div className="space-y-1">
          <h3 className="text-sm font-bold flex items-center gap-2">
            <CalendarClock className="size-4 text-rose-500" /> 服务器到期提醒与 TG 自动推送
          </h3>
          <p className="text-xs text-muted-foreground">
            自动扫描各服务器的到期时间（expires_at）。在服务器到期前 N 天自动向管理员 Telegram 发送警报通知，防止漏续费导致业务中断。
          </p>
        </div>
        <Badge variant={enabled ? "secondary" : "outline"} className={enabled ? "bg-emerald-500/10 text-emerald-600 border-emerald-500/30" : ""}>
          {enabled ? "监控中" : "已关闭"}
        </Badge>
      </div>

      <div className="space-y-4 pt-1">
        <div className="flex items-center gap-2 text-sm">
          <Switch checked={enabled} onCheckedChange={setEnabled} id="server-expiry-toggle" />
          <Label htmlFor="server-expiry-toggle" className="cursor-pointer text-xs font-medium">
            开启服务器到期 Telegram 自动推送提醒
          </Label>
        </div>

        {enabled && (
          <div className="grid gap-2 sm:grid-cols-2">
            <div className="space-y-1.5">
              <Label className="text-xs font-medium">提前提醒天数</Label>
              <div className="flex items-center gap-2">
                <Input
                  type="number"
                  min="1"
                  max="60"
                  value={remindDays}
                  onChange={e => setRemindDays(parseInt(e.target.value) || 3)}
                  className="text-xs h-9 font-mono w-28"
                />
                <span className="text-xs text-muted-foreground">天 (在到期日前持续发送 TG 告警)</span>
              </div>
            </div>
          </div>
        )}

        <div className="flex items-center gap-2 pt-1">
          <Button size="sm" onClick={handleSave} disabled={saving || loading} className="text-xs h-8">
            {saving ? "保存中..." : "保存到期提醒配置"}
          </Button>
          <Button variant="outline" size="sm" onClick={handleTestNotify} disabled={testing} className="text-xs h-8 gap-1.5">
            <Send className="size-3.5" /> {testing ? "检测中..." : "立即检测并测试 TG 推送"}
          </Button>
        </div>
      </div>
    </Card>
  )
}

function AnnouncementSettingsCard() {
  const [announcements, setAnnouncements] = useState<any[]>([])
  const [createOpen, setCreateOpen] = useState(false)
  const [editingAnno, setEditingAnno] = useState<any | null>(null)
  const [title, setTitle] = useState("")
  const [content, setContent] = useState("")
  const [isPinned, setIsPinned] = useState(false)
  const [saving, setSaving] = useState(false)

  const loadAnnouncements = async () => {
    try {
      const res = await fetch("/api/proxy/announcements")
      const d = await res.json()
      if (d.ok && Array.isArray(d.announcements)) setAnnouncements(d.announcements)
    } catch {}
  }

  useEffect(() => { loadAnnouncements() }, [])

  const handleOpenCreate = () => {
    setEditingAnno(null)
    setTitle("")
    setContent("")
    setIsPinned(false)
    setCreateOpen(true)
  }

  const handleEdit = (a: any) => {
    setEditingAnno(a)
    setTitle(a.title || "")
    setContent(a.content || "")
    setIsPinned(Boolean(a.is_pinned))
    setCreateOpen(true)
  }

  const handleSaveAnno = async (e: React.FormEvent) => {
    e.preventDefault()
    setSaving(true)
    try {
      const payload: any = {
        title: title.trim(),
        content: content.trim(),
        is_pinned: isPinned ? 1 : 0,
      }
      if (editingAnno) {
        payload.id = editingAnno.id
      }
      const res = await fetch("/api/proxy/announcements", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
      const d = await res.json()
      if (d.ok) {
        toast.success(editingAnno ? "系统公告修改成功！" : "系统公告发布成功！")
        setCreateOpen(false)
        setEditingAnno(null)
        setTitle("")
        setContent("")
        setIsPinned(false)
        loadAnnouncements()
      } else {
        toast.error(d.message || "操作失败")
      }
    } catch {
      toast.error("网络请求错误")
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm("确定删除此条公告吗？")) return
    try {
      const res = await fetch(`/api/proxy/announcements/${id}`, { method: "DELETE" })
      const d = await res.json()
      if (d.ok) {
        toast.success("公告已删除")
        loadAnnouncements()
      } else {
        toast.error(d.message || "删除失败")
      }
    } catch {
      toast.error("网络错误")
    }
  }

  return (
    <Card className="gap-4 p-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b pb-4">
        <div className="space-y-1">
          <h3 className="text-sm font-bold flex items-center gap-2">
            <Bell className="size-4 text-primary" /> 系统公告栏管理
          </h3>
          <p className="text-xs text-muted-foreground">
            发布全站公告（通知更新、维护、线路新增）。用户登录后可在公告栏查看标题，点击进入展开查看详细图文内容。
          </p>
        </div>
        <Button size="sm" onClick={handleOpenCreate} className="gap-1.5 text-xs h-8">
          <Plus className="size-3.5" /> 发布新公告
        </Button>
      </div>

      <div className="pt-2">
        {announcements.length === 0 ? (
          <div className="p-6 text-center text-xs text-muted-foreground">
            暂未发布任何公告，点击右上角【发布新公告】即可发布。
          </div>
        ) : (
          <div className="space-y-2">
            {announcements.map((a) => (
              <div key={a.id} className="p-3 rounded-lg border bg-muted/20 flex items-center justify-between gap-3">
                <div className="space-y-1 min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    {a.is_pinned === 1 && (
                      <Badge className="text-[10px] bg-rose-500/10 text-rose-600 border border-rose-500/30">
                        置顶
                      </Badge>
                    )}
                    <span className="font-semibold text-xs text-foreground truncate">{a.title}</span>
                  </div>
                  <p className="text-[11px] text-muted-foreground line-clamp-1">{a.content}</p>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <span className="text-[10px] text-muted-foreground font-mono mr-1">
                    {new Date(a.created_at * 1000).toLocaleDateString()}
                  </span>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleEdit(a)}
                    className="h-7 w-7 p-0 text-primary hover:text-primary hover:bg-primary/10"
                    title="编辑公告"
                  >
                    <Pencil className="size-3.5" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleDelete(a.id)}
                    className="h-7 w-7 p-0 text-rose-500 hover:text-rose-600"
                    title="删除公告"
                  >
                    <Trash2 className="size-3.5" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <Dialog open={createOpen} onOpenChange={(open) => {
        setCreateOpen(open)
        if (!open) setEditingAnno(null)
      }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="text-base font-bold flex items-center gap-2">
              {editingAnno ? (
                <>
                  <Pencil className="size-4 text-primary" /> 编辑系统公告
                </>
              ) : (
                <>
                  <Plus className="size-4 text-primary" /> 发布系统公告
                </>
              )}
            </DialogTitle>
            <DialogDescription className="text-xs">
              在客户端用户中心首页公告栏展示此条通知。
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleSaveAnno} className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label className="text-xs">公告标题</Label>
              <Input
                className="text-xs h-9"
                placeholder="如: 关于新增香港/新加坡 IPLC 专线节点的通知"
                value={title}
                onChange={e => setTitle(e.target.value)}
                required
              />
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs">详细内容 (支持多行文本与说明)</Label>
              <textarea
                className="w-full min-w-0 rounded-md border border-input bg-transparent px-3 py-2 text-xs shadow-xs outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 h-32"
                placeholder="填写完整的公告内容..."
                value={content}
                onChange={e => setContent(e.target.value)}
                required
              />
            </div>

            <div className="flex items-center gap-2">
              <Switch checked={isPinned} onCheckedChange={setIsPinned} id="pinned-toggle" />
              <Label htmlFor="pinned-toggle" className="cursor-pointer text-xs font-medium">
                置顶该公告 (显示在最前列)
              </Label>
            </div>

            <DialogFooter className="pt-2">
              <Button type="button" variant="outline" size="sm" onClick={() => setCreateOpen(false)} className="h-8 text-xs">
                取消
              </Button>
              <Button type="submit" size="sm" disabled={saving} className="h-8 text-xs">
                {saving ? "保存中..." : (editingAnno ? "保存修改" : "立即发布")}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </Card>
  )
}

function GlobalNotificationSettingsCard() {
  const [enabled, setEnabled] = useState(false)
  const [title, setTitle] = useState("")
  const [content, setContent] = useState("")
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch("/api/proxy/settings/notification")
      .then(r => r.json())
      .then(d => {
        if (d.ok) {
          setEnabled(Boolean(d.enabled))
          setTitle(d.title || "")
          setContent(d.content || "")
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const handleSave = async () => {
    setSaving(true)
    try {
      const res = await fetch("/api/proxy/settings/notification", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          enabled: enabled ? 1 : 0,
          title: title.trim(),
          content: content.trim(),
        }),
      })
      const d = await res.json()
      if (d.ok) toast.success(d.message || "登录全局通知设置已保存")
      else toast.error(d.message || "保存失败")
    } catch {
      toast.error("网络请求错误")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card className="gap-4 p-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b pb-4">
        <div className="space-y-1">
          <h3 className="text-sm font-bold flex items-center gap-2">
            <Radio className="size-4 text-purple-500" /> 用户登录后全局自动弹窗通知
          </h3>
          <p className="text-xs text-muted-foreground">
            设置后，用户每次或首次登录用户控制台时，将自动以弹窗浮层形式强提示通知内容。
          </p>
        </div>
        <Badge variant={enabled ? "secondary" : "outline"} className={enabled ? "bg-purple-500/10 text-purple-600 border-purple-500/30" : ""}>
          {enabled ? "已开启弹窗" : "已停用"}
        </Badge>
      </div>

      <div className="space-y-4 pt-1">
        <div className="flex items-center gap-2 text-sm">
          <Switch checked={enabled} onCheckedChange={setEnabled} id="notice-toggle" />
          <Label htmlFor="notice-toggle" className="cursor-pointer text-xs font-medium">
            开启登录自动弹窗通知
          </Label>
        </div>

        {enabled && (
          <div className="space-y-3">
            <div className="space-y-1.5">
              <Label className="text-xs font-medium">通知标题</Label>
              <Input
                value={title}
                onChange={e => setTitle(e.target.value)}
                placeholder="如: 重要安全提醒 / 最新更新通报"
                className="text-xs h-9"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-medium">弹窗通知正文</Label>
              <textarea
                className="w-full min-w-0 rounded-md border border-input bg-transparent px-3 py-2 text-xs shadow-xs outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 h-28"
                placeholder="输入展示给用户的详细弹窗说明..."
                value={content}
                onChange={e => setContent(e.target.value)}
              />
            </div>
          </div>
        )}

        <div>
          <Button size="sm" onClick={handleSave} disabled={saving || loading} className="text-xs h-8">
            {saving ? "保存中..." : "保存通知配置"}
          </Button>
        </div>
      </div>
    </Card>
  )
}

function ClientAppsSettingsCard() {
  const [apps, setApps] = useState<any[]>([])
  const [createOpen, setCreateOpen] = useState(false)
  const [editingApp, setEditingApp] = useState<any | null>(null)
  const [uploadFile, setUploadFile] = useState<File | null>(null)
  const [form, setForm] = useState({
    name: "Clash Verge",
    platform: "Windows",
    version: "v1.7.5",
    mirror_url: "",
    description: "",
  })
  const [submitting, setSubmitting] = useState(false)

  const PRESET_APPS = [
    { name: "Clash Verge Rev", platform: "Windows", mirror_url: "https://github.com/clash-verge-rev/clash-verge-rev/releases" },
    { name: "FLClash", platform: "Android", mirror_url: "https://github.com/chen08209/FlClash/releases" },
    { name: "NekoBox", platform: "Android", mirror_url: "https://github.com/MatsuriDayo/NekoBoxForAndroid/releases" },
    { name: "Hiddify", platform: "Windows", mirror_url: "https://github.com/hiddify/hiddify-next/releases" },
    { name: "Sing-box", platform: "macOS", mirror_url: "https://github.com/SagerNet/sing-box/releases" },
    { name: "Shadowrocket", platform: "iOS", mirror_url: "https://apps.apple.com/app/shadowrocket/id932747118" },
  ]

  const loadApps = async () => {
    try {
      const res = await fetch("/api/proxy/apps")
      const d = await res.json()
      if (d.ok && Array.isArray(d.apps)) setApps(d.apps)
    } catch {}
  }

  useEffect(() => { loadApps() }, [])

  const handleOpenCreate = () => {
    setEditingApp(null)
    setForm({ name: "Clash Verge", platform: "Windows", version: "v1.7.5", mirror_url: "", description: "" })
    setUploadFile(null)
    setCreateOpen(true)
  }

  const handleEdit = (app: any) => {
    setEditingApp(app)
    setForm({
      name: app.name || "",
      platform: app.platform || "Windows",
      version: app.version || "",
      mirror_url: app.external_url || app.mirror_url || "",
      description: app.description || "",
    })
    setUploadFile(null)
    setCreateOpen(true)
  }

  const handleSelectPreset = (p: typeof PRESET_APPS[0]) => {
    setForm(prev => ({
      ...prev,
      name: p.name,
      platform: p.platform,
      mirror_url: p.mirror_url,
    }))
  }

  const handleSaveApp = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    try {
      const payload: any = {
        name: form.name.trim(),
        platform: form.platform,
        version: form.version.trim(),
        mirror_url: form.mirror_url.trim(),
        description: form.description.trim(),
      }
      if (editingApp) {
        payload.id = editingApp.id
      }
      const res = await fetch("/api/proxy/apps", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      })
      const d = await res.json()
      if (!res.ok || !d.ok) throw new Error(d.message || "保存软件条目失败")

      const appId = d.app_id || (editingApp ? editingApp.id : null)
      if (uploadFile && appId) {
        toast.info("正在将安装包上传到本地服务器...")
        const upRes = await fetch("/api/proxy/apps/upload", {
          method: "POST",
          headers: {
            "X-App-Id": String(appId),
            "X-Filename": encodeURIComponent(uploadFile.name),
            "Content-Type": "application/octet-stream",
          },
          body: uploadFile,
        })
        const upData = await upRes.json()
        if (upData.ok) {
          toast.success("文件包已成功上传到服务器！")
        } else {
          toast.error(upData.message || "文件包上传失败")
        }
      }

      toast.success(editingApp ? "客户端软件修改成功！" : "客户端软件添加成功！")
      setCreateOpen(false)
      setEditingApp(null)
      setUploadFile(null)
      loadApps()
    } catch (err: any) {
      toast.error(err.message || "操作软件出错")
    } finally {
      setSubmitting(false)
    }
  }

  const handleDelete = async (id: number) => {
    if (!confirm("确定删除该客户端软件吗？")) return
    try {
      const res = await fetch(`/api/proxy/apps/${id}`, { method: "DELETE" })
      const d = await res.json()
      if (d.ok) {
        toast.success("软件已移除")
        loadApps()
      } else {
        toast.error(d.message || "删除失败")
      }
    } catch {
      toast.error("网络请求错误")
    }
  }

  return (
    <Card className="gap-4 p-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b pb-4">
        <div className="space-y-1">
          <h3 className="text-sm font-bold flex items-center gap-2">
            <Download className="size-4 text-emerald-500" /> 客户端软件下载与上传专区
          </h3>
          <p className="text-xs text-muted-foreground">
            上传翻墙客户端安装包或提供镜像外链，预设 Clash、NekoBox、FLClash、Hiddify 等。用户在中心专区可自主选择「本地服务器高速下载」或「官方镜像直链下载」。
          </p>
        </div>
        <Button size="sm" onClick={handleOpenCreate} className="gap-1.5 text-xs h-8">
          <Plus className="size-3.5" /> 上传 / 添加软件
        </Button>
      </div>

      <div className="pt-2">
        {apps.length === 0 ? (
          <div className="p-6 text-center text-xs text-muted-foreground">
            暂无已添加的软件，点击右上角【上传 / 添加软件】添加翻墙客户端。
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
            {apps.map((app) => (
              <div key={app.id} className="p-3.5 rounded-lg border bg-muted/20 space-y-2 flex flex-col justify-between">
                <div className="space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="font-bold text-xs text-foreground truncate">{app.name}</span>
                    <Badge variant="outline" className="text-[10px] font-mono">
                      {app.platform}
                    </Badge>
                  </div>
                  <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                    <span>版本: {app.version || "最新版"}</span>
                    <span>·</span>
                    <span>下载: {app.downloads || 0} 次</span>
                  </div>
                  <div className="flex flex-wrap gap-1 pt-1">
                    {app.has_local_file === 1 ? (
                      <Badge className="text-[10px] bg-emerald-500/10 text-emerald-600 border border-emerald-500/30">
                        ⚡ 本地高速安装包
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="text-[10px] text-muted-foreground">
                        仅外链直链
                      </Badge>
                    )}
                    {app.mirror_url && (
                      <Badge className="text-[10px] bg-blue-500/10 text-blue-600 border border-blue-500/30">
                        🌐 官方镜像外链
                      </Badge>
                    )}
                  </div>
                </div>

                <div className="flex justify-end gap-1 pt-2 border-t">
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleEdit(app)}
                    className="h-6 px-2 text-primary hover:text-primary hover:bg-primary/10 text-[11px] gap-1"
                  >
                    <Pencil className="size-3" /> 编辑
                  </Button>
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => handleDelete(app.id)}
                    className="h-6 px-2 text-rose-500 hover:text-rose-600 hover:bg-rose-50 dark:hover:bg-rose-950/30 text-[11px] gap-1"
                  >
                    <Trash2 className="size-3" /> 删除
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>

      <Dialog open={createOpen} onOpenChange={(open) => {
        setCreateOpen(open)
        if (!open) setEditingApp(null)
      }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="text-base font-bold flex items-center gap-2">
              {editingApp ? (
                <>
                  <Pencil className="size-4 text-primary" /> 编辑客户端软件
                </>
              ) : (
                <>
                  <Upload className="size-4 text-primary" /> 添加客户端软件
                </>
              )}
            </DialogTitle>
            <DialogDescription className="text-xs">
              支持上传安装包二进制文件至本地服务器，亦可填写官方镜像下载外链。
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleSaveApp} className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label className="text-xs">预设常用软件快速填入</Label>
              <div className="flex flex-wrap gap-1.5">
                {PRESET_APPS.map(p => (
                  <Button
                    key={p.name}
                    type="button"
                    variant="outline"
                    size="sm"
                    className="h-6 text-[11px] px-2"
                    onClick={() => handleSelectPreset(p)}
                  >
                    {p.name}
                  </Button>
                ))}
              </div>
            </div>

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-xs">软件名称</Label>
                <Input
                  className="text-xs h-9"
                  placeholder="如: Clash Verge"
                  value={form.name}
                  onChange={e => setForm(prev => ({ ...prev, name: e.target.value }))}
                  required
                />
              </div>
              <div className="space-y-1.5">
                <Label className="text-xs">适用系统</Label>
                <Select value={form.platform} onValueChange={v => setForm(prev => ({ ...prev, platform: v }))}>
                  <SelectTrigger className="text-xs h-9">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="Windows">Windows</SelectItem>
                    <SelectItem value="Android">Android</SelectItem>
                    <SelectItem value="macOS">macOS</SelectItem>
                    <SelectItem value="iOS">iOS</SelectItem>
                    <SelectItem value="Linux">Linux</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs">版本号</Label>
              <Input
                className="text-xs h-9 font-mono"
                placeholder="如: v1.7.5"
                value={form.version}
                onChange={e => setForm(prev => ({ ...prev, version: e.target.value }))}
              />
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs">官方下载外链 (可选)</Label>
              <Input
                className="text-xs h-9 font-mono"
                placeholder="https://github.com/.../releases"
                value={form.mirror_url}
                onChange={e => setForm(prev => ({ ...prev, mirror_url: e.target.value }))}
              />
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs">上传本地安装包文件至服务器 (可选)</Label>
              <input
                type="file"
                className="text-xs border rounded p-1.5 w-full bg-background"
                onChange={e => {
                  if (e.target.files && e.target.files[0]) {
                    setUploadFile(e.target.files[0])
                  }
                }}
              />
              <p className="text-[11px] text-muted-foreground">
                直接上传 .apk / .exe / .dmg / .zip，用户可直接从服务器极速下载。
              </p>
            </div>

            <DialogFooter className="pt-2">
              <Button type="button" variant="outline" size="sm" onClick={() => setCreateOpen(false)} className="h-8 text-xs">
                取消
              </Button>
              <Button type="submit" size="sm" disabled={submitting} className="h-8 text-xs">
                {submitting ? "正在保存与上传..." : "确认添加"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </Card>
  )
}

function TelegramSupportSettingsCard() {
  const [enabled, setEnabled] = useState(false)
  const [telegramUrl, setTelegramUrl] = useState("")
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    fetch("/api/proxy/settings/support")
      .then((r) => r.json())
      .then((d) => {
        if (d.ok) {
          setEnabled(!!d.enabled)
          setTelegramUrl(d.telegram_url || "")
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const handleSave = async () => {
    setSaving(true)
    try {
      const res = await fetch("/api/proxy/settings/support", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled, telegram_url: telegramUrl }),
      })
      const d = await res.json()
      if (d.ok) {
        toast.success(d.message || "客服设置已成功保存")
      } else {
        toast.error(d.message || "保存失败")
      }
    } catch (e: any) {
      toast.error(e.message || "网络请求失败")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Card className="gap-4 p-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b pb-4">
        <div className="space-y-1">
          <h3 className="text-sm font-bold flex items-center gap-2">
            <Send className="size-4 text-[#229ED9] fill-[#229ED9]" /> 客服与支持设置 (Telegram)
          </h3>
          <p className="text-xs text-muted-foreground">
            配置官方 Telegram 客服入口。默认关闭（用户界面 100% 隐藏）；开启后在用户控制台展示联系通道。
          </p>
        </div>
        <Badge
          variant={enabled ? "secondary" : "outline"}
          className={enabled ? "bg-[#229ED9]/10 text-[#229ED9] border-[#229ED9]/30" : ""}
        >
          {enabled ? "已开启" : "已隐藏"}
        </Badge>
      </div>

      <div className="space-y-4 pt-1">
        <div className="flex items-center gap-2 text-sm">
          <Switch checked={enabled} onCheckedChange={setEnabled} id="support-tg-toggle" />
          <Label htmlFor="support-tg-toggle" className="cursor-pointer text-xs font-medium">
            在用户中心与登录界面展示 Telegram 客服联系入口
          </Label>
        </div>

        {enabled && (
          <div className="grid gap-2">
            <Label className="text-xs font-medium">Telegram 客服链接 / 用户名</Label>
            <Input
              value={telegramUrl}
              onChange={(e) => setTelegramUrl(e.target.value)}
              placeholder="https://t.me/your_telegram_bot 或 @your_customer_service"
              className="text-xs h-9 font-mono"
            />
            <p className="text-[11px] text-muted-foreground">
              用户点击客服入口后将直接唤起 Telegram 客户端跳转至对应客服聊天对话。
            </p>
          </div>
        )}

        <div>
          <Button size="sm" onClick={handleSave} disabled={saving || loading} className="text-xs h-8">
            {saving ? "保存中..." : "保存客服设置"}
          </Button>
        </div>
      </div>
    </Card>
  )
}

function SmtpSettingsCard() {
  const [smtpEnabled, setSmtpEnabled] = useState(false)
  const [registerEnabled, setRegisterEnabled] = useState(true)
  const [smtpHost, setSmtpHost] = useState("smtp.gmail.com")
  const [smtpPort, setSmtpPort] = useState(465)
  const [smtpSsl, setSmtpSsl] = useState(true)
  const [smtpUser, setSmtpUser] = useState("")
  const [smtpPass, setSmtpPass] = useState("")
  const [smtpFromName, setSmtpFromName] = useState("HHUB")
  const [siteName, setSiteName] = useState("HHUB-加速中心")

  const [testEmail, setTestEmail] = useState("")
  const [testDialogOpen, setTestDialogOpen] = useState(false)
  const [testing, setTesting] = useState(false)
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    fetch("/api/proxy/settings/smtp")
      .then((r) => r.json())
      .then((d) => {
        if (d.ok) {
          setSmtpEnabled(!!d.smtp_enabled)
          setRegisterEnabled(!!d.register_enabled)
          if (d.smtp_host) setSmtpHost(d.smtp_host)
          if (d.smtp_port) setSmtpPort(d.smtp_port)
          setSmtpSsl(d.smtp_ssl !== false)
          if (d.smtp_user) setSmtpUser(d.smtp_user)
          if (d.smtp_pass) setSmtpPass(d.smtp_pass)
          if (d.smtp_from_name) setSmtpFromName(d.smtp_from_name)
          if (d.site_name) setSiteName(d.site_name)
          if (d.smtp_user && !testEmail) setTestEmail(d.smtp_user)
        }
      })
      .catch(() => {})
      .finally(() => setLoading(false))
  }, [])

  const handleSave = async () => {
    setSaving(true)
    try {
      const res = await fetch("/api/proxy/settings/smtp", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          smtp_enabled: smtpEnabled,
          register_enabled: registerEnabled,
          smtp_host: smtpHost,
          smtp_port: smtpPort,
          smtp_ssl: smtpSsl,
          smtp_user: smtpUser,
          smtp_pass: smtpPass,
          smtp_from_name: smtpFromName,
          site_name: siteName,
        }),
      })
      const d = await res.json()
      if (d.ok) {
        toast.success(d.message || "SMTP 发信配置已成功保存")
      } else {
        toast.error(d.message || "保存失败")
      }
    } catch (e: any) {
      toast.error(e.message || "网络请求失败")
    } finally {
      setSaving(false)
    }
  }

  const handleTestSend = async () => {
    if (!testEmail) {
      toast.error("请输入测试接收邮箱地址")
      return
    }
    setTesting(true)
    try {
      const res = await fetch("/api/proxy/smtp/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ to_email: testEmail }),
      })
      const d = await res.json()
      if (d.ok) {
        toast.success(d.message || "测试邮件已发送，请查收！")
        setTestDialogOpen(false)
      } else {
        toast.error(d.message || "测试发信失败")
      }
    } catch (e: any) {
      toast.error(e.message || "网络请求失败")
    } finally {
      setTesting(false)
    }
  }

  return (
    <Card className="gap-4 p-5">
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b pb-4">
        <div className="space-y-1">
          <h3 className="text-sm font-bold flex items-center gap-2">
            <Mail className="size-4 text-primary" /> 邮箱注册与 SMTP 邮件服务配置
          </h3>
          <p className="text-xs text-muted-foreground">
            配置 SMTP 邮箱发信凭据，用于用户自主注册账号与忘记密码时发送 6 位数字验证码邮件。
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant="outline"
            onClick={() => setTestDialogOpen(true)}
            className="text-xs h-8 gap-1.5"
          >
            <Send className="size-3" /> 测试发信
          </Button>
          <Badge
            variant={smtpEnabled ? "secondary" : "outline"}
            className={smtpEnabled ? "bg-emerald-500/10 text-emerald-600 border-emerald-500/30" : ""}
          >
            {smtpEnabled ? "发信已启用" : "发信未启用"}
          </Badge>
        </div>
      </div>

      <div className="space-y-4 pt-1">
        <div className="flex flex-wrap items-center gap-6 text-sm">
          <div className="flex items-center gap-2">
            <Switch checked={registerEnabled} onCheckedChange={setRegisterEnabled} id="register-toggle" />
            <Label htmlFor="register-toggle" className="cursor-pointer text-xs font-medium">
              开放用户自主邮箱注册
            </Label>
          </div>

          <div className="flex items-center gap-2">
            <Switch checked={smtpEnabled} onCheckedChange={setSmtpEnabled} id="smtp-toggle" />
            <Label htmlFor="smtp-toggle" className="cursor-pointer text-xs font-medium">
              启用 SMTP 邮件发信服务
            </Label>
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2 pt-2">
          <Field label="SMTP 服务器主机" hint="例如: smtp.gmail.com 或 smtp.qq.com">
            <Input
              value={smtpHost}
              onChange={(e) => setSmtpHost(e.target.value)}
              placeholder="smtp.gmail.com"
              className="text-xs h-9 font-mono"
            />
          </Field>

          <Field label="SMTP 端口与加密" hint="SSL 推荐 465；STARTTLS 推荐 587">
            <div className="flex gap-2">
              <Input
                type="number"
                value={smtpPort}
                onChange={(e) => setSmtpPort(parseInt(e.target.value) || 465)}
                className="text-xs h-9 font-mono w-28"
              />
              <div className="flex items-center gap-2 px-3 border rounded-md text-xs bg-muted/20">
                <Switch checked={smtpSsl} onCheckedChange={setSmtpSsl} id="smtp-ssl-toggle" />
                <Label htmlFor="smtp-ssl-toggle" className="cursor-pointer text-xs">
                  {smtpSsl ? "SSL 协议 (465)" : "TLS 协议 (587)"}
                </Label>
              </div>
            </div>
          </Field>

          <Field label="发信邮箱账号" hint="Google 邮箱或 QQ/163 账号">
            <Input
              value={smtpUser}
              onChange={(e) => {
                setSmtpUser(e.target.value)
                if (!testEmail) setTestEmail(e.target.value)
              }}
              placeholder="your_email@gmail.com"
              className="text-xs h-9 font-mono"
            />
          </Field>

          <Field label="授权密码 / 应用专用密码" hint="Google 邮箱需在 Google 账户安全性中生成 16 位「应用专用密码」">
            <Input
              type="password"
              value={smtpPass}
              onChange={(e) => setSmtpPass(e.target.value)}
              placeholder="••••••••••••••••"
              className="text-xs h-9 font-mono"
            />
          </Field>

          <Field label="发信人名称" hint="邮件中显示的发件人署名">
            <Input
              value={smtpFromName}
              onChange={(e) => setSmtpFromName(e.target.value)}
              placeholder="HHUB 安全中心"
              className="text-xs h-9"
            />
          </Field>

          <Field label="站点安全名称" hint="验证码邮件正文中引用的系统名称">
            <Input
              value={siteName}
              onChange={(e) => setSiteName(e.target.value)}
              placeholder="HHUB-加速中心"
              className="text-xs h-9"
            />
          </Field>
        </div>

        <div className="flex items-center gap-3 pt-2">
          <Button size="sm" onClick={handleSave} disabled={saving || loading} className="text-xs h-8">
            {saving ? "保存中..." : "保存 SMTP 设置"}
          </Button>
          <Button size="sm" variant="outline" onClick={() => setTestDialogOpen(true)} className="text-xs h-8">
            发送测试邮件
          </Button>
        </div>
      </div>

      <Dialog open={testDialogOpen} onOpenChange={setTestDialogOpen}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle className="text-sm font-semibold">SMTP 发信测试</DialogTitle>
            <DialogDescription className="text-xs">
              输入接收测试邮件的邮箱，验证服务器 SMTP 配置连通性
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="space-y-1.5">
              <Label className="text-xs">接收测试邮箱</Label>
              <Input
                type="email"
                value={testEmail}
                onChange={(e) => setTestEmail(e.target.value)}
                placeholder="test@example.com"
                className="text-xs h-9"
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" size="sm" onClick={() => setTestDialogOpen(false)} className="text-xs h-8">
              取消
            </Button>
            <Button size="sm" onClick={handleTestSend} disabled={testing || !testEmail} className="text-xs h-8 gap-1.5">
              {testing ? "正在发送..." : "发送测试"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </Card>
  )
}

const TEXTAREA =
  "w-full min-w-0 rounded-md border border-input bg-transparent px-3 py-2 font-mono text-xs shadow-xs outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-[3px] focus-visible:ring-ring/50 dark:bg-input/30"

// One offline alert, filled in the way the hub fills a template: in a single pass,
// JSON-escaped for the webhook body. Previews only; nothing here is sent.
const SAMPLE_NOTE: Record<string, string> = {
  event: "offline",
  node: "香港 · 甲商家",
  title: "🔴 香港 · 甲商家 离线",
  message: "最后上报 09-15 20:13 +08:00",
  time: "09-15 20:16 +08:00",
}

const PLACEHOLDERS = "{{title}} {{message}} {{node}} {{event}} {{site}} {{time}}"

function TemplatePreview({ template, site, json = false }: { template: string; site: string; json?: boolean }) {
  if (!template.trim()) return <p className="text-xs text-muted-foreground">留空保存即恢复默认模板</p>
  const values = { ...SAMPLE_NOTE, site }
  let out = template.replace(/\{\{(event|node|title|message|site|time)\}\}/g, (_, key: keyof typeof values) =>
    json ? JSON.stringify(values[key]).slice(1, -1) : values[key],
  )
  if (json) {
    try {
      out = JSON.stringify(JSON.parse(out), null, 2)
    } catch {
      return (
        <p className="rounded-md bg-destructive/10 px-3 py-2 text-xs text-destructive">
          代入后不是合法 JSON，保存会被拒绝。占位符要写在引号里，例如 "text": "{"{{title}}"}"
        </p>
      )
    }
  }
  return (
    <div className="space-y-1">
      <div className="text-xs text-muted-foreground">预览（以一条离线通知为例）</div>
      <pre className="overflow-x-auto rounded-md bg-muted/50 px-3 py-2 font-mono text-xs whitespace-pre-wrap break-all">{out}</pre>
    </div>
  )
}

// A channel's form, collapsed until needed. The summary carries whether the
// channel is configured, so the closed card still answers the common question.
function ChannelCard({ title, configured, children }: { title: string; configured: boolean; children: React.ReactNode }) {
  return (
    <Card className="p-5">
      <details className="group">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-3 rounded-md outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50 [&::-webkit-details-marker]:hidden">
          <span className="flex items-center gap-2 text-sm font-medium">
            <ChevronRight className="size-4 text-muted-foreground transition-transform group-open:rotate-90" />
            {title}
          </span>
          <Badge variant={configured ? "secondary" : "outline"}>{configured ? "已配置" : "未配置"}</Badge>
        </summary>
        <div className="mt-4 space-y-4">{children}</div>
      </details>
    </Card>
  )
}

// Offline alerts are opt-in per node, so turning them on for a fleet needs one
// place rather than one dialog per node.
function OfflineNodes({ nodes, refresh }: { nodes: Node[]; refresh: () => void }) {
  const [busy, setBusy] = useState(false)

  async function apply(targets: Node[], on: boolean) {
    setBusy(true)
    try {
      // Awaited in turn, the requests would cost one round trip per node, and
      // the two-second stream would render each one as it lands.
      await Promise.all(
        targets
          .filter((n) => !!n.notify !== on)
          .map((n) => api(`/nodes/${n.id}`, { method: "PUT", body: JSON.stringify({ notify: on }) })),
      )
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      refresh()
      setBusy(false)
    }
  }

  const enabled = new Set(nodes.filter((n) => n.notify).map((n) => n.id))
  return (
    <Card className="gap-4 p-5">
      <div>
        <h3 className="text-sm font-medium">离线通知</h3>
        <p className="mt-1 text-xs text-muted-foreground">按服务器打开，默认关。已打开 {enabled.size} / {nodes.length} 台</p>
      </div>
      <NodePicker nodes={nodes} chosen={enabled} onPick={apply} disabled={busy} />
    </Card>
  )
}

function Notify({ nodes, refresh }: { nodes: Node[]; refresh: () => void }) {
  const { s, set, save } = useSettings()
  const [testing, setTesting] = useState(false)
  if (!s) return null
  const text = (k: string) => String(s[k] ?? "")
  // A credential is sent only when something was typed: the field starts empty
  // because the hub never returns the stored value.
  const typed = (...keys: string[]) =>
    Object.fromEntries(keys.filter((k) => typeof s[k] === "string" && s[k] !== "").map((k) => [k, text(k)]))
  const secretHint = (k: string) => (s[`${k}_set`] ? "已设置，留空不变" : "未设置")

  async function test() {
    setTesting(true)
    try {
      const { sent } = await api<{ sent: string[] }>("/notify/test", { method: "POST" })
      toast.success(`测试通知已发送：${sent.join("、")}`)
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setTesting(false)
    }
  }

  return (
    <div className="space-y-4">
      <Card className="gap-4 p-5">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <h3 className="text-sm font-medium">通知渠道</h3>
            <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
              Telegram 和 Webhook 配了哪个就发哪个，也可以同时用。离线通知在下方按服务器打开；流量和到期提醒对填了额度、到期日的服务器生效。
            </p>
          </div>
          <Button size="sm" variant="secondary" disabled={testing} onClick={test}>
            <Send /> {testing ? "发送中…" : "发送测试"}
          </Button>
        </div>
      </Card>

      <ChannelCard title="Telegram" configured={!!s.notify_telegram_token_set && text("notify_telegram_chat") !== ""}>
        <div className="rounded-lg border border-primary/20 bg-primary/5 p-3 text-xs text-muted-foreground flex items-center gap-2 mb-2">
          <span>🛡️ <strong>静默无扰守护模式：</strong>保存后后台守护进程将自动常驻监测全部服务器。任何服务器离线超 75 秒或恢复上线时，自动静默推送信令通知，0 界面负担。</span>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Bot Token" hint={secretHint("notify_telegram_token")}>
            <Input
              type="password"
              autoComplete="off"
              placeholder={s.notify_telegram_token_set ? "••••••••" : "123456:ABC-DEF…"}
              value={text("notify_telegram_token")}
              onChange={(e) => set("notify_telegram_token", e.target.value)}
            />
          </Field>
          <Field label="Chat ID" hint="数字 ID，群组是负数；公开频道可填 @频道名">
            <Input value={text("notify_telegram_chat")} onChange={(e) => set("notify_telegram_chat", e.target.value)} placeholder="-1001234567890" />
          </Field>
        </div>
        <Field label="消息模板" hint={`纯文本。占位符 ${PLACEHOLDERS}`}>
          <textarea rows={3} className={TEXTAREA} value={text("notify_telegram_text")} onChange={(e) => set("notify_telegram_text", e.target.value)} />
        </Field>
        <TemplatePreview template={text("notify_telegram_text")} site={text("site_name") || "HHUB"} />
        <div className="flex flex-wrap items-center gap-2">
          <Button
            size="sm"
            onClick={() =>
              save({
                notify_telegram_chat: text("notify_telegram_chat"),
                notify_telegram_text: text("notify_telegram_text"),
                ...typed("notify_telegram_token"),
              })
            }
          >
            保存 Telegram
          </Button>
          <Button
            size="sm"
            variant="outline"
            disabled={testing || (!s.notify_telegram_token_set && !text("notify_telegram_token"))}
            onClick={async () => {
              try {
                const res = await fetch("/api/proxy/notify/telegram/test", {
                  method: "POST",
                  headers: { "Content-Type": "application/json" },
                  body: JSON.stringify({
                    token: text("notify_telegram_token"),
                    chat_id: text("notify_telegram_chat")
                  })
                })
                const data = await res.json()
                if (data.ok) {
                  toast.success(data.message || "测试通知已成功送达您的 Telegram！")
                } else {
                  toast.error(data.error || "发送测试失败，请检查 Token 与 Chat ID")
                }
              } catch (e: any) {
                toast.error(e.message || "网络请求失败")
              }
            }}
          >
            <Send className="size-3.5 mr-1" /> 测试发送
          </Button>
          {s.notify_telegram_token_set && (
            <Button size="sm" variant="ghost" onClick={() => save({ notify_telegram_token: "", notify_telegram_chat: "" })}>
              清除
            </Button>
          )}
        </div>
      </ChannelCard>

      <ChannelCard title="Webhook" configured={!!s.notify_webhook_url_set}>
        <Field label="URL" hint={secretHint("notify_webhook_url")}>
          <Input
            type="password"
            autoComplete="off"
            placeholder={s.notify_webhook_url_set ? "••••••••" : "https://…"}
            value={text("notify_webhook_url")}
            onChange={(e) => set("notify_webhook_url", e.target.value)}
          />
        </Field>
        <Field label="请求头" hint={`可选，一行一个。${s.notify_webhook_headers_set ? "已设置，留空不变" : ""}`}>
          <textarea
            rows={2}
            className={TEXTAREA}
            placeholder={s.notify_webhook_headers_set ? "••••••••" : "Authorization: Bearer xxx"}
            value={text("notify_webhook_headers")}
            onChange={(e) => set("notify_webhook_headers", e.target.value)}
          />
        </Field>
        <Field label="请求体" hint={`以 POST 发送，Content-Type 为 application/json。占位符 ${PLACEHOLDERS}，须写在引号内`}>
          <textarea rows={4} className={TEXTAREA} value={text("notify_webhook_body")} onChange={(e) => set("notify_webhook_body", e.target.value)} />
        </Field>
        <TemplatePreview template={text("notify_webhook_body")} site={text("site_name") || "HHUB"} json />
        <div className="flex gap-2">
          <Button
            size="sm"
            onClick={() => save({ notify_webhook_body: text("notify_webhook_body"), ...typed("notify_webhook_url", "notify_webhook_headers") })}
          >
            保存 Webhook
          </Button>
          {s.notify_webhook_headers_set && (
            <Button size="sm" variant="ghost" onClick={() => save({ notify_webhook_headers: "" })}>
              清除请求头
            </Button>
          )}
          {s.notify_webhook_url_set && (
            <Button size="sm" variant="ghost" onClick={() => save({ notify_webhook_url: "", notify_webhook_headers: "" })}>
              清除
            </Button>
          )}
        </div>
      </ChannelCard>

      <OfflineNodes nodes={nodes} refresh={refresh} />

      <Card className="gap-4 p-5">
        <h3 className="text-sm font-medium">事件</h3>
        <div className="grid gap-4 sm:grid-cols-3">
          <Field label="离线宽限期（分钟）" hint="断开超过这么久才算离线，1–30">
            <Input type="number" min={1} max={30}value={text("notify_grace")} onChange={(e) => set("notify_grace", e.target.value)} />
          </Field>
          <Field label="流量提醒（%）" hint="本期用量达到该比例和 100% 时各提醒一次，0 关闭">
            <Input type="number" min={0} max={100} value={text("notify_traffic")} onChange={(e) => set("notify_traffic", e.target.value)} />
          </Field>
          <Field label="到期提醒（天）" hint="每天 9 点汇总这么多天内到期的服务器，自动续期时也提醒，0 关闭">
            <Input type="number" min={0} max={365} value={text("notify_expiry")} onChange={(e) => set("notify_expiry", e.target.value)} />
          </Field>
        </div>
        <div className="flex items-center gap-2 text-sm">
          <Switch aria-labelledby="notify-login-label" checked={s.notify_login !== "off"} onCheckedChange={(v) => set("notify_login", v ? "on" : "off")} />
          <span id="notify-login-label">登录后台时提醒</span>
        </div>
        <div>
          <Button
            size="sm"
            onClick={() =>
              save({
                notify_grace: text("notify_grace"),
                notify_traffic: text("notify_traffic"),
                notify_expiry: text("notify_expiry"),
                notify_login: s.notify_login === "off" ? "off" : "on",
              })
            }
          >
            保存事件设置
          </Button>
        </div>
      </Card>

      {/* 服务器到期 Telegram 自动推送提醒设置 */}
      <ServerExpirySettingsCard />

      {/* Telegram 双向交互运维机器人卡片 */}
      <Card className="p-5 bg-card/60">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="size-9 rounded-lg bg-sky-500/10 border border-sky-500/30 flex items-center justify-center text-sky-500 shrink-0">
              <Bot className="size-5" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold">Telegram 双向交互式运维机器人</h3>
                {s.notify_telegram_token_set && text("notify_telegram_chat") !== "" ? (
                  <Badge variant="outline" className="border-emerald-500/30 bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 text-[10px] px-1.5 py-0">
                    🟢 已就绪
                  </Badge>
                ) : (
                  <Badge variant="outline" className="border-amber-500/30 bg-amber-500/10 text-amber-600 dark:text-amber-400 text-[10px] px-1.5 py-0">
                    ⚪ 待配置
                  </Badge>
                )}
              </div>
              <p className="text-xs text-muted-foreground mt-0.5">
                无需打开面板，在 Telegram 发送指令即可秒级感知全网状态、发起巡检或打包备份数据库
              </p>
            </div>
          </div>
        </div>

        {/* 交互指令说明胶囊 */}
        <div className="mt-4 grid grid-cols-2 sm:grid-cols-4 gap-2 pt-3 border-t border-border/30 text-xs">
          <div className="p-2 rounded-md bg-muted/40 border border-border/30">
            <div className="font-mono font-semibold text-primary">/status</div>
            <div className="text-[11px] text-muted-foreground mt-0.5">全网大盘与服务器负载概览</div>
          </div>
          <div className="p-2 rounded-md bg-muted/40 border border-border/30">
            <div className="font-mono font-semibold text-emerald-600 dark:text-emerald-400">/test</div>
            <div className="text-[11px] text-muted-foreground mt-0.5">手机即时触发全节点连通测试</div>
          </div>
          <div className="p-2 rounded-md bg-muted/40 border border-border/30">
            <div className="font-mono font-semibold text-purple-600 dark:text-purple-400">/backup</div>
            <div className="text-[11px] text-muted-foreground mt-0.5">立即打包并发送数据库备份文件</div>
          </div>
          <div className="p-2 rounded-md bg-muted/40 border border-border/30">
            <div className="font-mono font-semibold text-sky-600 dark:text-sky-400">/nodes</div>
            <div className="text-[11px] text-muted-foreground mt-0.5">查询各节点实时延迟与感知状态</div>
          </div>
        </div>
      </Card>
    </div>
  )
}

// The two ways into this panel, on their own page: the GitHub identity it trusts
// and the password that works when GitHub does not.
type Session = { id: string; current: boolean; created_at: number }

function Sessions() {
  const [rows, setRows] = useState<Session[] | null>(null)
  const [busy, setBusy] = useState("")

  const load = () => api<Session[]>("/sessions").then(setRows).catch((e: Error) => toast.error(e.message))
  useEffect(() => { load() }, [])

  async function remove(id: string) {
    setBusy(id)
    try {
      await api(`/sessions/${id}`, { method: "DELETE" })
      toast.success("已删除会话")
      load()
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setBusy("")
    }
  }

  if (!rows) return null
  return (
    <Card className="gap-4 p-5">
      <div>
        <h3 className="text-sm font-medium">登录会话</h3>
        <p className="mt-1 text-xs text-muted-foreground">
          每次登录一条，14 天后过期。删除后该设备下一次请求就被登出。
        </p>
      </div>
      <div className="divide-y">
        {rows.map((s) => (
          <div key={s.id} className="flex items-center justify-between gap-3 py-2.5 first:pt-0 last:pb-0">
            <div className="flex min-w-0 items-center gap-2 text-sm">
              <span className="tnum">{new Date(s.created_at * 1000).toLocaleString()}</span>
              {s.current && <Badge variant="secondary">当前设备</Badge>}
            </div>
            {/* 当前会话没有删除按钮：右上角的退出登录做的就是这件事，而在这里删
                只会让已经渲染好的面板以为自己还登着。 */}
            {!s.current && (
              <Button size="icon" variant="ghost" disabled={!!busy} onClick={() => remove(s.id)}>
                <Trash2 />
              </Button>
            )}
          </div>
        ))}
      </div>
    </Card>
  )
}

function Security({ site }: { site: string }) {
  const { s, set, save } = useSettings()
  const [password, setPassword] = useState("")
  if (!s) return null
  const callback = `${site}/api/auth/github/callback`

  return (
    <div className="space-y-4">
      <Sessions />

      <Card className="gap-4 p-5">
        <div>
          <h3 className="text-sm font-medium">GitHub 单点登录</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            OAuth App 回调地址 <code className="rounded bg-muted px-1">{callback}</code>
          </p>
        </div>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Client ID">
            <Input value={String(s.github_client_id ?? "")} onChange={(e) => set("github_client_id", e.target.value)} />
          </Field>
          <Field label="Client Secret" hint={s.github_secret_set ? "已设置，留空不变" : "未设置"}>
            <Input type="password" placeholder={s.github_secret_set ? "••••••••" : ""} onChange={(e) => set("github_client_secret", e.target.value)} />
          </Field>
        </div>
        {String(s.github_client_id ?? "") !== "" && String(s.github_allowed_users ?? "").trim() === "" && (
          <p className="rounded-md bg-destructive/10 px-3 py-2 text-sm text-destructive">
            白名单为空，GitHub 登录拒绝所有人。填入用户名并保存后生效。
          </p>
        )}
        <Field label="允许登录的 GitHub 用户名" hint="逗号分隔。留空 = 拒绝所有人，不是放行所有人">
          <Input value={String(s.github_allowed_users ?? "")} onChange={(e) => set("github_allowed_users", e.target.value)} placeholder="GitHub 用户名" />
        </Field>
        <div>
          <Button
            size="sm"
            onClick={() => {
              const patch: Record<string, string> = {
                github_client_id: String(s.github_client_id ?? ""),
                github_allowed_users: String(s.github_allowed_users ?? ""),
              }
              if (typeof s.github_client_secret === "string" && s.github_client_secret) {
                patch.github_client_secret = s.github_client_secret
              }
              save(patch)
            }}
          >
            保存 GitHub 设置
          </Button>
        </div>
      </Card>

      <Card className="gap-4 p-5">
        <div>
          <h3 className="text-sm font-medium">应急密码</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            GitHub 不可用时的备用入口。修改后其它设备登录立即失效，当前设备不受影响。
          </p>
        </div>
        <Field label="新密码" hint="至少 12 位">
          <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} autoComplete="new-password" />
        </Field>
        <div>
          <Button
            size="sm"
            disabled={password.length < 12}
            onClick={() => save({ admin_password: password }).then(() => setPassword(""))}
          >
            修改密码
          </Button>
        </div>
      </Card>
    </div>
  )
}

type DbInfo = {
  path: string
  size: number
  wal: number
  free: number
  /** Timestamp of the earliest history row, null on a database with none. */
  oldest: number | null
  retention: number
  rows: Record<string, number>
}

// The only two tables whose row count indicates anything about size. Every other
// holds one row per node or per key.
const DB_ROWS: [string, string][] = [
  ["metric", "历史明细"],
  ["ping_record", "延迟记录"],
]

function TelegramBackupCard({ go, onOpenPicker }: { go?: (to: string) => void; onOpenPicker?: () => void }) {
  const [config, setConfig] = useState<{
    enabled: boolean
    interval_hours: number
    custom_chat: string
    default_chat: string
    has_token: boolean
    last_time: number
    last_status: string
  } | null>(null)
  const [enabled, setEnabled] = useState(false)
  const [intervalHours, setIntervalHours] = useState("24")
  const [customChat, setCustomChat] = useState("")
  const [saving, setSaving] = useState(false)
  const [running, setRunning] = useState(false)

  const loadConfig = () => {
    fetch("/api/proxy/backup/telegram/config")
      .then((r) => r.json())
      .then((res) => {
        if (res.ok) {
          setConfig(res)
          setEnabled(res.enabled)
          setIntervalHours(String(res.interval_hours || 24))
          setCustomChat(res.custom_chat || "")
        }
      })
      .catch(() => {})
  }

  useEffect(() => {
    loadConfig()
  }, [])

  const tgConfigured = Boolean(config?.has_token && (config?.default_chat || customChat.trim()))

  const handleSave = async () => {
    setSaving(true)
    try {
      const res = await fetch("/api/proxy/backup/telegram/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          enabled,
          interval_hours: parseInt(intervalHours, 10) || 24,
          custom_chat: customChat.trim(),
        }),
      }).then((r) => r.json())
      if (res.ok) {
        toast.success("定时备份设置已保存")
        loadConfig()
      } else {
        toast.error(res.error || "保存失败")
      }
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setSaving(false)
    }
  }

  const handleRunNow = async () => {
    setRunning(true)
    try {
      const res = await fetch("/api/proxy/backup/telegram/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ custom_chat: customChat.trim() }),
      }).then((r) => r.json())
      if (res.ok) {
        toast.success(res.message || "备份已成功推送至 Telegram！")
        loadConfig()
      } else {
        toast.error(res.error || "备份发送失败")
      }
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setRunning(false)
    }
  }

  const formatTime = (ts?: number) => {
    if (!ts) return "尚未执行"
    return new Date(ts * 1000).toLocaleString("zh-CN", { hour12: false })
  }

  const isConfigured = Boolean(enabled && tgConfigured)

  return (
    <Card className="gap-4 p-5">
      <div className="flex items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <Database className="size-4 text-primary" />
            <h3 className="text-sm font-medium">Telegram 机器人定时自动备份</h3>
          </div>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            利用「通知」中配置的 Telegram 机器人，按指定周期自动将系统 SQLite 完整数据库（含节点、用户、设置及许可证数据）打包为 Gzip 镜像压缩包（.db.gz）推送到指定的 Telegram Chat。
          </p>
        </div>
        <Badge variant={isConfigured ? "secondary" : "outline"} className="shrink-0">
          {isConfigured ? "已开启自动备份" : "未开启"}
        </Badge>
      </div>

      {!tgConfigured && config !== null && (
        <div className="rounded-lg border border-amber-500/20 bg-amber-500/10 p-3 text-xs text-amber-500 flex flex-wrap items-center justify-between gap-2">
          <span>⚠️ 提示：自动备份功能复用「通知」页面中配置的 Telegram 机器人。当前尚未检测到有效的 Telegram 配置。</span>
          {go && (
            <Button
              size="sm"
              variant="outline"
              className="h-7 text-xs border-amber-500/30 text-amber-500 hover:bg-amber-500/20 cursor-pointer"
              onClick={() => go("/admin/notify")}
            >
              去配置 Telegram
            </Button>
          )}
        </div>
      )}

      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="定时自动备份" hint="后台守护进程常驻独立调度，服务器重启自动生效">
          <div className="flex h-9 items-center gap-3">
            <Switch
              id="backup-enabled-switch"
              checked={enabled}
              onCheckedChange={setEnabled}
              disabled={!tgConfigured}
            />
            <Label htmlFor="backup-enabled-switch" className="cursor-pointer text-sm">
              {enabled ? "开启自动定时备份" : "已关闭定时备份"}
            </Label>
          </div>
        </Field>

        <Field label="备份执行周期" hint="推荐设置为每天一次">
          <Select value={intervalHours} onValueChange={setIntervalHours} disabled={!enabled}>
            <SelectTrigger>
              <SelectValue placeholder="选择备份周期" />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="6">每 6 小时备份一次</SelectItem>
              <SelectItem value="12">每 12 小时备份一次</SelectItem>
              <SelectItem value="24">每天备份一次 (推荐)</SelectItem>
              <SelectItem value="72">每 3 天备份一次</SelectItem>
              <SelectItem value="168">每周备份一次</SelectItem>
            </SelectContent>
          </Select>
        </Field>

        <Field
          label="专属接收 Chat ID（可选）"
          hint={config?.default_chat ? `留空默认使用「通知」设置中的 Chat ID: ${config.default_chat}` : "留空则使用「通知」设置中配置的 Chat ID"}
        >
          <Input
            placeholder={config?.default_chat || "-100xxxxxxxxxx"}
            value={customChat}
            onChange={(e) => setCustomChat(e.target.value)}
          />
        </Field>

        <Field label="最近备份状态" hint={config?.last_status ? `运行记录: ${config.last_status}` : "暂无历史备份记录"}>
          <div className="flex h-9 items-center text-xs text-muted-foreground">
            <span className="font-mono">上次备份: {formatTime(config?.last_time)}</span>
          </div>
        </Field>
      </div>

      <div className="flex flex-wrap items-center gap-2 pt-1">
        <Button size="sm" onClick={handleSave} disabled={saving}>
          {saving ? "保存中…" : "保存备份设置"}
        </Button>
        <Button
          size="sm"
          variant="secondary"
          disabled={running || !tgConfigured}
          onClick={handleRunNow}
        >
          <Send className="mr-1 size-3.5" />
          {running ? "正在打包并发送至 TG…" : "立即备份并推送到 TG"}
        </Button>
        <Button size="sm" variant="outline" asChild>
          <a href="/api/proxy/backup/download" download>
            <Download className="mr-1 size-3.5" />
            导出下载镜像副本 (.db.gz)
          </a>
        </Button>
        {onOpenPicker && (
          <Button size="sm" variant="secondary" onClick={onOpenPicker}>
            <Upload className="mr-1 size-3.5" />
            导入恢复备份包 (.db / .db.gz)
          </Button>
        )}
      </div>

      <div className="rounded-lg border bg-muted/40 p-3 text-xs text-muted-foreground space-y-1">
        <div className="font-medium text-foreground flex items-center gap-1.5">
          <span>💡 备份文件如何导入与还原？</span>
        </div>
        <p>
          从 Telegram 机器人下载推送的 <code>monitor_backup_*.db.gz</code> 文件后，可直接点击上方的<strong>「导入恢复备份包」</strong>或「备份」卡片中的<strong>「导入备份」</strong>按钮上传。系统已全面支持 <code>.db</code> 与 <code>.db.gz</code>，将在浏览器本地自动完成解压验算并覆盖恢复，所有服务器、代理节点、用户及许可证数据即刻恢复。
        </p>
      </div>
    </Card>
  )
}

function Data({ go }: { go?: (to: string) => void }) {
  const [info, setInfo] = useState<DbInfo | null>(null)
  const [busy, setBusy] = useState("")
  const [confirm, setConfirm] = useState<"vacuum" | null>(null)
  const [pending, setPending] = useState<File | null>(null)
  const [sent, setSent] = useState(0)
  // Closing the dialog must stop the upload rather than merely hide it: restore
  // is the one irreversible action here, and it takes minutes on a large
  // backup.
  const abort = useRef<AbortController | null>(null)
  const picker = useRef<HTMLInputElement>(null)

  const load = () => api<DbInfo>("/db").then(setInfo).catch((e: Error) => toast.error(e.message))
  useEffect(() => { load() }, [])

  async function vacuum() {
    setBusy("vacuum")
    try {
      const { pruned, freed } = await api<{ pruned: number; freed: number }>("/db/vacuum", { method: "POST" })
      toast.success(`已清理 ${pruned} 行，回收 ${bytes(freed)}`)
      load()
    } catch (e) {
      toast.error((e as Error).message)
    } finally {
      setBusy("")
      setConfirm(null)
    }
  }

  async function restore(file: File) {
    setBusy("restore")
    setSent(0)
    abort.current = new AbortController()
    try {
      let uploadFile = file
      // 支持直接导入来自 Telegram 机器人推送的 .db.gz 镜像备份
      if (file.name.endsWith(".gz") || file.name.endsWith(".gzip")) {
        toast.info("检测到 Gzip 压缩备份包，正在解压校验...")
        try {
          const ds = new DecompressionStream("gzip")
          const decompressedStream = file.stream().pipeThrough(ds)
          const res = new Response(decompressedStream)
          const blob = await res.blob()
          const uncompressedName = file.name.replace(/\.gz$/i, "").replace(/\.gzip$/i, "")
          uploadFile = new File([blob], uncompressedName.endsWith(".db") ? uncompressedName : `${uncompressedName}.db`, {
            type: "application/octet-stream",
          })
        } catch (decompErr) {
          throw new Error("解压 .gz 备份文件失败，请确认文件是否完整: " + (decompErr as Error).message)
        }
      }
      await upload("/db/restore", uploadFile, setSent, abort.current.signal)
      toast.success("已恢复，正在重新加载")
      // Every node, setting and session on the page came from the database just
      // replaced.
      setTimeout(() => location.reload(), 800)
    } catch (e) {
      // Aborting partway is not a failure: the hub replaces nothing until the
      // last chunk, so the original database remains.
      const aborted = (e as Error).name === "AbortError"
      if (aborted) toast.info("已取消，数据库没有改动")
      else toast.error((e as Error).message)
      setBusy("")
    }
    setPending(null)
  }

  if (!info) return null
  const stat = (label: string, value: string) => (
    <div key={label}>
      <div className="text-xs text-muted-foreground">{label}</div>
      <div className="tnum mt-0.5 text-sm">{value}</div>
    </div>
  )

  return (
    <div className="space-y-4">
      <Card className="gap-4 p-5">
        <h3 className="text-sm font-medium">数据库</h3>
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
          {stat("文件大小", bytes(info.size))}
          {stat("预写日志", bytes(info.wal))}
          {stat("可回收空间", bytes(info.free))}
          {stat("保留天数", `${info.retention} 天`)}
          {/* 和保留天数并排：跨度小于保留期是还没攒够，大于保留期就是每小时
              那次 prune 没在跑。 */}
          {stat("历史跨度", info.oldest ? `${Math.floor((Date.now() / 1000 - info.oldest) / 86400)} 天` : "—")}
          {DB_ROWS.map(([key, label]) => stat(label, (info.rows[key] ?? 0).toLocaleString()))}
        </div>
        <p className="truncate text-xs text-muted-foreground" title={info.path}>
          <code>{info.path}</code>
        </p>
      </Card>

      <Card className="gap-4 p-5">
        <div>
          <h3 className="text-sm font-medium">回收空间</h3>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            按保留天数清掉过期明细，再重建数据库文件把空出来的页还给磁盘（SQLite 的 VACUUM）。
            重建期间需要与数据库等量的空闲磁盘，过程中面板和上报会短暂变慢。
          </p>
        </div>
        <div>
          <Button size="sm" variant="secondary" disabled={!!busy} onClick={() => setConfirm("vacuum")}>
            {busy === "vacuum" ? "回收中…" : "立即回收"}
          </Button>
        </div>
      </Card>

      <Card className="gap-4 p-5">
        <div>
          <h3 className="text-sm font-medium">备份</h3>
          <p className="mt-1 text-xs leading-relaxed text-muted-foreground">
            导出的是整个数据库，含节点凭证与登录密码哈希，请当作密钥保管。恢复会用备份文件整体覆盖当前数据，
            当前服务器、设置、历史全部作废，所有设备需要重新登录。
            <br />
            请用这里导出的文件恢复：直接复制 <code>monitor.db</code> 会丢掉预写日志里还没落盘的那部分。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          {/* The browser's own download: the file is streamed straight from
              the response, never held in the page. */}
          <Button size="sm" asChild>
            <a href="/api/db/backup" download>
              <Download /> 导出备份
            </a>
          </Button>
          <Button size="sm" variant="secondary" disabled={!!busy} onClick={() => picker.current?.click()}>
            <Upload /> 导入备份
          </Button>
          <input
            ref={picker}
            type="file"
            accept=".db,.gz,.gzip,application/octet-stream,application/gzip,application/x-gzip"
            className="hidden"
            onChange={(e) => {
              setPending(e.target.files?.[0] ?? null)
              e.target.value = ""
            }}
          />
        </div>
      </Card>

      <TelegramBackupCard go={go} onOpenPicker={() => picker.current?.click()} />

      {confirm === "vacuum" && (
        <ConfirmDialog
          title="回收空间？"
          description="超出保留天数的历史明细会被删除，然后重建数据库文件。累计流量不受影响。"
          confirmLabel="开始回收"
          busy={!!busy}
          onClose={() => setConfirm(null)}
          onConfirm={vacuum}
        />
      )}
      {pending && (
        <ConfirmDialog
          title="用备份覆盖当前数据？"
          description={`将用 ${pending.name}（${bytes(pending.size)}）整体替换当前数据库。当前的服务器、设置和历史全部丢失，且无法撤销。${
            pending.name.endsWith(".gz") || pending.name.endsWith(".gzip")
              ? "（已识别为 Telegram 自动备份压缩包，系统将自动解压还原）"
              : ""
          }`}
          confirmLabel={busy === "restore" ? `已上传 ${bytes(sent)} / ${bytes(pending.size)}` : "确认恢复"}
          busy={!!busy}
          onClose={() => { abort.current?.abort(); setPending(null) }}
          onConfirm={() => restore(pending)}
        />
      )}
    </div>
  )
}

// Each area is its own route rather than a tab, so a page can be linked to and a
// reload returns to the same section.
const ADMIN_SECTIONS = [
  { path: "/admin/overview", label: "监控大盘", icon: BarChart3 },
  { path: "/admin/nodes", label: "服务器", icon: Server },
  { path: "/admin/proxy", label: "代理协议", icon: Globe },
  { path: "/admin/users", label: "用户管理", icon: Users },
  { path: "/admin/tiers", label: "套餐管理", icon: PackageCheck },
  { path: "/admin/announcements", label: "公告通知", icon: Megaphone },
  { path: "/admin/rules", label: "规则配置", icon: SlidersHorizontal },
  { path: "/admin/license", label: "商业授权", icon: KeyRound },
  { path: "/admin/ping", label: "延迟", icon: Radio },
  { path: "/admin/notify", label: "通知", icon: Bell },
  { path: "/admin/data", label: "数据", icon: Database },
  { path: "/admin/security", label: "安全", icon: Shield },
  { path: "/admin/settings", label: "设置", icon: Settings },
] as const

export function Admin({
  path,
  go,
  nodes,
  refresh,
  site,
  refusal,
  updateInfo,
  onOpenUpdateDialog,
}: {
  path: string
  go: (to: string) => void
  nodes: Node[]
  refresh: () => void
  site: string
  refusal: string
  updateInfo?: UpdateInfo | null
  onOpenUpdateDialog?: () => void
}) {
  return (
    <div className="flex flex-col gap-6 md:flex-row">
      <nav className="flex gap-1 overflow-x-auto md:w-44 md:shrink-0 md:flex-col md:overflow-visible">
        {ADMIN_SECTIONS.map(({ path: to, label, icon: Icon }) => {
          const active = path === to
          return (
            <button
              key={to}
              onClick={() => go(to)}
              aria-current={active ? "page" : undefined}
              className={`flex shrink-0 items-center gap-2 rounded-md px-3 py-2 text-sm transition-colors ${
                active ? "bg-secondary font-medium" : "text-muted-foreground hover:bg-muted"
              }`}
            >
              <Icon className="size-4" />
              {label}
            </button>
          )
        })}
        <div className="mt-4 hidden pt-3 md:block border-t border-border/40 text-[11px] text-muted-foreground/60 px-3 space-y-1.5">
          <div className="flex items-center justify-between">
            <span>ProxyProbe</span>
            <span className="font-mono text-primary/70 font-medium">
              {updateInfo?.current_version || "v2.5.7"}
            </span>
          </div>

          {updateInfo?.has_update ? (
            <button
              onClick={onOpenUpdateDialog}
              className="w-full text-left rounded-md p-1.5 bg-amber-500/10 border border-amber-500/30 text-[10px] text-amber-600 dark:text-amber-400 hover:bg-amber-500/20 transition-all flex items-center gap-1.5 font-medium"
            >
              <span className="relative flex size-1.5 shrink-0">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
                <span className="relative inline-flex rounded-full size-1.5 bg-amber-500" />
              </span>
              <span className="truncate">可升级至 {updateInfo.latest_version}</span>
            </button>
          ) : (
            <button
              onClick={onOpenUpdateDialog}
              className="w-full text-left text-[10px] text-muted-foreground hover:text-foreground flex items-center gap-1 transition-colors"
            >
              <RefreshCw className="size-2.5" />
              <span>检查系统更新</span>
            </button>
          )}
        </div>
      </nav>

      <div className="min-w-0 flex-1">
        {path === "/admin/overview" ? (
          <ProxyDashboard onNavigate={go} />
        ) : path === "/admin/proxy" ? (
          <ProxyNodes nodes={nodes} />
        ) : path === "/admin/users" ? (
          <ProxyUsers />
        ) : path === "/admin/tiers" ? (
          <TiersManagementTab />
        ) : path === "/admin/announcements" ? (
          <AnnouncementsTab />
        ) : path === "/admin/rules" ? (
          <ProxyRules />
        ) : path === "/admin/license" ? (
          <LicenseManager />
        ) : path === "/admin/ping" ? (
          <Ping nodes={nodes} />
        ) : path === "/admin/notify" ? (
          <Notify nodes={nodes} refresh={refresh} />
        ) : path === "/admin/data" ? (
          <Data go={go} />
        ) : path === "/admin/security" ? (
          <Security site={site} />
        ) : path === "/admin/settings" ? (
          <SettingsTab updateInfo={updateInfo} onOpenUpdateDialog={onOpenUpdateDialog} />
        ) : (
          <Nodes nodes={nodes} refresh={refresh} site={site} refusal={refusal} />
        )}
      </div>
    </div>
  )
}
