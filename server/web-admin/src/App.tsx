import { useCallback, useEffect, useState } from "react"
import { Activity, AlertTriangle, ExternalLink, KeyRound, LogOut, Moon, Sun } from "lucide-react"
import { Toaster } from "sonner"

import { Admin } from "@/components/Admin"
import { Login } from "@/components/Login"
import { ChangePasswordDialog } from "@/components/ChangePasswordDialog"
import { UpdateDialog, type UpdateInfo } from "@/components/UpdateDialog"
import { UserDashboard, type UserProfile } from "@/components/UserDashboard"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { api, provisionRefusal, useNodes } from "@/lib/api"

type Me = { authed: boolean; github: boolean; site_name: string; public_page: boolean; site: string }

// `/admin` alone is not a page; it is normalised to the first section so that a
// bookmark and the OAuth redirect both resolve to a real route.
function normalise(p: string) {
  if (p === "/admin" || p === "/admin/" || p === "" || p === "/") return "/admin/overview"
  if (p === "/panel" || p === "/panel/") return "/admin/overview"
  if (p.startsWith("/panel/")) return p.replace("/panel/", "/admin/")
  if (!p.startsWith("/admin/")) return "/admin/overview"
  return p.replace(/\/$/, "") || "/admin/overview"
}

function usePath() {
  const [path, setPath] = useState(() => {
    const start = normalise(location.pathname)
    if (start !== location.pathname) history.replaceState({}, "", start + location.search)
    return start
  })
  useEffect(() => {
    const sync = () => setPath(normalise(location.pathname))
    addEventListener("popstate", sync)
    return () => removeEventListener("popstate", sync)
  }, [])
  return [
    path,
    useCallback((next: string) => {
      const to = normalise(next)
      history.pushState({}, "", to)
      setPath(to)
    }, []),
  ] as const
}

function useTheme() {
  const [dark, setDark] = useState(() => {
    const saved = localStorage.getItem("theme")
    return saved ? saved === "dark" : matchMedia("(prefers-color-scheme: dark)").matches
  })

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark)
    localStorage.setItem("theme", dark ? "dark" : "light")
    document.documentElement.classList.remove("theme-sakura")
    localStorage.removeItem("theme_style")
  }, [dark])

  return {
    dark,
    toggleTheme: () => setDark((d) => !d),
  }
}

