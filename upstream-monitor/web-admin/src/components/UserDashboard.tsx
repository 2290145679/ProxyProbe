import { useEffect, useState } from "react"
import {
  Activity,
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  Calendar,
  Copy,
  Globe,
  HardDrive,
  LogOut,
  Moon,
  QrCode,
  RefreshCw,
  Send,
  Smartphone,
  Sun,
  Zap,
} from "lucide-react"
import QRCode from "qrcode"
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
import { Input } from "@/components/ui/input"

export type UserProfile = {
  id: number
  username: string
  is_admin: boolean
  sub_token: string
  sub_url: string
  traffic_limit_bytes: number
  upload_bytes: number
  download_bytes: number
  total_used_bytes: number
  remaining_bytes: number
  expires_at: number
  enabled: number
  status: "active" | "over_quota" | "expired" | "disabled"
  created_at: number
}

type NodeItem = {
  id: number
  name: string
  protocol: string
  server_name: string
  server_host: string
  port: number
  enabled: number
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

export function UserDashboard({
  user,
  siteName,
  refreshUser,
  onSignOut,
  toggleTheme,
  dark,
}: {
  user: UserProfile
  siteName: string
  refreshUser: () => void
  onSignOut: () => void
  toggleTheme: () => void
  dark: boolean
}) {
  const [nodes, setNodes] = useState<NodeItem[]>([])
  const [testingId, setTestingId] = useState<number | null>(null)
  const [latencies, setLatencies] = useState<Record<number, { ok: boolean; msg: string; ms: number }>>({})
  const [qrOpen, setQrOpen] = useState(false)
  const [qrUrl, setQrUrl] = useState("")
  const [resettingToken, setResettingToken] = useState(false)

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

  // 生成二维码
  useEffect(() => {
    if (user.sub_url) {
      QRCode.toDataURL(user.sub_url, { width: 300, margin: 2 })
        .then(url => setQrUrl(url))
        .catch(() => {})
    }
  }, [user.sub_url])

  // 复制订阅链接
  function copySubUrl() {
    navigator.clipboard.writeText(user.sub_url)
    toast.success("聚合订阅链接已复制到剪贴板！")
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

  // 单节点延迟测试
  async function testNode(nodeId: number) {
    setTestingId(nodeId)
    try {
      const res = await fetch(`/api/proxy/nodes/${nodeId}/test`)
      const data = await res.json()
      setLatencies(prev => ({
        ...prev,
        [nodeId]: { ok: data.ok, msg: data.message, ms: data.latency_ms }
      }))
    } catch {
      setLatencies(prev => ({
        ...prev,
        [nodeId]: { ok: false, msg: "网络错误", ms: -1 }
      }))
    } finally {
      setTestingId(null)
    }
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
    <div className="min-h-svh bg-background/50">
      {/* 顶部导航条 */}
      <header className="sticky top-0 z-10 border-b bg-background/80 backdrop-blur">
        <div className="mx-auto flex max-w-6xl items-center gap-3 px-4 py-3">
          <div className="flex items-center gap-2">
            <span className="font-bold text-base tracking-tight">{siteName || "Monitor"}</span>
            <Badge variant="outline" className="text-[11px] font-normal">用户中心</Badge>
          </div>

          <div className="flex-1" />

          <div className="flex items-center gap-2">
            <span className="text-xs text-muted-foreground mr-1 hidden sm:inline-flex items-center gap-1.5">
              <span>用户:</span>
              <strong className="text-foreground">{user.username}</strong>
            </span>

            <Button variant="ghost" size="icon" onClick={toggleTheme} title="切换主题">
              {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
            </Button>

            <Button variant="ghost" size="sm" onClick={onSignOut} className="gap-1.5 text-xs text-muted-foreground hover:text-foreground">
              <LogOut className="size-3.5" /> 退出
            </Button>
          </div>
        </div>
      </header>

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
              </p>
              <p className="text-muted-foreground dark:text-red-300">
                当前订阅服务处于熔断状态，客户端无法继续连接代理节点。请联系管理员续期或增加流量配额。
              </p>
            </div>
          </div>
        )}

        {/* 卡片 1：流量与配额状态概览 */}
        <Card className="p-6 space-y-5 border shadow-sm">
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

            <Button variant="outline" size="sm" onClick={refreshUser} className="text-xs gap-1.5 shrink-0 self-start sm:self-auto">
              <RefreshCw className="size-3.5" /> 刷新统计
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
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 pt-2">
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
                <Calendar className="size-3.5 text-amber-500" /> 到期时间
              </div>
              <p className="text-base font-semibold tracking-tight truncate" title={formatDate(user.expires_at)}>
                {formatDate(user.expires_at)}
              </p>
            </div>
          </div>
        </Card>

        {/* 卡片 2：专属聚合订阅与一键导入 */}
        <Card className="p-6 space-y-5 border shadow-sm">
          <div className="border-b pb-4 space-y-1">
            <h2 className="text-lg font-bold flex items-center gap-2">
              <Zap className="size-4 text-amber-500" /> 一键聚合订阅
            </h2>
            <p className="text-xs text-muted-foreground">
              支持一键同步全部可用节点，兼容 Clash、Shadowrocket、Sing-box 等主流客户端
            </p>
          </div>

          <div className="space-y-3">
            <div className="flex gap-2">
              <Input
                readOnly
                value={user.sub_url}
                className="font-mono text-xs h-9 bg-muted/40"
              />
              <Button onClick={copySubUrl} size="sm" className="h-9 gap-1.5 shrink-0 text-xs">
                <Copy className="size-3.5" /> 复制订阅
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setQrOpen(true)}
                className="h-9 gap-1.5 shrink-0 text-xs"
                title="手机扫码导入"
              >
                <QrCode className="size-3.5" /> 扫码
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={handleResetToken}
                disabled={resettingToken}
                className="h-9 gap-1.5 shrink-0 text-xs text-muted-foreground hover:text-foreground"
                title="若订阅泄漏，可一键重置"
              >
                <RefreshCw className={`size-3.5 ${resettingToken ? "animate-spin" : ""}`} /> 重置
              </Button>
            </div>

            {/* 客户端快捷导入按钮组 */}
            <div className="pt-2">
              <div className="text-xs font-medium text-muted-foreground mb-2.5">快捷一键导入到客户端：</div>
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-2.5">
                <Button
                  variant="outline"
                  size="sm"
                  asChild
                  className="h-9 text-xs justify-start gap-2 hover:border-primary/50"
                >
                  <a href={`clash://install-config?url=${encodeURIComponent(user.sub_url)}&name=${encodeURIComponent(subName)}`}>
                    <Send className="size-3.5 text-blue-500" />
                    <span>导入 Clash / Verge</span>
                  </a>
                </Button>

                <Button
                  variant="outline"
                  size="sm"
                  asChild
                  className="h-9 text-xs justify-start gap-2 hover:border-primary/50"
                >
                  <a href={`shadowrocket://add/sub://${btoa(user.sub_url)}?title=${encodeURIComponent(subName)}`}>
                    <Smartphone className="size-3.5 text-indigo-500" />
                    <span>导入 小火箭 (Shadowrocket)</span>
                  </a>
                </Button>

                <Button
                  variant="outline"
                  size="sm"
                  asChild
                  className="h-9 text-xs justify-start gap-2 hover:border-primary/50"
                >
                  <a href={`sing-box://import-remote-profile?url=${encodeURIComponent(user.sub_url)}#${encodeURIComponent(subName)}`}>
                    <Globe className="size-3.5 text-amber-500" />
                    <span>导入 Sing-box</span>
                  </a>
                </Button>

                <Button
                  variant="outline"
                  size="sm"
                  onClick={copySubUrl}
                  className="h-9 text-xs justify-start gap-2 hover:border-primary/50"
                >
                  <Activity className="size-3.5 text-emerald-500" />
                  <span>复制到 v2rayN / Nekobox</span>
                </Button>
              </div>
            </div>
          </div>
        </Card>

        {/* 卡片 3：可用节点列表与延迟测试 */}
        <Card className="p-6 space-y-5 border shadow-sm">
          <div className="flex items-center justify-between border-b pb-4">
            <div className="space-y-1">
              <h2 className="text-lg font-bold flex items-center gap-2">
                <Globe className="size-4 text-emerald-500" /> 可用代理节点列表 ({nodes.length})
              </h2>
              <p className="text-xs text-muted-foreground">
                当前包含在您订阅中的节点，可点击“测试延迟”实时检测连通性
              </p>
            </div>
          </div>

          {nodes.length === 0 ? (
            <div className="py-8 text-center text-xs text-muted-foreground">
              暂无已启用的代理节点，请联系管理员添加节点。
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {nodes.map(n => {
                const lat = latencies[n.id]
                const isTesting = testingId === n.id

                return (
                  <div
                    key={n.id}
                    className="flex items-center justify-between rounded-lg border bg-card p-3 text-xs gap-3 hover:border-primary/30 transition-all"
                  >
                    <div className="space-y-1 min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold truncate">{n.name}</span>
                        <Badge variant="secondary" className="text-[10px] py-0 px-1 font-mono uppercase shrink-0">
                          {n.protocol.replace("_", " ")}
                        </Badge>
                      </div>
                      <div className="text-[11px] text-muted-foreground truncate">
                        {n.server_name} · {n.server_host}:{n.port}
                      </div>
                    </div>

                    <div className="flex items-center gap-2 shrink-0">
                      {lat && (
                        <span
                          className={`text-[11px] font-mono font-medium ${
                            lat.ok ? "text-emerald-600 dark:text-emerald-400" : "text-red-500"
                          }`}
                        >
                          {lat.ok ? `${lat.ms} ms` : "超时"}
                        </span>
                      )}

                      <Button
                        variant="outline"
                        size="sm"
                        disabled={isTesting}
                        onClick={() => testNode(n.id)}
                        className="h-7 px-2 text-[11px] gap-1"
                      >
                        <Activity className={`size-3 ${isTesting ? "animate-spin text-primary" : ""}`} />
                        {isTesting ? "测试中…" : "测速"}
                      </Button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </Card>
      </main>

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
    </div>
  )
}
