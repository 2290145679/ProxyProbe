import { useState, useEffect } from "react"
import {
  ArrowRightLeft,
  Check,
  Copy,
  Layers,
  RefreshCw,
  Server,
  ShieldCheck,
  Sparkles,
  Terminal,
  Truck,
  Users,
  Zap,
} from "lucide-react"
import { toast } from "sonner"
import { copyToClipboard } from "@/lib/clipboard"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"

export function isIpAddress(val: string): boolean {
  if (!val) return false
  const clean = val.split(":")[0].trim().replace(/^\[|\]$/g, "")
  return /^(\d{1,3}\.){3}\d{1,3}$/.test(clean) || clean.includes(":")
}

// ============================================================================
// 1. 搬家与克隆中心弹窗 (MigrationCenterDialog)
// ============================================================================
export function MigrationCenterDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [activeTab, setActiveTab] = useState<"clone" | "push">("clone")

  // 思路一：一键克隆安装指令状态
  const [cloneLoading, setCloneLoading] = useState(false)
  const [cloneCmd, setCloneCmd] = useState("")
  const [cloneSourceDomain, setCloneSourceDomain] = useState("")
  const [cloneTargetDomain, setCloneTargetDomain] = useState("")
  const [newDomainInput, setNewDomainInput] = useState("")
  const [copiedClone, setCopiedClone] = useState(false)

  // 思路二：网页搬家 - 接收端状态
  const [receiveLoading, setReceiveLoading] = useState(false)
  const [receiveCode, setReceiveCode] = useState("")
  const [receiveIp, setReceiveIp] = useState("")
  const [copiedCode, setCopiedCode] = useState(false)

  // 思路二：网页搬家 - 发起端状态
  const [targetUrl, setTargetUrl] = useState("")
  const [pushCode, setPushCode] = useState("")
  const [pushNewDomain, setPushNewDomain] = useState("")
  const [pushing, setPushing] = useState(false)
  const [pushSuccessResult, setPushSuccessResult] = useState<any | null>(null)

  // 打开弹窗时，如果思路一为空，自动请求一次克隆指令
  useEffect(() => {
    if (open && !cloneCmd && !cloneLoading) {
      generateCloneCommand()
    }
  }, [open])

  // 生成思路一克隆命令 (支持可选新域名或新 IP)
  const generateCloneCommand = async (customTargetDomain?: string) => {
    setCloneLoading(true)
    const dom = customTargetDomain !== undefined ? customTargetDomain.trim() : newDomainInput.trim()
    try {
      const q = dom ? `?target_domain=${encodeURIComponent(dom)}` : ""
      const res = await fetch(`/api/proxy/migration/clone-token${q}`).then((r) => r.json())
      if (res.ok) {
        setCloneCmd(res.clone_cmd)
        setCloneSourceDomain(res.source_domain)
        setCloneTargetDomain(res.target_domain || res.source_domain)
      } else {
        toast.error(res.error || "生成克隆凭据失败")
      }
    } catch (e: any) {
      toast.error("网络请求异常: " + e.message)
    } finally {
      setCloneLoading(false)
    }
  }

  // 生成思路二接收码
  const generateReceiveCode = async () => {
    setReceiveLoading(true)
    try {
      const res = await fetch("/api/proxy/migration/prepare-receive", {
        method: "POST",
      }).then((r) => r.json())
      if (res.ok) {
        setReceiveCode(res.receive_code)
        setReceiveIp(res.public_ip)
        toast.success("搬家连接码已生成，15分钟内有效！")
      } else {
        toast.error(res.message || "生成连接码失败")
      }
    } catch (e: any) {
      toast.error("网络请求异常: " + e.message)
    } finally {
      setReceiveLoading(false)
    }
  }

  // 发起纯网页端搬家 (支持可选新域名或新 IP)
  const handlePushMigration = async () => {
    if (!targetUrl.trim()) {
      toast.error("请输入新服务器的 IP 地址或访问 URL")
      return
    }
    if (!pushCode.trim()) {
      toast.error("请输入新服务器上显示的 6 位搬家连接码")
      return
    }
    setPushing(true)
    setPushSuccessResult(null)
    try {
      const res = await fetch("/api/proxy/migration/push", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          target_url: targetUrl.trim(),
          receive_code: pushCode.trim().toUpperCase(),
          target_domain: pushNewDomain.trim() || undefined,
        }),
      }).then((r) => r.json())

      if (res.ok) {
        setPushSuccessResult(res)
        toast.success("🎉 数据已成功跨机直传并载入新服务器！")
      } else {
        toast.error(res.message || "搬家推送失败，请检查网络或连接码")
      }
    } catch (e: any) {
      toast.error("推送异常: " + e.message)
    } finally {
      setPushing(false)
    }
  }

  const isInputIp = isIpAddress(newDomainInput.trim())
  const isSourceIp = isIpAddress(cloneSourceDomain)
  const isTargetIp = newDomainInput.trim() ? isInputIp : isSourceIp
  const isChangingDomain = Boolean(newDomainInput.trim() && newDomainInput.trim() !== cloneSourceDomain)

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <div className="rounded-lg bg-primary/10 p-2 text-primary">
              <Truck className="size-5" />
            </div>
            <div>
              <DialogTitle className="text-lg font-bold flex items-center gap-2">
                跨机平滑搬家与克隆中心
                <Badge variant="secondary" className="text-xs bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-none">
                  纯 IP / 同域名 / 换域名全兼容
                </Badge>
              </DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground mt-0.5">
                支持全新空白机一键终端克隆，或两台已安装面板间纯网页直连秒级搬迁
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        {/* 顶部标签切换 */}
        <div className="grid grid-cols-2 gap-2 p-1 bg-muted/60 rounded-xl mt-1">
          <button
            onClick={() => setActiveTab("clone")}
            className={`flex items-center justify-center gap-2 py-2 px-3 text-xs font-medium rounded-lg transition-all ${
              activeTab === "clone"
                ? "bg-background text-foreground shadow-sm font-semibold"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <Terminal className="size-3.5 text-primary" />
            <span>思路一：全新机一键克隆安装</span>
            <Badge variant="outline" className="text-[10px] px-1 py-0 h-4 border-primary/30 text-primary">
              推荐
            </Badge>
          </button>
          <button
            onClick={() => setActiveTab("push")}
            className={`flex items-center justify-center gap-2 py-2 px-3 text-xs font-medium rounded-lg transition-all ${
              activeTab === "push"
                ? "bg-background text-foreground shadow-sm font-semibold"
                : "text-muted-foreground hover:text-foreground"
            }`}
          >
            <ArrowRightLeft className="size-3.5 text-blue-500" />
            <span>思路二：纯网页端一键跨机搬家</span>
          </button>
        </div>

        {/* 内容区域：思路一 (一键克隆安装) */}
        {activeTab === "clone" && (
          <div className="space-y-4 pt-1">
            <div className="rounded-xl border border-border/60 bg-card p-4 space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <Zap className="size-4 text-amber-500" />
                  <span className="text-sm font-semibold">全新 VPS 终端全自动克隆指令</span>
                </div>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-7 text-xs text-muted-foreground hover:text-foreground"
                  disabled={cloneLoading}
                  onClick={() => generateCloneCommand()}
                >
                  <RefreshCw className={`mr-1 size-3 ${cloneLoading ? "animate-spin" : ""}`} />
                  重新生成
                </Button>
              </div>

              {/* 域名或 IP 配置项 */}
              <div className="rounded-lg border border-border/80 bg-muted/30 p-3 space-y-2">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
                  <div className="space-y-0.5">
                    <Label className="text-xs font-medium flex items-center gap-1.5">
                      <span>新主控计划使用的域名或公网 IP（可选）</span>
                      {isTargetIp ? (
                        <Badge variant="secondary" className="text-[10px] bg-amber-500/15 text-amber-600 dark:text-amber-400">
                          ⚡ 纯 IP 模式 (免 DNS)
                        </Badge>
                      ) : isChangingDomain ? (
                        <Badge variant="secondary" className="text-[10px] bg-purple-500/15 text-purple-600 dark:text-purple-400">
                          🌐 域名模式 (自动 SSL)
                        </Badge>
                      ) : (
                        <Badge variant="outline" className="text-[10px] text-muted-foreground">
                          🔄 保持原域名无感接管
                        </Badge>
                      )}
                    </Label>
                    <p className="text-[11px] text-muted-foreground">
                      若新 VPS 使用新域名（如 b.com）或无域名的纯 IP（如 154.22.100.88），在此填入；留空则自动根据当前面板模式智能继承。
                    </p>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    <Input
                      placeholder={cloneSourceDomain ? `如: ${cloneSourceDomain} 或新域名/IP` : "如: b.com 或 IP (留空继承)"}
                      value={newDomainInput}
                      onChange={(e) => setNewDomainInput(e.target.value)}
                      onBlur={() => generateCloneCommand()}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") {
                          generateCloneCommand()
                        }
                      }}
                      className="h-7 text-xs w-48 font-mono"
                    />
                    <Button
                      size="sm"
                      variant="outline"
                      className="h-7 text-xs px-2.5"
                      onClick={() => generateCloneCommand()}
                      disabled={cloneLoading}
                    >
                      更新
                    </Button>
                  </div>
                </div>
              </div>

              <p className="text-xs text-muted-foreground leading-relaxed">
                无需在新服务器预先安装任何环境！在新买的 Linux VPS 终端中直接粘贴执行以下命令，脚本将自动配置基础环境、无损镜像拉取当前面板的所有数据、证书配置并自动启动：
              </p>

              <div className="relative group">
                <pre className="font-mono text-xs bg-muted/80 p-3 rounded-lg border border-border/80 overflow-x-auto select-all text-foreground/90 whitespace-pre-wrap break-all leading-5">
                  {cloneCmd || "正在生成安全克隆指令..."}
                </pre>
                <Button
                  size="sm"
                  variant="secondary"
                  className="absolute top-2 right-2 h-7 text-xs shadow-sm bg-background/80 backdrop-blur hover:bg-background cursor-pointer"
                  onClick={() => {
                    if (cloneCmd) {
                      copyToClipboard(cloneCmd)
                      setCopiedClone(true)
                      toast.success("克隆指令已复制到剪贴板！")
                      setTimeout(() => setCopiedClone(false), 2000)
                    }
                  }}
                >
                  {copiedClone ? (
                    <>
                      <Check className="mr-1 size-3 text-emerald-500" />
                      已复制
                    </>
                  ) : (
                    <>
                      <Copy className="mr-1 size-3" />
                      一键复制
                    </>
                  )}
                </Button>
              </div>

              <div className="flex items-center justify-between text-[11px] text-muted-foreground pt-1">
                <span>⏱️ 指令凭据有效期为 30 分钟，过期可重新生成</span>
                <span className="font-mono text-primary">
                  目标主控：{cloneTargetDomain || cloneSourceDomain || "当前面板"}
                  {isChangingDomain && ` (原: ${cloneSourceDomain})`}
                </span>
              </div>
            </div>

            {/* 三大场景的平滑过渡指南 */}
            <div className="rounded-xl border border-muted bg-muted/30 p-4 space-y-3">
              <h4 className="text-xs font-semibold text-foreground flex items-center gap-1.5">
                <Sparkles className="size-3.5 text-amber-500" />
                {isTargetIp
                  ? "⚡ 纯 IP 模式（无域名）极速接入指引："
                  : isChangingDomain
                  ? "🌐 换服务器 + 换域名场景的极简接入指引："
                  : "🔄 换服务器（保持原域名）小白接入指引："}
              </h4>

              {isTargetIp ? (
                <div className="grid gap-2 text-xs text-muted-foreground">
                  <div className="flex items-start gap-2">
                    <span className="flex size-4.5 shrink-0 items-center justify-center rounded-full bg-amber-500/20 text-amber-600 dark:text-amber-400 text-[10px] font-bold">1</span>
                    <span>复制上方指令，在新购买的 Linux VPS 终端中以 <code className="text-foreground">root</code> 用户直接运行，脚本全自动安装主控并配置 HTTP 纯 IP 模式。</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="flex size-4.5 shrink-0 items-center justify-center rounded-full bg-amber-500/20 text-amber-600 dark:text-amber-400 text-[10px] font-bold">2</span>
                    <span><strong>完全无需任何 DNS 解析</strong>！等待约 1 分钟后，在浏览器直接访问 <code className="text-foreground">http://新服务器IP/admin</code> 即可登录新后台。</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="flex size-4.5 shrink-0 items-center justify-center rounded-full bg-amber-500/20 text-amber-600 dark:text-amber-400 text-[10px] font-bold">3</span>
                    <span>
                      <strong className="text-foreground">子服务器节点对接：</strong>由于没有域名自动切换，登录新后台后在「服务器」列表点击复制对接指令并在各服务器重新执行（密钥 Token 不变，秒级上线）。
                    </span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="flex size-4.5 shrink-0 items-center justify-center rounded-full bg-amber-500/20 text-amber-600 dark:text-amber-400 text-[10px] font-bold">4</span>
                    <span>
                      <strong className="text-foreground">客户端用户更新：</strong>用户订阅链接已自动调整为新机器 IP，客户端点击“更新订阅”即可正常使用！
                    </span>
                  </div>
                </div>
              ) : isChangingDomain ? (
                <div className="grid gap-2 text-xs text-muted-foreground">
                  <div className="flex items-start gap-2">
                    <span className="flex size-4.5 shrink-0 items-center justify-center rounded-full bg-purple-500/20 text-purple-600 dark:text-purple-400 text-[10px] font-bold">1</span>
                    <span>复制上方指令在新 VPS 的 root 终端执行，脚本将自动配置环境并绑定新域名 <strong className="text-foreground">{cloneTargetDomain}</strong>。</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="flex size-4.5 shrink-0 items-center justify-center rounded-full bg-purple-500/20 text-purple-600 dark:text-purple-400 text-[10px] font-bold">2</span>
                    <span>前往 DNS 解析后台，将新域名 <strong className="text-foreground">{cloneTargetDomain}</strong> 的 A 记录指向新服务器公网 IP。</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="flex size-4.5 shrink-0 items-center justify-center rounded-full bg-purple-500/20 text-purple-600 dark:text-purple-400 text-[10px] font-bold">3</span>
                    <span>
                      <strong className="text-foreground">子服务器节点重连：</strong>由于主控域名变更，登录新后台后在「服务器」列表点击复制对接指令并在各服务器重新执行（节点密钥 Token 完全不变，秒级重连上线）。
                    </span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="flex size-4.5 shrink-0 items-center justify-center rounded-full bg-purple-500/20 text-purple-600 dark:text-purple-400 text-[10px] font-bold">4</span>
                    <span>
                      <strong className="text-foreground">客户端用户更新：</strong>用户订阅链接已自动变更为新域名，客户端点击“更新订阅”即可正常享受服务！
                    </span>
                  </div>
                  <div className="mt-1 p-2 rounded-lg bg-emerald-500/10 border border-emerald-500/20 text-[11px] text-emerald-700 dark:text-emerald-300">
                    💡 <strong>双域名平滑过渡神技：</strong>若原域名 {cloneSourceDomain} 依然在您手中，只需在 DNS 将其解析（CNAME）指向新域名 {cloneTargetDomain}，新机 Caddy 会同时响应两套域名证书，子节点与客户端可 <strong>零修改无感过渡</strong>！
                  </div>
                </div>
              ) : (
                <div className="grid gap-2 text-xs text-muted-foreground">
                  <div className="flex items-start gap-2">
                    <span className="flex size-4.5 shrink-0 items-center justify-center rounded-full bg-primary/20 text-primary text-[10px] font-bold">1</span>
                    <span>复制上方指令，在新购买的 Linux VPS 终端中以 <code className="text-foreground">root</code> 用户直接回车运行。</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="flex size-4.5 shrink-0 items-center justify-center rounded-full bg-primary/20 text-primary text-[10px] font-bold">2</span>
                    <span>等待约 1 分钟，脚本全自动安装主控服务并热载入当前所有监控节点、代理用户和配置规则。</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="flex size-4.5 shrink-0 items-center justify-center rounded-full bg-primary/20 text-primary text-[10px] font-bold">3</span>
                    <span>打开域名 DNS 解析后台，将原域名 <code className="text-foreground">{cloneSourceDomain || "原域名"}</code> 的 A 记录修改指向<strong>新服务器 IP</strong>。</span>
                  </div>
                  <div className="flex items-start gap-2">
                    <span className="flex size-4.5 shrink-0 items-center justify-center rounded-full bg-primary/20 text-primary text-[10px] font-bold">4</span>
                    <span>DNS 生效后浏览器重新打开原域名登录，所有子节点自动无感重连上线，客户端订阅无需任何变更！</span>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* 内容区域：思路二 (纯网页端跨机搬家) */}
        {activeTab === "push" && (
          <div className="space-y-4 pt-1">
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* 卡片 A：我是新服务器 (接收端) */}
              <div className="rounded-xl border border-border/60 bg-card p-4 space-y-3 flex flex-col justify-between">
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <Badge variant="outline" className="bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/30">
                      接收端
                    </Badge>
                    <span className="text-sm font-semibold">我是新服务器</span>
                  </div>
                  <p className="text-xs text-muted-foreground leading-relaxed">
                    如果当前这台面板是<strong>新机器</strong>，点击下方生成 6 位搬家连接码，以便从旧服务器接收数据：
                  </p>
                </div>

                <div className="space-y-3 pt-2">
                  {receiveCode ? (
                    <div className="rounded-lg bg-emerald-500/10 border border-emerald-500/30 p-3 space-y-2 text-center">
                      <div className="text-[11px] text-muted-foreground">当前新机 6 位搬家连接码：</div>
                      <div className="font-mono text-2xl font-black tracking-wider text-emerald-600 dark:text-emerald-400 select-all">
                        {receiveCode}
                      </div>
                      <div className="text-[11px] text-muted-foreground flex items-center justify-center gap-1">
                        <span>本机公网 IP:</span>
                        <code className="text-foreground font-semibold">{receiveIp || "自动识别"}</code>
                      </div>
                      <Button
                        size="sm"
                        variant="secondary"
                        className="w-full h-7 text-xs mt-1 cursor-pointer"
                        onClick={() => {
                          copyToClipboard(receiveCode)
                          setCopiedCode(true)
                          toast.success("连接码已复制")
                          setTimeout(() => setCopiedCode(false), 2000)
                        }}
                      >
                        {copiedCode ? <Check className="mr-1 size-3 text-emerald-500" /> : <Copy className="mr-1 size-3" />}
                        复制连接码
                      </Button>
                    </div>
                  ) : (
                    <div className="rounded-lg bg-muted/40 border border-dashed border-border/80 p-5 text-center text-xs text-muted-foreground">
                      尚未生成连接码
                    </div>
                  )}

                  <Button
                    size="sm"
                    variant={receiveCode ? "outline" : "default"}
                    className="w-full text-xs cursor-pointer"
                    disabled={receiveLoading}
                    onClick={generateReceiveCode}
                  >
                    <RefreshCw className={`mr-1 size-3 ${receiveLoading ? "animate-spin" : ""}`} />
                    {receiveCode ? "刷新重置连接码" : "生成 6 位搬家连接码"}
                  </Button>
                </div>
              </div>

              {/* 卡片 B：我是旧服务器 (发起端) */}
              <div className="rounded-xl border border-border/60 bg-card p-4 space-y-3 flex flex-col justify-between">
                <div>
                  <div className="flex items-center gap-2 mb-2">
                    <Badge variant="outline" className="bg-blue-500/10 text-blue-600 dark:text-blue-400 border-blue-500/30">
                      发起端
                    </Badge>
                    <span className="text-sm font-semibold">我是旧服务器</span>
                  </div>
                  <p className="text-xs text-muted-foreground leading-relaxed">
                    如果当前这台面板是<strong>旧机器</strong>，在此填入新服务器的 IP 及接收端连接码，点击立即传输：
                  </p>
                </div>

                <div className="space-y-2.5 pt-1">
                  <div className="space-y-1">
                    <Label className="text-xs">新服务器 IP 或访问地址</Label>
                    <Input
                      placeholder="例如: 154.22.100.88 或 域名"
                      value={targetUrl}
                      onChange={(e) => setTargetUrl(e.target.value)}
                      className="h-8 text-xs font-mono"
                    />
                  </div>

                  <div className="space-y-1">
                    <Label className="text-xs">新服务器 6 位搬家连接码</Label>
                    <Input
                      placeholder="例如: MIG-8F3A"
                      value={pushCode}
                      onChange={(e) => setPushCode(e.target.value.toUpperCase())}
                      className="h-8 text-xs font-mono tracking-wider"
                    />
                  </div>

                  <div className="space-y-1">
                    <Label className="text-xs">新服务器计划绑定域名 (可选)</Label>
                    <Input
                      placeholder="例如: b.com (留空则默认继承当前域名)"
                      value={pushNewDomain}
                      onChange={(e) => setPushNewDomain(e.target.value)}
                      className="h-8 text-xs font-mono"
                    />
                  </div>

                  <Button
                    size="sm"
                    className="w-full text-xs bg-blue-600 hover:bg-blue-700 text-white font-medium cursor-pointer"
                    disabled={pushing || !targetUrl || !pushCode}
                    onClick={handlePushMigration}
                  >
                    {pushing ? (
                      <>
                        <RefreshCw className="mr-1 size-3 animate-spin" />
                        正在打包并直传至新服务器…
                      </>
                    ) : (
                      <>
                        <Truck className="mr-1 size-3" />
                        立即打包搬家至新服务器
                      </>
                    )}
                  </Button>
                </div>
              </div>
            </div>

            {/* 搬迁推送成功提示卡片 */}
            {pushSuccessResult && (
              <div className="rounded-xl border border-emerald-500/30 bg-emerald-500/10 p-4 space-y-2">
                <div className="flex items-center gap-2 text-emerald-600 dark:text-emerald-400 font-bold text-sm">
                  <Check className="size-4" />
                  <span>搬家数据直传并装载成功！</span>
                </div>
                <p className="text-xs text-muted-foreground leading-relaxed">
                  系统已成功将数据库完整快照（含全部节点密钥、用户订阅、分流规则）写入新服务器并自动启动服务。
                </p>
                {pushSuccessResult.stats && (
                  <div className="grid grid-cols-3 gap-2 pt-1 text-center">
                    <div className="bg-background/60 p-2 rounded-lg border border-emerald-500/20">
                      <div className="text-[10px] text-muted-foreground">已迁移子节点</div>
                      <div className="text-sm font-bold text-emerald-600 dark:text-emerald-400">{pushSuccessResult.stats.node_count ?? 0} 个</div>
                    </div>
                    <div className="bg-background/60 p-2 rounded-lg border border-emerald-500/20">
                      <div className="text-[10px] text-muted-foreground">已迁移用户</div>
                      <div className="text-sm font-bold text-emerald-600 dark:text-emerald-400">{pushSuccessResult.stats.user_count ?? 0} 个</div>
                    </div>
                    <div className="bg-background/60 p-2 rounded-lg border border-emerald-500/20">
                      <div className="text-[10px] text-muted-foreground">已迁移规则</div>
                      <div className="text-sm font-bold text-emerald-600 dark:text-emerald-400">{pushSuccessResult.stats.rule_count ?? 0} 条</div>
                    </div>
                  </div>
                )}
                <div className="text-xs text-amber-600 dark:text-amber-400 pt-1 font-medium">
                  {pushSuccessResult.target_domain && pushSuccessResult.target_domain !== pushSuccessResult.source_domain ? (
                    <span>👉 下一步：已指定新域名 <strong>{pushSuccessResult.target_domain}</strong>，请将新域名解析至新服务器 IP，并在子服务器重新运行对接指令。</span>
                  ) : (
                    <span>👉 下一步：请前往 DNS 控制台，将原域名的 A 记录修改解析至新服务器 IP 即可大功告成！</span>
                  )}
                </div>
              </div>
            )}
          </div>
        )}

        {/* 底部保障与回退说明 */}
        <div className="rounded-xl border border-border/40 bg-muted/20 p-3 text-xs text-muted-foreground space-y-1">
          <div className="flex items-center gap-1.5 font-medium text-foreground">
            <ShieldCheck className="size-3.5 text-emerald-500" />
            <span>平滑过渡与随时回退保障机制：</span>
          </div>
          <p className="leading-relaxed">
            迁移与克隆操作<strong>绝对不会修改或删除原旧服务器上的任何数据与证书</strong>。在测试新服务器期间，若想回退使用原服务器，只需在域名 DNS 解析中将 A 记录重新改回旧服务器 IP 即可秒级切回，完全无风险！
          </p>
        </div>
      </DialogContent>
    </Dialog>
  )
}

// ============================================================================
// 2. 首次登录迁移成功祝贺与接入报告弹窗 (MigrationCelebrationDialog)
// ============================================================================
export type MigrationStatus = {
  ok: boolean
  just_completed: boolean
  source_domain: string
  target_domain?: string
  source_ip: string
  completed_at: number
  current_ip: string
  node_count: number
  user_count: number
  rule_count: number
}

export function MigrationCelebrationDialog({
  status,
  onDismiss,
}: {
  status: MigrationStatus | null
  onDismiss: () => void
}) {
  const [closing, setClosing] = useState(false)

  if (!status || !status.just_completed) return null

  const isTargetIp = Boolean(
    (status.target_domain && isIpAddress(status.target_domain)) ||
    (!status.target_domain && isIpAddress(status.source_domain)) ||
    (!status.target_domain && !status.source_domain)
  )

  const isDomainChanged = Boolean(
    !isTargetIp &&
    status.target_domain &&
    status.source_domain &&
    status.target_domain !== status.source_domain
  )

  const handleConfirm = async () => {
    setClosing(true)
    try {
      await fetch("/api/proxy/migration/dismiss", { method: "POST" })
      onDismiss()
      toast.success("迁移接管已确认，欢迎使用！")
    } catch (e: any) {
      onDismiss()
    } finally {
      setClosing(false)
    }
  }

  return (
    <Dialog open={true} onOpenChange={() => handleConfirm()}>
      <DialogContent className="max-w-lg border-emerald-500/40 shadow-2xl">
        <DialogHeader>
          <div className="flex items-center gap-2">
            <div className="rounded-xl bg-emerald-500/20 p-2.5 text-emerald-600 dark:text-emerald-400">
              <Sparkles className="size-6" />
            </div>
            <div>
              <DialogTitle className="text-lg font-bold text-foreground flex items-center gap-2">
                🎉 跨机平滑迁移成功！
                <Badge className="bg-emerald-500 text-white hover:bg-emerald-600 text-xs">
                  资产全量接管
                </Badge>
              </DialogTitle>
              <DialogDescription className="text-xs text-muted-foreground mt-0.5">
                恭喜！本服务器已成功完整载入原主控面板的所有系统资产
              </DialogDescription>
            </div>
          </div>
        </DialogHeader>

        <div className="space-y-4 pt-2">
          {/* 资产统计卡片 */}
          <div className="grid grid-cols-3 gap-2 text-center">
            <div className="rounded-xl border border-border/80 bg-card p-3 shadow-sm">
              <Server className="size-4 text-primary mx-auto mb-1" />
              <div className="text-[11px] text-muted-foreground">子服务器节点</div>
              <div className="text-lg font-black text-foreground mt-0.5">{status.node_count ?? 0} 台</div>
            </div>
            <div className="rounded-xl border border-border/80 bg-card p-3 shadow-sm">
              <Users className="size-4 text-blue-500 mx-auto mb-1" />
              <div className="text-[11px] text-muted-foreground">代理用户/订阅</div>
              <div className="text-lg font-black text-foreground mt-0.5">{status.user_count ?? 0} 个</div>
            </div>
            <div className="rounded-xl border border-border/80 bg-card p-3 shadow-sm">
              <Layers className="size-4 text-purple-500 mx-auto mb-1" />
              <div className="text-[11px] text-muted-foreground">协议分流规则</div>
              <div className="text-lg font-black text-foreground mt-0.5">{status.rule_count ?? 0} 条</div>
            </div>
          </div>

          {/* 关键接管状态提示 */}
          <div className="rounded-xl border border-border/60 bg-muted/40 p-3.5 space-y-2 text-xs">
            {isTargetIp ? (
              <>
                <div className="flex items-center justify-between text-muted-foreground">
                  <span>当前运行模式：</span>
                  <Badge variant="secondary" className="text-[10px] bg-amber-500/15 text-amber-600 dark:text-amber-400">
                    ⚡ 纯 IP 模式 (HTTP - 免 DNS)
                  </Badge>
                </div>
                <div className="flex items-center justify-between text-muted-foreground">
                  <span>面板登录地址：</span>
                  <code className="text-primary font-bold">http://{status.current_ip || "本机 IP"}/admin</code>
                </div>
                {status.source_domain && (
                  <div className="flex items-center justify-between text-muted-foreground">
                    <span>原主控地址：</span>
                    <code className="text-foreground font-semibold">{status.source_domain}</code>
                  </div>
                )}
              </>
            ) : isDomainChanged ? (
              <>
                <div className="flex items-center justify-between text-muted-foreground">
                  <span>当前新主控域名：</span>
                  <code className="text-purple-600 dark:text-purple-400 font-bold">{status.target_domain}</code>
                </div>
                <div className="flex items-center justify-between text-muted-foreground">
                  <span>原主控域名：</span>
                  <code className="text-foreground font-semibold">{status.source_domain}</code>
                </div>
              </>
            ) : (
              <div className="flex items-center justify-between text-muted-foreground">
                <span>主控域名：</span>
                <code className="text-foreground font-semibold">{status.source_domain || "未指定"}</code>
              </div>
            )}
            <div className="flex items-center justify-between text-muted-foreground">
              <span>本机当前公网 IP：</span>
              <code className="text-primary font-bold">{status.current_ip || "本机 IP"}</code>
            </div>
          </div>

          {/* 接管指引 */}
          <div className="rounded-xl border border-amber-500/30 bg-amber-500/10 p-3.5 space-y-2 text-xs">
            <div className="font-semibold text-amber-700 dark:text-amber-400 flex items-center gap-1.5">
              <span>👉 终极接入与对接确认：</span>
            </div>
            {isTargetIp ? (
              <div className="space-y-1.5 text-muted-foreground leading-relaxed">
                <p className="text-foreground font-medium">
                  ⚡ 当前已成功运行在纯 IP 模式，无需进行任何域名 DNS 解析：
                </p>
                <div className="space-y-1 text-[11px]">
                  <div>
                    1️⃣ <strong>子服务器节点</strong>：请前往「服务器」列表复制节点对接指令，在各服务器重新执行（密钥不变，秒级上线）。
                  </div>
                  <div>
                    2️⃣ <strong>客户端订阅</strong>：订阅链接已同步变更为本机 IP，客户端点击“更新订阅”即可正常享受服务！
                  </div>
                  <div>
                    3️⃣ <strong>极速访问</strong>：直接访问 <code className="text-foreground font-semibold">http://{status.current_ip}/admin</code> 管理后台。
                  </div>
                </div>
              </div>
            ) : isDomainChanged ? (
              <div className="space-y-1.5 text-muted-foreground leading-relaxed">
                <p>
                  由于主控域名已更换为 <strong className="text-foreground">{status.target_domain}</strong>：
                </p>
                <div className="space-y-1 text-[11px]">
                  <div>
                    1️⃣ <strong>子服务器节点</strong>：请前往「服务器」列表复制节点对接指令，在各服务器重新执行（密钥不变，秒级上线）。
                  </div>
                  <div>
                    2️⃣ <strong>客户端订阅</strong>：订阅链接已同步变更为新域名，客户端点击“更新订阅”即可正常享受服务！
                  </div>
                  <div className="text-emerald-600 dark:text-emerald-400 font-medium">
                    🌟 <strong>双域名免改技巧</strong>：若原域名仍可用，在 DNS 将原域名 CNAME 指向新域名，子节点与客户端可 0 改动无感过渡！
                  </div>
                </div>
              </div>
            ) : (
              <>
                <p className="text-muted-foreground leading-relaxed">
                  请确认已将原域名 <strong className="text-foreground">{status.source_domain}</strong> 的 DNS A 记录修改指向本机 IP（<strong className="text-foreground">{status.current_ip}</strong>）。
                </p>
                <div className="text-[11px] text-muted-foreground">
                  ✅ DNS 指向本机后：所有子节点探针将全自动重新上线，客户端订阅无感续享，无需任何客户端配置变更！
                </div>
              </>
            )}
          </div>

          <Button
            className="w-full bg-emerald-600 hover:bg-emerald-700 text-white font-semibold cursor-pointer"
            disabled={closing}
            onClick={handleConfirm}
          >
            {closing ? "正在确认…" : "我知道了，开始使用新面板"}
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  )
}
