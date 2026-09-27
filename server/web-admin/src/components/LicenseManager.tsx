import { useState, useEffect } from "react"
import { ShieldCheck, KeyRound, Copy, Check, RefreshCw, AlertTriangle, Clock, XCircle, Sparkles, Server, Network, Users } from "lucide-react"
import { toast } from "sonner"
import { copyToClipboard } from "@/lib/clipboard"
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"

export interface LicenseStatus {
  active: boolean
  type: string
  plan_name?: string
  customer?: string
  license_id?: string
  max_servers?: number
  max_nodes?: number
  max_users?: number
  expire_at?: number
  expire_date?: string
  days_left?: number
  machine_id: string
  last_sync?: number
  message: string
  limits?: {
    max_servers: number
    max_nodes: number
    max_users: number
  }
  usage?: {
    server_count: number
    node_count: number
    user_count: number
    free_limits: {
      max_servers: number
      max_nodes: number
      max_users: number
    }
  }
}

const PLAN_BADGES: Record<string, { label: string; color: string }> = {
  stardust: { label: "星尘套餐", color: "bg-cyan-500/10 text-cyan-600 dark:text-cyan-400 border-cyan-500/30" },
  planet: { label: "行星套餐", color: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30" },
  star: { label: "恒星套餐", color: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/30" },
  galaxy: { label: "星系套餐", color: "bg-indigo-500/10 text-indigo-600 dark:text-indigo-400 border-indigo-500/30" },
  universe: { label: "宇宙套餐", color: "bg-fuchsia-500/10 text-fuchsia-600 dark:text-fuchsia-400 border-fuchsia-500/30" },
}

export function LicenseManager() {
  const [status, setStatus] = useState<LicenseStatus | null>(() => {
    try {
      return JSON.parse(localStorage.getItem("proxyprobe_license_status") || "null")
    } catch {
      return null
    }
  })
  const [loading, setLoading] = useState(false)
  const [activating, setActivating] = useState(false)
  const [licenseInput, setLicenseInput] = useState("")
  const [copied, setCopied] = useState(false)

  const fetchStatus = async () => {
    try {
      const res = await fetch("/api/proxy/license/status")
      if (res.ok) {
        const data = await res.json()
        setStatus(data)
        try { localStorage.setItem("proxyprobe_license_status", JSON.stringify(data)) } catch {}
      } else {
        toast.error("获取许可证状态失败")
      }
    } catch {
      toast.error("网络连接异常，无法查询许可证状态")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchStatus()
  }, [])

  const copyMachineId = async () => {
    if (!status?.machine_id) return
    const ok = await copyToClipboard(status.machine_id)
    if (ok) {
      setCopied(true)
      toast.success("机器识别码已复制到剪贴板")
      setTimeout(() => setCopied(false), 2000)
    } else {
      toast.error("复制失败，请手动选取复制")
    }
  }

  const handleActivate = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!licenseInput.trim()) {
      toast.error("请输入许可证密钥")
      return
    }

    try {
      setActivating(true)
      const res = await fetch("/api/proxy/license/activate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ license_key: licenseInput.trim() }),
      })

      const data = await res.json()
      if (res.ok && data.ok) {
        toast.success(data.message || "恭喜，商业许可证激活成功！")
        setStatus(data.status)
        setLicenseInput("")
        fetchStatus()
      } else {
        toast.error(data.message || "许可证无效或激活失败")
      }
    } catch {
      toast.error("请求失败，请检查网络或后端状态")
    } finally {
      setActivating(false)
    }
  }

  const maxNodes = status?.max_nodes || status?.limits?.max_nodes || 1
  const maxUsers = status?.max_users || status?.limits?.max_users || 1

  const curServers = status?.usage?.server_count ?? 1
  const curNodes = status?.usage?.node_count ?? 0
  const curUsers = status?.usage?.user_count ?? 0

  const planBadge = (status?.type && PLAN_BADGES[status.type]) || null

  return (
    <div className="space-y-6 max-w-5xl">
      {/* 顶部标题栏 */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b">
        <div>
          <h2 className="text-xl font-bold tracking-tight flex items-center gap-2">
            <KeyRound className="size-5 text-indigo-500" />
            商业许可证授权管理
          </h2>
          <p className="text-sm text-muted-foreground mt-1">
            探针基础监控无限添加、终身免费；激活商业授权即可解锁多协议节点与海量用户订阅体系
          </p>
        </div>
        <Button
          variant="outline"
          size="sm"
          onClick={fetchStatus}
          disabled={loading}
          className="self-start sm:self-auto gap-1 text-xs"
        >
          <RefreshCw className={`size-3.5 ${loading ? "animate-spin" : ""}`} />
          刷新状态
        </Button>
      </div>

      {/* 授权状态概览卡片 */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <Card className="md:col-span-2">
          <CardHeader className="pb-3">
            <div className="flex items-center justify-between">
              <CardTitle className="text-base font-semibold">当前授权状态</CardTitle>
              {status?.active ? (
                <Badge className={`${planBadge?.color || "bg-emerald-500/10 text-emerald-600 border-emerald-500/20"} gap-1.5 py-1 px-3 text-xs`}>
                  <Sparkles className="size-3.5" />
                  {status.plan_name || planBadge?.label || "商业授权版"}
                </Badge>
              ) : status?.type === "expired" ? (
                <Badge variant="destructive" className="gap-1">
                  <Clock className="size-3" />
                  已过期
                </Badge>
              ) : status?.type === "revoked" ? (
                <Badge variant="destructive" className="gap-1">
                  <XCircle className="size-3" />
                  已吊销
                </Badge>
              ) : status?.type === "tampered" ? (
                <Badge variant="destructive" className="gap-1">
                  <AlertTriangle className="size-3" />
                  时钟异常已锁定
                </Badge>
              ) : (
                <Badge variant="secondary" className="gap-1 text-muted-foreground">
                  免费体验版 (探针无限/1节/1户)
                </Badge>
              )}
            </div>
            <CardDescription className="text-xs">
              {status?.message}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 pt-0">
            {status?.active ? (
              <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 bg-muted/30 rounded-lg p-3 text-xs">
                <div>
                  <span className="text-muted-foreground block mb-0.5">有效期限</span>
                  <span className="font-medium text-foreground">{status.expire_date}</span>
                </div>
                <div>
                  <span className="text-muted-foreground block mb-0.5">剩余天数</span>
                  <span className="font-semibold text-emerald-600 dark:text-emerald-400">
                    {status.days_left && status.days_left > 3000 ? "永久买断" : `${status.days_left} 天`}
                  </span>
                </div>
                <div>
                  <span className="text-muted-foreground block mb-0.5">授权套餐</span>
                  <span className="font-semibold text-foreground">{status.plan_name || "商业版"}</span>
                </div>
                <div>
                  <span className="text-muted-foreground block mb-0.5">许可证 ID</span>
                  <span className="font-mono text-muted-foreground">{status.license_id || "—"}</span>
                </div>
              </div>
            ) : (
              <div className="bg-amber-500/10 border border-amber-500/20 text-amber-800 dark:text-amber-300 rounded-lg p-3 text-xs flex items-start gap-2.5">
                <AlertTriangle className="size-4 shrink-0 text-amber-500 mt-0.5" />
                <div>
                  <span className="font-semibold block mb-0.5">免费体验模式配额限制</span>
                  探针服务器支持<strong>无限制添加与监控</strong>。免费体验模式限制运行：<strong>最多 1 个代理节点、1 个客户端用户</strong>。若需增加代理节点或用户规模，请联系管理员签发商业授权。
                </div>
              </div>
            )}

            {/* 3 项核心配额进度展示 */}
            <div className="space-y-2.5 pt-1">
              <label className="text-xs font-semibold text-foreground flex items-center justify-between">
                <span>套餐资源配额占用进度</span>
                <span className="text-[11px] text-muted-foreground font-normal">
                  {status?.active ? `当前套餐：${status.plan_name}` : "当前模式：免费体验版"}
                </span>
              </label>

              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {/* 服务器配额 */}
                <div className="p-3 rounded-lg border bg-muted/20 space-y-1.5">
                  <div className="flex items-center justify-between text-xs">
                    <span className="flex items-center gap-1.5 text-muted-foreground font-medium">
                      <Server className="size-3.5 text-cyan-500" /> 服务器纳管
                    </span>
                    <span className="font-semibold text-emerald-600 dark:text-emerald-400 font-mono">
                      {curServers} 台 (无限制)
                    </span>
                  </div>
                  <div className="w-full bg-muted rounded-full h-1.5 overflow-hidden">
                    <div
                      className="h-full bg-emerald-500 transition-all"
                      style={{ width: "100%" }}
                    />
                  </div>
                </div>

                {/* 代理节点配额 */}
                <div className="p-3 rounded-lg border bg-muted/20 space-y-1.5">
                  <div className="flex items-center justify-between text-xs">
                    <span className="flex items-center gap-1.5 text-muted-foreground font-medium">
                      <Network className="size-3.5 text-emerald-500" /> 代理节点
                    </span>
                    <span className="font-semibold text-foreground font-mono">
                      {curNodes} / {maxNodes} 个
                    </span>
                  </div>
                  <div className="w-full bg-muted rounded-full h-1.5 overflow-hidden">
                    <div
                      className={`h-full transition-all ${curNodes >= maxNodes ? "bg-amber-500" : "bg-emerald-500"}`}
                      style={{ width: `${Math.min(100, Math.round((curNodes / maxNodes) * 100))}%` }}
                    />
                  </div>
                </div>

                {/* 用户配额 */}
                <div className="p-3 rounded-lg border bg-muted/20 space-y-1.5">
                  <div className="flex items-center justify-between text-xs">
                    <span className="flex items-center gap-1.5 text-muted-foreground font-medium">
                      <Users className="size-3.5 text-indigo-500" /> 客户端用户
                    </span>
                    <span className="font-semibold text-foreground font-mono">
                      {curUsers} / {maxUsers} 户
                    </span>
                  </div>
                  <div className="w-full bg-muted rounded-full h-1.5 overflow-hidden">
                    <div
                      className={`h-full transition-all ${curUsers >= maxUsers ? "bg-amber-500" : "bg-indigo-500"}`}
                      style={{ width: `${Math.min(100, Math.round((curUsers / maxUsers) * 100))}%` }}
                    />
                  </div>
                </div>
              </div>
            </div>

            {/* 机器识别码 (一键复制) */}
            <div className="pt-2">
              <label className="text-xs font-medium text-muted-foreground block mb-1.5">
                本机唯一机器识别码 (Machine ID)
              </label>
              <div className="flex items-center gap-2">
                <div className="font-mono text-sm tracking-wider bg-muted/60 border rounded-md px-3 py-1.5 select-all flex-1 text-foreground font-semibold">
                  {status?.machine_id || "正在采集指纹..."}
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={copyMachineId}
                  className="shrink-0 gap-1.5 text-xs h-9 px-3"
                >
                  {copied ? <Check className="size-3.5 text-emerald-500" /> : <Copy className="size-3.5" />}
                  {copied ? "已复制" : "复制机器码"}
                </Button>
              </div>
              <p className="text-[11px] text-muted-foreground mt-1">
                基于 Linux 硬件哈希与主板 DMI 特征生成。开通或升级商业套餐时请将此识别码提交给管理员。
              </p>
            </div>
          </CardContent>
        </Card>

        {/* 5 大套餐规格对比卡片 */}
        <Card className="flex flex-col justify-between">
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-semibold">套餐梯队标准 (节点 / 用户)</CardTitle>
            <CardDescription className="text-xs">✨ 基础探针全套餐无限纳管，仅按节点与用户配额授权</CardDescription>
          </CardHeader>
          <CardContent className="space-y-2.5 text-xs pt-0 flex-1">
            <div className="space-y-1.5">
              <div className="flex items-center justify-between p-2 rounded border bg-muted/10">
                <span className="font-medium text-muted-foreground">免费体验版</span>
                <span className="font-mono text-xs font-semibold">1 节点 / 1 用户</span>
              </div>
              <div className="flex items-center justify-between p-2 rounded border bg-cyan-500/5 border-cyan-500/20">
                <span className="font-semibold text-cyan-500">1. 星尘套餐</span>
                <span className="font-mono text-xs font-semibold text-cyan-600 dark:text-cyan-400">6 节点 / 6 用户</span>
              </div>
              <div className="flex items-center justify-between p-2 rounded border bg-emerald-500/5 border-emerald-500/20">
                <span className="font-semibold text-emerald-500">2. 行星套餐</span>
                <span className="font-mono text-xs font-semibold text-emerald-600 dark:text-emerald-400">12 节点 / 12 用户</span>
              </div>
              <div className="flex items-center justify-between p-2 rounded border bg-amber-500/5 border-amber-500/20">
                <span className="font-semibold text-amber-500">3. 恒星套餐</span>
                <span className="font-mono text-xs font-semibold text-amber-600 dark:text-amber-400">18 节点 / 18 用户</span>
              </div>
              <div className="flex items-center justify-between p-2 rounded border bg-indigo-500/5 border-indigo-500/20">
                <span className="font-semibold text-indigo-500">4. 星系套餐</span>
                <span className="font-mono text-xs font-semibold text-indigo-600 dark:text-indigo-400">30 节点 / 30 用户</span>
              </div>
              <div className="flex items-center justify-between p-2 rounded border bg-fuchsia-500/5 border-fuchsia-500/20">
                <span className="font-semibold text-fuchsia-500">5. 宇宙套餐</span>
                <span className="font-mono text-xs font-semibold text-fuchsia-600 dark:text-fuchsia-400">50 节点 / 50 用户</span>
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* 许可证输入与激活表单 */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-semibold">
            {status?.active ? "升级 / 更换 / 续期许可证" : "输入许可证密钥激活"}
          </CardTitle>
          <CardDescription className="text-xs">
            输入以 <code className="text-xs font-mono font-bold">PP-</code> 开头的 23 位商业授权码或离线签名凭据即可即刻生效
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleActivate} className="space-y-4">
            <textarea
              className="w-full h-24 font-mono text-xs p-3 bg-muted/20 border rounded-md focus:outline-none focus:ring-1 focus:ring-ring resize-none"
              placeholder="请粘贴您的专属商业授权码（如: PP-XXXX-XXXX-XXXX-XXXX）或离线激活密钥"
              value={licenseInput}
              onChange={(e) => setLicenseInput(e.target.value)}
              disabled={activating}
            />

            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">
                采用 Ed25519 机器码非对称签名加密，激活立即可用，无需重启服务。
              </span>
              <Button
                type="submit"
                disabled={activating || !licenseInput.trim()}
                className="gap-2 text-xs bg-black text-white hover:bg-neutral-800 dark:bg-white dark:text-black shrink-0"
              >
                {activating ? (
                  <>
                    <RefreshCw className="size-3.5 animate-spin" />
                    正在验签激活...
                  </>
                ) : (
                  <>
                    <ShieldCheck className="size-3.5" />
                    {status?.active ? "确认更新授权" : "立即验证并激活"}
                  </>
                )}
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  )
}
