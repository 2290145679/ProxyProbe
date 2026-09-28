import { useEffect, useState, useCallback } from "react"
import { 
  GitFork, Layers, Plus, RefreshCw, Copy, Check, Trash2, 
  QrCode, Box, Activity, Download, AlertCircle, ArrowRightLeft,
  SlidersHorizontal, Sparkles, Globe, Pencil, ChevronDown, ChevronUp
} from "lucide-react"
import { toast } from "sonner"
import QRCode from "qrcode"
import { copyToClipboard } from "@/lib/clipboard"

import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Badge } from "@/components/ui/badge"
import { Switch } from "@/components/ui/switch"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog"
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select"
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table"
import type { Node } from "@/lib/api"

export interface ProxyNode {
  id: number
  server_id: number
  server_name: string
  server_host: string
  name: string
  protocol: string
  port: number
  flag?: string
  display_name?: string
  uuid: string
  flow?: string
  sni?: string
  dest?: string
  public_key?: string
  private_key?: string
  short_id?: string
  ws_path?: string
  method?: string
  password?: string
  username?: string
  enabled: number
  created_at: number
  link?: string
  is_relay?: number
  relay_server_id?: number
  relay_port?: number
  remote_host?: string
  remote_port?: number
  target_node_id?: number
  bandwidth_limit_mbps?: number
  vip_levels?: string
}

export interface ProxyServer {
  id: number
  name: string
  host: string
  ipv4?: string
  ipv6?: string
  is_local: boolean
  token: string
  xray_installed: boolean
  xray_running: boolean
  xray_version?: string
  singbox_installed: boolean
  singbox_running: boolean
  singbox_version?: string
  realm_installed?: boolean
  realm_running?: boolean
  realm_version?: string
  last_seen?: number
}

export interface UnlockData {
  ok: boolean
  msg: string
  region?: string
}

export interface UnlockPresetItem {
  id: string
  name: string
  shortName: string
  category: "ai" | "media" | "custom"
  color?: string
  desc?: string
}

export interface CustomUnlockItem {
  id: string
  name: string
  url: string
}

export interface NodeUnlockStatus {
  gemini?: UnlockData
  chatgpt?: UnlockData
  claude?: UnlockData
  netflix?: UnlockData
  youtube?: UnlockData
  disney?: UnlockData
  tiktok?: UnlockData
  spotify?: UnlockData
  region?: string
  updated_at?: number
  [key: string]: any
}

function UnlockBadges({
  status,
  testing,
  onTest,
  enabledKeys,
  presets,
  customItems,
  showBadges = true,
}: {
  status?: Record<string, any>
  testing: boolean
  onTest: () => void
  enabledKeys?: string[]
  presets?: UnlockPresetItem[]
  customItems?: CustomUnlockItem[]
  showBadges?: boolean
}) {
  if (!showBadges) return null
  const activeKeys = enabledKeys || []
  if (activeKeys.length === 0) {
    return <span className="text-[11px] text-muted-foreground/60 italic select-none">未启用展示项</span>
  }

  const defaultPresetsMap: Record<string, { shortName: string; name: string }> = {
    gemini: { shortName: "Gemini", name: "Google Gemini" },
    chatgpt: { shortName: "GPT", name: "OpenAI ChatGPT" },
    claude: { shortName: "Claude", name: "Anthropic Claude" },
    netflix: { shortName: "NF", name: "Netflix" },
    youtube: { shortName: "YT", name: "YouTube" },
    disney: { shortName: "D+", name: "Disney+" },
    tiktok: { shortName: "TikTok", name: "TikTok" },
    spotify: { shortName: "Spotify", name: "Spotify" },
  }

  return (
    <div className="flex items-center gap-1.5 flex-nowrap overflow-x-auto no-scrollbar py-0.5 max-w-[230px]">
      {activeKeys.map((key) => {
        let label = key
        let fullName = key
        const preset = presets?.find((p) => p.id === key)
        if (preset) {
          label = preset.shortName || preset.name
          fullName = preset.name
        } else if (defaultPresetsMap[key]) {
          label = defaultPresetsMap[key].shortName
          fullName = defaultPresetsMap[key].name
        } else if (customItems) {
          const cust = customItems.find((c) => c.id === key)
          if (cust) {
            label = cust.name
            fullName = cust.name
          }
        }

        const itemRes = status?.[key] as UnlockData | undefined
        const isTested = itemRes && typeof itemRes.ok === "boolean"
        const isOk = isTested && itemRes.ok
        const isFail = isTested && !itemRes.ok

        let displayLabel = label
        if (key === "chatgpt" && isOk) {
          const reg = itemRes.region || status?.region
          if (reg) displayLabel = `GPT · ${reg}`
        }

        const tooltipMsg = isTested
          ? `${fullName}: ${itemRes.msg || (isOk ? "支持" : "受限")} (点击重新检测)`
          : `${fullName}: 未检测 (点击检测)`

        return (
          <span
            key={key}
            onClick={onTest}
            title={tooltipMsg}
            className={`inline-flex items-center gap-1 px-1.5 py-0.5 rounded-full text-[10px] font-medium border cursor-pointer select-none transition-all duration-150 shrink-0 ${
              isOk
                ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/25 hover:bg-emerald-500/20"
                : isFail
                ? "bg-rose-500/10 text-rose-500 dark:text-rose-400 border-rose-500/25 hover:bg-rose-500/20"
                : "bg-muted/40 text-muted-foreground border-border/40 hover:bg-muted/70 hover:text-foreground"
            }`}
          >
            <span
              className={`size-1.5 rounded-full shrink-0 ${
                isOk
                  ? "bg-emerald-500 shadow-[0_0_4px_rgba(16,185,129,0.7)]"
                  : isFail
                  ? "bg-rose-500/80"
                  : "bg-muted-foreground/40"
              }`}
            />
            <span>{displayLabel}</span>
          </span>
        )
      })}

      <button
        type="button"
        title="刷新该节点流媒体与 AI 解锁检测"
        onClick={onTest}
        disabled={testing}
        className="p-1 rounded text-muted-foreground/60 hover:text-foreground hover:bg-muted/50 transition-colors shrink-0 disabled:opacity-50 cursor-pointer"
      >
        <RefreshCw className={`size-3 ${testing ? "animate-spin text-primary" : ""}`} />
      </button>
    </div>
  )
}

interface CoreStatus {
  installed: boolean
  version: string
  running: boolean
}

const PROTOCOL_OPTIONS = [
  { value: "vless_reality", label: "VLESS + Reality", badge: "推荐" },
  { value: "vless_reality_xhttp", label: "VLESS + Reality + XHTTP", badge: "新特性" },
  { value: "anytls", label: "AnyTLS (Sing-box 极速防识别)", badge: "新协议" },
  { value: "hysteria2", label: "Hysteria 2 (Hy2)", badge: "极速UDP" },
  { value: "vless_ws", label: "VLESS + WebSocket", badge: "CDN" },
  { value: "vmess_ws", label: "VMess + WebSocket", badge: "兼容" },
  { value: "trojan", label: "Trojan (TCP)", badge: "经典" },
  { value: "ss2022", label: "Shadowsocks 2022", badge: "高性能" },
  { value: "socks5", label: "SOCKS5 代理", badge: "纯净" },
]

