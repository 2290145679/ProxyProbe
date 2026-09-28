import { useEffect, useState } from "react"
import {
  Activity,
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  Bell,
  Calendar,
  ChevronRight,
  ChevronDown,
  ChevronUp,
  Clock,
  Copy,
  CreditCard,
  Crown,
  Download,
  ExternalLink,
  Eye,
  EyeOff,
  Globe,
  HardDrive,
  Laptop,
  LogOut,
  Moon,
  Palette,
  QrCode,
  RefreshCw,
  Send,
  ShoppingBag,
  Smartphone,
  Sun,
  Wallet,
  Zap,
} from "lucide-react"
import QRCode from "qrcode"
import { toast } from "sonner"
import { copyToClipboard } from "@/lib/clipboard"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { ThemeSettingsDialog } from "@/components/ThemeSettingsDialog"

export type UserProfile = {
  id: number
  username: string
  is_admin: boolean
  vip_level?: string
  balance?: number
  sub_token: string
  sub_url: string
  clash_url?: string
  singbox_url?: string
  traffic_limit_bytes: number
  device_limit?: number
  online_devices?: number
  upload_bytes: number
  download_bytes: number
  total_used_bytes: number
  remaining_bytes: number
  expires_at: number
  enabled: number
  status: "active" | "over_quota" | "expired" | "disabled" | "over_device_limit"
  created_at: number
  theme_style?: "default" | "sakura"
}

type NodeItem = {
  id: number
  name: string
  protocol: string
  server_name: string
  server_host: string
  port: number
  enabled: number
  flag?: string
  display_name?: string
  bandwidth_limit_mbps?: number
}

