import { useEffect, useState } from "react"
import {
  ArrowRight,
  Check,
  CheckCircle2,
  Copy,
  ExternalLink,
  Flame,
  RefreshCw,
  Rocket,
  Sparkles,
  Terminal,
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

export type UpdateInfo = {
  ok: boolean
  current_version: string
  latest_version: string
  has_update: boolean
  title?: string
  changelog?: string[]
  release_date?: string
  release_url?: string
}

export function UpdateDialog({
  open,
  onOpenChange,
  updateInfo: initialInfo,
  onUpdateInfoChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  updateInfo: UpdateInfo | null
  onUpdateInfoChange?: (info: UpdateInfo) => void
}) {
  const [info, setInfo] = useState<UpdateInfo | null>(initialInfo)
  const [checking, setChecking] = useState(false)
  const [upgrading, setUpgrading] = useState(false)
  const [progressMsg, setProgressMsg] = useState("")

  useEffect(() => {
    setInfo(initialInfo)
  }, [initialInfo])

  // 手动/自动检查更新
  const handleCheck = async (force = true, notifyToast = true) => {
    setChecking(true)
    try {
      const endpoints = [
        `/api/proxy/system/update-check${force ? "?force=1" : ""}`,
        `/api/proxy/update-check${force ? "?force=1" : ""}`,
        `/api/system/update-check${force ? "?force=1" : ""}`,
      ]
      let fetchedData: UpdateInfo | null = null
      for (const ep of endpoints) {
        try {
          const res = await fetch(ep)
          if (res.status === 200) {
            const data: UpdateInfo = await res.json()
            if (data?.ok) {
              fetchedData = data
              break
            }
          }
        } catch {
          // ignore and fallback
        }
      }

      // 如果后端接口未能成功返回（例如旧版实例未包含该接口），尝试前端直连 GitHub Release version.json
      if (!fetchedData) {
        try {
          const ghRes = await fetch("https://raw.githubusercontent.com/2290145679/ProxyProbe-Release/main/version.json")
          if (ghRes.ok) {
            const vData = await ghRes.json()
            const cur = info?.current_version || "v2.5.0"
            const latest = vData.version || cur
            fetchedData = {
              ok: true,
              current_version: cur,
              latest_version: latest,
              has_update: latest !== cur,
              title: vData.title,
              changelog: vData.changelog,
              release_date: vData.release_date,
              release_url: vData.release_url,
            }
          }
        } catch {
          // ignore
        }
      }

      if (fetchedData && fetchedData.ok) {
        setInfo(fetchedData)
        if (onUpdateInfoChange) onUpdateInfoChange(fetchedData)
        if (notifyToast) {
          if (fetchedData.has_update) {
            toast.info(`🎉 发现新版本：${fetchedData.latest_version}！`)
          } else {
            toast.success(`当前已是最新版本 (${fetchedData.current_version})，无需更新。`)
          }
        }
      } else {
        if (notifyToast) toast.error("检查更新失败，请确认服务器或浏览器网络是否可访问 GitHub")
      }
    } catch {
      if (notifyToast) toast.error("检查更新失败，请确认网络连接")
    } finally {
      setChecking(false)
    }
  }

  // 弹窗打开时自动核验最新版本
  useEffect(() => {
    if (open) {
      handleCheck(true, false)
    }
  }, [open])

  // 触发在线无损热升级
  const handleUpgrade = async () => {
    if (!confirm(`确定要立即将 ProxyProbe 升级到最新版本【${info?.latest_version}】吗？升级过程全自动无损，不会丢失任何配置和数据。`)) {
      return
    }

    setUpgrading(true)
    setProgressMsg("正在向后台提交热升级指令...")

    const upgradeEndpoints = [
      "/api/proxy/system/upgrade",
      "/api/proxy/upgrade",
      "/api/system/upgrade",
    ]

    let isSuccess = false
    let is404 = false
    let is401 = false
    let lastErrorMsg = ""

    for (const ep of upgradeEndpoints) {
      try {
        const res = await fetch(ep, { method: "POST" })
        if (res.status === 404) {
          is404 = true
          continue
        }
        if (res.status === 401) {
          is401 = true
          break
        }
        const data = await res.json()
        if (data.ok) {
          isSuccess = true
          break
        } else {
          lastErrorMsg = data.error || ""
        }
      } catch (e: any) {
        lastErrorMsg = e?.message || ""
      }
    }

    if (isSuccess) {
      setProgressMsg("正在后台拉取最新二进制与前端资源并重启服务，请稍候约 8 秒...")
      let countdown = 8
      const timer = setInterval(() => {
        countdown -= 1
        if (countdown > 0) {
          setProgressMsg(`正在重启服务并同步资源，剩余 ${countdown} 秒即将刷新页面...`)
        } else {
          clearInterval(timer)
          setProgressMsg("升级完成！正在重新载入控制面板...")
          setTimeout(() => {
            window.location.reload()
          }, 1000)
        }
      }, 1000)
    } else {
      setUpgrading(false)
      if (is401) {
        toast.error("未授权：请先登录管理员账号后再执行系统升级")
      } else if (is404) {
        toast.error(
          "当前运行的旧版后端程序尚未集成免终端热升级接口（返回 404 Not Found）。请在 SSH 终端执行一次【hhub upgrade】完成初始化升级！",
          { duration: 8000 }
        )
      } else {
        toast.error(lastErrorMsg || "启动升级失败，建议在 SSH 终端执行【hhub upgrade】进行升级")
      }
    }
  }

  const curVer = info?.current_version || "v2.5.3"
  const latestVer = info?.latest_version || curVer
  const hasUpdate = !!info?.has_update

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="w-[94vw] max-w-md sm:max-w-lg p-4 sm:p-6 space-y-4 max-h-[88vh] overflow-y-auto overflow-x-hidden">
        <DialogHeader>
          <DialogTitle className="text-base sm:text-lg font-bold flex items-center justify-between">
            <span className="flex items-center gap-2">
              <Sparkles className="size-5 text-amber-500" />
              <span>系统版本与更新检测</span>
            </span>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => handleCheck(true)}
              disabled={checking || upgrading}
              className="size-8"
              title="强制重新检查更新"
            >
              <RefreshCw className={`size-3.5 ${checking ? "animate-spin text-primary" : ""}`} />
            </Button>
          </DialogTitle>
          <DialogDescription className="text-xs">
            自动比对 GitHub 官方发行仓库，支持一键无损热升级或通过终端快速升级。
          </DialogDescription>
        </DialogHeader>

        {/* 版本对比展示卡片 */}
        <div className="rounded-xl border bg-muted/20 p-4 space-y-3">
          <div className="flex items-center justify-between">
            <div className="space-y-0.5">
              <span className="text-[11px] text-muted-foreground">当前运行版本</span>
              <p className="font-mono text-sm font-semibold">{curVer}</p>
            </div>

            <ArrowRight className="size-4 text-muted-foreground shrink-0" />

            <div className="space-y-0.5 text-right">
              <div className="flex items-center justify-end gap-1.5">
                <span className="text-[11px] text-muted-foreground">最新可用版本</span>
                {hasUpdate ? (
                  <Badge className="bg-amber-500 hover:bg-amber-600 text-white text-[10px] px-1.5 py-0 font-medium">
                    有更新
                  </Badge>
                ) : (
                  <Badge variant="outline" className="text-[10px] px-1.5 py-0 text-emerald-600 border-emerald-500/30">
                    已是最新
                  </Badge>
                )}
              </div>
              <p className="font-mono text-sm font-semibold text-primary">{latestVer}</p>
            </div>
          </div>

          {info?.release_date && (
            <div className="text-[11px] text-muted-foreground border-t border-border/50 pt-2 flex items-center justify-between">
              <span>发行日期：{info.release_date}</span>
              {info.release_url && (
                <a
                  href={info.release_url}
                  target="_blank"
                  rel="noreferrer"
                  className="text-primary hover:underline flex items-center gap-1"
                >
                  <span>查看 Release 仓库</span>
                  <ExternalLink className="size-3" />
                </a>
              )}
            </div>
          )}
        </div>

        {/* 更新日志详情 */}
        {hasUpdate && info?.changelog && info.changelog.length > 0 && (
          <div className="rounded-lg border bg-card p-3 space-y-2">
            <span className="text-xs font-semibold flex items-center gap-1.5 text-foreground">
              <Flame className="size-3.5 text-amber-500" />
              <span>新版本核心特性：</span>
            </span>
            <ul className="space-y-1.5 text-xs text-muted-foreground">
              {info.changelog.map((item, idx) => (
                <li key={idx} className="flex items-start gap-2">
                  <CheckCircle2 className="size-3.5 text-emerald-500 shrink-0 mt-0.5" />
                  <span className="leading-relaxed">{item}</span>
                </li>
              ))}
            </ul>
          </div>
        )}

        {/* 正在升级进度状态提示 */}
        {upgrading && (
          <div className="rounded-lg border border-primary/30 bg-primary/10 p-3 text-xs text-primary space-y-2">
            <div className="flex items-center gap-2 font-semibold">
              <RefreshCw className="size-4 animate-spin shrink-0" />
              <span>正在执行平滑热升级…</span>
            </div>
            <p className="text-muted-foreground text-[11px]">{progressMsg}</p>
          </div>
        )}

        {/* 操作区 */}
        <div className="space-y-2.5 pt-1">
          {hasUpdate ? (
            <div className="space-y-2">
              <Button
                onClick={handleUpgrade}
                disabled={upgrading}
                className="w-full h-9 text-xs gap-1.5 bg-primary text-primary-foreground hover:bg-primary/90 shadow-sm"
              >
                {upgrading ? (
                  <RefreshCw className="size-3.5 animate-spin" />
                ) : (
                  <Rocket className="size-3.5" />
                )}
                <span>立即一键在线热升级 (免命令行)</span>
              </Button>

              <div className="rounded-md border bg-muted/40 p-2.5 text-[11px] space-y-1">
                <div className="flex items-center justify-between text-muted-foreground">
                  <span className="flex items-center gap-1 font-mono">
                    <Terminal className="size-3" />
                    <span>亦可在 SSH 终端执行命令升级：</span>
                  </span>
                  <button
                    type="button"
                    onClick={async () => {
                      const ok = await copyToClipboard("hhub upgrade")
                      if (ok) toast.success("已复制升级命令")
                    }}
                    className="text-primary hover:underline flex items-center gap-0.5"
                  >
                    <Copy className="size-3" /> 复制
                  </button>
                </div>
                <code className="block font-mono bg-background/80 px-2 py-1 rounded text-foreground">
                  hhub upgrade
                </code>
              </div>
            </div>
          ) : (
            <div className="flex flex-col sm:flex-row items-center justify-between gap-2 pt-1">
              <div className="flex items-center gap-1.5 text-xs text-emerald-600 dark:text-emerald-400">
                <Check className="size-4" />
                <span>恭喜，您的系统已是最新版本！无需升级。</span>
              </div>
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleCheck(true)}
                disabled={checking}
                className="h-8 text-xs gap-1 self-stretch sm:self-auto"
              >
                <RefreshCw className={`size-3 ${checking ? "animate-spin" : ""}`} />
                <span>立即重新核验</span>
              </Button>
            </div>
          )}
        </div>
      </DialogContent>
    </Dialog>
  )
}