export function ProxyNodes({ nodes }: { nodes: Node[] }) {
  const [proxyNodes, setProxyNodes] = useState<ProxyNode[]>([])
  const [servers, setServers] = useState<ProxyServer[]>([])
  const [subToken, setSubToken] = useState<string>("")
  const [recommendedPort, setRecommendedPort] = useState<number>(20443)
  const [ipType, setIpType] = useState<"ipv4" | "ipv6" | "custom">("ipv4")
  const [loading, setLoading] = useState(false)
  const [statusLoading, setStatusLoading] = useState(false)
  const [coreActionLoading, setCoreActionLoading] = useState<string | null>(null)
  const [xrayStatus, setXrayStatus] = useState<CoreStatus>({
    installed: true,
    version: "Xray 26.3.27 (Xray, Penetrates Everything.) d2758a0 (go1.26.1 linux/amd64)",
    running: true,
  })
  const [singboxStatus, setSingboxStatus] = useState<CoreStatus>({
    installed: true,
    version: "sing-box version 1.14.1 (linux/amd64)",
    running: true,
  })
  const [nodeMode, setNodeMode] = useState<"direct" | "relay">("direct")
  const [relayTargetMode, setRelayTargetMode] = useState<"link_existing" | "custom">("link_existing")
  const [selectedTargetNodeId, setSelectedTargetNodeId] = useState<string>("")
  const [testingId, setTestingId] = useState<number | null>(null)
  const [testResult, setTestResult] = useState<Record<number, { ok: boolean; msg: string; ms: number }>>({})
  const [unlockStatus, setUnlockStatus] = useState<Record<string, NodeUnlockStatus>>({})
  const [testingUnlockId, setTestingUnlockId] = useState<number | null>(null)
  const [showUnlockBadges, setShowUnlockBadges] = useState<boolean>(() => {
    const saved = localStorage.getItem("proxy_show_unlock_badges")
    return saved !== null ? saved === "true" : false
  })
  const [tempShowBadges, setTempShowBadges] = useState<boolean>(false)
  const [unlockConfigOpen, setUnlockConfigOpen] = useState(false)
  const [unlockEnabled, setUnlockEnabled] = useState<string[]>(["gemini", "chatgpt", "netflix", "youtube"])
  const [unlockPresets, setUnlockPresets] = useState<UnlockPresetItem[]>([])
  const [unlockCustom, setUnlockCustom] = useState<CustomUnlockItem[]>([])
  const [tempEnabled, setTempEnabled] = useState<string[]>(["gemini", "chatgpt", "netflix", "youtube"])
  const [tempCustom, setTempCustom] = useState<CustomUnlockItem[]>([])
  const [newCustomName, setNewCustomName] = useState("")
  const [newCustomUrl, setNewCustomUrl] = useState("")
  const [savingUnlockConfig, setSavingUnlockConfig] = useState(false)

  const [copiedId, setCopiedId] = useState<number | null>(null)
  const [subCopied, setSubCopied] = useState(false)

  // QR Code Dialog
  const [qrNode, setQrNode] = useState<ProxyNode | null>(null)
  const [qrDataUrl, setQrDataUrl] = useState<string>("")

  // Group by server & Edit & Delete Dialog states
  const [groupByServer, setGroupByServer] = useState(false)
  const [collapsedServers, setCollapsedServers] = useState<Record<string, boolean>>({})
  const [editNode, setEditNode] = useState<ProxyNode | null>(null)
  const [editOpen, setEditOpen] = useState(false)
  const [deleteConfirmNode, setDeleteConfirmNode] = useState<{ id: number; name: string } | null>(null)
  const [deleting, setDeleting] = useState(false)

  // Create Modal State
  const [licenseStatus, setLicenseStatus] = useState<any>(() => {
    try {
      return JSON.parse(localStorage.getItem("proxyprobe_license_status") || "null")
    } catch {
      return null
    }
  })
  const [dialogOpen, setDialogOpen] = useState(false)
  const [batchDialogOpen, setBatchDialogOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [vipTiers, setVipTiers] = useState<any[]>([])
  const [includeServerPrefix, setIncludeServerPrefix] = useState<boolean>(false)
  const [form, setForm] = useState({
    server_id: "0",
    server_name: "本机",
    server_host: "189.24.108.25",
    name: "",
    protocol: "vless_reality",
    port: "20443",
    uuid: "",
    flow: "xtls-rprx-vision",
    sni: "www.apple.com",
    dest: "www.apple.com:443",
    public_key: "",
    private_key: "",
    short_id: "",
    ws_path: "/ws-proxy",
    method: "2022-blake3-aes-128-gcm",
    password: "",
    username: "",
    is_relay: 0,
    remote_host: "",
    remote_port: "",
    target_node_id: 0,
    bandwidth_limit_mbps: "0",
    vip_levels: "",
  })

  const getProtocolCleanLabel = (p: string) => {
    switch (p) {
      case "vless_reality": return "VLESS Reality"
      case "vless_reality_xhttp": return "VLESS Reality XHTTP"
      case "anytls": return "AnyTLS"
      case "hysteria2": return "Hysteria 2"
      case "vless_ws": return "VLESS WS"
      case "vmess_ws": return "VMess WS"
      case "trojan": return "Trojan"
      case "ss2022": return "Shadowsocks 2022"
      case "socks5": return "SOCKS5"
      default: {
        const opt = PROTOCOL_OPTIONS.find(o => o.value === p)
        return opt ? opt.label.replace(/\s*\([^)]*\)/g, "").replace(/\+/g, "").trim() : p
      }
    }
  }

  const computeNodeName = (
    serverName: string,
    proto: string,
    mode: "direct" | "relay",
    prefixEnabled: boolean,
    targetName?: string
  ) => {
    const cleanProto = getProtocolCleanLabel(proto)
    if (mode === "relay") {
      const base = targetName ? `中转 ➔ ${targetName}` : "中转落地"
      return prefixEnabled ? `[${serverName}] ${base}` : base
    } else {
      const base = cleanProto || "Reality"
      return prefixEnabled ? `[${serverName}] ${base}` : base
    }
  }

  const handleTogglePrefix = (checked: boolean) => {
    setIncludeServerPrefix(checked)
    setForm(prev => {
      let curName = prev.name.trim()
      const sPrefix = `[${prev.server_name}] `
      const sPrefixNoSpace = `[${prev.server_name}]`
      const sDash = `${prev.server_name}-`
      if (checked) {
        if (!curName.startsWith(sPrefix) && !curName.startsWith(sPrefixNoSpace)) {
          curName = `${sPrefix}${curName}`
        }
      } else {
        if (curName.startsWith(sPrefix)) {
          curName = curName.substring(sPrefix.length).trim()
        } else if (curName.startsWith(sPrefixNoSpace)) {
          curName = curName.substring(sPrefixNoSpace.length).trim()
        } else if (curName.startsWith(sDash)) {
          curName = curName.substring(sDash.length).trim()
        }
      }
      return { ...prev, name: curName }
    })
  }

  const loadStatus = useCallback(async () => {
    setStatusLoading(true)
    try {
      const res = await fetch("/api/proxy/status")
      if (res.ok) {
        const data = await res.json()
        if (data.xray) {
          setXrayStatus(data.xray)
        } else if (data.installed !== undefined) {
          setXrayStatus({ installed: data.installed, version: data.version, running: data.running })
        }
        if (data.singbox) {
          setSingboxStatus(data.singbox)
        }
      }
    } catch {
      // Keep default
    } finally {
      setStatusLoading(false)
    }
  }, [])

  const loadUnlockStatus = useCallback(async () => {
    try {
      const res = await fetch("/api/proxy/unlock-status")
      if (res.ok) {
        const data = await res.json()
        if (data.status) {
          setUnlockStatus(data.status)
        }
        if (data.enabled && Array.isArray(data.enabled)) {
          setUnlockEnabled(data.enabled)
        }
        if (data.presets && Array.isArray(data.presets)) {
          setUnlockPresets(data.presets)
        }
        if (data.custom && Array.isArray(data.custom)) {
          setUnlockCustom(data.custom)
        }
        if (data.show_badges !== undefined) {
          const val = Boolean(data.show_badges)
          setShowUnlockBadges(val)
          localStorage.setItem("proxy_show_unlock_badges", String(val))
        }
      }
    } catch {}
  }, [])

  const handleSaveUnlockConfig = async (newEnabled: string[], newCustom: CustomUnlockItem[], showBadgesVal: boolean) => {
    setSavingUnlockConfig(true)
    try {
      localStorage.setItem("proxy_show_unlock_badges", String(showBadgesVal))
      setShowUnlockBadges(showBadgesVal)

      const res = await fetch("/api/proxy/unlock/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ enabled: newEnabled, custom: newCustom, show_badges: showBadgesVal })
      })
      const data = await res.json()
      if (data.ok) {
        setUnlockEnabled(newEnabled)
        setUnlockCustom(newCustom)
        toast.success("流媒体与 AI 检测配置已更新并生效")
        setUnlockConfigOpen(false)
      } else {
        toast.error(data.message || "配置保存失败")
      }
    } catch {
      toast.error("网络请求失败")
    } finally {
      setSavingUnlockConfig(false)
    }
  }

  const openUnlockConfig = () => {
    setTempShowBadges(showUnlockBadges)
    setTempEnabled(unlockEnabled)
    setTempCustom(unlockCustom)
    setNewCustomName("")
    setNewCustomUrl("")
    setUnlockConfigOpen(true)
  }

  const togglePreset = (id: string) => {
    setTempEnabled(prev =>
      prev.includes(id) ? prev.filter(k => k !== id) : [...prev, id]
    )
  }

  const handleAddCustom = () => {
    if (!newCustomName.trim() || !newCustomUrl.trim()) {
      toast.error("请填写检测规则名称和目标 URL")
      return
    }
    const newId = `custom_${Date.now()}`
    const item: CustomUnlockItem = {
      id: newId,
      name: newCustomName.trim(),
      url: newCustomUrl.trim()
    }
    setTempCustom(prev => [...prev, item])
    setTempEnabled(prev => [...prev, newId])
    setNewCustomName("")
    setNewCustomUrl("")
    toast.success(`已添加自定义规则: ${item.name}`)
  }

  const handleRemoveCustom = (id: string) => {
    setTempCustom(prev => prev.filter(c => c.id !== id))
    setTempEnabled(prev => prev.filter(k => k !== id))
  }

  const handleTestUnlock = async (id: number) => {
    setTestingUnlockId(id)
    try {
      const res = await fetch(`/api/proxy/nodes/${id}/unlock-test`, { method: "POST" })
      const data = await res.json()
      if (data.ok && data.result) {
        setUnlockStatus(prev => ({ ...prev, [String(id)]: data.result }))
        toast.success(`节点 [${id}] 流媒体与 AI 解锁检测完成`)
      } else {
        toast.error(data.message || "解锁检测未完成")
      }
    } catch {
      toast.error("网络请求失败")
    } finally {
      setTestingUnlockId(null)
    }
  }

  const handleTestNode = async (id: number) => {
    setTestingId(id)
    handleTestUnlock(id)
    try {
      const res = await fetch(`/api/proxy/nodes/${id}/test`)
      const data = await res.json()
      setTestResult(prev => ({ ...prev, [id]: { ok: data.ok, msg: data.message, ms: data.latency_ms } }))
      if (data.ok) {
        toast.success(data.message || `测试通过 (延迟 ~${data.latency_ms}ms)`)
      } else {
        toast.error(data.message || "连通性测试未通过")
      }
    } catch {
      toast.error("网络请求测试失败")
    } finally {
      setTestingId(null)
    }
  }

  const loadData = useCallback(async () => {
    setLoading(true)
    loadUnlockStatus()
    try {
      const res = await fetch("/api/proxy/nodes")
      if (!res.ok) throw new Error("获取节点列表失败")
      const data = await res.json()
      setProxyNodes(data.nodes || [])
      setSubToken(data.sub_token || "")
      setRecommendedPort(data.recommended_port || 20443)

      // Fetch servers with accurate core installed/running status
      const sRes = await fetch("/api/proxy/servers")
      if (sRes.ok) {
        const sData = await sRes.json()
        if (sData.servers && sData.servers.length > 0) {
          setServers(sData.servers)
        }
      }

      // Fetch license status
      try {
        const licRes = await fetch("/api/proxy/license/status")
        if (licRes.ok) {
          const licData = await licRes.json()
          setLicenseStatus(licData)
          try { localStorage.setItem("proxyprobe_license_status", JSON.stringify(licData)) } catch {}
        }
      } catch {}
    } catch (e: any) {
      toast.error(e.message || "加载代理节点失败")
    } finally {
      setLoading(false)
    }
  }, [])

  const handleCoreAction = async (core: "xray" | "singbox" | "realm", action: "install" | "uninstall") => {
    const coreName = core === "xray" ? "Xray-Core" : (core === "singbox" ? "Sing-box" : "Realm")
    const actionName = action === "install" ? "安装" : "卸载"
    if (action === "uninstall" && !confirm(`确定要${actionName} ${coreName} 核心吗？卸载后依赖此核心的节点将停止服务。`)) {
      return
    }

    setCoreActionLoading(`${core}-${action}`)
    try {
      const res = await fetch(`/api/proxy/core/${core}/${action}`, {
        method: "POST"
      })
      const data = await res.json()
      if (data.ok) {
        toast.success(data.message || `${coreName} 核心${actionName}成功！`)
        await loadStatus()
        await loadData()
      } else {
        toast.error(data.message || `${coreName} 核心${actionName}失败`)
      }
    } catch (e: any) {
      toast.error(e.message || `请求执行${actionName}失败`)
    } finally {
      setCoreActionLoading(null)
    }
  }

  useEffect(() => {
    loadData()
    loadStatus()
    fetch("/api/proxy/tiers")
      .then(res => res.json())
      .then(data => {
        if (data.ok && Array.isArray(data.tiers)) {
          setVipTiers(data.tiers)
        }
      })
      .catch(() => {})
  }, [loadData, loadStatus])

  // Keygen helper
  const handleKeygen = async (proto: string, method?: string) => {
    try {
      const res = await fetch(`/api/proxy/keygen?protocol=${proto}&method=${method || "2022-blake3-aes-128-gcm"}`)
      if (res.ok) {
        const data = await res.json()
        setForm(prev => ({
          ...prev,
          port: data.port ? String(data.port) : prev.port,
          uuid: data.uuid || prev.uuid,
          public_key: data.public_key || prev.public_key,
          private_key: data.private_key || prev.private_key,
          short_id: data.short_id || prev.short_id,
          password: data.password || prev.password,
          username: data.username || prev.username,
          ws_path: data.ws_path || prev.ws_path,
          sni: data.sni || prev.sni,
          dest: data.dest || prev.dest,
        }))
      }
    } catch {
      // Ignored
    }
  }

  const serverOptions: ProxyServer[] = (servers.length > 0 ? servers : nodes.map(n => ({
    id: n.id,
    name: n.name,
    host: n.ip || n.ipv4 || "自动解析",
    ipv4: n.ip || n.ipv4 || "",
    ipv6: n.ipv6 || "",
    is_local: false,
    token: "",
    xray_installed: false,
    xray_running: false,
    singbox_installed: false,
    singbox_running: false,
    realm_installed: false,
    realm_running: false
  }))).filter(s => s.id !== 0)

  const currentSelectedServer = serverOptions.find(s => String(s.id) === form.server_id)
  const isSingboxProto = form.protocol === "hysteria2" || form.protocol === "tuic" || form.protocol === "anytls"
  const isRequiredCoreInstalled = nodeMode === "relay"
    ? Boolean(currentSelectedServer?.realm_installed)
    : (isSingboxProto ? Boolean(currentSelectedServer?.singbox_installed) : Boolean(currentSelectedServer?.xray_installed))

  const openCreateDialog = () => {
    if (licenseStatus?.type === "revoked") {
      toast.error("当前商业许可证已被授权中心吊销冻结，禁止创建新节点！")
      return
    }

    if (licenseStatus) {
      const maxNodes = licenseStatus?.max_nodes || licenseStatus?.limits?.max_nodes || (licenseStatus?.active ? 12 : 1)
      if (proxyNodes.length >= maxNodes) {
        const planName = licenseStatus?.plan_name || (licenseStatus?.active ? "商业版" : "免费体验版")
        toast.error(`当前【${planName}】配额已满（上限 ${maxNodes} 个节点，当前已建 ${proxyNodes.length} 个），添加更多节点请升级商业套餐！`)
        return
      }
    }

    if (serverOptions.length === 0) {
      toast.error("暂无可用的服务器！请先在「节点」页面添加探针服务器并在其上安装代理探针。")
      return
    }

    setIpType("ipv4")
    const defaultServer = serverOptions[0]
    const sId = String(defaultServer.id)
    const sName = defaultServer.name
    const sHost = defaultServer.host || defaultServer.ipv4 || ""

    setNodeMode("direct")
    setRelayTargetMode("link_existing")
    setSelectedTargetNodeId("")
    setIncludeServerPrefix(false)
    setForm({
      server_id: sId,
      server_name: sName,
      server_host: sHost,
      name: computeNodeName(sName, "vless_reality", "direct", false),
      protocol: "vless_reality",
      port: String(recommendedPort),
      uuid: "",
      flow: "xtls-rprx-vision",
      sni: "www.apple.com",
      dest: "www.apple.com:443",
      public_key: "",
      private_key: "",
      short_id: "",
      ws_path: "/ws-proxy",
      method: "2022-blake3-aes-128-gcm",
      password: "",
      username: "",
      is_relay: 0,
      remote_host: "",
      remote_port: "",
      target_node_id: 0,
      bandwidth_limit_mbps: "0",
      vip_levels: "",
    })
    setDialogOpen(true)
    handleKeygen("vless_reality")
  }

  const handleProtocolChange = (p: string) => {
    setForm(prev => {
      const targetNode = proxyNodes.find(n => String(n.id) === selectedTargetNodeId)
      const newName = computeNodeName(prev.server_name, p, nodeMode, includeServerPrefix, targetNode?.name)
      return { ...prev, protocol: p, name: newName }
    })
    handleKeygen(p, form.method)
  }

  const handleServerChange = (sId: string) => {
    const s = serverOptions.find(n => String(n.id) === sId)
    if (!s) return

    if (nodeMode === "relay" && !s.realm_installed) {
      toast.error(`服务器【${s.name}】未安装 Realm 核心，无法作为中转入口！`)
      return
    }

    let chosenHost = s.host || s.ipv4 || ""
    if (ipType === "ipv6") {
      if (s.ipv6) {
        chosenHost = s.ipv6
      } else {
        setIpType("ipv4")
      }
    }
    setForm(prev => {
      const targetNode = proxyNodes.find(n => String(n.id) === selectedTargetNodeId)
      const newName = computeNodeName(s.name, prev.protocol, nodeMode, includeServerPrefix, targetNode?.name)
      return { 
        ...prev, 
        server_id: sId, 
        server_name: s.name, 
        server_host: chosenHost,
        name: newName
      }
    })
  }

  const handleSelectTargetNode = (targetId: string) => {
    setSelectedTargetNodeId(targetId)
    const targetNode = proxyNodes.find(n => String(n.id) === targetId)
    if (targetNode) {
      const newName = computeNodeName(form.server_name, targetNode.protocol, "relay", includeServerPrefix, targetNode.name)
      setForm(prev => ({
        ...prev,
        target_node_id: targetNode.id,
        name: newName,
        protocol: targetNode.protocol,
        remote_host: targetNode.server_host,
        remote_port: String(targetNode.port),
        uuid: targetNode.uuid || prev.uuid,
        flow: targetNode.flow || prev.flow,
        sni: targetNode.sni || prev.sni,
        dest: targetNode.dest || prev.dest,
        public_key: targetNode.public_key || prev.public_key,
        private_key: targetNode.private_key || prev.private_key,
        short_id: targetNode.short_id || prev.short_id,
        ws_path: targetNode.ws_path || prev.ws_path,
        method: targetNode.method || prev.method,
        password: targetNode.password || prev.password,
        username: targetNode.username || prev.username,
      }))
    }
  }

  const handleCreateNode = async (e: React.FormEvent) => {
    e.preventDefault()

    if (!isRequiredCoreInstalled) {
      if (nodeMode === "relay") {
        toast.error(`中转服务器【${form.server_name}】未安装 Realm 核心，无法创建中转落地节点！`)
      } else {
        toast.error(`所选服务器【${form.server_name}】未安装 ${isSingboxProto ? "Sing-box" : "Xray-Core"} 核心，无法创建节点！`)
      }
      return
    }

    if (nodeMode === "relay") {
      if (!form.remote_host || !form.remote_port) {
        toast.error("请完善落地目标服务器的地址与端口！")
        return
      }
    }

    if (!form.vip_levels) {
      toast.error("请选择 VIP 访问权限等级（此项为必填项）！")
      return
    }

    setSubmitting(true)
    try {
      const res = await fetch("/api/proxy/nodes", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          server_id: Number(form.server_id),
          server_name: form.server_name,
          server_host: form.server_host,
          name: form.name,
          protocol: form.protocol,
          port: Number(form.port),
          uuid: form.uuid,
          flow: form.flow,
          sni: form.sni,
          dest: form.dest,
          public_key: form.public_key,
          private_key: form.private_key,
          short_id: form.short_id,
          ws_path: form.ws_path,
          method: form.method,
          password: form.password,
          username: form.username,
          is_relay: nodeMode === "relay" ? 1 : 0,
          relay_server_id: nodeMode === "relay" ? Number(form.server_id) : 0,
          relay_port: Number(form.port),
          remote_host: nodeMode === "relay" ? form.remote_host : "",
          remote_port: nodeMode === "relay" ? Number(form.remote_port) : 0,
          target_node_id: nodeMode === "relay" ? Number(form.target_node_id || 0) : 0,
          bandwidth_limit_mbps: Number(form.bandwidth_limit_mbps || 0),
          vip_levels: form.vip_levels || "",
        })
      })
      const data = await res.json()
      if (!res.ok || !data.ok) throw new Error(data.message || "创建节点失败")
      
      toast.success(data.message || "节点创建成功！")
      setDialogOpen(false)
      loadData()
      loadStatus()
    } catch (err: any) {
      toast.error(err.message || "创建节点出错")
    } finally {
      setSubmitting(false)
    }
  }

  const handleToggle = async (id: number) => {
    try {
      const res = await fetch(`/api/proxy/nodes/${id}/toggle`, { method: "POST" })
      const data = await res.json()
      if (data.ok) {
        toast.success(data.message)
        loadData()
      } else {
        toast.error(data.message || "操作失败")
      }
    } catch {
      toast.error("网络请求失败")
    }
  }

  const handleDelete = (id: number, name: string) => {
    setDeleteConfirmNode({ id, name })
  }

  const handleConfirmDelete = async () => {
    if (!deleteConfirmNode) return
    const id = deleteConfirmNode.id
    setDeleting(true)
    // 乐观立即从前端移除，提供零延迟极速体验并彻底杜绝弹窗堆叠
    setProxyNodes(prev => prev.filter(n => n.id !== id))
    setDeleteConfirmNode(null)
    try {
      const res = await fetch(`/api/proxy/nodes/${id}`, { method: "DELETE" })
      const data = await res.json()
      if (data.ok) {
        toast.success("节点已成功删除")
        loadData()
      } else {
        toast.error(data.message || "删除失败")
        loadData()
      }
    } catch {
      toast.error("网络异常，无法同步删除")
      loadData()
    } finally {
      setDeleting(false)
    }
  }

  const copyLink = async (link: string, id: number) => {
    const ok = await copyToClipboard(link)
    if (ok) {
      setCopiedId(id)
      toast.success("复制链接成功")
      setTimeout(() => setCopiedId(null), 2000)
    } else {
      toast.error("复制失败，请手动选取复制")
    }
  }

  const copySub = async () => {
    const subUrl = `${location.origin}/api/proxy/sub?token=${subToken}`
    const ok = await copyToClipboard(subUrl)
    if (ok) {
      setSubCopied(true)
      toast.success("订阅链接已复制")
      setTimeout(() => setSubCopied(false), 2000)
    } else {
      toast.error("复制失败，请手动选取复制")
    }
  }

  const handleResetToken = async () => {
    if (!confirm("确定要重置聚合订阅 Token 吗？已分发给客户端的旧订阅链接将全部失效。")) return
    try {
      const res = await fetch("/api/proxy/reset-sub-token", { method: "POST" })
      const data = await res.json()
      if (data.ok && data.token) {
        setSubToken(data.token)
        toast.success("订阅 Token 已重置！")
      }
    } catch {
      toast.error("重置失败")
    }
  }

  const showQr = async (node: ProxyNode) => {
    if (!node.link) {
      toast.error("该节点无可用分享链接")
      return
    }
    try {
      const url = await QRCode.toDataURL(node.link, { width: 260, margin: 1 })
      setQrNode(node)
      setQrDataUrl(url)
    } catch {
      toast.error("生成二维码失败")
    }
  }

  const formatProtocolBadge = (proto: string) => {
    switch (proto) {
      case "vless_reality": return "VLESS + Reality"
      case "vless_reality_xhttp": return "VLESS + Reality + XHTTP"
      case "anytls": return "AnyTLS"
      case "vless_ws": return "VLESS + WS"
      case "vmess_ws": return "VMess + WS"
      case "trojan": return "Trojan"
      case "ss2022": return "Shadowsocks 2022"
      case "socks5": return "SOCKS5"
      case "hysteria2": return "Hysteria 2"
      case "tuic": return "TUIC v5"
      default: return proto.toUpperCase()
    }
  }

  const subUrl = `${location.origin}/api/proxy/sub?token=${subToken}`
  const isUnlockColVisible = showUnlockBadges && unlockEnabled.length > 0

  return (
    <div className="space-y-5">
      {/* Row 1: Dual Core Status: Xray & Sing-box side by side */}
      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        {/* Left Card: Xray-Core 核心状态 */}
        <Card className="p-5 flex flex-col justify-between rounded-xl border bg-card shadow-sm">
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <GitFork className="size-4 text-foreground/80" />
                <h3 className="font-semibold text-sm">Xray-Core 核心状态</h3>
              </div>
              {!xrayStatus.installed ? (
                <Badge variant="outline" className="border-neutral-300 text-muted-foreground rounded-full px-2.5 py-0.5 text-xs font-normal">
                  未安装
                </Badge>
              ) : (
                <Badge 
                  className={xrayStatus.running ? "bg-emerald-600 hover:bg-emerald-600 text-white rounded-full px-2.5 py-0.5 text-xs font-normal" : "bg-destructive text-destructive-foreground rounded-full px-2.5 py-0.5 text-xs font-normal"}
                >
                  {xrayStatus.running ? "运行中" : "未运行"}
                </Badge>
              )}
            </div>

            <p className="text-xs text-muted-foreground leading-relaxed font-mono whitespace-pre-wrap break-all mb-4">
              {!xrayStatus.installed 
                ? "当前服务器尚未安装 Xray-Core 核心。点击下方按钮即可一键自动安装。" 
                : (xrayStatus.version || "Xray 26.3.27 (Xray, Penetrates Everything.)\n(go1.26.1 linux/amd64)")}
            </p>
          </div>

          <div className="flex items-center gap-2.5 pt-2">
            <Button 
              variant="outline" 
              size="sm" 
              onClick={() => { loadStatus(); loadData() }} 
              disabled={statusLoading || loading || !!coreActionLoading}
              className="text-xs h-8 gap-1.5"
            >
              <RefreshCw className={`size-3.5 ${(statusLoading || loading) ? "animate-spin" : ""}`} />
              刷新状态
            </Button>

            {!xrayStatus.installed ? (
              <Button 
                size="sm" 
                onClick={() => handleCoreAction("xray", "install")}
                disabled={!!coreActionLoading}
                className="text-xs h-8 gap-1.5 bg-black hover:bg-neutral-800 text-white dark:bg-white dark:text-black dark:hover:bg-neutral-200"
              >
                <Download className="size-3.5" />
                {coreActionLoading === "xray-install" ? "正在安装..." : "安装核心"}
              </Button>
            ) : (
              <Button 
                variant="outline"
                size="sm" 
                onClick={() => handleCoreAction("xray", "uninstall")}
                disabled={!!coreActionLoading}
                className="text-xs h-8 gap-1.5 text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-950/20 border-red-200 dark:border-red-900/50"
              >
                <Trash2 className="size-3.5" />
                {coreActionLoading === "xray-uninstall" ? "正在卸载..." : "卸载核心"}
              </Button>
            )}
          </div>
        </Card>

        {/* Right Card: Sing-box 核心状态 (样式与 Xray 1:1 对齐) */}
        <Card className="p-5 flex flex-col justify-between rounded-xl border bg-card shadow-sm">
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Box className="size-4 text-foreground/80" />
                <h3 className="font-semibold text-sm">Sing-box 核心状态</h3>
              </div>
              {!singboxStatus.installed ? (
                <Badge variant="outline" className="border-neutral-300 text-muted-foreground rounded-full px-2.5 py-0.5 text-xs font-normal">
                  未安装
                </Badge>
              ) : (
                <Badge 
                  className={singboxStatus.running ? "bg-emerald-600 hover:bg-emerald-600 text-white rounded-full px-2.5 py-0.5 text-xs font-normal" : "bg-destructive text-destructive-foreground rounded-full px-2.5 py-0.5 text-xs font-normal"}
                >
                  {singboxStatus.running ? "运行中" : "未运行"}
                </Badge>
              )}
            </div>

            <p className="text-xs text-muted-foreground leading-relaxed font-mono whitespace-pre-wrap break-all mb-4">
              {!singboxStatus.installed
                ? "当前服务器尚未安装 Sing-box 核心。安装后可运行 Hysteria 2、TUIC 等 UDP 高速协议。"
                : (singboxStatus.version || "sing-box version 1.14.1 (linux/amd64)")}
            </p>
          </div>

          <div className="flex items-center gap-2.5 pt-2">
            <Button 
              variant="outline" 
              size="sm" 
              onClick={() => { loadStatus(); loadData() }} 
              disabled={statusLoading || loading || !!coreActionLoading}
              className="text-xs h-8 gap-1.5"
            >
              <RefreshCw className={`size-3.5 ${(statusLoading || loading) ? "animate-spin" : ""}`} />
              刷新状态
            </Button>

            {!singboxStatus.installed ? (
              <Button 
                size="sm" 
                onClick={() => handleCoreAction("singbox", "install")}
                disabled={!!coreActionLoading}
                className="text-xs h-8 gap-1.5 bg-black hover:bg-neutral-800 text-white dark:bg-white dark:text-black dark:hover:bg-neutral-200"
              >
                <Download className="size-3.5" />
                {coreActionLoading === "singbox-install" ? "正在安装..." : "安装核心"}
              </Button>
            ) : (
              <Button 
                variant="outline"
                size="sm" 
                onClick={() => handleCoreAction("singbox", "uninstall")}
                disabled={!!coreActionLoading}
                className="text-xs h-8 gap-1.5 text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-950/20 border-red-200 dark:border-red-900/50"
              >
                <Trash2 className="size-3.5" />
                {coreActionLoading === "singbox-uninstall" ? "正在卸载..." : "卸载核心"}
              </Button>
            )}
          </div>
        </Card>
      </div>

      {/* Row 2: 聚合订阅服务 (一键导入所有节点) - 独立全宽下移 */}
      <Card className="p-5 flex flex-col justify-between rounded-xl border bg-card shadow-sm">
        <div>
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Layers className="size-4 text-blue-600 dark:text-blue-400" />
              <h3 className="font-semibold text-sm">聚合订阅服务 (一键导入所有节点)</h3>
            </div>
            <button 
              type="button"
              onClick={handleResetToken}
              className="text-xs text-muted-foreground hover:text-foreground cursor-pointer transition-colors"
            >
              重置 Token
            </button>
          </div>

          <p className="text-xs text-muted-foreground leading-relaxed mb-4">
            支持一键导入 Clash Verge Rev、v2rayN、Shadowrocket、Sing-box、Loon 等常见客户端。所有启用的协议节点将自动合并导出。
          </p>
        </div>

        <div className="flex items-center gap-2 pt-2">
          <Input 
            value={subUrl} 
            readOnly 
            className="h-8 text-xs font-mono select-all bg-muted/30 border-muted-foreground/20 text-muted-foreground"
          />
          <Button 
            variant="outline" 
            size="sm" 
            onClick={copySub} 
            className="h-8 text-xs shrink-0 gap-1.5"
          >
            {subCopied ? <Check className="size-3.5 text-emerald-600" /> : <Copy className="size-3.5" />}
            {subCopied ? "已复制" : "复制订阅"}
          </Button>
        </div>
      </Card>

      {/* Bottom Card: 已配置的代理节点 */}
      <Card className="rounded-xl border bg-card shadow-sm overflow-hidden">
        {licenseStatus && (
          <div className="bg-muted/30 border-b px-5 py-2.5 text-xs text-muted-foreground flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
            <div className="flex items-center gap-2">
              <span className={`px-2 py-0.5 rounded text-[10px] font-semibold ${licenseStatus.active ? "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/20" : "bg-amber-500/10 text-amber-600 border border-amber-500/20"}`}>
                {licenseStatus.plan_name || (licenseStatus.active ? "商业版" : "免费体验版")}
              </span>
              <span>
                代理节点配额：<strong>{proxyNodes.length} / {licenseStatus.max_nodes || licenseStatus.limits?.max_nodes || (licenseStatus.active ? 12 : 1)} 个</strong>
                {proxyNodes.length >= (licenseStatus.max_nodes || licenseStatus.limits?.max_nodes || (licenseStatus.active ? 12 : 1)) && (
                  <span className="text-amber-500 font-medium ml-1.5">(配额已满，升级套餐以添加更多)</span>
                )}
              </span>
            </div>
            {!licenseStatus.active && (
              <span className="text-amber-600 dark:text-amber-400 font-medium shrink-0">
                免费版限额 1 节点，激活商业版解锁更高配额
              </span>
            )}
          </div>
        )}
        <div className="p-5 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between border-b bg-card">
          <div>
            <h3 className="font-semibold text-base">已配置的代理节点</h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              每个节点都可直接复制导入链接或通过手机扫码导入，已启用的节点会自动加入聚合订阅。
            </p>
          </div>

          <div className="flex items-center gap-2 self-start sm:self-auto shrink-0">
            <Button
              variant="outline"
              size="sm"
              onClick={openUnlockConfig}
              className="text-xs h-8 gap-1.5 border-dashed hover:border-primary/50"
              title="自定义流媒体与 AI 解锁检测展示项 (可隐藏或仅选择其中两个)"
            >
              <SlidersHorizontal className="size-3.5 text-primary" />
              <span>AI与流媒体解锁</span>
              {isUnlockColVisible ? (
                <Badge variant="secondary" className="text-[10px] h-5 px-1.5 bg-primary/10 text-primary font-mono border-none">
                  {unlockEnabled.length} 项
                </Badge>
              ) : (
                <Badge variant="outline" className="text-[10px] h-5 px-1.5 text-muted-foreground border-dashed">
                  已隐藏
                </Badge>
              )}
            </Button>

            <div className="flex items-center gap-1.5 px-2.5 py-1 rounded-md border bg-muted/40 text-xs shrink-0 select-none">
              <Layers className="size-3.5 text-muted-foreground" />
              <span className="text-[11px] font-medium text-foreground">按服务器归类</span>
              <Switch
                checked={groupByServer}
                onCheckedChange={setGroupByServer}
                className="scale-75"
              />
            </div>

            <Button 
              size="sm" 
              variant="outline"
              onClick={() => {
                if (licenseStatus?.type === "revoked") {
                  toast.error("当前商业许可证已被授权中心吊销冻结，禁止创建新节点！")
                  return
                }
                if (serverOptions.length === 0) {
                  toast.error("暂无可用的服务器！请先添加探针服务器。")
                  return
                }
                setBatchDialogOpen(true)
              }}
              className="text-xs h-8 gap-1.5 border-primary/40 text-primary hover:bg-primary/10 shadow-sm font-medium"
            >
              <Sparkles className="size-3.5" />
              一键全家桶
            </Button>

            <Button 
              size="sm" 
              onClick={openCreateDialog}
              className="text-xs h-8 gap-1.5 bg-primary text-primary-foreground hover:bg-primary/90 shadow-sm"
            >
              <Plus className="size-3.5" />
              新建节点
            </Button>
          </div>
        </div>

        {proxyNodes.length === 0 ? (
          <div className="p-12 text-center text-sm text-muted-foreground">
            暂无已配置的代理节点，点击右上角【+ 新建节点】即可添加。
          </div>
        ) : groupByServer ? (
          <div className="space-y-4 p-4 pt-1">
            {serverOptions
              .map(srv => ({
                server: srv,
                nodes: proxyNodes.filter(n => n.server_id === srv.id || n.server_name === srv.name)
              }))
              .filter(g => g.nodes.length > 0)
              .map(({ server, nodes: sNodes }) => {
                const isCollapsed = Boolean(collapsedServers[String(server.id)])
                return (
                  <Card key={server.id} className="overflow-hidden border shadow-xs">
                    <div
                      onClick={() => setCollapsedServers(prev => ({ ...prev, [String(server.id)]: !prev[String(server.id)] }))}
                      className="flex flex-col sm:flex-row sm:items-center justify-between p-3 sm:p-3.5 bg-muted/40 hover:bg-muted/60 transition cursor-pointer select-none gap-2.5"
                    >
                      <div className="flex items-center justify-between w-full sm:w-auto min-w-0 gap-2">
                        <div className="flex items-center gap-2 min-w-0 flex-1">
                          <span className="size-2.5 rounded-full bg-emerald-500 shrink-0" />
                          <span className="font-bold text-sm text-foreground break-all sm:truncate" title={server.name}>
                            {server.name}
                          </span>
                        </div>
                        <div className="flex sm:hidden items-center gap-1 text-[11px] text-muted-foreground shrink-0 bg-background/80 px-2 py-0.5 rounded border">
                          <span>{isCollapsed ? "展开" : "折叠"}</span>
                          {isCollapsed ? <ChevronDown className="size-3.5" /> : <ChevronUp className="size-3.5" />}
                        </div>
                      </div>

                      <div className="flex flex-wrap items-center gap-2 text-xs">
                        <span className="text-xs font-mono text-muted-foreground bg-muted/60 px-1.5 py-0.5 rounded">
                          {server.host || server.ipv4 || "本机"}
                        </span>
                        <Badge variant="secondary" className="text-[11px] px-2 py-0.5 font-normal">
                          {sNodes.length} 个协议节点
                        </Badge>
                        <div className="hidden sm:flex items-center gap-1 text-xs text-muted-foreground ml-1">
                          <span>{isCollapsed ? "点击展开" : "点击折叠"}</span>
                          {isCollapsed ? <ChevronDown className="size-4" /> : <ChevronUp className="size-4" />}
                        </div>
                      </div>
                    </div>

                    {!isCollapsed && (
                      <div className="w-full overflow-x-auto border-t">
                        <Table>
                          <TableHeader className="bg-muted/10">
                            <TableRow className="hover:bg-transparent">
                              <TableHead className="sticky left-0 z-20 bg-background min-w-[130px] max-w-[160px] text-xs font-semibold shadow-[2px_0_4px_-1px_rgba(0,0,0,0.1)]">
                                节点名称
                              </TableHead>
                              <TableHead className="w-[100px] text-xs font-medium">VIP 权限</TableHead>
                              {isUnlockColVisible && (
                                <TableHead className="min-w-[170px] text-xs font-medium">流媒体 / AI</TableHead>
                              )}
                              <TableHead className="w-[140px] text-xs font-medium">协议</TableHead>
                              <TableHead className="w-[85px] text-xs font-medium">端口</TableHead>
                              <TableHead className="text-xs font-medium">伪装目标 / SNI</TableHead>
                              <TableHead className="w-[65px] text-xs font-medium">状态</TableHead>
                              <TableHead className="w-[190px] text-right text-xs font-medium">操作</TableHead>
                            </TableRow>
                          </TableHeader>
                          <TableBody>
                            {sNodes.map((n) => (
                              <TableRow key={n.id} className="hover:bg-muted/30">
                                <TableCell className="sticky left-0 z-10 bg-background min-w-[130px] max-w-[160px] text-xs font-medium shadow-[2px_0_4px_-1px_rgba(0,0,0,0.1)]">
                                  <div className="flex items-center gap-1.5 font-medium text-foreground">
                                    {n.flag && <span className="text-sm select-none leading-none shrink-0">{n.flag}</span>}
                                    <span className="truncate max-w-[120px] font-semibold" title={n.name}>{n.name}</span>
                                  </div>
                                </TableCell>

                                <TableCell className="text-xs">
                                  {n.vip_levels ? (
                                    <div className="flex flex-wrap gap-1">
                                      {n.vip_levels.split(",").map(v => v.trim()).filter(Boolean).map(v => (
                                        <Badge key={v} className="text-[10px] py-0 px-1.5 bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/30 uppercase font-mono font-semibold">
                                          {v}
                                        </Badge>
                                      ))}
                                    </div>
                                  ) : (
                                    <Badge variant="outline" className="text-[10px] py-0 px-1 text-muted-foreground">
                                      全员
                                    </Badge>
                                  )}
                                </TableCell>

                                {isUnlockColVisible && (
                                  <TableCell className="text-xs">
                                    <UnlockBadges
                                      status={unlockStatus[String(n.id)]}
                                      testing={testingUnlockId === n.id}
                                      onTest={() => handleTestUnlock(n.id)}
                                      enabledKeys={unlockEnabled}
                                      presets={unlockPresets}
                                      customItems={unlockCustom}
                                      showBadges={showUnlockBadges}
                                    />
                                  </TableCell>
                                )}

                                <TableCell className="text-xs">
                                  <div className="flex flex-wrap items-center gap-1">
                                    <span className="inline-block bg-[#7c3aed] text-white text-[11px] px-2.5 py-0.5 rounded-full font-medium shadow-sm">
                                      {formatProtocolBadge(n.protocol)}
                                    </span>
                                    {Boolean(n.bandwidth_limit_mbps && n.bandwidth_limit_mbps > 0) && (
                                      <span className="inline-block bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20 text-[10px] px-1.5 py-0.5 rounded-full font-mono font-medium" title={`限速: ${n.bandwidth_limit_mbps} Mbps`}>
                                        ⚡ {n.bandwidth_limit_mbps}M
                                      </span>
                                    )}
                                    {n.is_relay === 1 && (
                                      <span className="inline-block bg-sky-600 text-white text-[10px] px-1.5 py-0.5 rounded-full font-medium shadow-sm">
                                        Realm
                                      </span>
                                    )}
                                  </div>
                                </TableCell>

                                <TableCell className="text-xs font-mono text-muted-foreground">
                                  {n.is_relay === 1 ? (
                                    <span title={`中转端口 ${n.port} ➔ 落地端口 ${n.remote_port}`}>
                                      {n.port} <span className="text-blue-500 font-bold">➔</span> {n.remote_port}
                                    </span>
                                  ) : (
                                    n.port
                                  )}
                                </TableCell>

                                <TableCell className="text-xs font-mono text-muted-foreground">
                                  {n.sni || (n.is_relay === 1 ? n.remote_host : "—")}
                                </TableCell>

                                <TableCell>
                                  <Switch
                                    checked={n.enabled === 1}
                                    onCheckedChange={() => handleToggle(n.id)}
                                    className="data-[state=checked]:bg-black dark:data-[state=checked]:bg-white"
                                  />
                                </TableCell>

                                <TableCell className="text-right">
                                  <div className="flex items-center justify-end gap-1">
                                    <Button
                                      variant="ghost"
                                      size="sm"
                                      className={`h-7 text-xs gap-1 px-2 ${
                                        testResult[n.id]?.ok === true
                                          ? "text-emerald-600 hover:text-emerald-700 font-medium"
                                          : testResult[n.id]?.ok === false
                                          ? "text-red-500 hover:text-red-600 font-medium"
                                          : "text-muted-foreground hover:text-foreground"
                                      }`}
                                      onClick={() => handleTestNode(n.id)}
                                      disabled={testingId === n.id}
                                      title={testResult[n.id]?.msg || "测试节点连通性"}
                                    >
                                      <Activity className={`size-3.5 ${testingId === n.id ? "animate-spin text-primary" : ""}`} />
                                      {testingId === n.id ? "测试中" : testResult[n.id] ? `${testResult[n.id].ms}ms` : "测试"}
                                    </Button>
                                    {n.link && (
                                      <Button
                                        variant="ghost"
                                        size="sm"
                                        className="h-7 text-xs gap-1 text-muted-foreground hover:text-foreground px-2"
                                        onClick={() => copyLink(n.link!, n.id)}
                                      >
                                        {copiedId === n.id ? <Check className="size-3.5 text-emerald-600" /> : <Copy className="size-3.5" />}
                                        复制链接
                                      </Button>
                                    )}

                                    {n.link && (
                                      <Button
                                        variant="ghost"
                                        size="icon"
                                        className="size-7 text-muted-foreground hover:text-foreground"
                                        onClick={() => showQr(n)}
                                        title="手机扫码"
                                      >
                                        <QrCode className="size-3.5" />
                                      </Button>
                                    )}

                                    <Button
                                      variant="ghost"
                                      size="icon"
                                      className="size-7 text-muted-foreground hover:text-foreground"
                                      onClick={() => {
                                        setEditNode(n)
                                        setEditOpen(true)
                                      }}
                                      title="编辑节点配置"
                                    >
                                      <Pencil className="size-3.5" />
                                    </Button>

                                    <Button
                                      variant="ghost"
                                      size="icon"
                                      className="size-7 text-red-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30"
                                      onClick={() => handleDelete(n.id, n.name)}
                                      title="删除节点"
                                    >
                                      <Trash2 className="size-3.5" />
                                    </Button>
                                  </div>
                                </TableCell>
                              </TableRow>
                            ))}
                          </TableBody>
                        </Table>
                      </div>
                    )}
                  </Card>
                )
              })}
          </div>
        ) : (
          <div className="w-full overflow-x-auto">
            <Table>
              <TableHeader className="bg-muted/10">
                <TableRow className="hover:bg-transparent">
                  <TableHead className="sticky left-0 z-20 bg-background min-w-[130px] max-w-[160px] text-xs font-semibold shadow-[2px_0_4px_-1px_rgba(0,0,0,0.1)]">
                    节点名称
                  </TableHead>
                  <TableHead className="w-[150px] text-xs font-medium">所属服务器</TableHead>
                  <TableHead className="w-[90px] text-xs font-medium">VIP 权限</TableHead>
                  {isUnlockColVisible && (
                    <TableHead className="min-w-[170px] text-xs font-medium">
                      <div className="flex items-center gap-1.5">
                        <span>流媒体 / AI</span>
                        <button
                          type="button"
                          onClick={openUnlockConfig}
                          title="自定义检测项与偏好设置 (Gemini / GPT / 奈飞等)"
                          className="p-1 rounded text-muted-foreground hover:text-primary hover:bg-primary/10 transition-colors"
                        >
                          <SlidersHorizontal className="size-3.5" />
                        </button>
                      </div>
                    </TableHead>
                  )}
                  <TableHead className="w-[140px] text-xs font-medium">协议</TableHead>
                  <TableHead className="w-[85px] text-xs font-medium">端口</TableHead>
                  <TableHead className="text-xs font-medium">伪装目标 / SNI</TableHead>
                  <TableHead className="w-[65px] text-xs font-medium">状态</TableHead>
                  <TableHead className="w-[190px] text-right text-xs font-medium">操作</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {proxyNodes.map((n) => (
                  <TableRow key={n.id} className="hover:bg-muted/30">
                    <TableCell className="sticky left-0 z-10 bg-background min-w-[130px] max-w-[160px] text-xs font-medium shadow-[2px_0_4px_-1px_rgba(0,0,0,0.1)]">
                      <div className="flex items-center gap-1.5 font-medium text-foreground">
                        {n.flag && <span className="text-sm select-none leading-none shrink-0">{n.flag}</span>}
                        <span className="truncate max-w-[120px] font-semibold" title={n.name}>{n.name}</span>
                      </div>
                    </TableCell>

                    <TableCell className="text-xs">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className={`size-2 rounded-full shrink-0 ${n.is_relay ? "bg-blue-500" : "bg-emerald-500"}`} />
                        <span className="font-medium text-foreground">{n.server_name}</span>
                        <Badge 
                          variant={n.server_host.includes(":") ? "secondary" : "outline"} 
                          className={`text-[10px] py-0 px-1 font-mono shrink-0 ${
                            n.server_host.includes(":")
                              ? "bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-300 dark:border-purple-800"
                              : "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-300 dark:border-emerald-800"
                          }`}
                        >
                          {n.server_host.includes(":") ? "IPv6" : "IPv4"}
                        </Badge>
                        {n.is_relay === 1 && (
                          <Badge variant="outline" className="text-[10px] py-0 px-1 border-blue-400 text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-950/30">
                            中转
                          </Badge>
                        )}
                      </div>
                      <div className="text-[11px] text-muted-foreground font-mono truncate max-w-[150px] mt-0.5" title={n.server_host}>
                        {n.server_host}
                      </div>
                      {n.is_relay === 1 && (
                        <div className="text-[11px] text-muted-foreground mt-0.5 font-mono truncate max-w-[150px]" title={`转发至落地 ${n.remote_host}:${n.remote_port}`}>
                          ➔ {n.remote_host}:{n.remote_port}
                        </div>
                      )}
                    </TableCell>

                    <TableCell className="text-xs">
                      {n.vip_levels ? (
                        <div className="flex flex-wrap gap-1">
                          {n.vip_levels.split(",").map(v => v.trim()).filter(Boolean).map(v => (
                            <Badge key={v} className="text-[10px] py-0 px-1.5 bg-amber-500/15 text-amber-700 dark:text-amber-400 border-amber-500/30 uppercase font-mono font-semibold">
                              {v}
                            </Badge>
                          ))}
                        </div>
                      ) : (
                        <Badge variant="outline" className="text-[10px] py-0 px-1 text-muted-foreground">
                          全员
                        </Badge>
                      )}
                    </TableCell>

                    {isUnlockColVisible && (
                      <TableCell className="text-xs">
                        <UnlockBadges
                          status={unlockStatus[String(n.id)]}
                          testing={testingUnlockId === n.id}
                          onTest={() => handleTestUnlock(n.id)}
                          enabledKeys={unlockEnabled}
                          presets={unlockPresets}
                          customItems={unlockCustom}
                          showBadges={showUnlockBadges}
                        />
                      </TableCell>
                    )}

                    <TableCell className="text-xs">
                      <div className="flex flex-wrap items-center gap-1">
                        <span className="inline-block bg-[#7c3aed] text-white text-[11px] px-2.5 py-0.5 rounded-full font-medium shadow-sm">
                          {formatProtocolBadge(n.protocol)}
                        </span>
                        {Boolean(n.bandwidth_limit_mbps && n.bandwidth_limit_mbps > 0) && (
                          <span className="inline-block bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/20 text-[10px] px-1.5 py-0.5 rounded-full font-mono font-medium" title={`限速: ${n.bandwidth_limit_mbps} Mbps`}>
                            ⚡ {n.bandwidth_limit_mbps}M
                          </span>
                        )}
                        {n.is_relay === 1 && (
                          <span className="inline-block bg-sky-600 text-white text-[10px] px-1.5 py-0.5 rounded-full font-medium shadow-sm">
                            Realm
                          </span>
                        )}
                      </div>
                    </TableCell>

                    <TableCell className="text-xs font-mono text-muted-foreground">
                      {n.is_relay === 1 ? (
                        <span title={`中转端口 ${n.port} ➔ 落地端口 ${n.remote_port}`}>
                          {n.port} <span className="text-blue-500 font-bold">➔</span> {n.remote_port}
                        </span>
                      ) : (
                        n.port
                      )}
                    </TableCell>

                    <TableCell className="text-xs font-mono text-muted-foreground">
                      {n.sni || (n.is_relay === 1 ? n.remote_host : "—")}
                    </TableCell>

                    <TableCell>
                      <Switch
                        checked={n.enabled === 1}
                        onCheckedChange={() => handleToggle(n.id)}
                        className="data-[state=checked]:bg-black dark:data-[state=checked]:bg-white"
                      />
                    </TableCell>

                    <TableCell className="text-right">
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          className={`h-7 text-xs gap-1 px-2 ${
                            testResult[n.id]?.ok === true
                              ? "text-emerald-600 hover:text-emerald-700 font-medium"
                              : testResult[n.id]?.ok === false
                              ? "text-red-500 hover:text-red-600 font-medium"
                              : "text-muted-foreground hover:text-foreground"
                          }`}
                          onClick={() => handleTestNode(n.id)}
                          disabled={testingId === n.id}
                          title={testResult[n.id]?.msg || "测试节点连通性"}
                        >
                          <Activity className={`size-3.5 ${testingId === n.id ? "animate-spin text-primary" : ""}`} />
                          {testingId === n.id ? "测试中" : testResult[n.id] ? `${testResult[n.id].ms}ms` : "测试"}
                        </Button>
                        {n.link && (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 text-xs gap-1 text-muted-foreground hover:text-foreground px-2"
                            onClick={() => copyLink(n.link!, n.id)}
                          >
                            {copiedId === n.id ? <Check className="size-3.5 text-emerald-600" /> : <Copy className="size-3.5" />}
                            复制链接
                          </Button>
                        )}

                        {n.link && (
                          <Button
                            variant="ghost"
                            size="icon"
                            className="size-7 text-muted-foreground hover:text-foreground"
                            onClick={() => showQr(n)}
                            title="手机扫码"
                          >
                            <QrCode className="size-3.5" />
                          </Button>
                        )}

                        <Button
                          variant="ghost"
                          size="icon"
                          className="size-7 text-muted-foreground hover:text-foreground"
                          onClick={() => {
                            setEditNode(n)
                            setEditOpen(true)
                          }}
                          title="编辑节点配置"
                        >
                          <Pencil className="size-3.5" />
                        </Button>

                        <Button
                          variant="ghost"
                          size="icon"
                          className="size-7 text-red-500 hover:text-red-600 hover:bg-red-50 dark:hover:bg-red-950/30"
                          onClick={() => handleDelete(n.id, n.name)}
                          title="删除节点"
                        >
                          <Trash2 className="size-3.5" />
                        </Button>
                      </div>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}
      </Card>

      {/* QR Code Modal */}
      {qrNode && (
        <Dialog open={!!qrNode} onOpenChange={(open) => !open && setQrNode(null)}>
          <DialogContent className="sm:max-w-xs text-center">
            <DialogHeader>
              <DialogTitle className="text-sm font-semibold">{qrNode.name}</DialogTitle>
              <DialogDescription className="text-xs">
                使用 Shadowrocket / Clash 等客户端扫码导入
              </DialogDescription>
            </DialogHeader>

            <div className="flex justify-center p-3 bg-white rounded-lg border my-2">
              {qrDataUrl && <img src={qrDataUrl} alt="QR Code" className="size-48" />}
            </div>

            <DialogFooter className="sm:justify-center">
              <Button 
                variant="outline" 
                size="sm" 
                className="text-xs gap-1.5 w-full"
                onClick={() => qrNode.link && copyLink(qrNode.link, qrNode.id)}
              >
                <Copy className="size-3.5" />
                复制节点链接
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}

      {/* Create Node Modal */}
      <Dialog open={dialogOpen} onOpenChange={setDialogOpen}>
        <DialogContent className="w-[96vw] max-w-2xl max-h-[88vh] overflow-y-auto overflow-x-hidden p-4 sm:p-6">
          <DialogHeader>
            <DialogTitle className="text-base font-semibold">新建代理节点</DialogTitle>
            <DialogDescription className="text-xs">
              选择服务器与协议，配置将被自动下发并热生效。
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleCreateNode} className="space-y-4 py-1 w-full min-w-0 overflow-x-hidden">
            {/* 节点模式选择：直连 vs 中转落地 */}
            <div className="grid grid-cols-2 p-1 bg-muted/60 rounded-lg text-xs font-medium gap-1">
              <button
                type="button"
                className={`py-1.5 px-2 rounded-md transition-all truncate text-center ${
                  nodeMode === "direct"
                    ? "bg-card text-foreground shadow-sm font-semibold"
                    : "text-muted-foreground hover:text-foreground"
                }`}
                onClick={() => {
                  setNodeMode("direct")
                  const newName = computeNodeName(form.server_name, form.protocol, "direct", includeServerPrefix)
                  setForm(prev => ({ ...prev, is_relay: 0, name: newName }))
                }}
              >
                🟢 普通直连节点 (Direct)
              </button>
              <button
                type="button"
                className={`py-1.5 px-2 rounded-md transition-all truncate text-center ${
                  nodeMode === "relay"
                    ? "bg-card text-foreground shadow-sm font-semibold"
                    : "text-muted-foreground hover:text-foreground"
                }`}
                onClick={() => {
                  setNodeMode("relay")
                  const curServer = serverOptions.find(s => String(s.id) === form.server_id)
                  let targetServer = curServer
                  if (!curServer || !curServer.realm_installed) {
                    const realmServer = serverOptions.find(s => s.realm_installed)
                    if (realmServer) {
                      targetServer = realmServer
                      toast.info(`当前服务器未安装 Realm，已自动切换至已装 Realm 的【${realmServer.name}】`)
                    } else {
                      toast.error("当前无任何已安装 Realm 核心的服务器，请先在服务器管理中安装 Realm 核心！")
                    }
                  }
                  const targetNode = proxyNodes.find(n => String(n.id) === selectedTargetNodeId)
                  const chosenHost = targetServer ? (ipType === "ipv6" && targetServer.ipv6 ? targetServer.ipv6 : (targetServer.host || targetServer.ipv4 || "")) : form.server_host
                  const newName = computeNodeName(targetServer ? targetServer.name : form.server_name, form.protocol, "relay", includeServerPrefix, targetNode?.name)
                  setForm(prev => ({ 
                    ...prev, 
                    is_relay: 1, 
                    name: newName,
                    ...(targetServer ? {
                      server_id: String(targetServer.id),
                      server_name: targetServer.name,
                      server_host: chosenHost
                    } : {})
                  }))
                }}
              >
                🔄 中转落地节点 (Realm)
              </button>
            </div>

            {/* 所属服务器 / 入口中转机 */}
            <div className="space-y-1.5 w-full min-w-0">
              <Label className="text-xs">{nodeMode === "relay" ? "入口中转服务器" : "所属服务器"}</Label>
              <Select value={form.server_id} onValueChange={handleServerChange}>
                <SelectTrigger className="text-xs h-9 w-full min-w-0">
                  <SelectValue placeholder="选择服务器">
                    {(() => {
                      const cur = serverOptions.find(s => String(s.id) === form.server_id)
                      if (!cur) return form.server_name
                      return (
                        <div className="flex items-center justify-between w-full min-w-0 pr-1 gap-2 overflow-hidden">
                          <span className="truncate font-medium min-w-0 flex-1 text-left">{cur.name} ({cur.host})</span>
                          <div className="flex items-center gap-1.5 shrink-0 text-[11px]">
                            <span className="inline-flex items-center gap-1">
                              <span className={`size-1.5 rounded-full ${cur.xray_installed ? "bg-emerald-500" : "bg-red-500"}`} />
                              <span className={cur.xray_installed ? "text-emerald-700 dark:text-emerald-400 font-medium" : "text-red-500"}>Xray</span>
                            </span>
                            <span className="inline-flex items-center gap-1">
                              <span className={`size-1.5 rounded-full ${cur.singbox_installed ? "bg-emerald-500" : "bg-red-500"}`} />
                              <span className={cur.singbox_installed ? "text-emerald-700 dark:text-emerald-400 font-medium" : "text-red-500"}>Sing-box</span>
                            </span>
                            <span className="inline-flex items-center gap-1">
                              <span className={`size-1.5 rounded-full ${cur.realm_installed ? "bg-emerald-500" : "bg-red-500"}`} />
                              <span className={cur.realm_installed ? "text-emerald-700 dark:text-emerald-400 font-medium" : "text-red-500"}>Realm</span>
                            </span>
                          </div>
                        </div>
                      )
                    })()}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {serverOptions.length === 0 ? (
                    <div className="p-3 text-xs text-muted-foreground text-center">暂无可用的探针服务器</div>
                  ) : (
                    serverOptions.map(s => {
                      const isRelayInvalid = nodeMode === "relay" && !s.realm_installed
                      return (
                        <SelectItem 
                          key={s.id} 
                          value={String(s.id)}
                          className={isRelayInvalid ? "opacity-60 cursor-not-allowed hover:bg-destructive/10" : ""}
                        >
                          <div className="flex items-center justify-between w-full min-w-0 max-w-full gap-3">
                            <div className="flex items-center gap-1.5 min-w-0 truncate">
                              <span className="truncate font-medium text-xs">
                                {s.name} ({s.host})
                              </span>
                              {isRelayInvalid && (
                                <span className="text-[10px] text-red-500 bg-red-500/10 px-1 py-0.5 rounded font-normal shrink-0">
                                  未装Realm
                                </span>
                              )}
                            </div>
                            <div className="flex items-center gap-2 shrink-0">
                              <span className="inline-flex items-center gap-1 text-[11px]">
                                <span className={`size-1.5 rounded-full ${s.xray_installed ? "bg-emerald-500" : "bg-red-500"}`} />
                                <span className={s.xray_installed ? "text-emerald-700 dark:text-emerald-400 font-medium" : "text-red-500"}>Xray</span>
                              </span>
                              <span className="inline-flex items-center gap-1 text-[11px]">
                                <span className={`size-1.5 rounded-full ${s.singbox_installed ? "bg-emerald-500" : "bg-red-500"}`} />
                                <span className={s.singbox_installed ? "text-emerald-700 dark:text-emerald-400 font-medium" : "text-red-500"}>Sing-box</span>
                              </span>
                              <span className="inline-flex items-center gap-1 text-[11px]">
                                <span className={`size-1.5 rounded-full ${s.realm_installed ? "bg-emerald-500" : "bg-red-500"}`} />
                                <span className={s.realm_installed ? "text-emerald-700 dark:text-emerald-400 font-medium" : "text-red-500"}>Realm</span>
                              </span>
                            </div>
                          </div>
                        </SelectItem>
                      )
                    })
                  )}
                </SelectContent>
              </Select>
            </div>

            {/* 连接 IP 类型与地址协议 (IPv4 vs IPv6 vs 自定义) */}
            <div className="space-y-2 p-3 rounded-lg border bg-muted/20 w-full min-w-0">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <Label className="text-xs font-medium">连接 IP 协议 / 连接地址</Label>
                <div className="flex flex-wrap gap-1 bg-muted p-0.5 rounded-md text-[11px]">
                  <button
                    type="button"
                    className={`px-2.5 py-0.5 rounded transition-all ${
                      ipType === "ipv4"
                        ? "bg-card text-foreground shadow-xs font-semibold"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                    onClick={() => {
                      setIpType("ipv4")
                      const targetIp = currentSelectedServer?.host || currentSelectedServer?.ipv4 || ""
                      if (targetIp) {
                        setForm(prev => ({ ...prev, server_host: targetIp }))
                      }
                    }}
                  >
                    🌐 IPv4 连接
                  </button>
                  <button
                    type="button"
                    disabled={!currentSelectedServer?.ipv6}
                    className={`px-2.5 py-0.5 rounded transition-all ${
                      ipType === "ipv6"
                        ? "bg-card text-foreground shadow-xs font-semibold"
                        : currentSelectedServer?.ipv6
                        ? "text-muted-foreground hover:text-foreground"
                        : "opacity-40 cursor-not-allowed"
                    }`}
                    onClick={() => {
                      if (currentSelectedServer?.ipv6) {
                        setIpType("ipv6")
                        setForm(prev => ({ ...prev, server_host: currentSelectedServer.ipv6! }))
                      }
                    }}
                    title={currentSelectedServer?.ipv6 ? `使用 IPv6 连接 (${currentSelectedServer.ipv6})` : "所选服务器未检测到公网 IPv6 地址"}
                  >
                    ⚡ IPv6 连接 {currentSelectedServer?.ipv6 ? "" : "(无)"}
                  </button>
                  <button
                    type="button"
                    className={`px-2.5 py-0.5 rounded transition-all ${
                      ipType === "custom"
                        ? "bg-card text-foreground shadow-xs font-semibold"
                        : "text-muted-foreground hover:text-foreground"
                    }`}
                    onClick={() => setIpType("custom")}
                  >
                    ✏️ 自定义
                  </button>
                </div>
              </div>

              <div className="flex items-center gap-2 pt-0.5 w-full min-w-0">
                <Input
                  className="text-xs h-8 font-mono flex-1 min-w-0"
                  value={form.server_host}
                  onChange={e => {
                    setForm(prev => ({ ...prev, server_host: e.target.value }))
                    setIpType("custom")
                  }}
                  placeholder="客户端连接地址 (IPv4 / IPv6 / 域名)"
                  required
                />
                <Badge
                  variant={form.server_host.includes(":") ? "secondary" : "outline"}
                  className={`text-[11px] shrink-0 font-mono py-1 px-2 ${
                    form.server_host.includes(":")
                      ? "bg-purple-500/10 text-purple-600 dark:text-purple-400 border-purple-300 dark:border-purple-800"
                      : "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-300 dark:border-emerald-800"
                  }`}
                >
                  {form.server_host.includes(":") ? "IPv6" : "IPv4"}
                </Badge>
              </div>

              <div className="text-[11px] text-muted-foreground flex flex-wrap items-center justify-between gap-1">
                <span className="min-w-0 flex-1 truncate">
                  {ipType === "ipv6" && currentSelectedServer?.ipv6 && (
                    <span className="text-purple-600 dark:text-purple-400 font-medium">✓ 已绑定该服务器的 IPv6 专属连接地址</span>
                  )}
                  {ipType === "ipv4" && (
                    <span>已选用 IPv4 连接地址 ({currentSelectedServer?.host || currentSelectedServer?.ipv4})</span>
                  )}
                  {ipType === "custom" && (
                    <span>自定义连接地址（支持绑定 DDNS 域名或 CDN 节点）</span>
                  )}
                  {currentSelectedServer && !currentSelectedServer.ipv6 && ipType === "ipv6" && (
                    <span className="text-amber-500">提示：所选服务器未检测到公网 IPv6</span>
                  )}
                </span>
                {currentSelectedServer?.ipv6 && (
                  <span className="text-[10px] text-muted-foreground/80 font-mono truncate max-w-[200px]" title={currentSelectedServer.ipv6}>
                    v6: {currentSelectedServer.ipv6}
                  </span>
                )}
              </div>
            </div>

            {/* 中转落地专属：落地机目标设置 */}
            {nodeMode === "relay" && (
              <div className="rounded-xl border p-3.5 bg-muted/20 space-y-3 w-full min-w-0">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                    <ArrowRightLeft className="size-3.5 text-blue-600 dark:text-blue-400" />
                    <span>落地机目标设置</span>
                  </div>
                  <div className="flex flex-wrap gap-1 bg-muted p-0.5 rounded-md text-[11px]">
                    <button
                      type="button"
                      className={`px-2 py-0.5 rounded transition-all ${
                        relayTargetMode === "link_existing"
                          ? "bg-card text-foreground shadow-xs font-medium"
                          : "text-muted-foreground hover:text-foreground"
                      }`}
                      onClick={() => setRelayTargetMode("link_existing")}
                    >
                      关联已有节点 (推荐)
                    </button>
                    <button
                      type="button"
                      className={`px-2 py-0.5 rounded transition-all ${
                        relayTargetMode === "custom"
                          ? "bg-card text-foreground shadow-xs font-medium"
                          : "text-muted-foreground hover:text-foreground"
                      }`}
                      onClick={() => setRelayTargetMode("custom")}
                    >
                      自定义外部目标
                    </button>
                  </div>
                </div>

                {relayTargetMode === "link_existing" ? (
                  <div className="space-y-1.5 w-full min-w-0">
                    <Label className="text-xs">选择关联的落地节点</Label>
                    <Select value={selectedTargetNodeId} onValueChange={handleSelectTargetNode}>
                      <SelectTrigger className="text-xs h-9 w-full min-w-0">
                        <SelectValue placeholder="点击选择落地代理节点..." />
                      </SelectTrigger>
                      <SelectContent>
                        {proxyNodes.filter(n => !n.is_relay).map(n => (
                          <SelectItem key={n.id} value={String(n.id)}>
                            <div className="flex items-center justify-between w-full min-w-0 max-w-full gap-2">
                              <span className="font-medium text-xs truncate min-w-0">
                                {n.name}
                              </span>
                              <div className="flex items-center gap-1.5 shrink-0 text-[11px] text-muted-foreground font-mono">
                                <span className="truncate max-w-[120px]">{n.server_host}:{n.port}</span>
                                <Badge variant="secondary" className="text-[10px] py-0 px-1">{formatProtocolBadge(n.protocol)}</Badge>
                              </div>
                            </div>
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {form.remote_host && (
                      <p className="text-[11px] text-emerald-600 dark:text-emerald-400 break-words leading-relaxed">
                        ✓ 已自动继承落地目标: {form.remote_host}:{form.remote_port} ({formatProtocolBadge(form.protocol)}) 及其全部解密凭证
                      </p>
                    )}
                  </div>
                ) : (
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full min-w-0">
                    <div className="space-y-1.5 min-w-0">
                      <Label className="text-xs">落地服务器 IP / 域名</Label>
                      <Input
                        className="text-xs h-8 font-mono w-full"
                        placeholder="如 156.226.173.102"
                        value={form.remote_host}
                        onChange={e => setForm(prev => ({ ...prev, remote_host: e.target.value }))}
                        required
                      />
                    </div>
                    <div className="space-y-1.5 min-w-0">
                      <Label className="text-xs">落地监听端口</Label>
                      <Input
                        className="text-xs h-8 font-mono w-full"
                        type="number"
                        placeholder="如 44297"
                        value={form.remote_port}
                        onChange={e => setForm(prev => ({ ...prev, remote_port: e.target.value }))}
                        required
                      />
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* 节点名称与协议类型并排展示 (响应式网格) */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full min-w-0">
              <div className="space-y-1.5 min-w-0">
                <div className="flex items-center justify-between">
                  <Label className="text-xs">节点名称</Label>
                </div>
                <Input
                  className="text-xs h-9 w-full"
                  placeholder="如：Reality 或 直连节点"
                  value={form.name}
                  onChange={e => setForm(prev => ({ ...prev, name: e.target.value }))}
                  required
                />
                <div className="flex items-center gap-2 pt-0.5">
                  <input
                    type="checkbox"
                    id="checkbox-server-prefix"
                    checked={includeServerPrefix}
                    onChange={e => handleTogglePrefix(e.target.checked)}
                    className="size-3.5 rounded border-muted-foreground/30 accent-primary cursor-pointer shrink-0"
                  />
                  <Label htmlFor="checkbox-server-prefix" className="text-[11px] text-muted-foreground cursor-pointer font-normal select-none">
                    附加服务器名称前缀 (如 [{form.server_name}])
                  </Label>
                </div>
              </div>

              <div className="space-y-1.5 min-w-0">
                <Label className="text-xs">{nodeMode === "relay" ? "落地协议类型" : "协议类型"}</Label>
                <Select 
                  value={form.protocol} 
                  onValueChange={handleProtocolChange}
                  disabled={nodeMode === "relay" && relayTargetMode === "link_existing" && !!selectedTargetNodeId}
                >
                  <SelectTrigger className="text-xs h-9 w-full min-w-0">
                    <SelectValue placeholder="选择协议" />
                  </SelectTrigger>
                  <SelectContent>
                    {PROTOCOL_OPTIONS.map(opt => (
                      <SelectItem key={opt.value} value={opt.value}>
                        <div className="flex items-center justify-between w-full gap-2">
                          <span>{opt.label}</span>
                          <Badge variant="secondary" className="text-[10px] py-0 px-1">{opt.badge}</Badge>
                        </div>
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {!isRequiredCoreInstalled && (
              <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-700 dark:text-red-400 flex items-start gap-2 w-full min-w-0">
                <AlertCircle className="size-4 shrink-0 mt-0.5 text-red-600" />
                <div>
                  <span className="font-semibold">核心未安装提醒：</span>
                  {nodeMode === "relay" ? (
                    <>中转服务器【{form.server_name}】当前未安装 Realm 核心。中转端口转发需要 Realm 核心支持，请先在顶栏核心状态卡片中一键安装 Realm 核心后再创建中转落地节点。</>
                  ) : (
                    <>服务器【{form.server_name}】当前未安装 {isSingboxProto ? "Sing-box" : "Xray-Core"} 核心。{isSingboxProto ? "Hysteria 2 / AnyTLS 协议需要 Sing-box 核心支持。" : "此协议需要 Xray-Core 核心支持。"}请先在该服务器上安装对应核心后再创建节点。</>
                  )}
                </div>
              </div>
            )}

            {/* 监听端口 & 单节点限速 (并排完美对齐，响应式适配移动端) */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full min-w-0">
              <div className="space-y-1.5 min-w-0">
                <div className="flex items-center justify-between">
                  <Label className="text-xs">{nodeMode === "relay" ? "中转机监听端口 (对外开放)" : "服务器监听端口"}</Label>
                  <button
                    type="button"
                    onClick={() => handleKeygen(form.protocol, form.method)}
                    className="text-[11px] text-primary hover:underline"
                  >
                    随机空闲
                  </button>
                </div>
                <Input
                  className="text-xs h-8 font-mono w-full"
                  type="number"
                  value={form.port}
                  onChange={e => setForm(prev => ({ ...prev, port: e.target.value }))}
                  required
                />
              </div>

              <div className="space-y-1.5 min-w-0">
                <div className="flex items-center justify-between">
                  <Label className="text-xs">单节点限速 (Mbps)</Label>
                  <span className="text-[11px] text-muted-foreground font-mono">0 为不限速</span>
                </div>
                <Input
                  type="number"
                  min="0"
                  className="text-xs h-8 font-mono w-full"
                  value={form.bandwidth_limit_mbps}
                  placeholder="0"
                  onChange={e => setForm(prev => ({ ...prev, bandwidth_limit_mbps: e.target.value }))}
                />
              </div>
            </div>

            {/* 协议专属附加参数 (Shadowsocks 加密 / Socks5 用户名 / WebSocket 路径) */}
            {(form.protocol === "ss2022" || form.protocol === "socks5" || form.protocol.includes("ws") || form.protocol.includes("xhttp")) && (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 w-full min-w-0">
                {form.protocol === "ss2022" && (
                  <div className="space-y-1.5 min-w-0">
                    <Label className="text-xs">加密算法</Label>
                    <Select
                      value={form.method}
                      onValueChange={(m) => {
                        setForm(prev => ({ ...prev, method: m }))
                        handleKeygen("ss2022", m)
                      }}
                    >
                      <SelectTrigger className="text-xs h-8 w-full min-w-0">
                        <SelectValue placeholder="选择加密" />
                      </SelectTrigger>
                      <SelectContent>
                        <SelectItem value="2022-blake3-aes-128-gcm">2022-blake3-aes-128-gcm</SelectItem>
                        <SelectItem value="2022-blake3-aes-256-gcm">2022-blake3-aes-256-gcm</SelectItem>
                      </SelectContent>
                    </Select>
                  </div>
                )}

                {form.protocol === "socks5" && (
                  <div className="space-y-1.5 min-w-0">
                    <Label className="text-xs">用户名 (可选)</Label>
                    <Input
                      className="text-xs h-8 w-full"
                      placeholder="留空为无认证"
                      value={form.username}
                      onChange={e => setForm(prev => ({ ...prev, username: e.target.value }))}
                    />
                  </div>
                )}

                {(form.protocol.includes("ws") || form.protocol.includes("xhttp")) && (
                  <div className="space-y-1.5 min-w-0">
                    <Label className="text-xs">路径 (Path)</Label>
                    <Input
                      className="text-xs h-8 font-mono w-full"
                      value={form.ws_path}
                      onChange={e => setForm(prev => ({ ...prev, ws_path: e.target.value }))}
                    />
                  </div>
                )}
              </div>
            )}

                        {/* 极简折叠：高级配置与密钥 (默认收起降噪) */}
            <details className="group rounded-lg border border-border/70 bg-muted/15 p-3 space-y-3 transition-all [&_summary::-webkit-details-marker]:hidden">
              <summary className="flex cursor-pointer items-center justify-between text-xs font-semibold text-muted-foreground select-none hover:text-foreground">
                <span className="flex items-center gap-1.5">
                  <SlidersHorizontal className="size-3.5 text-primary" />
                  <span>⚙️ 高级配置 (SNI / 密钥 / UUID · 已自动生成)</span>
                </span>
                <span className="text-[10px] rounded px-1.5 py-0.5 bg-muted text-muted-foreground group-open:bg-primary/10 group-open:text-primary transition-colors">
                  点击展开
                </span>
              </summary>

              <div className="pt-2 space-y-3 border-t border-border/40">
{(form.protocol === "vless_reality" || form.protocol === "vless_reality_xhttp") && (
              <div className="rounded-lg border p-3 bg-muted/20 space-y-2.5 w-full min-w-0">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-medium">Reality 伪装与 x25519 密钥</span>
                  <button
                    type="button"
                    onClick={() => handleKeygen(form.protocol)}
                    className="text-[11px] text-primary hover:underline flex items-center gap-1"
                  >
                    <RefreshCw className="size-3" />
                    重新生成
                  </button>
                </div>

                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs w-full min-w-0">
                  <div className="min-w-0">
                    <Label className="text-[11px] text-muted-foreground">SNI 伪装域名</Label>
                    <Input
                      className="text-xs h-7 font-mono w-full"
                      value={form.sni}
                      onChange={e => setForm(prev => ({ ...prev, sni: e.target.value, dest: `${e.target.value}:443` }))}
                    />
                  </div>
                  <div className="min-w-0">
                    <Label className="text-[11px] text-muted-foreground">Dest 目标</Label>
                    <Input
                      className="text-xs h-7 font-mono w-full"
                      value={form.dest}
                      onChange={e => setForm(prev => ({ ...prev, dest: e.target.value }))}
                    />
                  </div>
                </div>

                <div className="space-y-1 text-xs w-full min-w-0">
                  <Label className="text-[11px] text-muted-foreground">Public Key (公钥)</Label>
                  <Input className="text-xs h-7 font-mono bg-background w-full truncate" value={form.public_key} readOnly />
                </div>
              </div>
            )}

            {(form.protocol === "hysteria2" || form.protocol === "anytls") && (
              <div className="space-y-1.5 w-full min-w-0">
                <Label className="text-xs">SNI 伪装域名</Label>
                <Input
                  className="text-xs h-8 font-mono w-full"
                  value={form.sni}
                  placeholder="如: www.bing.com 或 www.apple.com"
                  onChange={e => setForm(prev => ({ ...prev, sni: e.target.value, dest: `https://${e.target.value}` }))}
                  required
                />
              </div>
            )}

            <div className="space-y-1.5 w-full min-w-0">
              <div className="flex items-center justify-between">
                <Label className="text-xs">
                  {form.protocol === "ss2022" ? "预共享密钥 (Base64 Key)" : 
                   form.protocol === "trojan" || form.protocol === "socks5" || form.protocol === "hysteria2" || form.protocol === "anytls" ? "连接认证密码" : 
                   "用户 UUID"}
                </Label>
                <button
                  type="button"
                  onClick={() => handleKeygen(form.protocol, form.method)}
                  className="text-[11px] text-primary hover:underline text-xs"
                >
                  重新生成
                </button>
              </div>
              <Input
                className="text-xs h-8 font-mono w-full"
                value={form.protocol === "ss2022" || form.protocol === "trojan" || form.protocol === "socks5" || form.protocol === "hysteria2" || form.protocol === "anytls" ? form.password : form.uuid}
                onChange={e => {
                  const val = e.target.value
                  if (form.protocol === "ss2022" || form.protocol === "trojan" || form.protocol === "socks5" || form.protocol === "hysteria2" || form.protocol === "anytls") {
                    setForm(prev => ({ ...prev, password: val }))
                  } else {
                    setForm(prev => ({ ...prev, uuid: val }))
                  }
                }}
                required
              />
            </div>
              </div>
            </details>

            <div className="space-y-1.5 w-full min-w-0 pt-2 border-t">
              <div className="flex items-center justify-between">
                <Label className="text-xs font-medium">VIP 访问权限等级 <span className="text-destructive font-bold">* (必选)</span></Label>
                <span className="text-[11px] text-muted-foreground font-mono">必选项</span>
              </div>
              <Select
                value={form.vip_levels}
                onValueChange={(v) => setForm(prev => ({ ...prev, vip_levels: v }))}
              >
                <SelectTrigger className="text-xs h-8 w-full">
                  <SelectValue placeholder="请选择 VIP 访问权限等级 (必选)" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all" className="text-xs font-medium">
                    🌐 所有用户可见 (全员开放，无权限限制)
                  </SelectItem>
                  {vipTiers.map((t) => (
                    <SelectItem key={t.id || t.tier_key} value={t.tier_key} className="text-xs font-mono">
                      ⭐ {t.name} ({t.tier_key})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-[11px] text-muted-foreground">
                选择允许访问该节点的 VIP 套餐等级。若选择“所有用户可见”，普通用户与全部 VIP 均可访问；新建节点时必须选择此项，否则无法创建。
              </p>
            </div>

            <DialogFooter className="pt-2">
              <Button type="button" variant="outline" size="sm" onClick={() => setDialogOpen(false)} className="h-8 text-xs">
                取消
              </Button>
              <Button type="submit" size="sm" disabled={submitting} className="h-8 text-xs bg-primary text-primary-foreground hover:bg-primary/90 shadow-sm">
                {submitting ? "正在下发..." : "新建节点"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* 「全协议全家桶」一键批量生成 Dialog */}
      <BatchCreateDialog
        open={batchDialogOpen}
        onOpenChange={setBatchDialogOpen}
        servers={serverOptions}
        vipTiers={vipTiers}
        onSuccess={() => {
          loadData()
          loadStatus()
        }}
      />

      {/* 流媒体与 AI 解锁配置 Dialog */}
      <Dialog open={unlockConfigOpen} onOpenChange={setUnlockConfigOpen}>
        <DialogContent className="max-w-2xl max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base font-semibold">
              <SlidersHorizontal className="size-4 text-primary" />
              <span>流媒体与 AI 解锁检测配置</span>
            </DialogTitle>
            <DialogDescription className="text-xs text-muted-foreground">
              自定义在代理节点列表中实时监控与展示的平台，支持一键开关与添加自定义检测 URL。
            </DialogDescription>
          </DialogHeader>

          <div className="space-y-5 py-2">
            {/* 0. 解锁展示主开关与快捷模式 */}
            <div className="p-3.5 rounded-xl border border-rose-300/40 dark:border-rose-900/40 bg-gradient-to-r from-rose-500/5 via-card to-card space-y-3">
              <div className="flex items-center justify-between">
                <div className="space-y-0.5">
                  <div className="text-xs font-semibold text-foreground flex items-center gap-2">
                    <SlidersHorizontal className="size-3.5 text-primary" />
                    <span>在节点列表中展示【流媒体 / AI】检测栏</span>
                    {tempShowBadges ? (
                      <Badge className="text-[10px] h-4 bg-emerald-500/10 text-emerald-600 border border-emerald-500/20">已开启</Badge>
                    ) : (
                      <Badge variant="outline" className="text-[10px] h-4 text-muted-foreground border-dashed">已隐藏</Badge>
                    )}
                  </div>
                  <p className="text-[11px] text-muted-foreground">
                    若无需查看解锁，关闭此开关即可隐藏整个表格列，保持节点列表极简清爽。
                  </p>
                </div>
                <Switch
                  checked={tempShowBadges}
                  onCheckedChange={setTempShowBadges}
                />
              </div>

              {tempShowBadges && (
                <div className="pt-2 border-t border-border/40 flex flex-wrap items-center gap-1.5">
                  <span className="text-[11px] text-muted-foreground mr-1">快捷方案：</span>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setTempEnabled(["gemini", "chatgpt"])}
                    className="h-6 px-2 text-[11px] rounded-md border-blue-500/30 text-blue-600 dark:text-blue-400 bg-blue-500/5 hover:bg-blue-500/10"
                  >
                    仅看两大 AI (Gemini + ChatGPT)
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => setTempEnabled(["netflix", "youtube"])}
                    className="h-6 px-2 text-[11px] rounded-md border-rose-500/30 text-rose-600 dark:text-rose-400 bg-rose-500/5 hover:bg-rose-500/10"
                  >
                    仅看主流流媒体 (Netflix + YouTube)
                  </Button>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={() => {
                      const allPresetIds = ["gemini", "chatgpt", "claude", "netflix", "youtube", "disney", "tiktok", "spotify"]
                      setTempEnabled(allPresetIds)
                    }}
                    className="h-6 px-2 text-[11px] rounded-md"
                  >
                    全选预设
                  </Button>
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => setTempEnabled([])}
                    className="h-6 px-2 text-[11px] text-muted-foreground hover:text-rose-500"
                  >
                    清空已选 ({tempEnabled.length})
                  </Button>
                </div>
              )}
            </div>

            {/* 预设 AI 大模型 */}
            <div className="space-y-2.5">
              <div className="flex items-center gap-2">
                <Sparkles className="size-3.5 text-primary" />
                <span className="text-xs font-semibold text-foreground">AI 大模型服务</span>
                <span className="text-[11px] text-muted-foreground">（实时检测可用性与地区解锁）</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5">
                {[
                  { id: "gemini", name: "Google Gemini", desc: "Google 多模态大模型 Web & API", color: "border-blue-500/30 bg-blue-500/5" },
                  { id: "chatgpt", name: "OpenAI ChatGPT", desc: "OpenAI 官方 Web 与 App (含地区识别)", color: "border-emerald-500/30 bg-emerald-500/5" },
                  { id: "claude", name: "Anthropic Claude", desc: "Claude 对话与 API 地区支持", color: "border-amber-500/30 bg-amber-500/5" },
                ].map(item => {
                  const isChecked = tempEnabled.includes(item.id)
                  return (
                    <div
                      key={item.id}
                      onClick={() => togglePreset(item.id)}
                      className={`p-3 rounded-lg border transition-all cursor-pointer select-none flex flex-col justify-between gap-2 ${
                        isChecked
                          ? `${item.color} shadow-xs`
                          : "border-border/50 bg-card hover:border-border"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-medium text-foreground">{item.name}</span>
                        <Switch
                          checked={isChecked}
                          onCheckedChange={() => togglePreset(item.id)}
                          onClick={e => e.stopPropagation()}
                        />
                      </div>
                      <p className="text-[11px] text-muted-foreground leading-tight">{item.desc}</p>
                    </div>
                  )
                })}
              </div>
            </div>

            {/* 预设主流流媒体 */}
            <div className="space-y-2.5">
              <div className="flex items-center gap-2">
                <Activity className="size-3.5 text-rose-500" />
                <span className="text-xs font-semibold text-foreground">主流流媒体 & 视听服务</span>
                <span className="text-[11px] text-muted-foreground">（原生全解锁与跨区会员）</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2.5">
                {[
                  { id: "netflix", name: "Netflix 奈飞", desc: "原生全解锁检测 (非仅自制剧)", color: "border-rose-500/30 bg-rose-500/5" },
                  { id: "youtube", name: "YouTube Premium", desc: "Premium 跨区会员与免翻广告", color: "border-red-500/30 bg-red-500/5" },
                  { id: "disney", name: "Disney+ 迪士尼", desc: "跨国流媒体区域验证", color: "border-sky-500/30 bg-sky-500/5" },
                  { id: "tiktok", name: "TikTok 国际版", desc: "国际短视频地区封锁与免拔卡", color: "border-purple-500/30 bg-purple-500/5" },
                  { id: "spotify", name: "Spotify 音乐", desc: "全球音乐曲库与注册地区检测", color: "border-green-500/30 bg-green-500/5" },
                ].map(item => {
                  const isChecked = tempEnabled.includes(item.id)
                  return (
                    <div
                      key={item.id}
                      onClick={() => togglePreset(item.id)}
                      className={`p-3 rounded-lg border transition-all cursor-pointer select-none flex flex-col justify-between gap-2 ${
                        isChecked
                          ? `${item.color} shadow-xs`
                          : "border-border/50 bg-card hover:border-border"
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className="text-xs font-medium text-foreground">{item.name}</span>
                        <Switch
                          checked={isChecked}
                          onCheckedChange={() => togglePreset(item.id)}
                          onClick={e => e.stopPropagation()}
                        />
                      </div>
                      <p className="text-[11px] text-muted-foreground leading-tight">{item.desc}</p>
                    </div>
                  )
                })}
              </div>
            </div>

            {/* 自定义检测目标 (Custom URLs) */}
            <div className="space-y-2.5 pt-2 border-t">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Globe className="size-3.5 text-primary" />
                  <span className="text-xs font-semibold text-foreground">自定义检测规则</span>
                  <span className="text-[11px] text-muted-foreground">（探测任意特定网站或私有 API）</span>
                </div>
              </div>

              {/* 添加自定义规则输入框 */}
              <div className="flex flex-col sm:flex-row items-center gap-2">
                <Input
                  className="h-8 text-xs w-full sm:w-1/3"
                  placeholder="规则名称 (如 Bilibili港澳台)"
                  value={newCustomName}
                  onChange={e => setNewCustomName(e.target.value)}
                />
                <Input
                  className="h-8 text-xs font-mono w-full sm:flex-1"
                  placeholder="https://example.com/api/test"
                  value={newCustomUrl}
                  onChange={e => setNewCustomUrl(e.target.value)}
                />
                <Button
                  type="button"
                  size="sm"
                  onClick={handleAddCustom}
                  className="h-8 text-xs shrink-0 w-full sm:w-auto gap-1"
                >
                  <Plus className="size-3" />
                  添加规则
                </Button>
              </div>

              {/* 已添加的自定义规则列表 */}
              {tempCustom.length > 0 && (
                <div className="space-y-1.5 mt-2">
                  {tempCustom.map(cust => (
                    <div
                      key={cust.id}
                      className="flex items-center justify-between p-2 rounded-md border bg-muted/20 text-xs"
                    >
                      <div className="flex items-center gap-2 min-w-0">
                        <Switch
                          checked={tempEnabled.includes(cust.id)}
                          onCheckedChange={() => togglePreset(cust.id)}
                        />
                        <span className="font-medium text-foreground">{cust.name}</span>
                        <span className="text-[11px] font-mono text-muted-foreground truncate max-w-[280px]" title={cust.url}>
                          {cust.url}
                        </span>
                      </div>
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        onClick={() => handleRemoveCustom(cust.id)}
                        className="h-6 w-6 p-0 text-muted-foreground hover:text-rose-500"
                        title="删除该规则"
                      >
                        <Trash2 className="size-3.5" />
                      </Button>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>

          <DialogFooter className="pt-3 border-t">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => setUnlockConfigOpen(false)}
              className="h-8 text-xs"
            >
              取消
            </Button>
            <Button
              type="button"
              size="sm"
              disabled={savingUnlockConfig}
              onClick={() => handleSaveUnlockConfig(tempEnabled, tempCustom, tempShowBadges)}
              className="h-8 text-xs bg-primary text-primary-foreground hover:bg-primary/90 shadow-sm"
            >
              {savingUnlockConfig ? "正在保存..." : "保存配置"}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 节点编辑 Dialog */}
      <EditNodeDialog
        open={editOpen}
        onOpenChange={setEditOpen}
        node={editNode}
        vipTiers={vipTiers}
        onSuccess={() => {
          loadData()
          loadStatus()
        }}
      />

      {/* 删除单实例确认 Dialog (杜绝系统弹窗堆叠与删除延迟) */}
      {deleteConfirmNode && (
        <Dialog open={true} onOpenChange={(open) => { if (!open) setDeleteConfirmNode(null) }}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle className="text-base font-semibold flex items-center gap-2 text-rose-600">
                <Trash2 className="size-4" /> 确认删除节点
              </DialogTitle>
              <DialogDescription className="text-xs pt-1">
                确定要删除节点【{deleteConfirmNode.name}】吗？此操作将立即停止该协议服务并不可恢复。
              </DialogDescription>
            </DialogHeader>
            <DialogFooter className="pt-3">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setDeleteConfirmNode(null)}
                className="h-8 text-xs"
              >
                取消
              </Button>
              <Button
                variant="destructive"
                size="sm"
                disabled={deleting}
                onClick={handleConfirmDelete}
                className="h-8 text-xs"
              >
                {deleting ? "正在删除..." : "确认删除"}
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  )
}

function BatchCreateDialog({
  open,
  onOpenChange,
  servers,
  vipTiers = [],
  onSuccess,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  servers: any[]
  vipTiers?: any[]
  onSuccess: () => void
}) {
  const [serverId, setServerId] = useState<string>(servers[0] ? String(servers[0].id) : "0")
  const [protocols, setProtocols] = useState<string[]>([
    "vless_reality",
    "hysteria2",
    "anytls",
    "trojan",
    "ss2022",
  ])
  const [bandwidth, setBandwidth] = useState<string>("0")
  const [vipLevels, setVipLevels] = useState<string>("")
  const [submitting, setSubmitting] = useState(false)

  // 当外部服务器列表更新且当前尚未选定时自动同步
  useEffect(() => {
    if (servers.length > 0 && (!serverId || serverId === "0")) {
      setServerId(String(servers[0].id))
    }
  }, [servers, serverId])

  const ALL_BATCH_PROTOS = [
    { id: "vless_reality", name: "VLESS Reality", desc: "XTLS Vision + TCP (高隐蔽主流伪装)" },
    { id: "vless_reality_xhttp", name: "VLESS XHTTP", desc: "XHTTP 流协议 (抗弱网与抗封锁)" },
    { id: "hysteria2", name: "Hysteria 2", desc: "极速 UDP 拥塞控制 (弱网暴力提速)" },
    { id: "anytls", name: "AnyTLS", desc: "自适应 TLS 隧道协议 (Sing-box 专属)" },
    { id: "trojan", name: "Trojan", desc: "标准 TLS 仿真实流量伪装协议" },
    { id: "ss2022", name: "Shadowsocks 2022", desc: "AEAD-2022 Blake3 轻量加密" },
  ]

  const toggleProto = (p: string) => {
    setProtocols((prev) =>
      prev.includes(p) ? prev.filter((x) => x !== p) : [...prev, p]
    )
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (protocols.length === 0) {
      toast.error("请至少勾选一个协议！")
      return
    }
    setSubmitting(true)
    try {
      const res = await fetch("/api/proxy/nodes/batch-create", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          server_id: parseInt(serverId) || 0,
          protocols,
          bandwidth_limit_mbps: parseInt(bandwidth) || 0,
          vip_levels: vipLevels,
        }),
      })
      const data = await res.json()
      if (!res.ok || !data.ok) {
        throw new Error(data.message || "批量生成全家桶失败")
      }
      toast.success(data.message || `成功生成 ${protocols.length} 个协议节点！`)
      onOpenChange(false)
      onSuccess()
    } catch (err: any) {
      toast.error(err.message || "批量创建出错")
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[96vw] max-w-lg max-h-[88vh] overflow-y-auto overflow-x-hidden p-4 sm:p-6">
        <DialogHeader>
          <DialogTitle className="text-base font-semibold flex items-center gap-2">
            <Sparkles className="size-4 text-primary" /> 「全协议全家桶」一键批量生成
          </DialogTitle>
          <DialogDescription className="text-xs">
            选择目标服务器后，系统将自动分配独立端口并一键批量创建 VLESS Reality、Hysteria 2、AnyTLS、Trojan、SS2022 等主流核心协议节点。
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 pt-2">
          <div className="space-y-1.5">
            <Label className="text-xs font-medium">选择目标服务器</Label>
            <Select value={serverId} onValueChange={setServerId}>
              <SelectTrigger className="h-9 text-xs">
                <SelectValue placeholder="选择目标服务器" />
              </SelectTrigger>
              <SelectContent>
                {servers.map((s) => (
                  <SelectItem key={s.id} value={String(s.id)} className="text-xs">
                    {s.name} ({s.host || s.ipv4 || "本机"})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label className="text-xs font-medium">勾选要生成的协议组合</Label>
              <span className="text-[11px] text-muted-foreground">已选择 {protocols.length} 个协议</span>
            </div>
            <div className="grid grid-cols-1 gap-2 border rounded-lg p-2.5 bg-muted/20">
              {ALL_BATCH_PROTOS.map((p) => {
                const checked = protocols.includes(p.id)
                return (
                  <div
                    key={p.id}
                    onClick={() => toggleProto(p.id)}
                    className={`flex items-start gap-2.5 p-2 rounded-md border cursor-pointer transition-all ${
                      checked
                        ? "bg-primary/5 border-primary/40 text-foreground"
                        : "border-transparent text-muted-foreground hover:bg-muted/40"
                    }`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => {}}
                      className="mt-0.5 rounded border-muted-foreground/30 text-primary focus:ring-primary cursor-pointer"
                    />
                    <div className="flex-1 min-w-0">
                      <div className="text-xs font-medium flex items-center gap-1.5">
                        <span>{p.name}</span>
                        {checked && <Check className="size-3 text-primary shrink-0" />}
                      </div>
                      <div className="text-[11px] text-muted-foreground leading-tight mt-0.5">
                        {p.desc}
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs font-medium">统一单节点带宽限制 (Mbps)</Label>
            <div className="flex items-center gap-2">
              <Input
                type="number"
                min="0"
                value={bandwidth}
                onChange={(e) => setBandwidth(e.target.value)}
                placeholder="0"
                className="text-xs h-9 font-mono w-36"
              />
              <span className="text-xs text-muted-foreground shrink-0 font-mono">Mbps (0 为不限速)</span>
            </div>
            <p className="text-[11px] text-muted-foreground">
              为本次批量创建的每个节点配置 QoS 速率上限，0 代表不限制带宽速率。
            </p>
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label className="text-xs font-medium">统一 VIP 访问等级</Label>
              <span className="text-[11px] text-muted-foreground font-mono">必选项</span>
            </div>
            <Select
              value={vipLevels || "all"}
              onValueChange={setVipLevels}
            >
              <SelectTrigger className="h-9 text-xs">
                <SelectValue placeholder="请选择 VIP 访问等级" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all" className="text-xs font-medium">
                  🌐 所有用户可见 (全员开放，无权限限制)
                </SelectItem>
                {vipTiers.map((t) => (
                  <SelectItem key={t.id || t.tier_key} value={t.tier_key} className="text-xs font-mono">
                    ⭐ {t.name} ({t.tier_key})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-[11px] text-muted-foreground">
              为批量创建的所有节点绑定 VIP 权限。选择“所有用户可见”代表全员可访问与订阅。
            </p>
          </div>

          <DialogFooter className="pt-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => onOpenChange(false)}
              className="h-8 text-xs"
            >
              取消
            </Button>
            <Button
              type="submit"
              size="sm"
              disabled={submitting || protocols.length === 0}
              className="h-8 text-xs gap-1.5 bg-primary text-primary-foreground hover:bg-primary/90"
            >
              {submitting ? "正在批量生成..." : `立即生成全家桶 (${protocols.length} 个节点)`}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}

function EditNodeDialog({
  open,
  onOpenChange,
  node,
  vipTiers = [],
  onSuccess,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  node: ProxyNode | null
  vipTiers?: any[]
  onSuccess: () => void
}) {
  const [form, setForm] = useState({
    name: "",
    port: "",
    uuid: "",
    password: "",
    sni: "",
    bandwidth_limit_mbps: "0",
    vip_levels: "",
    enabled: 1,
  })
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (node) {
      setForm({
        name: node.name || "",
        port: String(node.port || ""),
        uuid: node.uuid || "",
        password: node.password || "",
        sni: node.sni || "",
        bandwidth_limit_mbps: String(node.bandwidth_limit_mbps || 0),
        vip_levels: node.vip_levels || "",
        enabled: node.enabled ?? 1,
      })
    }
  }, [node])

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!node) return
    setSaving(true)
    try {
      const res = await fetch(`/api/proxy/nodes/${node.id}/edit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          name: form.name,
          port: parseInt(form.port),
          uuid: form.uuid,
          password: form.password,
          sni: form.sni,
          bandwidth_limit_mbps: parseInt(form.bandwidth_limit_mbps) || 0,
          vip_levels: form.vip_levels,
          enabled: form.enabled,
        }),
      })
      const data = await res.json()
      if (!res.ok || !data.ok) throw new Error(data.message || "更新节点失败")
      toast.success(data.message || "节点配置已更新！")
      onOpenChange(false)
      onSuccess()
    } catch (err: any) {
      toast.error(err.message || "更新出错")
    } finally {
      setSaving(false)
    }
  }

  if (!node) return null

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[96vw] max-w-lg max-h-[88vh] overflow-y-auto p-4 sm:p-6">
        <DialogHeader>
          <DialogTitle className="text-base font-semibold flex items-center gap-2">
            <Pencil className="size-4 text-primary" /> 编辑代理节点: {node.name}
          </DialogTitle>
          <DialogDescription className="text-xs">
            修改节点的端口、密钥、SNI 伪装、限速策略及 VIP 套餐访问权限。
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 pt-2">
          <div className="space-y-1.5">
            <Label className="text-xs font-medium">节点名称</Label>
            <Input
              value={form.name}
              onChange={e => setForm(prev => ({ ...prev, name: e.target.value }))}
              required
              className="text-xs h-8"
            />
          </div>

          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1.5">
              <Label className="text-xs font-medium">服务监听端口</Label>
              <Input
                type="number"
                value={form.port}
                onChange={e => setForm(prev => ({ ...prev, port: e.target.value }))}
                required
                className="text-xs h-8 font-mono"
              />
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-medium">单节点限速 (Mbps, 0为不限)</Label>
              <Input
                type="number"
                min="0"
                value={form.bandwidth_limit_mbps}
                onChange={e => setForm(prev => ({ ...prev, bandwidth_limit_mbps: e.target.value }))}
                className="text-xs h-8 font-mono"
              />
            </div>
          </div>

          {node.uuid && (
            <div className="space-y-1.5">
              <Label className="text-xs font-medium">用户 UUID</Label>
              <Input
                value={form.uuid}
                onChange={e => setForm(prev => ({ ...prev, uuid: e.target.value }))}
                className="text-xs h-8 font-mono"
              />
            </div>
          )}

          {node.password && (
            <div className="space-y-1.5">
              <Label className="text-xs font-medium">认证密码 / 预共享密钥</Label>
              <Input
                value={form.password}
                onChange={e => setForm(prev => ({ ...prev, password: e.target.value }))}
                className="text-xs h-8 font-mono"
              />
            </div>
          )}

          <div className="space-y-1.5">
            <Label className="text-xs font-medium">SNI 伪装域名</Label>
            <Input
              value={form.sni}
              onChange={e => setForm(prev => ({ ...prev, sni: e.target.value }))}
              className="text-xs h-8 font-mono"
              placeholder="如 www.apple.com"
            />
          </div>

          <div className="space-y-1.5">
            <div className="flex items-center justify-between">
              <Label className="text-xs font-medium">VIP 访问权限等级 <span className="text-destructive">*</span></Label>
              <span className="text-[11px] text-muted-foreground font-mono">控制可见权限</span>
            </div>
            <Select
              value={form.vip_levels || "all"}
              onValueChange={(v) => setForm(prev => ({ ...prev, vip_levels: v }))}
            >
              <SelectTrigger className="text-xs h-8 w-full">
                <SelectValue placeholder="请选择 VIP 访问权限等级" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="all" className="text-xs font-medium">
                  🌐 所有用户可见 (全员开放，无权限限制)
                </SelectItem>
                {vipTiers.map((t) => (
                  <SelectItem key={t.id || t.tier_key} value={t.tier_key} className="text-xs font-mono">
                    ⭐ {t.name} ({t.tier_key})
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <p className="text-[11px] text-muted-foreground">
              绑定对应的 VIP 套餐等级。选择“所有用户可见”则普通用户和所有 VIP 用户均可获取。
            </p>
          </div>

          <div className="flex items-center justify-between p-3 rounded-lg border bg-muted/20">
            <div className="space-y-0.5">
              <div className="text-xs font-medium">节点启用状态</div>
              <div className="text-[11px] text-muted-foreground">关闭后将停止下发该节点</div>
            </div>
            <Switch
              checked={form.enabled === 1}
              onCheckedChange={checked => setForm(prev => ({ ...prev, enabled: checked ? 1 : 0 }))}
            />
          </div>

          <DialogFooter className="pt-2">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => onOpenChange(false)}
              className="h-8 text-xs"
            >
              取消
            </Button>
            <Button
              type="submit"
              size="sm"
              disabled={saving}
              className="h-8 text-xs bg-primary text-primary-foreground hover:bg-primary/90 shadow-sm"
            >
              {saving ? "正在保存..." : "保存修改"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
