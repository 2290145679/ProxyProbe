import { useEffect, useState, useCallback } from "react"
import { 
  GitFork, Layers, Plus, RefreshCw, Copy, Check, Trash2, 
  QrCode, Box, Activity, Download, AlertCircle, ArrowRightLeft
} from "lucide-react"
import { toast } from "sonner"
import QRCode from "qrcode"

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
}

export interface ProxyServer {
  id: number
  name: string
  host: string
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

interface CoreStatus {
  installed: boolean
  version: string
  running: boolean
}

const PROTOCOL_OPTIONS = [
  { value: "vless_reality", label: "VLESS + Reality", badge: "推荐" },
  { value: "vless_reality_xhttp", label: "VLESS + Reality + XHTTP", badge: "新特性" },
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
  const [realmStatus, setRealmStatus] = useState<CoreStatus>({
    installed: false,
    version: "",
    running: false,
  })
  const [nodeMode, setNodeMode] = useState<"direct" | "relay">("direct")
  const [relayTargetMode, setRelayTargetMode] = useState<"link_existing" | "custom">("link_existing")
  const [selectedTargetNodeId, setSelectedTargetNodeId] = useState<string>("")
  const [testingId, setTestingId] = useState<number | null>(null)
  const [testResult, setTestResult] = useState<Record<number, { ok: boolean; msg: string; ms: number }>>({})

  const [copiedId, setCopiedId] = useState<number | null>(null)
  const [subCopied, setSubCopied] = useState(false)

  // QR Code Dialog
  const [qrNode, setQrNode] = useState<ProxyNode | null>(null)
  const [qrDataUrl, setQrDataUrl] = useState<string>("")

  // Create Modal State
  const [dialogOpen, setDialogOpen] = useState(false)
  const [submitting, setSubmitting] = useState(false)
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
  })

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
        if (data.realm) {
          setRealmStatus(data.realm)
        }
      }
    } catch {
      // Keep default
    } finally {
      setStatusLoading(false)
    }
  }, [])

  const handleTestNode = async (id: number) => {
    setTestingId(id)
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

  const serverOptions: ProxyServer[] = servers.length > 0 ? servers : [
    {
      id: 0,
      name: "本机 (当前服务器)",
      host: "189.24.108.25",
      is_local: true,
      token: "",
      xray_installed: xrayStatus.installed,
      xray_running: xrayStatus.running,
      singbox_installed: singboxStatus.installed,
      singbox_running: singboxStatus.running,
      realm_installed: realmStatus.installed,
      realm_running: realmStatus.running
    },
    ...nodes.map(n => ({
      id: n.id,
      name: n.name,
      host: n.ipv4 || n.ip || "自动解析",
      is_local: false,
      token: "",
      xray_installed: false,
      xray_running: false,
      singbox_installed: false,
      singbox_running: false,
      realm_installed: false,
      realm_running: false
    }))
  ]

  const currentSelectedServer = serverOptions.find(s => String(s.id) === form.server_id)
  const isSingboxProto = form.protocol === "hysteria2" || form.protocol === "tuic"
  const isRequiredCoreInstalled = nodeMode === "relay"
    ? Boolean(currentSelectedServer?.realm_installed)
    : (isSingboxProto ? Boolean(currentSelectedServer?.singbox_installed) : Boolean(currentSelectedServer?.xray_installed))

  const openCreateDialog = () => {
    const defaultServer = serverOptions.length > 0 ? serverOptions[0] : null
    const sId = defaultServer ? String(defaultServer.id) : "0"
    const sName = defaultServer ? defaultServer.name : "本机"
    const sHost = defaultServer ? defaultServer.host : "189.24.108.25"

    setNodeMode("direct")
    setRelayTargetMode("link_existing")
    setSelectedTargetNodeId("")
    setForm({
      server_id: sId,
      server_name: sName,
      server_host: sHost,
      name: `${sName}-Reality`,
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
    })
    setDialogOpen(true)
    handleKeygen("vless_reality")
  }

  const handleProtocolChange = (p: string) => {
    const label = PROTOCOL_OPTIONS.find(o => o.value === p)?.label || p
    const cleanLabel = label.split(" ")[0]
    setForm(prev => ({ ...prev, protocol: p, name: `${prev.server_name}-${cleanLabel}` }))
    handleKeygen(p, form.method)
  }

  const handleServerChange = (sId: string) => {
    const s = serverOptions.find(n => String(n.id) === sId)
    if (s) {
      const cleanProto = PROTOCOL_OPTIONS.find(o => o.value === form.protocol)?.label?.split(" ")[0] || "Node"
      setForm(prev => ({ 
        ...prev, 
        server_id: sId, 
        server_name: s.name, 
        server_host: s.host,
        name: nodeMode === "relay" 
          ? `[中转] ${s.name} ➔ ${prev.remote_host || "落地"}`
          : `${s.name}-${cleanProto}`
      }))
    }
  }

  const handleSelectTargetNode = (targetId: string) => {
    setSelectedTargetNodeId(targetId)
    const targetNode = proxyNodes.find(n => String(n.id) === targetId)
    if (targetNode) {
      setForm(prev => ({
        ...prev,
        target_node_id: targetNode.id,
        name: `[中转] ${prev.server_name} ➔ ${targetNode.name}`,
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

  const handleDelete = async (id: number, name: string) => {
    if (!confirm(`确定要删除节点 [${name}] 吗？`)) return
    try {
      const res = await fetch(`/api/proxy/nodes/${id}`, { method: "DELETE" })
      const data = await res.json()
      if (data.ok) {
        toast.success("节点已删除")
        loadData()
      } else {
        toast.error(data.message || "删除失败")
      }
    } catch {
      toast.error("网络异常")
    }
  }

  const copyLink = (link: string, id: number) => {
    navigator.clipboard.writeText(link)
    setCopiedId(id)
    toast.success("复制链接成功")
    setTimeout(() => setCopiedId(null), 2000)
  }

  const copySub = () => {
    const subUrl = `${location.origin}/api/proxy/sub?token=${subToken}`
    navigator.clipboard.writeText(subUrl)
    setSubCopied(true)
    toast.success("订阅链接已复制")
    setTimeout(() => setSubCopied(false), 2000)
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

  return (
    <div className="space-y-5">
      {/* Row 1: Triple Core Status: Xray & Sing-box & Realm side by side */}
      <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
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

        {/* Third Card: Realm 端口转发核心状态 (样式与 Xray/Sing-box 1:1 对齐) */}
        <Card className="p-5 flex flex-col justify-between rounded-xl border bg-card shadow-sm">
          <div>
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <ArrowRightLeft className="size-4 text-foreground/80" />
                <h3 className="font-semibold text-sm">Realm 转发核心状态</h3>
              </div>
              {!realmStatus.installed ? (
                <Badge variant="outline" className="border-neutral-300 text-muted-foreground rounded-full px-2.5 py-0.5 text-xs font-normal">
                  未安装
                </Badge>
              ) : (
                <Badge 
                  className={realmStatus.running ? "bg-emerald-600 hover:bg-emerald-600 text-white rounded-full px-2.5 py-0.5 text-xs font-normal" : "bg-destructive text-destructive-foreground rounded-full px-2.5 py-0.5 text-xs font-normal"}
                >
                  {realmStatus.running ? "运行中" : "未运行"}
                </Badge>
              )}
            </div>

            <p className="text-xs text-muted-foreground leading-relaxed font-mono whitespace-pre-wrap break-all mb-4">
              {!realmStatus.installed
                ? "当前服务器尚未安装 Realm 核心。安装后支持极速 TCP/UDP 端口转发与中转落地。"
                : (realmStatus.version || "Realm 2.9 (rust musl)")}
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

            {!realmStatus.installed ? (
              <Button 
                size="sm" 
                onClick={() => handleCoreAction("realm", "install")}
                disabled={!!coreActionLoading}
                className="text-xs h-8 gap-1.5 bg-black hover:bg-neutral-800 text-white dark:bg-white dark:text-black dark:hover:bg-neutral-200"
              >
                <Download className="size-3.5" />
                {coreActionLoading === "realm-install" ? "正在安装..." : "安装核心"}
              </Button>
            ) : (
              <Button 
                variant="outline"
                size="sm" 
                onClick={() => handleCoreAction("realm", "uninstall")}
                disabled={!!coreActionLoading}
                className="text-xs h-8 gap-1.5 text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-950/20 border-red-200 dark:border-red-900/50"
              >
                <Trash2 className="size-3.5" />
                {coreActionLoading === "realm-uninstall" ? "正在卸载..." : "卸载核心"}
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
        <div className="p-5 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between border-b bg-card">
          <div>
            <h3 className="font-semibold text-base">已配置的代理节点</h3>
            <p className="text-xs text-muted-foreground mt-0.5">
              每个节点都可直接复制导入链接或通过手机扫码导入，已启用的节点会自动加入聚合订阅。
            </p>
          </div>

          <Button 
            size="sm" 
            onClick={openCreateDialog}
            className="text-xs h-8 gap-1.5 bg-black hover:bg-neutral-800 text-white dark:bg-white dark:text-black dark:hover:bg-neutral-200 self-start sm:self-auto shrink-0"
          >
            <Plus className="size-3.5" />
            新建节点
          </Button>
        </div>

        {proxyNodes.length === 0 ? (
          <div className="p-12 text-center text-sm text-muted-foreground">
            暂无已配置的代理节点，点击右上角【+ 新建节点】即可添加。
          </div>
        ) : (
          <Table>
            <TableHeader className="bg-muted/10">
              <TableRow className="hover:bg-transparent">
                <TableHead className="w-[160px] text-xs font-medium">所属服务器</TableHead>
                <TableHead className="w-[180px] text-xs font-medium">节点名称</TableHead>
                <TableHead className="w-[180px] text-xs font-medium">协议</TableHead>
                <TableHead className="w-[100px] text-xs font-medium">端口</TableHead>
                <TableHead className="text-xs font-medium">伪装目标 / SNI</TableHead>
                <TableHead className="w-[80px] text-xs font-medium">状态</TableHead>
                <TableHead className="w-[180px] text-right text-xs font-medium">操作</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {proxyNodes.map((n) => (
                <TableRow key={n.id} className="hover:bg-muted/30">
                  <TableCell className="text-xs">
                    <div className="flex items-center gap-2">
                      <span className={`size-2 rounded-full shrink-0 ${n.is_relay ? "bg-blue-500" : "bg-emerald-500"}`} />
                      <span className="font-medium text-foreground">{n.server_name}</span>
                      {n.is_relay === 1 && (
                        <Badge variant="outline" className="text-[10px] py-0 px-1 border-blue-400 text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-950/30">
                          中转
                        </Badge>
                      )}
                    </div>
                    {n.is_relay === 1 && (
                      <div className="text-[11px] text-muted-foreground mt-0.5 font-mono truncate max-w-[150px]" title={`转发至落地 ${n.remote_host}:${n.remote_port}`}>
                        ➔ {n.remote_host}:{n.remote_port}
                      </div>
                    )}
                  </TableCell>

                  <TableCell className="text-xs font-medium">
                    {n.name}
                  </TableCell>

                  <TableCell className="text-xs">
                    <div className="flex flex-wrap items-center gap-1">
                      <span className="inline-block bg-[#7c3aed] text-white text-[11px] px-2.5 py-0.5 rounded-full font-medium shadow-sm">
                        {formatProtocolBadge(n.protocol)}
                      </span>
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
        <DialogContent className="sm:max-w-lg max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle className="text-base font-semibold">新建代理节点</DialogTitle>
            <DialogDescription className="text-xs">
              选择服务器与协议，配置将被自动下发并热生效。
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleCreateNode} className="space-y-4 py-2">
            {/* 节点模式选择：直连 vs 中转落地 */}
            <div className="flex p-1 bg-muted/60 rounded-lg text-xs font-medium">
              <button
                type="button"
                className={`flex-1 py-1.5 px-3 rounded-md transition-all ${
                  nodeMode === "direct"
                    ? "bg-card text-foreground shadow-sm font-semibold"
                    : "text-muted-foreground hover:text-foreground"
                }`}
                onClick={() => {
                  setNodeMode("direct")
                  setForm(prev => ({ ...prev, is_relay: 0 }))
                }}
              >
                🟢 普通直连节点 (Direct)
              </button>
              <button
                type="button"
                className={`flex-1 py-1.5 px-3 rounded-md transition-all ${
                  nodeMode === "relay"
                    ? "bg-card text-foreground shadow-sm font-semibold"
                    : "text-muted-foreground hover:text-foreground"
                }`}
                onClick={() => {
                  setNodeMode("relay")
                  setForm(prev => ({ 
                    ...prev, 
                    is_relay: 1,
                    name: `[中转] ${prev.server_name} ➔ 落地`
                  }))
                }}
              >
                🔄 中转落地节点 (Realm 转发)
              </button>
            </div>

            {/* 所属服务器 / 入口中转机 */}
            <div className="space-y-1.5 w-full">
              <Label className="text-xs">{nodeMode === "relay" ? "入口中转服务器" : "所属服务器"}</Label>
              <Select value={form.server_id} onValueChange={handleServerChange}>
                <SelectTrigger className="text-xs h-9 w-full">
                  <SelectValue placeholder="选择服务器">
                    {(() => {
                      const cur = serverOptions.find(s => String(s.id) === form.server_id)
                      if (!cur) return form.server_name
                      return (
                        <div className="flex items-center justify-between w-full pr-1 gap-2 overflow-hidden">
                          <span className="truncate font-medium">{cur.name} ({cur.host})</span>
                          <div className="flex items-center gap-2.5 shrink-0">
                            <span className="inline-flex items-center gap-1 text-[11px]">
                              <span className={`size-2 rounded-full ${cur.xray_installed ? "bg-emerald-500" : "bg-red-500"}`} />
                              <span className={cur.xray_installed ? "text-emerald-700 dark:text-emerald-400 font-medium" : "text-red-500"}>Xray</span>
                            </span>
                            <span className="inline-flex items-center gap-1 text-[11px]">
                              <span className={`size-2 rounded-full ${cur.singbox_installed ? "bg-emerald-500" : "bg-red-500"}`} />
                              <span className={cur.singbox_installed ? "text-emerald-700 dark:text-emerald-400 font-medium" : "text-red-500"}>Sing-box</span>
                            </span>
                            <span className="inline-flex items-center gap-1 text-[11px]">
                              <span className={`size-2 rounded-full ${cur.realm_installed ? "bg-emerald-500" : "bg-red-500"}`} />
                              <span className={cur.realm_installed ? "text-emerald-700 dark:text-emerald-400 font-medium" : "text-red-500"}>Realm</span>
                            </span>
                          </div>
                        </div>
                      )
                    })()}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {serverOptions.map(s => (
                    <SelectItem key={s.id} value={String(s.id)}>
                      <div className="flex items-center justify-between w-full min-w-[320px] gap-3">
                        <span className="truncate font-medium text-xs">
                          {s.name} ({s.host})
                        </span>
                        <div className="flex items-center gap-2 shrink-0">
                          <span className="inline-flex items-center gap-1 text-[11px]">
                            <span className={`size-2 rounded-full ${s.xray_installed ? "bg-emerald-500" : "bg-red-500"}`} />
                            <span className={s.xray_installed ? "text-emerald-700 dark:text-emerald-400 font-medium" : "text-red-500"}>Xray</span>
                          </span>
                          <span className="inline-flex items-center gap-1 text-[11px]">
                            <span className={`size-2 rounded-full ${s.singbox_installed ? "bg-emerald-500" : "bg-red-500"}`} />
                            <span className={s.singbox_installed ? "text-emerald-700 dark:text-emerald-400 font-medium" : "text-red-500"}>Sing-box</span>
                          </span>
                          <span className="inline-flex items-center gap-1 text-[11px]">
                            <span className={`size-2 rounded-full ${s.realm_installed ? "bg-emerald-500" : "bg-red-500"}`} />
                            <span className={s.realm_installed ? "text-emerald-700 dark:text-emerald-400 font-medium" : "text-red-500"}>Realm</span>
                          </span>
                        </div>
                      </div>
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {/* 中转落地专属：落地机目标设置 */}
            {nodeMode === "relay" && (
              <div className="rounded-xl border p-3.5 bg-muted/20 space-y-3">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-1.5 text-xs font-semibold text-foreground">
                    <ArrowRightLeft className="size-3.5 text-blue-600 dark:text-blue-400" />
                    <span>落地机目标设置</span>
                  </div>
                  <div className="flex gap-1 bg-muted p-0.5 rounded-md text-[11px]">
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
                  <div className="space-y-1.5">
                    <Label className="text-xs">选择关联的落地节点</Label>
                    <Select value={selectedTargetNodeId} onValueChange={handleSelectTargetNode}>
                      <SelectTrigger className="text-xs h-9">
                        <SelectValue placeholder="点击选择落地代理节点..." />
                      </SelectTrigger>
                      <SelectContent>
                        {proxyNodes.filter(n => !n.is_relay).map(n => (
                          <SelectItem key={n.id} value={String(n.id)}>
                            <div className="flex items-center justify-between w-full min-w-[320px] gap-3">
                              <span className="font-medium text-xs truncate">
                                [{n.server_name}] {n.name}
                              </span>
                              <div className="flex items-center gap-1.5 shrink-0 text-[11px] text-muted-foreground font-mono">
                                <span>{n.server_host}:{n.port}</span>
                                <Badge variant="secondary" className="text-[10px] py-0 px-1">{formatProtocolBadge(n.protocol)}</Badge>
                              </div>
                            </div>
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    {form.remote_host && (
                      <p className="text-[11px] text-emerald-600 dark:text-emerald-400">
                        ✓ 已自动继承落地目标: {form.remote_host}:{form.remote_port} ({formatProtocolBadge(form.protocol)}) 及其全部解密凭证
                      </p>
                    )}
                  </div>
                ) : (
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1.5">
                      <Label className="text-xs">落地服务器 IP / 域名</Label>
                      <Input
                        className="text-xs h-8 font-mono"
                        placeholder="如 156.226.173.102"
                        value={form.remote_host}
                        onChange={e => setForm(prev => ({ ...prev, remote_host: e.target.value }))}
                        required
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label className="text-xs">落地监听端口</Label>
                      <Input
                        className="text-xs h-8 font-mono"
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

            {/* 节点名称与协议类型并排展示 */}
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-xs">节点名称</Label>
                <Input
                  className="text-xs h-9"
                  placeholder="如：香港-Reality"
                  value={form.name}
                  onChange={e => setForm(prev => ({ ...prev, name: e.target.value }))}
                  required
                />
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs">{nodeMode === "relay" ? "落地协议类型" : "协议类型"}</Label>
                <Select 
                  value={form.protocol} 
                  onValueChange={handleProtocolChange}
                  disabled={nodeMode === "relay" && relayTargetMode === "link_existing" && !!selectedTargetNodeId}
                >
                  <SelectTrigger className="text-xs h-9">
                    <SelectValue placeholder="选择协议" />
                  </SelectTrigger>
                  <SelectContent>
                    {PROTOCOL_OPTIONS.map(opt => (
                      <SelectItem key={opt.value} value={opt.value}>
                        <div className="flex items-center gap-2">
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
              <div className="rounded-lg border border-red-500/30 bg-red-500/10 p-3 text-xs text-red-700 dark:text-red-400 flex items-start gap-2">
                <AlertCircle className="size-4 shrink-0 mt-0.5 text-red-600" />
                <div>
                  <span className="font-semibold">核心未安装提醒：</span>
                  {nodeMode === "relay" ? (
                    <>中转服务器【{form.server_name}】当前未安装 Realm 核心。中转端口转发需要 Realm 核心支持，请先在顶栏核心状态卡片中一键安装 Realm 核心后再创建中转落地节点。</>
                  ) : (
                    <>服务器【{form.server_name}】当前未安装 {isSingboxProto ? "Sing-box" : "Xray-Core"} 核心。{isSingboxProto ? "Hysteria 2 (HY2) 协议需要 Sing-box 核心支持。" : "此协议需要 Xray-Core 核心支持。"}请先在该服务器上安装对应核心后再创建节点。</>
                  )}
                </div>
              </div>
            )}

            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <div className="flex items-center justify-between">
                  <Label className="text-xs">{nodeMode === "relay" ? "中转机监听端口 (对外开放)" : "端口"}</Label>
                  <button
                    type="button"
                    onClick={() => handleKeygen(form.protocol, form.method)}
                    className="text-[11px] text-primary hover:underline"
                  >
                    随机空闲
                  </button>
                </div>
                <Input
                  className="text-xs h-8 font-mono"
                  type="number"
                  value={form.port}
                  onChange={e => setForm(prev => ({ ...prev, port: e.target.value }))}
                  required
                />
              </div>

              {form.protocol === "ss2022" && (
                <div className="space-y-1.5">
                  <Label className="text-xs">加密算法</Label>
                  <Select
                    value={form.method}
                    onValueChange={(m) => {
                      setForm(prev => ({ ...prev, method: m }))
                      handleKeygen("ss2022", m)
                    }}
                  >
                    <SelectTrigger className="text-xs h-8">
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
                <div className="space-y-1.5">
                  <Label className="text-xs">用户名 (可选)</Label>
                  <Input
                    className="text-xs h-8"
                    placeholder="留空为无认证"
                    value={form.username}
                    onChange={e => setForm(prev => ({ ...prev, username: e.target.value }))}
                  />
                </div>
              )}

              {(form.protocol.includes("ws") || form.protocol.includes("xhttp")) && (
                <div className="space-y-1.5">
                  <Label className="text-xs">路径 (Path)</Label>
                  <Input
                    className="text-xs h-8 font-mono"
                    value={form.ws_path}
                    onChange={e => setForm(prev => ({ ...prev, ws_path: e.target.value }))}
                  />
                </div>
              )}
            </div>

            {(form.protocol === "vless_reality" || form.protocol === "vless_reality_xhttp") && (
              <div className="rounded-lg border p-3 bg-muted/20 space-y-2.5">
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

                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div>
                    <Label className="text-[11px] text-muted-foreground">SNI 伪装域名</Label>
                    <Input
                      className="text-xs h-7 font-mono"
                      value={form.sni}
                      onChange={e => setForm(prev => ({ ...prev, sni: e.target.value, dest: `${e.target.value}:443` }))}
                    />
                  </div>
                  <div>
                    <Label className="text-[11px] text-muted-foreground">Dest 目标</Label>
                    <Input
                      className="text-xs h-7 font-mono"
                      value={form.dest}
                      onChange={e => setForm(prev => ({ ...prev, dest: e.target.value }))}
                    />
                  </div>
                </div>

                <div className="space-y-1 text-xs">
                  <Label className="text-[11px] text-muted-foreground">Public Key (公钥)</Label>
                  <Input className="text-xs h-7 font-mono bg-background" value={form.public_key} readOnly />
                </div>
              </div>
            )}

            {form.protocol === "hysteria2" && (
              <div className="space-y-1.5">
                <Label className="text-xs">SNI 伪装域名</Label>
                <Input
                  className="text-xs h-8 font-mono"
                  value={form.sni}
                  placeholder="如: bing.com 或 www.apple.com"
                  onChange={e => setForm(prev => ({ ...prev, sni: e.target.value, dest: `https://${e.target.value}` }))}
                  required
                />
              </div>
            )}

            <div className="space-y-1.5">
              <div className="flex items-center justify-between">
                <Label className="text-xs">
                  {form.protocol === "ss2022" ? "预共享密钥 (Base64 Key)" : 
                   form.protocol === "trojan" || form.protocol === "socks5" || form.protocol === "hysteria2" ? "连接认证密码" : 
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
                className="text-xs h-8 font-mono"
                value={form.protocol === "ss2022" || form.protocol === "trojan" || form.protocol === "socks5" || form.protocol === "hysteria2" ? form.password : form.uuid}
                onChange={e => {
                  const val = e.target.value
                  if (form.protocol === "ss2022" || form.protocol === "trojan" || form.protocol === "socks5" || form.protocol === "hysteria2") {
                    setForm(prev => ({ ...prev, password: val }))
                  } else {
                    setForm(prev => ({ ...prev, uuid: val }))
                  }
                }}
                required
              />
            </div>

            <DialogFooter className="pt-2">
              <Button type="button" variant="outline" size="sm" onClick={() => setDialogOpen(false)} className="h-8 text-xs">
                取消
              </Button>
              <Button type="submit" size="sm" disabled={submitting} className="h-8 text-xs bg-black text-white hover:bg-neutral-800 dark:bg-white dark:text-black">
                {submitting ? "正在下发..." : "新建节点"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
