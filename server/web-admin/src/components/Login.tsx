import { useState } from "react"
import { Shield, User } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { api } from "@/lib/api"

function GithubMark() {
  return (
    <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden className="size-4">
      <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27s1.36.09 2 .27c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z" />
    </svg>
  )
}

function callbackError(): string {
  const reason = new URLSearchParams(location.search).get("login_error")
  if (reason) history.replaceState({}, "", location.pathname)
  return reason ?? ""
}

export function Login({ github, onDone }: { github: boolean; onDone: () => void }) {
  const [tab, setTab] = useState<"user" | "admin">("user")
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [adminPassword, setAdminPassword] = useState("")
  const [error, setError] = useState(callbackError)
  const [busy, setBusy] = useState(false)

  async function handleUserSubmit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError("")
    try {
      const res = await fetch("/api/proxy/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password })
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok || !data.ok) {
        throw new Error(data.message || data.error || "登录失败，请检查账号密码")
      }
      onDone()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  async function handleAdminSubmit(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError("")
    try {
      await api("/auth/login", { method: "POST", body: JSON.stringify({ password: adminPassword }) })
      onDone()
    } catch (err) {
      setError((err as Error).message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="grid min-h-svh place-items-center p-6">
      <Card className="w-full max-w-sm gap-5 p-6 shadow-lg border">
        <div className="space-y-1.5 text-center">
          <h1 className="text-xl font-bold tracking-tight">网络聚合代理服务</h1>
          <p className="text-xs text-muted-foreground">用户登录以获取订阅配置与流量中心</p>
        </div>

        {/* 角色切换选项卡 */}
        <div className="grid grid-cols-2 rounded-lg bg-muted p-1 text-xs">
          <button
            type="button"
            className={`flex items-center justify-center gap-1.5 py-1.5 rounded-md transition-all ${
              tab === "user" ? "bg-background text-foreground shadow-sm font-semibold" : "text-muted-foreground hover:text-foreground"
            }`}
            onClick={() => { setTab("user"); setError("") }}
          >
            <User className="size-3.5" /> 用户登录
          </button>
          <button
            type="button"
            className={`flex items-center justify-center gap-1.5 py-1.5 rounded-md transition-all ${
              tab === "admin" ? "bg-background text-foreground shadow-sm font-semibold" : "text-muted-foreground hover:text-foreground"
            }`}
            onClick={() => { setTab("admin"); setError("") }}
          >
            <Shield className="size-3.5" /> 管理员登录
          </button>
        </div>

        {error && (
          <p className="rounded-md bg-destructive/10 px-3 py-2 text-xs text-destructive">{error}</p>
        )}

        {tab === "user" ? (
          <form onSubmit={handleUserSubmit} className="space-y-3 pt-1">
            <div className="space-y-1.5">
              <Label htmlFor="username" className="text-xs">用户名</Label>
              <Input
                id="username"
                type="text"
                placeholder="请输入用户名"
                className="h-9 text-xs"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                autoComplete="username"
                autoFocus
                required
              />
            </div>

            <div className="space-y-1.5">
              <Label htmlFor="password" className="text-xs">密码</Label>
              <Input
                id="password"
                type="password"
                placeholder="请输入登录密码"
                className="h-9 text-xs"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                autoComplete="current-password"
                required
              />
            </div>

            <Button type="submit" className="w-full h-9 text-xs font-medium" disabled={busy || !username || !password}>
              {busy ? "登录中…" : "登录用户中心"}
            </Button>
          </form>
        ) : (
          <div className="space-y-3 pt-1">
            {github && (
              <>
                <Button asChild variant="outline" className="w-full h-9 text-xs">
                  <a href="/api/auth/github">
                    <GithubMark /> 使用 GitHub 登录
                  </a>
                </Button>
                <div className="relative">
                  <Separator />
                  <span className="absolute inset-0 -top-2 mx-auto w-fit bg-card px-2 text-[10px] text-muted-foreground">
                    或使用应急管理密码
                  </span>
                </div>
              </>
            )}

            <form onSubmit={handleAdminSubmit} className="space-y-3">
              <div className="space-y-1.5">
                <Label htmlFor="admin-password" className="text-xs">应急管理员密码</Label>
                <Input
                  id="admin-password"
                  type="password"
                  placeholder="请输入后台管理员密码"
                  className="h-9 text-xs"
                  value={adminPassword}
                  onChange={(e) => setAdminPassword(e.target.value)}
                  autoComplete="current-password"
                  autoFocus={!github}
                  required
                />
              </div>
              <Button type="submit" className="w-full h-9 text-xs font-medium" disabled={busy || !adminPassword}>
                {busy ? "登录中…" : "进入管理后台"}
              </Button>
            </form>
          </div>
        )}
      </Card>
    </div>
  )
}
