import { useState, useEffect } from "react"
import { ShieldCheck, KeyRound, Copy, Check, RefreshCw, AlertTriangle, Clock, CheckCircle2, XCircle } from "lucide-react"
import { toast } from "sonner"
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from "@/components/ui/card"
import { Button } from "@/components/ui/button"
import { Badge } from "@/components/ui/badge"

export interface LicenseStatus {
  active: boolean
  type: string
  plan_name?: string
  customer?: string
  license_id?: string
  max_nodes?: number
  expire_at?: number
  expire_date?: string
  days_left?: number
  machine_id: string
  last_sync?: number
  message: string
}

export function LicenseManager() {
  const [status, setStatus] = useState<LicenseStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [activating, setActivating] = useState(false)
  const [licenseInput, setLicenseInput] = useState("")
  const [copied, setCopied] = useState(false)

  const fetchStatus = async () => {
    try {
      setLoading(true)
      const res = await fetch("/api/proxy/license/status")
      if (res.ok) {
        const data = await res.json()
        setStatus(data)
      } else {
        toast.error("获取许可证状态失败")
      }
    } catch (err) {
      toast.error("网络连接异常，无法查询许可证状态")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchStatus()
  }, [])

  const copyMachineId = () => {
    if (!status?.machine_id) return
    navigator.clipboard.writeText(status.machine_id).then(
      () => {
        setCopied(true)
        toast.success("机器识别码已复制到剪贴板")
        setTimeout(() => setCopied(false), 2000)
      },
      () => toast.error("复制失败，请手动选取复制")
    )
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
        body: json_payload(licenseInput.trim()),
      })

      const data = await res.json()
      if (res.ok && data.ok) {
        toast.success(data.message || "恭喜，商业许可证激活成功！")
        setStatus(data.status)
        setLicenseInput("")
      } else {
        toast.error(data.message || "许可证无效或激活失败")
      }
    } catch (err) {
      toast.error("请求失败，请检查网络或后端状态")
    } finally {
      setActivating(false)
    }
  }

  function json_payload(key: string) {
    return JSON.stringify({ license_key: key })
  }

  return (
    <div className="space-y-6 max-w-4xl">
      {/* 顶部标题栏 */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-4 border-b">
        <div>
          <h2 className="text-xl font-bold tracking-tight flex items-center gap-2">
            <KeyRound className="size-5 text-indigo-500" />
            商业许可证授权管理
          </h2>
          <p className="text-sm text-muted-foreground mt-1">
            探针基础功能终身免费；激活商业许可证即可解锁 Xray / Sing-box / Realm 代理多协议节点管理
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
                <Badge className="bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20 gap-1">
                  <CheckCircle2 className="size-3" />
                  {status.plan_name || "商业授权版"}
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
                  探针免费版 (未激活商业功能)
                </Badge>
              )}
            </div>
            <CardDescription className="text-xs">
              {status?.message}
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4 pt-0">
            {status?.active ? (
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 bg-muted/30 rounded-lg p-3 text-xs">
                <div>
                  <span className="text-muted-foreground block mb-0.5">授权客户</span>
                  <span className="font-medium text-foreground">{status.customer || "VIP客户"}</span>
                </div>
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
                  <span className="text-muted-foreground block mb-0.5">节点配额</span>
                  <span className="font-medium text-foreground">
                    {status.max_nodes && status.max_nodes > 0 ? `${status.max_nodes} 个` : "无限配额"}
                  </span>
                </div>
                <div>
                  <span className="text-muted-foreground block mb-0.5">许可证 ID</span>
                  <span className="font-mono text-muted-foreground">{status.license_id || "—"}</span>
                </div>
                <div>
                  <span className="text-muted-foreground block mb-0.5">双轨同步状态</span>
                  <span className="text-emerald-600 dark:text-emerald-400 font-medium">双轨保护中 (宽限7天)</span>
                </div>
              </div>
            ) : (
              <div className="bg-amber-500/10 border border-amber-500/20 text-amber-800 dark:text-amber-300 rounded-lg p-3 text-xs flex items-start gap-2.5">
                <AlertTriangle className="size-4 shrink-0 text-amber-500 mt-0.5" />
                <div>
                  <span className="font-semibold block mb-0.5">功能限制提示</span>
                  当前系统仅能作为服务器状态监控面板。若需创建代理节点、分配订阅给用户或进行流量限制，请在右侧输入购买的许可证密钥完成激活。
                </div>
              </div>
            )}

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
                基于 Linux 硬件哈希与主板 DMI 特征生成。开通商业授权时请将此识别码提交给管理员。
              </p>
            </div>
          </CardContent>
        </Card>

        {/* 权限对比卡片 */}
        <Card className="flex flex-col justify-between">
          <CardHeader className="pb-2">
            <CardTitle className="text-base font-semibold">版本权益对比</CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-xs pt-0 flex-1">
            <div className="space-y-2">
              <div className="flex items-center justify-between pb-1.5 border-b">
                <span className="text-muted-foreground">服务器状态遥测</span>
                <span className="text-emerald-500 font-medium">免费版 & 商业版</span>
              </div>
              <div className="flex items-center justify-between pb-1.5 border-b">
                <span className="text-muted-foreground">大屏公开状态页</span>
                <span className="text-emerald-500 font-medium">免费版 & 商业版</span>
              </div>
              <div className="flex items-center justify-between pb-1.5 border-b">
                <span className="text-muted-foreground">创建/下发代理节点</span>
                {status?.active ? (
                  <span className="text-emerald-500 font-semibold">已解锁</span>
                ) : (
                  <span className="text-amber-500 font-medium">需激活许可证</span>
                )}
              </div>
              <div className="flex items-center justify-between pb-1.5 border-b">
                <span className="text-muted-foreground">多用户订阅与设备限制</span>
                {status?.active ? (
                  <span className="text-emerald-500 font-semibold">已解锁</span>
                ) : (
                  <span className="text-amber-500 font-medium">需激活许可证</span>
                )}
              </div>
              <div className="flex items-center justify-between">
                <span className="text-muted-foreground">Xray/Sing-box 核心联动</span>
                {status?.active ? (
                  <span className="text-emerald-500 font-semibold">已解锁</span>
                ) : (
                  <span className="text-amber-500 font-medium">需激活许可证</span>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* 许可证输入与激活表单 */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-semibold">
            {status?.active ? "更新 / 续期许可证" : "输入许可证激活"}
          </CardTitle>
          <CardDescription className="text-xs">
            粘贴以 <code className="text-xs font-mono font-bold">PPLIC-</code> 开头的完整授权字符串并提交
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleActivate} className="space-y-4">
            <textarea
              className="w-full h-24 font-mono text-xs p-3 bg-muted/20 border rounded-md focus:outline-none focus:ring-1 focus:ring-ring resize-none"
              placeholder="请粘贴您的许可证激活代码，形如: PPLIC-eyJhbGciOiJFZDI1NTE5In0......."
              value={licenseInput}
              onChange={(e) => setLicenseInput(e.target.value)}
              disabled={activating}
            />

            <div className="flex items-center justify-between">
              <span className="text-xs text-muted-foreground">
                采用 Ed25519 非对称密码学防伪，激活立刻生效，无需重启服务。
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