export default function App() {
  const [path, go] = usePath()
  const { dark, toggleTheme } = useTheme()
  const [me, setMe] = useState<Me | null>(null)
  const [meError, setMeError] = useState("")
  const { nodes, admin, error, refresh } = useNodes()

  const loadMe = useCallback(() => {
    // `|| "..."` because an empty message reads as no error: api() falls back to
    // res.statusText, which HTTP/2 and HTTP/3 removed, so a bodiless 502 from a
    // proxy arrives as "". The check below would then take the loading branch and
    // the retry button would never render.
    return api<Me>("/me")
      .then((next) => { setMe(next); setMeError("") })
      .catch((e: Error) => setMeError(e.message || "网络错误"))
  }, [])
  useEffect(() => {
    loadMe()
  }, [loadMe])

  const [userProfile, setUserProfile] = useState<UserProfile | null>(null)

  const loadUserProfile = useCallback(() => {
    fetch("/api/proxy/user/me")
      .then((res) => res.json())
      .then((data) => {
        if (data.ok && data.user) {
          setUserProfile(data.user)
        }
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    if (me?.authed) {
      loadUserProfile()
    }
  }, [me?.authed, loadUserProfile])


  const [updateInfo, setUpdateInfo] = useState<UpdateInfo | null>(null)
  const [updateDialogOpen, setUpdateDialogOpen] = useState(false)
  const [changePasswordOpen, setChangePasswordOpen] = useState(false)
  const [probeUrl, setProbeUrl] = useState("")

  const loadProbeUrl = useCallback(() => {
    fetch("/api/proxy/auth/config")
      .then((r) => r.json())
      .then((d) => {
        if (d && d.probe_url) {
          setProbeUrl(d.probe_url)
        }
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    loadProbeUrl()
  }, [loadProbeUrl])

  // 自动检测系统更新 (仅管理员鉴权后执行)
  useEffect(() => {
    if (me?.authed && (!userProfile || userProfile.is_admin)) {
      fetch("/api/proxy/system/update-check")
        .then((r) => {
          if (!r.ok) throw new Error("not ok")
          return r.json()
        })
        .then((data: UpdateInfo) => {
          if (data?.ok) {
            setUpdateInfo(data)
          }
        })
        .catch(() => {
          // 后端未提供接口时，降级尝试直连 GitHub Release 获取最新版本
          fetch("https://raw.githubusercontent.com/2290145679/ProxyProbe/main/version.json")
            .then((r) => r.json())
            .then((vData) => {
              if (vData?.version) {
                setUpdateInfo({
                  ok: true,
                  current_version: "v2.5.0",
                  latest_version: vData.version,
                  has_update: vData.version !== "v2.5.0",
                  title: vData.title,
                  changelog: vData.changelog,
                  release_date: vData.release_date,
                  release_url: vData.release_url,
                })
              }
            })
            .catch(() => {})
        })
    }
  }, [me?.authed, userProfile])

  // Every frame declares its audience. The hub closes the stream when the session
  // behind it is revoked -- signed out from another device, a password change, a
  // restore -- and the reconnect returns as anonymous: the public list, with
  // private nodes absent and every admin field empty, rendered inside a panel that
  // still appears signed in. `authed` is read only at mount and after signing in,
  // so nothing else detects this. /api/me already handles signing out.
  useEffect(() => {
    if (me?.authed && admin === false) loadMe()
  }, [admin, me?.authed, loadMe])

  // Only while there is nothing else to show. Login's onDone reloads /me, so a
  // transient failure in the second after signing in would otherwise replace the
  // entire signed-in panel with a full-page error while the node list streamed
  // normally.
  if (!me) return (
    <div className="grid min-h-svh place-items-center p-6 text-sm text-muted-foreground">
      {meError ? <div className="space-y-3 text-center"><p role="alert">加载失败：{meError}</p><Button onClick={loadMe}>重试</Button></div> : "加载中…"}
    </div>
  )

  if (!me.authed) {
    return (
      <>
        <Login github={me.github} onDone={() => { loadMe(); loadUserProfile(); refresh(); go("/admin/overview") }} />
        <Toaster position="top-center" theme={dark ? "dark" : "light"} />
      </>
    )
  }

  async function signOut() {
    await api("/auth/logout", { method: "POST" }).catch(() => {})
    document.cookie = "monitor_session=; Path=/; Max-Age=0"
    location.href = "/admin"
  }

  // 普通用户登录后展示机场式用户面板
  if (userProfile && !userProfile.is_admin) {
    return (
      <>
        <UserDashboard
          user={userProfile}
          siteName={me.site_name}
          refreshUser={loadUserProfile}
          onSignOut={signOut}
          toggleTheme={toggleTheme}
          dark={dark}
        />
        <Toaster position="top-center" theme={dark ? "dark" : "light"} />
      </>
    )
  }

  const sorted = [...(nodes ?? [])].sort((a, b) => a.sort - b.sort || a.id - b.id)

  return (
    <div className="min-h-svh overflow-x-hidden w-full">
      <header className="sticky top-0 z-10 border-b bg-background/80 backdrop-blur w-full">
        <div className="mx-auto flex max-w-7xl items-center gap-2 sm:gap-3 px-3 sm:px-4 py-2.5 sm:py-3">
          {/* Logo / Site name */}
          <a href="/" className="font-semibold transition-opacity hover:opacity-70 flex items-center gap-1.5 shrink-0 text-sm sm:text-base">
            <span className="truncate max-w-[120px] sm:max-w-none">{me.site_name || "HHUB"}</span>
          </a>
          <span className="hidden sm:inline-flex text-[11px] px-2 py-0.5 rounded-full border border-primary/20 bg-primary/10 text-primary font-medium whitespace-nowrap shrink-0">
            管理后台
          </span>
          <div className="flex-1" />
          {/* 版本与在线升级入口 */}
          <Button
            variant="outline"
            size="sm"
            onClick={() => setUpdateDialogOpen(true)}
            className={`h-8 text-xs px-2 sm:px-2.5 gap-1.5 shrink-0 ${
              updateInfo?.need_migration
                ? "border-amber-500/50 bg-amber-500/15 text-amber-600 dark:text-amber-400 hover:bg-amber-500/25 shadow-xs animate-pulse"
                : updateInfo?.has_update
                ? "border-amber-500/40 bg-amber-500/10 text-amber-600 dark:text-amber-400 hover:bg-amber-500/20 shadow-xs"
                : "border-border/50 text-muted-foreground hover:text-foreground hover:bg-muted"
            }`}
            title={
              updateInfo?.need_migration
                ? "系统检测到旧版目录 /opt/monitor，点击查看【hhub migrate】一键平滑迁移指南"
                : updateInfo?.has_update
                ? `发现新版本 ${updateInfo.latest_version}，点击查看并升级`
                : `当前系统版本 ${updateInfo?.current_version || "v2.5.0"}，点击检查更新`
            }
          >
            {updateInfo?.need_migration ? (
              <>
                <AlertTriangle className="size-3.5 text-amber-500 shrink-0" />
                <span className="font-semibold text-amber-600 dark:text-amber-400 hidden sm:inline">架构待迁移</span>
                <span className="font-semibold text-amber-600 dark:text-amber-400 sm:hidden">待迁移</span>
              </>
            ) : updateInfo?.has_update ? (
              <>
                <span className="relative flex size-2 shrink-0">
                  <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-amber-400 opacity-75" />
                  <span className="relative inline-flex rounded-full size-2 bg-amber-500" />
                </span>
                <span className="font-medium hidden sm:inline">新版本</span>
                <span className="font-mono font-bold">{updateInfo.latest_version}</span>
              </>
            ) : (
              <>
                <span className="font-mono text-[11px] font-medium">{updateInfo?.current_version || "v2.5.0"}</span>
                <span className="hidden sm:inline text-[11px] text-muted-foreground">检查更新</span>
              </>
            )}
          </Button>
          {Boolean(probeUrl && probeUrl.trim()) && (
            <Button variant="outline" size="sm" asChild className="shrink-0 px-2.5 sm:px-3 text-xs h-8 border-emerald-500/30 text-emerald-600 dark:text-emerald-400 bg-emerald-500/10 hover:bg-emerald-500/20">
              <a href={probeUrl.trim()} target="_blank" rel="noopener noreferrer" title="直达探针监控大屏与服务状态">
                <Activity className="size-3.5 shrink-0 animate-pulse text-emerald-500" />
                <span className="hidden sm:inline ml-1.5 font-medium">探针监控</span>
                <ExternalLink className="size-3 ml-1 opacity-70 shrink-0" />
              </a>
            </Button>
          )}
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setChangePasswordOpen(true)}
            className="shrink-0 size-8 text-muted-foreground hover:text-foreground cursor-pointer"
            title="修改管理员密码"
          >
            <KeyRound className="size-4" />
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={toggleTheme}
            className="shrink-0 size-8"
            title={dark ? "切换为浅色" : "切换为深色"}
          >
            {dark ? <Sun className="size-4" /> : <Moon className="size-4" />}
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={signOut}
            className="shrink-0 size-8 text-muted-foreground hover:text-foreground"
            title="退出登录"
          >
            <LogOut className="size-4" />
          </Button>
        </div>
      </header>

      <UpdateDialog
        open={updateDialogOpen}
        onOpenChange={setUpdateDialogOpen}
        updateInfo={updateInfo}
        onUpdateInfoChange={setUpdateInfo}
      />

      <ChangePasswordDialog
        open={changePasswordOpen}
        onOpenChange={setChangePasswordOpen}
      />

      <main className="mx-auto max-w-7xl space-y-5 px-4 py-6">
        {error && <p className="text-sm text-destructive">{error}</p>}
        {nodes === null ? (
          <Skeleton className="h-64" />
        ) : (
          <Admin
            path={path}
            go={go}
            nodes={sorted}
            refresh={refresh}
            // The hub's own public URL rather than this browser's address: the
            // panel is frequently reached over a loopback port behind a proxy,
            // while the install command and OAuth callback need the real one.
            site={me.site || location.origin}
            // Why this page cannot add nodes, measured by the rule the hub applies
            // to the `Origin` it receives; empty when it can.
            refusal={provisionRefusal(location.origin, me.site)}
            updateInfo={updateInfo}
            onOpenUpdateDialog={() => setUpdateDialogOpen(true)}
            probeUrl={probeUrl}
            onProbeUrlChange={setProbeUrl}
          />
        )}
      </main>

      <Toaster position="top-center" theme={dark ? "dark" : "light"} />
    </div>
  )
}