function formatBytes(bytes: number) {
  if (bytes <= 0) return "0 B"
  const k = 1024
  const sizes = ["B", "KB", "MB", "GB", "TB"]
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`
}

function formatDate(ts: number) {
  if (!ts || ts === 0) return "永久有效"
  return new Date(ts * 1000).toLocaleString()
}

function maskHost(host: string) {
  if (!host) return ""
  const parts = host.split(".")
  if (parts.length === 4) {
    return `${parts[0]}.***.***.${parts[3]}`
  }
  if (host.length > 8) {
    return `${host.slice(0, 3)}****${host.slice(-4)}`
  }
  return "***"
}

export function UserDashboard({
  user,
  siteName,
  refreshUser,
  onSignOut,
  toggleTheme,
  dark,
  themeStyle = "default",
  onThemeStyleChange,
}: {
  user: UserProfile
  siteName: string
  refreshUser: () => void
  onSignOut: () => void
  toggleTheme: () => void
  dark: boolean
  themeStyle?: "default" | "sakura"
  onThemeStyleChange?: (style: "default" | "sakura") => void
}) {
  const [themeDialogOpen, setThemeDialogOpen] = useState(false)
  const [nodes, setNodes] = useState<NodeItem[]>([])
  const [showIps, setShowIps] = useState<Record<number, boolean>>({})
  const [qrOpen, setQrOpen] = useState(false)
  const [qrUrl, setQrUrl] = useState("")
  const [resettingToken, setResettingToken] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [supportTg, setSupportTg] = useState<{ enabled: boolean; telegram_url: string }>({ enabled: false, telegram_url: "" })

  // 系统公告、全局通知与客户端软件专区
  const [announcements, setAnnouncements] = useState<any[]>([])
  const [selectedAnnouncement, setSelectedAnnouncement] = useState<any | null>(null)
  const [announcementDialogOpen, setAnnouncementDialogOpen] = useState(false)

  const [globalNotice, setGlobalNotice] = useState<{ title: string; content: string } | null>(null)
  const [globalNoticeOpen, setGlobalNoticeOpen] = useState(false)

  const [clientApps, setClientApps] = useState<any[]>([])
  const [isAppsCollapsed, setIsAppsCollapsed] = useState(true)

  // 导航分类与商城订单状态
  const [activeTab, setActiveTab] = useState<"subs" | "store">("subs")
  const [tiers, setTiers] = useState<any[]>([])
  const [paymentConfig, setPaymentConfig] = useState<any>(null)
  const [userOrders, setUserOrders] = useState<any[]>([])
  const [checkoutTier, setCheckoutTier] = useState<any | null>(null)
  const [checkoutPeriod, setCheckoutPeriod] = useState<"monthly" | "quarterly" | "yearly">("monthly")
  const [checkoutMethod, setCheckoutMethod] = useState<string>("balance")
  const [checkoutNote, setCheckoutNote] = useState<string>("")
  const [submittingOrder, setSubmittingOrder] = useState<boolean>(false)

  const loadStoreData = async () => {
    try {
      const [resTiers, resPay, resOrders] = await Promise.all([
        fetch("/api/proxy/tiers").then(r => r.json()).catch(() => null),
        fetch("/api/proxy/user/payment-config").then(r => r.json()).catch(() => null),
        fetch("/api/proxy/user/orders").then(r => r.json()).catch(() => null),
      ])
      if (resTiers?.ok && Array.isArray(resTiers.tiers)) setTiers(resTiers.tiers)
      if (resPay?.ok) setPaymentConfig(resPay)
      if (resOrders?.ok && Array.isArray(resOrders.orders)) setUserOrders(resOrders.orders)
    } catch {}
  }

  // 购买套餐提交
  async function handleBuyOrder() {
    if (!checkoutTier) return
    setSubmittingOrder(true)
    try {
      const res = await fetch("/api/proxy/orders", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          tier_key: checkoutTier.tier_key,
          period: checkoutPeriod,
          pay_method: checkoutMethod,
          note: checkoutNote,
        }),
      })
      const data = await res.json()
      if (!res.ok || !data.ok) {
        throw new Error(data.message || "订单提交失败")
      }
      toast.success(data.message || "订单处理完成！")
      setCheckoutTier(null)
      setCheckoutNote("")
      refreshUser()
      loadStoreData()
    } catch (e: any) {
      toast.error(e.message || "操作异常")
    } finally {
      setSubmittingOrder(false)
    }
  }

  // 获取 Telegram 客服支持设置 (若后台关闭则完全不展示)
  useEffect(() => {
    fetch("/api/proxy/settings/support")
      .then(res => res.json())
      .then(data => {
        if (data.ok && data.enabled && data.telegram_url) {
          setSupportTg({ enabled: true, telegram_url: data.telegram_url })
        }
      })
      .catch(() => {})
  }, [])

  // 加载公告、通知与软件列表、商城数据
  useEffect(() => {
    fetch("/api/proxy/user/announcements")
      .then(r => r.json())
      .then(d => { if (d.ok && Array.isArray(d.announcements)) setAnnouncements(d.announcements) })
      .catch(() => {})

    fetch("/api/proxy/user/apps")
      .then(r => r.json())
      .then(d => { if (d.ok && Array.isArray(d.apps)) setClientApps(d.apps) })
      .catch(() => {})

    fetch("/api/proxy/user/notification")
      .then(r => r.json())
      .then(d => {
        if (d.ok && d.enabled && d.title) {
          setGlobalNotice({ title: d.title, content: d.content || "" })
          const dismissed = sessionStorage.getItem("dismissed_notice_" + d.title)
          if (!dismissed) {
            setGlobalNoticeOpen(true)
          }
        }
      })
      .catch(() => {})

    loadStoreData()
  }, [])

  // 实时轮询用户流量与订阅状态 (每 3 秒自动刷新)
  useEffect(() => {
    const timer = setInterval(() => {
      refreshUser()
    }, 3000)
    return () => clearInterval(timer)
  }, [refreshUser])

  // 手动点击刷新
  async function handleManualRefresh() {
    setRefreshing(true)
    try {
      await refreshUser()
    } finally {
      setTimeout(() => setRefreshing(false), 500)
    }
  }

  // 加载节点列表
  useEffect(() => {
    fetch("/api/proxy/user/nodes")
      .then(res => res.json())
      .then(data => {
        if (data.ok && Array.isArray(data.nodes)) {
          setNodes(data.nodes)
        }
      })
      .catch(() => {})
  }, [])

  // 确保使用当前页面的实际访问域名，防止旧数据或写死域名导致 403
  const getDynamicSubUrl = (rawUrl?: string) => {
    if (!rawUrl) return ""
    if (typeof window === "undefined") return rawUrl
    try {
      if (rawUrl.startsWith("http")) {
        const u = new URL(rawUrl)
        return `${window.location.origin}${u.pathname}${u.search}`
      }
      return `${window.location.origin}${rawUrl.startsWith("/") ? "" : "/"}${rawUrl}`
    } catch {
      return rawUrl
    }
  }

  const effectiveSubUrl = getDynamicSubUrl(user.sub_url)
  const effectiveClashUrl = user.clash_url
    ? getDynamicSubUrl(user.clash_url)
    : (effectiveSubUrl ? `${effectiveSubUrl}${effectiveSubUrl.includes("?") ? "&" : "?"}clash=1` : "")
  const effectiveSingboxUrl = user.singbox_url
    ? getDynamicSubUrl(user.singbox_url)
    : (effectiveSubUrl ? `${effectiveSubUrl}${effectiveSubUrl.includes("?") ? "&" : "?"}singbox=1` : "")

  // 生成二维码
  useEffect(() => {
    if (effectiveSubUrl) {
      QRCode.toDataURL(effectiveSubUrl, { width: 300, margin: 2 })
        .then(url => setQrUrl(url))
        .catch(() => {})
    }
  }, [effectiveSubUrl])

  // 复制订阅链接
  async function copySubUrl() {
    const ok = await copyToClipboard(effectiveSubUrl)
    if (ok) {
      toast.success("聚合订阅链接已复制到剪贴板！")
    } else {
      toast.error("复制失败，请手动选中文本进行复制")
    }
  }

  // 重置订阅链接
  async function handleResetToken() {
    if (!confirm("确定要重置当前订阅链接吗？重置后旧链接将立即失效，所有客户端需重新导入。")) return
    setResettingToken(true)
    try {
      const res = await fetch("/api/proxy/user/reset-token", { method: "POST" })
      const data = await res.json()
      if (data.ok) {
        toast.success("订阅链接重置成功！")
        refreshUser()
      } else {
        toast.error(data.message || "重置失败")
      }
    } catch {
      toast.error("网络错误")
    } finally {
      setResettingToken(false)
    }
  }

  // 切换节点 IP 显示/隐藏
  function toggleShowIp(nodeId: number) {
    setShowIps(prev => ({ ...prev, [nodeId]: !prev[nodeId] }))
  }

  // 计算流量百分比
  const limit = user.traffic_limit_bytes
  const used = user.total_used_bytes
  const percent = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0

  let progressColor = "bg-emerald-500"
  if (percent >= 90) progressColor = "bg-red-500"
  else if (percent >= 70) progressColor = "bg-amber-500"

  const subName = siteName || "ProxySub"

  return (
    <div className="min-h-svh bg-background/50 overflow-x-hidden w-full">
      {/* 顶部导航条 */}
      <header className="sticky top-0 z-10 border-b bg-background/80 backdrop-blur w-full">
        <div className="mx-auto flex max-w-6xl items-center gap-2 sm:gap-3 px-3 sm:px-4 py-2.5 sm:py-3">
          <div className="flex items-center gap-1.5 sm:gap-2 shrink-0">
            {themeStyle === "sakura" && <span className="text-base select-none">🌸</span>}
            <span className="font-bold text-sm sm:text-base tracking-tight truncate max-w-[120px] sm:max-w-none">
              {siteName || "HHUB"}
            </span>
            <Badge variant="outline" className="hidden sm:inline-flex text-[11px] font-medium border-primary/20 bg-primary/10 text-primary whitespace-nowrap shrink-0">
              用户中心
            </Badge>
          </div>

          <div className="flex-1" />

          <div className="flex items-center gap-1 sm:gap-2 shrink-0">
            <Button variant="outline" size="sm" asChild className="gap-1.5 text-xs h-8 px-2 sm:px-3 shrink-0">
              <a href="/" target="_blank" rel="noopener noreferrer" title="查看服务器探针状态">
                <Activity className="size-3.5 text-emerald-500 shrink-0" />
                <span className="hidden sm:inline">服务器探针</span>
                <ExternalLink className="size-3 text-muted-foreground ml-0.5 hidden sm:inline shrink-0" />
              </a>
            </Button>

            {supportTg.enabled && supportTg.telegram_url && (
              <Button
                variant="outline"
                size="sm"
                asChild
                className="gap-1.5 text-xs h-8 px-2 sm:px-3 shrink-0 border-[#229ED9]/40 text-[#229ED9] hover:bg-[#229ED9]/10"
              >
                <a href={supportTg.telegram_url} target="_blank" rel="noopener noreferrer" title="联系 Telegram 客服专员">
                  <Send className="size-3.5 fill-[#229ED9] shrink-0" />
                  <span>联系客服</span>
                </a>
              </Button>
            )}

            <span className="text-xs text-muted-foreground mr-1 hidden md:inline-flex items-center gap-1.5">
              <span>用户:</span>
              <strong className="text-foreground">{user.username}</strong>
            </span>

            <Button
              variant="ghost"
              size="icon"
              onClick={() => setThemeDialogOpen(true)}
              className="size-8 shrink-0"
              title="主题外观设置"
            >
              {themeStyle === "sakura" ? (
                <span className="text-sm select-none">🌸</span>
              ) : (
                <Palette className="size-4 text-muted-foreground" />
              )}
            </Button>

            <Button
              variant="ghost"
              size="icon"
              onClick={toggleTheme}
              className="size-8 shrink-0"
              title={dark ? "切换为浅色" : "切换为深色"}
            >
              {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
            </Button>

            <Button
              variant="ghost"
              size="sm"
              onClick={onSignOut}
              className="gap-1.5 text-xs text-muted-foreground hover:text-foreground h-8 px-2 sm:px-3 shrink-0"
              title="退出登录"
            >
              <LogOut className="size-3.5 shrink-0" />
              <span className="hidden sm:inline">退出</span>
            </Button>
          </div>
        </div>
      </header>

      {/* 主题外观切换弹窗 */}
      {onThemeStyleChange && (
        <ThemeSettingsDialog
          open={themeDialogOpen}
          onOpenChange={setThemeDialogOpen}
          themeStyle={themeStyle}
          onThemeStyleChange={onThemeStyleChange}
          dark={dark}
          onToggleDark={toggleTheme}
        />
      )}

      {/* 主面板内容 */}
      <main className="mx-auto max-w-6xl space-y-6 px-4 py-6">
        {/* 账户异常提示横幅 */}
        {user.status !== "active" && (
          <div className="rounded-xl border border-red-500/30 bg-red-500/10 p-4 text-xs text-red-700 dark:text-red-400 flex items-start gap-3 shadow-sm">
            <AlertTriangle className="size-5 shrink-0 mt-0.5 text-red-600 dark:text-red-400" />
            <div className="space-y-1">
              <p className="font-bold text-sm">
                {user.status === "over_quota" && "流量配额已用尽"}
                {user.status === "expired" && "订阅服务已到期"}
                {user.status === "disabled" && "账户已被管理员停用"}
                {user.status === "over_device_limit" && `在线客户端设备数已超限 (限制 ${user.device_limit || 0} 台)`}
              </p>
              <p className="text-muted-foreground dark:text-red-300">
                {user.status === "over_device_limit"
                  ? `当前已检测到 ${user.online_devices || 0} 台设备同时活跃，超过了允许的 ${user.device_limit || 0} 台限制。系统已自动熔断切断连接，请断开多余设备的连接，稍后将自动恢复。`
                  : "当前订阅服务处于熔断状态，客户端无法继续连接代理节点。请联系管理员续期或增加流量配额。"}
              </p>
            </div>
          </div>
        )}

        {/* 卡片 1：流量与配额状态概览 */}
        <Card className="p-4 sm:p-6 space-y-4 sm:space-y-5 border shadow-sm">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b pb-4">
            <div className="space-y-1">
              <div className="flex items-center gap-2">
                <h2 className="text-lg font-bold">流量与订阅配额</h2>
                {user.status === "active" ? (
                  <span className="inline-flex items-center gap-1 rounded-full bg-emerald-500/10 px-2 py-0.5 text-[11px] font-medium text-emerald-600 dark:text-emerald-400">
                    <span className="size-1.5 rounded-full bg-emerald-500 animate-pulse" /> 正常使用中
                  </span>
                ) : (
                  <span className="inline-flex items-center gap-1 rounded-full bg-red-500/10 px-2 py-0.5 text-[11px] font-medium text-red-600 dark:text-red-400">
                    <span className="size-1.5 rounded-full bg-red-500" /> 已停止
                  </span>
                )}
              </div>
              <p className="text-xs text-muted-foreground">实时统计所有代理节点产生的双向网络吞吐流量</p>
            </div>

            <Button variant="outline" size="sm" onClick={handleManualRefresh} disabled={refreshing} className="text-xs gap-1.5 shrink-0 self-start sm:self-auto">
              <RefreshCw className={`size-3.5 ${refreshing ? "animate-spin text-primary" : ""}`} /> 刷新统计
            </Button>
          </div>

          {/* 进度条展示 */}
          <div className="space-y-2">
            <div className="flex justify-between text-xs font-medium">
              <span>已用：{formatBytes(used)}</span>
              <span>
                {limit > 0 ? `限额：${formatBytes(limit)} (${percent}%)` : "无限制"}
              </span>
            </div>
            <div className="h-3 w-full rounded-full bg-muted overflow-hidden">
              <div
                className={`h-full transition-all duration-500 ${progressColor}`}
                style={{ width: `${limit > 0 ? percent : 0}%` }}
              />
            </div>
            <div className="flex justify-between text-[11px] text-muted-foreground pt-0.5">
              <span>起始：0 B</span>
              <span>
                剩余：{limit > 0 ? formatBytes(Math.max(0, limit - used)) : "不限量"}
              </span>
            </div>
          </div>

          {/* 详细指标网格 */}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-7 gap-3 pt-2">
            <div className="rounded-lg bg-emerald-500/10 p-3 space-y-1 border border-emerald-500/20">
              <div className="flex items-center justify-between text-xs text-emerald-700 dark:text-emerald-400">
                <span className="flex items-center gap-1.5"><Wallet className="size-3.5" /> 账户余额</span>
                <button
                  type="button"
                  onClick={() => setActiveTab("store")}
                  className="text-[10px] text-primary hover:underline cursor-pointer"
                >
                  选购
                </button>
              </div>
              <p className="text-base font-semibold font-mono tracking-tight text-emerald-600 dark:text-emerald-400">
                ￥{(user.balance || 0).toFixed(2)}
              </p>
            </div>

            <div className="rounded-lg bg-muted/50 p-3 space-y-1 border border-border/50">
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Crown className="size-3.5 text-amber-500" /> VIP 等级套餐
              </div>
              <p className="text-base font-semibold tracking-tight uppercase font-mono text-amber-600 dark:text-amber-400">
                {user.vip_level || "VIP1"}
              </p>
            </div>

            <div className="rounded-lg bg-muted/50 p-3 space-y-1 border border-border/50">
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <ArrowUp className="size-3.5 text-blue-500" /> 上传流量
              </div>
              <p className="text-base font-semibold tracking-tight">{formatBytes(user.upload_bytes)}</p>
            </div>

            <div className="rounded-lg bg-muted/50 p-3 space-y-1 border border-border/50">
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <ArrowDown className="size-3.5 text-emerald-500" /> 下载流量
              </div>
              <p className="text-base font-semibold tracking-tight">{formatBytes(user.download_bytes)}</p>
            </div>

            <div className="rounded-lg bg-muted/50 p-3 space-y-1 border border-border/50">
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <HardDrive className="size-3.5 text-purple-500" /> 剩余额度
              </div>
              <p className="text-base font-semibold tracking-tight">
                {limit > 0 ? formatBytes(Math.max(0, limit - used)) : "无限量"}
              </p>
            </div>

            <div className="rounded-lg bg-muted/50 p-3 space-y-1 border border-border/50">
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Laptop className="size-3.5 text-indigo-500" /> 在线设备
              </div>
              <p className="text-base font-semibold tracking-tight">
                {user.online_devices ?? 0} / {(user.device_limit && user.device_limit > 0) ? `${user.device_limit} 台` : "不限"}
              </p>
            </div>

            <div className="rounded-lg bg-muted/50 p-3 space-y-1 border border-border/50">
              <div className="flex items-center gap-1.5 text-xs text-muted-foreground">
                <Calendar className="size-3.5 text-amber-500" /> 到期时间
              </div>
              <p className="text-base font-semibold tracking-tight truncate" title={formatDate(user.expires_at)}>
                {formatDate(user.expires_at)}
              </p>
            </div>
          </div>
        </Card>

        {/* 系统公告栏 (点击展开详细内容) */}
        {announcements.length > 0 && (
          <Card className="p-4 sm:p-5 border shadow-sm space-y-3">
            <div className="flex items-center justify-between border-b pb-3">
              <div className="flex items-center gap-2">
                <Bell className="size-4 text-primary" />
                <h3 className="text-sm font-bold">系统公告</h3>
                <Badge variant="secondary" className="text-[10px] py-0 px-1.5">{announcements.length} 条</Badge>
              </div>
              <span className="text-[11px] text-muted-foreground">点击标题查看详细内容</span>
            </div>
            <div className="divide-y divide-border/60">
              {announcements.map((a) => (
                <div
                  key={a.id}
                  onClick={() => {
                    setSelectedAnnouncement(a)
                    setAnnouncementDialogOpen(true)
                  }}
                  className="py-2.5 flex items-center justify-between gap-3 hover:bg-muted/40 px-2 rounded-md transition cursor-pointer select-none group"
                >
                  <div className="flex items-center gap-2 min-w-0">
                    {a.is_pinned === 1 && (
                      <Badge className="text-[10px] py-0 px-1.5 bg-rose-500/10 text-rose-600 border border-rose-500/20 shrink-0">
                        置顶
                      </Badge>
                    )}
                    <span className="text-xs font-medium text-foreground group-hover:text-primary transition-colors truncate">
                      {a.title}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 shrink-0 text-muted-foreground">
                    <span className="text-[11px] font-mono">
                      {new Date(a.created_at * 1000).toLocaleDateString()}
                    </span>
                    <ChevronRight className="size-3.5 group-hover:translate-x-0.5 transition-transform" />
                  </div>
                </div>
              ))}
            </div>
          </Card>
        )}

        {/* 用户端核心分类导航 */}
        <div className="flex flex-wrap items-center gap-2 p-1.5 rounded-xl bg-muted/40 border shadow-xs">
          <button
            type="button"
            onClick={() => setActiveTab("subs")}
            className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
              activeTab === "subs"
                ? "bg-background text-foreground shadow-xs"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <Zap className="size-3.5 text-amber-500" />
            <span>我的订阅与节点</span>
          </button>

          <button
            type="button"
            onClick={() => setActiveTab("store")}
            className={`flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer ${
              activeTab === "store"
                ? "bg-background text-foreground shadow-xs"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <Crown className="size-3.5 text-primary" />
            <span>购买 / 升级订阅套餐</span>
            <Badge variant="outline" className="text-[10px] py-0 px-1 ml-0.5 bg-primary/10 text-primary border-primary/20">
              商城
            </Badge>
          </button>
        </div>

        {/* 分类 1：我的订阅与节点 */}
        {activeTab === "subs" && (
          <div className="space-y-6">

        {/* 卡片 2：专属聚合订阅与一键导入 */}
        <Card className="p-4 sm:p-6 space-y-4 sm:space-y-5 border shadow-sm">
          <div className="border-b pb-3 sm:pb-4 space-y-1">
            <h2 className="text-base sm:text-lg font-bold flex items-center gap-2">
              <Zap className="size-4 text-amber-500" /> 一键聚合订阅
            </h2>
            <p className="text-xs text-muted-foreground">
              ⚡ 采用智能 UA 自适应技术，单一链接自动适配 Clash、Sing-box、Shadowrocket、v2rayN 等全主流客户端
            </p>
          </div>

          <div className="space-y-4">
            {/* 订阅地址输入框与主要操作按钮 */}
            <div className="flex flex-col sm:flex-row gap-2">
              <div className="relative flex-1 min-w-0">
                <Input
                  readOnly
                  value={effectiveSubUrl}
                  className="font-mono text-xs h-10 bg-muted/40 pr-28 select-all"
                />
                <Button
                  onClick={copySubUrl}
                  size="sm"
                  className="absolute right-1 top-1 h-8 px-3 text-xs gap-1.5 shadow-sm font-medium"
                >
                  <Copy className="size-3.5" /> 复制订阅
                </Button>
              </div>

              <div className="flex items-center gap-2 shrink-0">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setQrOpen(true)}
                  className="flex-1 sm:flex-initial h-10 px-3 gap-1.5 text-xs"
                  title="手机扫码导入"
                >
                  <QrCode className="size-3.5 text-primary" />
                  <span>扫码导入</span>
                </Button>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={handleResetToken}
                  disabled={resettingToken}
                  className="flex-1 sm:flex-initial h-10 px-3 gap-1.5 text-xs text-muted-foreground hover:text-foreground"
                  title="若订阅泄漏，可一键重置"
                >
                  <RefreshCw className={`size-3.5 ${resettingToken ? "animate-spin" : ""}`} />
                  <span>重置链接</span>
                </Button>
              </div>
            </div>

            {/* 客户端快捷导入按钮组 */}
            <div className="pt-2 border-t border-border/50">
              <div className="text-xs font-medium text-muted-foreground mb-3 flex items-center justify-between">
                <span>快捷一键导入到客户端：</span>
                <span className="text-[11px] text-muted-foreground/80 hidden sm:inline">点击直接唤起客户端</span>
              </div>
              <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5">
                <Button
                  variant="outline"
                  size="sm"
                  asChild
                  className="h-11 px-3 text-xs justify-between hover:border-primary/50 hover:bg-accent/40 transition-colors"
                >
                  <a href={`clash://install-config?url=${encodeURIComponent(effectiveClashUrl)}&name=${encodeURIComponent(subName)}`}>
                    <div className="flex items-center gap-2.5 min-w-0">
                      <Send className="size-4 text-blue-500 shrink-0" />
                      <div className="flex flex-col text-left leading-tight min-w-0">
                        <span className="font-medium truncate">Clash / Verge</span>
                        <span className="text-[10px] text-muted-foreground truncate">一键导入配置</span>
                      </div>
                    </div>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-blue-500/10 text-blue-600 dark:text-blue-400 font-medium shrink-0">导入</span>
                  </a>
                </Button>

                <Button
                  variant="outline"
                  size="sm"
                  asChild
                  className="h-11 px-3 text-xs justify-between hover:border-primary/50 hover:bg-accent/40 transition-colors"
                >
                  <a href={`shadowrocket://add/sub://${btoa(effectiveSubUrl)}?title=${encodeURIComponent(subName)}`}>
                    <div className="flex items-center gap-2.5 min-w-0">
                      <Smartphone className="size-4 text-indigo-500 shrink-0" />
                      <div className="flex flex-col text-left leading-tight min-w-0">
                        <span className="font-medium truncate">小火箭 Shadowrocket</span>
                        <span className="text-[10px] text-muted-foreground truncate">iOS 专属导入</span>
                      </div>
                    </div>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 font-medium shrink-0">导入</span>
                  </a>
                </Button>

                <Button
                  variant="outline"
                  size="sm"
                  asChild
                  className="h-11 px-3 text-xs justify-between hover:border-primary/50 hover:bg-accent/40 transition-colors"
                >
                  <a href={`sing-box://import-remote-profile?url=${encodeURIComponent(effectiveSingboxUrl)}#${encodeURIComponent(subName)}`}>
                    <div className="flex items-center gap-2.5 min-w-0">
                      <Globe className="size-4 text-amber-500 shrink-0" />
                      <div className="flex flex-col text-left leading-tight min-w-0">
                        <span className="font-medium truncate">Sing-box</span>
                        <span className="text-[10px] text-muted-foreground truncate">跨平台通用核心</span>
                      </div>
                    </div>
                    <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-600 dark:text-amber-400 font-medium shrink-0">导入</span>
                  </a>
                </Button>

                <Button
                  variant="outline"
                  size="sm"
                  onClick={copySubUrl}
                  className="h-11 px-3 text-xs justify-between hover:border-primary/50 hover:bg-accent/40 transition-colors"
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <Activity className="size-4 text-emerald-500 shrink-0" />
                    <div className="flex flex-col text-left leading-tight min-w-0">
                      <span className="font-medium truncate">v2rayN / Nekobox</span>
                      <span className="text-[10px] text-muted-foreground truncate">点击复制订阅链接</span>
                    </div>
                  </div>
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 font-medium shrink-0">复制</span>
                </Button>
              </div>
            </div>
          </div>
        </Card>

        {/* 卡片：常用客户端软件下载专区 (可折叠展开，避免挤占订阅空间) */}
        {clientApps.length > 0 && (
          <Card className="p-4 sm:p-5 border shadow-sm transition-all bg-card/60 backdrop-blur-xs">
            <div
              className="flex items-center justify-between cursor-pointer select-none"
              onClick={() => setIsAppsCollapsed(!isAppsCollapsed)}
            >
              <div className="flex items-center gap-2.5">
                <div className="size-8 rounded-lg bg-emerald-500/10 flex items-center justify-center text-emerald-600 dark:text-emerald-400">
                  <Download className="size-4" />
                </div>
                <div>
                  <h3 className="text-sm font-bold flex items-center gap-2">
                    常用客户端软件下载专区
                    <Badge variant="outline" className="text-[10px] py-0 px-1.5 font-mono bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20">
                      {clientApps.length} 款官方与镜像
                    </Badge>
                  </h3>
                  <p className="text-xs text-muted-foreground mt-0.5">
                    {isAppsCollapsed
                      ? "点击展开快速下载 Windows / Android / iOS / macOS 代理软件与安装包"
                      : "官方安装包与镜像加速下载，支持本地高速下载与官方镜像"}
                  </p>
                </div>
              </div>
              <Button variant="ghost" size="sm" className="h-8 w-8 p-0 text-muted-foreground hover:text-foreground">
                {isAppsCollapsed ? <ChevronDown className="size-4" /> : <ChevronUp className="size-4" />}
              </Button>
            </div>

            {!isAppsCollapsed && (
              <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 pt-4 border-t mt-4">
                {clientApps.map((app) => {
                  const extUrl = (app.external_url || app.mirror_url || "").trim()
                  const hasLocal = app.has_local_file === 1
                  const localDownloadUrl = `/api/proxy/apps/download/${app.id}`

                  return (
                    <div key={app.id} className="p-3.5 rounded-lg border bg-muted/20 space-y-2.5 flex flex-col justify-between hover:border-primary/30 transition-all">
                      <div className="space-y-1">
                        <div className="flex items-center justify-between">
                          <span className="font-bold text-xs text-foreground truncate">{app.name}</span>
                          <Badge variant="outline" className="text-[10px] font-mono">
                            {app.platform}
                          </Badge>
                        </div>
                        <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                          <span>版本: {app.version || "最新版"}</span>
                          {app.file_size ? <span>· {formatBytes(app.file_size)}</span> : null}
                        </div>
                        {app.description && (
                          <p className="text-[11px] text-muted-foreground line-clamp-2 leading-relaxed">{app.description}</p>
                        )}
                      </div>

                      <div className="flex items-center gap-2 pt-2 border-t">
                        {hasLocal && (
                          <Button asChild size="sm" className="h-7 text-xs flex-1 gap-1 bg-emerald-600 hover:bg-emerald-700 text-white shadow-xs">
                            <a href={localDownloadUrl} target="_blank" rel="noopener noreferrer" download>
                              <Download className="size-3" /> 本地下载
                            </a>
                          </Button>
                        )}
                        {extUrl ? (
                          <Button asChild variant={hasLocal ? "outline" : "default"} size="sm" className="h-7 text-xs flex-1 gap-1 shadow-xs">
                            <a href={extUrl} target="_blank" rel="noopener noreferrer">
                              <ExternalLink className="size-3" /> {hasLocal ? "官方镜像" : "下载 / 官网"}
                            </a>
                          </Button>
                        ) : null}
                        {!hasLocal && !extUrl && (
                          <Button disabled variant="outline" size="sm" className="h-7 text-xs flex-1 text-muted-foreground">
                            暂无下载链接
                          </Button>
                        )}
                      </div>
                    </div>
                  )
                })}
              </div>
            )}
          </Card>
        )}

        {/* 卡片 3：可用节点列表 */}
        <Card className="p-4 sm:p-6 space-y-4 sm:space-y-5 border shadow-sm">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b pb-4">
            <div className="space-y-1">
              <h2 className="text-lg font-bold flex items-center gap-2">
                <Globe className="size-4 text-emerald-500" /> 可用代理节点列表 ({nodes.length})
              </h2>
              <p className="text-xs text-muted-foreground">
                当前包含在您订阅中的节点，节点真实 IP 默认已脱敏隐藏，可点击小眼睛查看
              </p>
            </div>
            <Button variant="outline" size="sm" asChild className="gap-1.5 text-xs h-8 shrink-0 self-start sm:self-auto">
              <a href="/" target="_blank" rel="noopener noreferrer">
                <Activity className="size-3.5 text-emerald-500" />
                <span>服务器探针</span>
                <ExternalLink className="size-3 text-muted-foreground ml-0.5" />
              </a>
            </Button>
          </div>

          {nodes.length === 0 ? (
            <div className="py-8 text-center text-xs text-muted-foreground">
              暂无已启用的代理节点，请联系管理员添加节点。
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {nodes.map(n => {
                const isIpShown = !!showIps[n.id]
                const displayHost = isIpShown ? n.server_host : maskHost(n.server_host)

                return (
                  <div
                    key={n.id}
                    className="flex items-center justify-between rounded-lg border bg-card p-3 text-xs gap-3 hover:border-primary/30 transition-all"
                  >
                    <div className="space-y-1 min-w-0 flex-1">
                      <div className="flex items-center gap-1.5 flex-wrap">
                        <span className="font-semibold truncate">{n.flag ? `${n.flag} ` : ""}{n.name}</span>
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
                        <Badge variant="secondary" className="text-[10px] py-0 px-1 font-mono uppercase shrink-0">
                          {n.protocol.replace("_", " ")}
                        </Badge>
                        {Boolean(n.bandwidth_limit_mbps && n.bandwidth_limit_mbps > 0) && (
                          <Badge variant="outline" className="text-[10px] py-0 px-1 font-mono shrink-0 bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30">
                            ⚡ {n.bandwidth_limit_mbps} Mbps
                          </Badge>
                        )}
                      </div>
                      <div className="text-[11px] text-muted-foreground truncate font-mono">
                        {n.server_name} · {displayHost}:{n.port}
                      </div>
                    </div>

                    <div className="flex items-center gap-1.5 shrink-0">
                      <Button
                        variant="ghost"
                        size="icon"
                        onClick={() => toggleShowIp(n.id)}
                        className="size-8 text-muted-foreground hover:text-foreground"
                        title={isIpShown ? "隐藏真实 IP" : "查看真实 IP"}
                      >
                        {isIpShown ? <Eye className="size-4 text-primary" /> : <EyeOff className="size-4" />}
                      </Button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </Card>
          </div>
        )}

        {/* 分类 2：购买 / 升级订阅套餐 (商城) */}
        {activeTab === "store" && (
          <div className="space-y-6">
            <Card className="p-4 sm:p-6 border shadow-sm space-y-4">
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b pb-4">
                <div className="space-y-1">
                  <h2 className="text-lg font-bold flex items-center gap-2">
                    <Crown className="size-5 text-amber-500" /> VIP 等级套餐选购与续费
                  </h2>
                  <p className="text-xs text-muted-foreground">
                    开通更高级别的套餐，解锁更多专属高速节点、更高带宽上限和更多设备连接数。
                  </p>
                </div>
                <div className="flex items-center gap-3 bg-muted/40 px-3.5 py-2 rounded-lg border text-xs">
                  <div>
                    <span className="text-muted-foreground">当前余额：</span>
                    <span className="font-bold text-emerald-600 dark:text-emerald-400 font-mono">
                      ￥{(user.balance || 0).toFixed(2)}
                    </span>
                  </div>
                  <div className="h-4 w-px bg-border" />
                  <div>
                    <span className="text-muted-foreground">当前级别：</span>
                    <span className="font-bold font-mono uppercase text-amber-600 dark:text-amber-400">
                      {user.vip_level || "VIP1"}
                    </span>
                  </div>
                </div>
              </div>

              {tiers.length === 0 ? (
                <div className="py-12 text-center text-xs text-muted-foreground">
                  管理员暂未配置套餐价格，请联系客服获取订阅支持。
                </div>
              ) : (
                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 pt-2">
                  {tiers.map((t) => {
                    const isCurrent = (user.vip_level || "VIP1").toLowerCase() === (t.tier_key || "").toLowerCase()
                    const mPrice = t.price_monthly ?? 0
                    const qPrice = t.price_quarterly ?? (mPrice ? mPrice * 3 * 0.9 : 0)
                    const yPrice = t.price_yearly ?? (mPrice ? mPrice * 12 * 0.8 : 0)

                    return (
                      <div
                        key={t.tier_key}
                        className={`rounded-xl border p-5 space-y-4 flex flex-col justify-between transition-all ${
                          isCurrent
                            ? "border-primary bg-primary/5 shadow-sm ring-1 ring-primary/20"
                            : "bg-card hover:border-primary/40 hover:shadow-xs"
                        }`}
                      >
                        <div className="space-y-3">
                          <div className="flex items-center justify-between">
                            <div className="flex items-center gap-2">
                              <span className="font-bold text-base text-foreground">
                                {t.tier_name || t.tier_key.toUpperCase()}
                              </span>
                              <Badge variant="outline" className="font-mono text-[10px] uppercase">
                                {t.tier_key}
                              </Badge>
                            </div>
                            {isCurrent && (
                              <Badge className="bg-primary/20 text-primary border-primary/30 text-[10px]">
                                当前使用中
                              </Badge>
                            )}
                          </div>

                          <div className="pt-1 border-b pb-3 space-y-1">
                            <div className="flex items-baseline gap-1">
                              <span className="text-2xl font-black font-mono tracking-tight text-foreground">
                                ￥{mPrice}
                              </span>
                              <span className="text-xs text-muted-foreground">/ 月</span>
                            </div>
                            <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                              <span>季付: ￥{qPrice.toFixed(0)}</span>
                              <span>·</span>
                              <span>年付: ￥{yPrice.toFixed(0)}</span>
                            </div>
                          </div>

                          <ul className="space-y-2 text-xs text-muted-foreground">
                            <li className="flex items-center gap-2">
                              <Zap className="size-3.5 text-amber-500 shrink-0" />
                              <span>
                                单节点限速:{" "}
                                <strong className="text-foreground font-mono">
                                  {t.bandwidth_limit_mbps && t.bandwidth_limit_mbps > 0 ? `${t.bandwidth_limit_mbps} Mbps` : "高速无限制"}
                                </strong>
                              </span>
                            </li>
                            <li className="flex items-center gap-2">
                              <Laptop className="size-3.5 text-indigo-500 shrink-0" />
                              <span>
                                同时在线设备:{" "}
                                <strong className="text-foreground font-mono">
                                  {t.device_limit && t.device_limit > 0 ? `${t.device_limit} 台` : "不限设备数"}
                                </strong>
                              </span>
                            </li>
                            <li className="flex items-center gap-2">
                              <HardDrive className="size-3.5 text-purple-500 shrink-0" />
                              <span>
                                每月可用流量:{" "}
                                <strong className="text-foreground font-mono">
                                  {t.traffic_limit_bytes && t.traffic_limit_bytes > 0 ? formatBytes(t.traffic_limit_bytes) : "无限流量"}
                                </strong>
                              </span>
                            </li>
                            <li className="flex items-center gap-2">
                              <Globe className="size-3.5 text-emerald-500 shrink-0" />
                              <span>专属 VIP 物理隔离线路</span>
                            </li>
                          </ul>
                        </div>

                        <Button
                          onClick={() => {
                            setCheckoutTier(t)
                            setCheckoutPeriod("monthly")
                            setCheckoutMethod("balance")
                          }}
                          className={`w-full text-xs font-semibold h-9 mt-3 gap-1.5 ${
                            isCurrent
                              ? "bg-amber-600 hover:bg-amber-700 text-white"
                              : "bg-primary text-primary-foreground hover:bg-primary/90"
                          }`}
                        >
                          <ShoppingBag className="size-3.5" />
                          {isCurrent ? "续费当前套餐" : "立即购买 / 升级"}
                        </Button>
                      </div>
                    )
                  })}
                </div>
              )}
            </Card>

            {/* 我的订购历史记录 */}
            <Card className="p-4 sm:p-6 border shadow-sm space-y-4">
              <div className="flex items-center justify-between border-b pb-3">
                <div className="space-y-0.5">
                  <h3 className="text-sm font-bold flex items-center gap-2">
                    <Clock className="size-4 text-primary" /> 我的订单记录 ({userOrders.length})
                  </h3>
                  <p className="text-xs text-muted-foreground">查看以往的套餐购买、续费记录与审核状态</p>
                </div>
                <Button variant="outline" size="sm" onClick={loadStoreData} className="text-xs h-7 gap-1">
                  <RefreshCw className="size-3" /> 刷新
                </Button>
              </div>

              {userOrders.length === 0 ? (
                <div className="py-8 text-center text-xs text-muted-foreground">暂无任何订单记录</div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead>
                      <tr className="border-b text-muted-foreground">
                        <th className="py-2 px-2 font-medium">订单编号</th>
                        <th className="py-2 px-2 font-medium">订购套餐</th>
                        <th className="py-2 px-2 font-medium">周期</th>
                        <th className="py-2 px-2 font-medium">金额</th>
                        <th className="py-2 px-2 font-medium">支付方式</th>
                        <th className="py-2 px-2 font-medium">状态</th>
                        <th className="py-2 px-2 font-medium">创建时间</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border/60">
                      {userOrders.map((o) => (
                        <tr key={o.id} className="hover:bg-muted/30 transition-colors">
                          <td className="py-2.5 px-2 font-mono text-[11px] text-muted-foreground">#{o.id}</td>
                          <td className="py-2.5 px-2 font-semibold uppercase font-mono">{o.tier_key}</td>
                          <td className="py-2.5 px-2">
                            {o.period === "yearly" ? "年付" : o.period === "quarterly" ? "季付" : "月付"}
                          </td>
                          <td className="py-2.5 px-2 font-bold font-mono text-emerald-600 dark:text-emerald-400">
                            ￥{Number(o.amount || 0).toFixed(2)}
                          </td>
                          <td className="py-2.5 px-2 capitalize font-mono text-[11px]">
                            {o.pay_method === "balance" ? "余额扣款" : o.pay_method}
                          </td>
                          <td className="py-2.5 px-2">
                            {o.status === "completed" && (
                              <Badge className="bg-emerald-500/10 text-emerald-600 border border-emerald-500/20 text-[10px]">
                                已生效
                              </Badge>
                            )}
                            {o.status === "pending" && (
                              <Badge className="bg-amber-500/10 text-amber-600 border border-amber-500/20 text-[10px]">
                                审核中
                              </Badge>
                            )}
                            {o.status === "rejected" && (
                              <Badge variant="destructive" className="text-[10px]">
                                已驳回
                              </Badge>
                            )}
                          </td>
                          <td className="py-2.5 px-2 text-muted-foreground text-[11px]">
                            {o.created_at ? new Date(o.created_at * 1000).toLocaleString() : "-"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          </div>
        )}

        {/* 客服支持快捷入口卡片 (仅当管理员后台开启时显示，默认关闭 100% 隐藏) */}
        {supportTg.enabled && supportTg.telegram_url && (
          <Card className="p-4 sm:p-5 border border-[#229ED9]/30 bg-[#229ED9]/5 shadow-sm">
            <div className="flex flex-col sm:flex-row items-center justify-between gap-3">
              <div className="flex items-center gap-3 text-center sm:text-left">
                <div className="size-10 rounded-full bg-[#229ED9]/15 flex items-center justify-center shrink-0">
                  <Send className="size-5 text-[#229ED9] fill-[#229ED9]" />
                </div>
                <div>
                  <h4 className="text-sm font-semibold text-foreground">需要人工协助？官方 Telegram 在线客服</h4>
                  <p className="text-xs text-muted-foreground mt-0.5">如需线路咨询、客户端导入排障或技术支持，欢迎随时联系 Telegram 在线客服</p>
                </div>
              </div>
              <Button asChild size="sm" className="bg-[#229ED9] hover:bg-[#229ED9]/90 text-white font-medium text-xs h-9 px-4 shrink-0 shadow-sm">
                <a href={supportTg.telegram_url} target="_blank" rel="noopener noreferrer">
                  <Send className="size-3.5 fill-white mr-1.5" />
                  联系 TG 客服
                </a>
              </Button>
            </div>
          </Card>
        )}
      </main>

      {/* 购买结算与支付弹窗 */}
      <Dialog open={!!checkoutTier} onOpenChange={(open) => { if (!open) setCheckoutTier(null) }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="text-base font-bold flex items-center gap-2">
              <Crown className="size-4 text-amber-500" />
              订购套餐: {checkoutTier?.tier_name || checkoutTier?.tier_key?.toUpperCase()}
            </DialogTitle>
            <DialogDescription className="text-xs">
              选择购买或续费周期并完成支付，系统将自动顺延账号有效期。
            </DialogDescription>
          </DialogHeader>

          {checkoutTier && (() => {
            const mPrice = checkoutTier.price_monthly ?? 0
            const qPrice = checkoutTier.price_quarterly ?? (mPrice ? Number((mPrice * 3 * 0.9).toFixed(0)) : 0)
            const yPrice = checkoutTier.price_yearly ?? (mPrice ? Number((mPrice * 12 * 0.8).toFixed(0)) : 0)
            const currentPrice = checkoutPeriod === "yearly" ? yPrice : checkoutPeriod === "quarterly" ? qPrice : mPrice
            const hasEnoughBalance = (user.balance || 0) >= currentPrice

            return (
              <div className="space-y-4 py-2">
                {/* 周期选择 */}
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-foreground">选择订购时长</label>
                  <div className="grid grid-cols-3 gap-2">
                    <button
                      type="button"
                      onClick={() => setCheckoutPeriod("monthly")}
                      className={`p-2.5 rounded-lg border text-center transition-all cursor-pointer ${
                        checkoutPeriod === "monthly"
                          ? "border-primary bg-primary/10 text-primary font-bold shadow-xs"
                          : "border-border hover:bg-muted/40 text-muted-foreground"
                      }`}
                    >
                      <div className="text-xs">月付 (30天)</div>
                      <div className="text-sm font-mono mt-0.5">￥{mPrice}</div>
                    </button>

                    <button
                      type="button"
                      onClick={() => setCheckoutPeriod("quarterly")}
                      className={`p-2.5 rounded-lg border text-center transition-all cursor-pointer ${
                        checkoutPeriod === "quarterly"
                          ? "border-primary bg-primary/10 text-primary font-bold shadow-xs"
                          : "border-border hover:bg-muted/40 text-muted-foreground"
                      }`}
                    >
                      <div className="text-xs">季付 (90天)</div>
                      <div className="text-sm font-mono mt-0.5">￥{qPrice}</div>
                    </button>

                    <button
                      type="button"
                      onClick={() => setCheckoutPeriod("yearly")}
                      className={`p-2.5 rounded-lg border text-center transition-all cursor-pointer ${
                        checkoutPeriod === "yearly"
                          ? "border-primary bg-primary/10 text-primary font-bold shadow-xs"
                          : "border-border hover:bg-muted/40 text-muted-foreground"
                      }`}
                    >
                      <div className="text-xs">年付 (365天)</div>
                      <div className="text-sm font-mono mt-0.5">￥{yPrice}</div>
                    </button>
                  </div>
                </div>

                {/* 支付方式 */}
                <div className="space-y-1.5">
                  <label className="text-xs font-semibold text-foreground">支付方式</label>
                  <div className="space-y-2">
                    <label className={`flex items-center justify-between p-3 rounded-lg border cursor-pointer transition-all ${
                      checkoutMethod === "balance" ? "border-primary bg-primary/5" : "border-border hover:bg-muted/30"
                    }`}>
                      <div className="flex items-center gap-2.5">
                        <input
                          type="radio"
                          name="payMethod"
                          value="balance"
                          checked={checkoutMethod === "balance"}
                          onChange={() => setCheckoutMethod("balance")}
                          className="accent-primary"
                        />
                        <div className="space-y-0.5">
                          <div className="text-xs font-semibold flex items-center gap-1.5">
                            <Wallet className="size-3.5 text-emerald-500" /> 账户余额直接扣款
                          </div>
                          <div className="text-[11px] text-muted-foreground">
                            可用余额: <strong className="font-mono text-emerald-600 dark:text-emerald-400">￥{(user.balance || 0).toFixed(2)}</strong>
                          </div>
                        </div>
                      </div>
                      <Badge variant={hasEnoughBalance ? "outline" : "destructive"} className="text-[10px]">
                        {hasEnoughBalance ? "余额充足" : "余额不足"}
                      </Badge>
                    </label>

                    {paymentConfig?.usdt_trc20 && (
                      <label className={`flex items-center justify-between p-3 rounded-lg border cursor-pointer transition-all ${
                        checkoutMethod === "usdt_trc20" ? "border-primary bg-primary/5" : "border-border hover:bg-muted/30"
                      }`}>
                        <div className="flex items-center gap-2.5">
                          <input
                            type="radio"
                            name="payMethod"
                            value="usdt_trc20"
                            checked={checkoutMethod === "usdt_trc20"}
                            onChange={() => setCheckoutMethod("usdt_trc20")}
                            className="accent-primary"
                          />
                          <div className="space-y-0.5">
                            <div className="text-xs font-semibold flex items-center gap-1.5">
                              <CreditCard className="size-3.5 text-blue-500" /> USDT (TRC20) 转账
                            </div>
                            <div className="text-[11px] text-muted-foreground font-mono truncate max-w-[240px]">
                              {paymentConfig.usdt_trc20}
                            </div>
                          </div>
                        </div>
                      </label>
                    )}

                    {paymentConfig?.alipay_qr && (
                      <label className={`flex items-center justify-between p-3 rounded-lg border cursor-pointer transition-all ${
                        checkoutMethod === "alipay" ? "border-primary bg-primary/5" : "border-border hover:bg-muted/30"
                      }`}>
                        <div className="flex items-center gap-2.5">
                          <input
                            type="radio"
                            name="payMethod"
                            value="alipay"
                            checked={checkoutMethod === "alipay"}
                            onChange={() => setCheckoutMethod("alipay")}
                            className="accent-primary"
                          />
                          <div className="text-xs font-semibold flex items-center gap-1.5">
                            <CreditCard className="size-3.5 text-sky-500" /> 支付宝扫码支付
                          </div>
                        </div>
                      </label>
                    )}

                    {paymentConfig?.wechat_qr && (
                      <label className={`flex items-center justify-between p-3 rounded-lg border cursor-pointer transition-all ${
                        checkoutMethod === "wechat" ? "border-primary bg-primary/5" : "border-border hover:bg-muted/30"
                      }`}>
                        <div className="flex items-center gap-2.5">
                          <input
                            type="radio"
                            name="payMethod"
                            value="wechat"
                            checked={checkoutMethod === "wechat"}
                            onChange={() => setCheckoutMethod("wechat")}
                            className="accent-primary"
                          />
                          <div className="text-xs font-semibold flex items-center gap-1.5">
                            <CreditCard className="size-3.5 text-emerald-500" /> 微信支付扫码
                          </div>
                        </div>
                      </label>
                    )}
                  </div>
                </div>

                {/* 外部支付指引与附言备注 */}
                {checkoutMethod !== "balance" && (
                  <div className="rounded-lg border p-3 bg-muted/20 space-y-2 text-xs">
                    {checkoutMethod === "usdt_trc20" && (
                      <div className="space-y-1">
                        <span className="text-muted-foreground font-medium">USDT TRC20 接收地址:</span>
                        <div className="p-2 rounded bg-card font-mono text-[11px] break-all border select-all">
                          {paymentConfig?.usdt_trc20}
                        </div>
                      </div>
                    )}
                    {checkoutMethod === "alipay" && paymentConfig?.alipay_qr && (
                      <div className="flex flex-col items-center p-2 bg-white rounded border">
                        <img src={paymentConfig.alipay_qr} alt="Alipay QR" className="size-40 object-contain" />
                        <span className="text-[10px] text-muted-foreground mt-1">使用支付宝 App 扫码转账</span>
                      </div>
                    )}
                    {checkoutMethod === "wechat" && paymentConfig?.wechat_qr && (
                      <div className="flex flex-col items-center p-2 bg-white rounded border">
                        <img src={paymentConfig.wechat_qr} alt="WeChat QR" className="size-40 object-contain" />
                        <span className="text-[10px] text-muted-foreground mt-1">使用微信 App 扫码转账</span>
                      </div>
                    )}

                    <div className="space-y-1 pt-1">
                      <label className="text-xs font-medium text-foreground">支付转账交易单号 / 附言哈希</label>
                      <input
                        type="text"
                        value={checkoutNote}
                        onChange={(e) => setCheckoutNote(e.target.value)}
                        placeholder="请输入转账单号或哈希，以便管理员审核快速生效"
                        className="w-full h-8 px-2.5 rounded border bg-background text-xs"
                      />
                    </div>
                  </div>
                )}

                <div className="flex items-center justify-between pt-2 border-t text-xs">
                  <div>
                    <span className="text-muted-foreground">应付总额：</span>
                    <span className="text-base font-bold font-mono text-emerald-600 dark:text-emerald-400">
                      ￥{currentPrice.toFixed(2)}
                    </span>
                  </div>
                  <div className="flex gap-2">
                    <Button variant="outline" size="sm" onClick={() => setCheckoutTier(null)} className="h-8 text-xs">
                      取消
                    </Button>
                    <Button
                      size="sm"
                      disabled={submittingOrder || (checkoutMethod === "balance" && !hasEnoughBalance)}
                      onClick={handleBuyOrder}
                      className="h-8 text-xs bg-primary text-primary-foreground font-semibold shadow-xs"
                    >
                      {submittingOrder ? "正在处理…" : checkoutMethod === "balance" ? "立即余额支付" : "提交订购单"}
                    </Button>
                  </div>
                </div>
              </div>
            )
          })()}
        </DialogContent>
      </Dialog>

      {/* 手机扫码弹窗 */}
      <Dialog open={qrOpen} onOpenChange={setQrOpen}>
        <DialogContent className="max-w-xs text-center space-y-4">
          <DialogHeader>
            <DialogTitle className="text-base font-bold">手机扫码快速导入</DialogTitle>
            <DialogDescription className="text-xs">
              使用小火箭 (Shadowrocket) 或相机扫码自动识别订阅
            </DialogDescription>
          </DialogHeader>

          <div className="flex justify-center p-2 bg-white rounded-lg border">
            {qrUrl ? (
              <img src={qrUrl} alt="Subscription QR" className="size-56 object-contain" />
            ) : (
              <div className="size-56 grid place-items-center text-xs text-muted-foreground">生成二维码中…</div>
            )}
          </div>

          <div className="text-xs text-muted-foreground">
            若扫码不响应，可点击“复制订阅”手动填入客户端中。
          </div>
        </DialogContent>
      </Dialog>

      {/* 公告详细弹窗 */}
      <Dialog open={announcementDialogOpen} onOpenChange={setAnnouncementDialogOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <div className="flex items-center gap-2">
              {selectedAnnouncement?.is_pinned === 1 && (
                <Badge className="text-[10px] py-0 px-1.5 bg-rose-500/10 text-rose-600 border border-rose-500/20">
                  置顶
                </Badge>
              )}
              <DialogTitle className="text-base font-bold">{selectedAnnouncement?.title}</DialogTitle>
            </div>
            <DialogDescription className="text-[11px] text-muted-foreground font-mono">
              发布时间：{selectedAnnouncement?.created_at ? new Date(selectedAnnouncement.created_at * 1000).toLocaleString() : ""}
            </DialogDescription>
          </DialogHeader>

          <div className="py-2 text-xs text-foreground whitespace-pre-wrap leading-relaxed max-h-[60vh] overflow-y-auto">
            {selectedAnnouncement?.content}
          </div>

          <DialogFooter className="pt-2">
            <Button size="sm" onClick={() => setAnnouncementDialogOpen(false)} className="h-8 text-xs">
              关闭
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* 登录全局自动弹窗通知 */}
      {globalNotice && (
        <Dialog open={globalNoticeOpen} onOpenChange={setGlobalNoticeOpen}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <div className="flex items-center gap-2">
                <Bell className="size-4 text-primary" />
                <DialogTitle className="text-base font-bold">{globalNotice.title}</DialogTitle>
              </div>
            </DialogHeader>

            <div className="py-2 text-xs text-foreground whitespace-pre-wrap leading-relaxed max-h-[60vh] overflow-y-auto">
              {globalNotice.content}
            </div>

            <DialogFooter className="pt-2">
              <Button
                size="sm"
                onClick={() => {
                  sessionStorage.setItem("dismissed_notice_" + globalNotice.title, "1")
                  setGlobalNoticeOpen(false)
                }}
                className="h-8 text-xs bg-primary text-primary-foreground hover:bg-primary/90"
              >
                我知道了
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      )}
    </div>
  )
}
