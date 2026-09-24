import { useCallback, useEffect, useState } from "react"
import { ExternalLink, LogOut, Moon, Palette, Sun } from "lucide-react"
import { Toaster } from "sonner"

import { Admin } from "@/components/Admin"
import { Login } from "@/components/Login"
import { ThemeSettingsDialog } from "@/components/ThemeSettingsDialog"
import { UserDashboard, type UserProfile } from "@/components/UserDashboard"
import { Button } from "@/components/ui/button"
import { Skeleton } from "@/components/ui/skeleton"
import { api, provisionRefusal, useNodes } from "@/lib/api"

type Me = { authed: boolean; github: boolean; site_name: string; public_page: boolean; site: string }

// `/admin` alone is not a page; it is normalised to the first section so that a
// bookmark and the OAuth redirect both resolve to a real route.
function normalise(p: string) {
  return p === "/admin" || p === "/admin/" ? "/admin/nodes" : p.replace(/\/$/, "") || "/admin/nodes"
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
  const [themeStyle, setThemeStyleState] = useState<"default" | "sakura">(() => {
    return (localStorage.getItem("theme_style") as "default" | "sakura") || "default"
  })

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark)
    localStorage.setItem("theme", dark ? "dark" : "light")
  }, [dark])

  useEffect(() => {
    document.documentElement.classList.toggle("theme-sakura", themeStyle === "sakura")
    localStorage.setItem("theme_style", themeStyle)
  }, [themeStyle])

  const setThemeStyle = useCallback((style: "default" | "sakura", syncRemote = true) => {
    setThemeStyleState(style)
    if (syncRemote) {
      fetch("/api/proxy/theme", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ theme_style: style }),
      }).catch(() => {})
    }
  }, [])

  return {
    dark,
    toggleTheme: () => setDark((d) => !d),
    themeStyle,
    setThemeStyle,
  }
}

export default function App() {
  const [path, go] = usePath()
  const { dark, toggleTheme, themeStyle, setThemeStyle } = useTheme()
  const [themeDialogOpen, setThemeDialogOpen] = useState(false)
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

  // 同步用户或管理员的主题设置 (跟随账号走)
  useEffect(() => {
    if (userProfile?.theme_style) {
      setThemeStyle(userProfile.theme_style, false)
    }
  }, [userProfile?.theme_style, setThemeStyle])

  useEffect(() => {
    if (me?.authed && (!userProfile || userProfile.is_admin)) {
      fetch("/api/proxy/theme")
        .then((r) => r.json())
        .then((data) => {
          if (data?.ok && data.theme_style) {
            setThemeStyle(data.theme_style, false)
          }
        })
        .catch(() => {})
    }
  }, [me?.authed, userProfile, setThemeStyle])

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
        <Login github={me.github} onDone={() => { loadMe(); loadUserProfile(); refresh(); go("/admin/nodes") }} />
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
          themeStyle={themeStyle}
          onThemeStyleChange={setThemeStyle}
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
            {themeStyle === "sakura" && <span className="text-base select-none">🌸</span>}
            <span className="truncate max-w-[120px] sm:max-w-none">{me.site_name || "HHUB"}</span>
          </a>
          <span className="hidden sm:inline-flex text-[11px] px-2 py-0.5 rounded-full border border-primary/20 bg-primary/10 text-primary font-medium whitespace-nowrap shrink-0">
            管理后台
          </span>
          <div className="flex-1" />
          <Button variant="ghost" size="sm" asChild className="shrink-0 px-2 sm:px-3 text-xs h-8">
            <a href="/" title="状态面板">
              <ExternalLink className="size-3.5 shrink-0" />
              <span className="hidden sm:inline ml-1">状态面板</span>
            </a>
          </Button>
          <Button
            variant="ghost"
            size="icon"
            onClick={() => setThemeDialogOpen(true)}
            className="shrink-0 size-8"
            title="主题风格设置"
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

      <ThemeSettingsDialog
        open={themeDialogOpen}
        onOpenChange={setThemeDialogOpen}
        themeStyle={themeStyle}
        onThemeStyleChange={setThemeStyle}
        dark={dark}
        onToggleDark={toggleTheme}
      />

      <main className="mx-auto max-w-7xl space-y-5 px-4 py-6">
        {error && <p className="text-sm text-destructive">{error}</p>}
        {!nodes ? (
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
          />
        )}
      </main>

      <Toaster position="top-center" theme={dark ? "dark" : "light"} />
    </div>
  )
}
