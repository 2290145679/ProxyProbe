import { useState, useEffect } from "react"
import { Shield, User, Send, ArrowLeft } from "lucide-react"

import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { Separator } from "@/components/ui/separator"
import { toast } from "sonner"
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
  const [userMode, setUserMode] = useState<"login" | "register" | "reset">("login")

  // Form states
  const [username, setUsername] = useState("")
  const [password, setPassword] = useState("")
  const [email, setEmail] = useState("")
  const [code, setCode] = useState("")
  const [newPassword, setNewPassword] = useState("")
  const [adminPassword, setAdminPassword] = useState("")

  const [error, setError] = useState(callbackError)
  const [busy, setBusy] = useState(false)
  const [sendingCode, setSendingCode] = useState(false)
  const [cooldown, setCooldown] = useState(0)

  // Auth config
  const [authConfig, setAuthConfig] = useState<{
    register_enabled: boolean
    smtp_enabled: boolean
    site_name: string
    support_tg_enabled: boolean
    support_tg_url: string
  }>({
    register_enabled: true,
    smtp_enabled: false,
    site_name: "网络聚合代理服务",
    support_tg_enabled: false,
    support_tg_url: "",
  })

  useEffect(() => {
    fetch("/api/proxy/auth/config")
      .then((r) => r.json())
      .then((d) => {
        if (d.ok) {
          setAuthConfig({
            register_enabled: !!d.register_enabled,
            smtp_enabled: !!d.smtp_enabled,
            site_name: d.site_name || "网络聚合代理服务",
            support_tg_enabled: !!d.support_tg_enabled,
            support_tg_url: d.support_tg_url || "",
          })
        }
      })
      .catch(() => {})
  }, [])

  // Cooldown countdown timer
  useEffect(() => {
    if (cooldown <= 0) return
    const t = setInterval(() => {
      setCooldown((c) => (c > 1 ? c - 1 : 0))
    }, 1000)
    return () => clearInterval(t)
  }, [cooldown])

  // 发送邮箱验证码
  async function handleSendCode(purpose: "register" | "reset_password") {
    if (!email || !email.includes("@")) {
      setError("请输入有效的电子邮箱地址")
      return
    }
    setSendingCode(true)
    setError("")
    try {
      const res = await fetch("/api/proxy/auth/send-code", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, action_type: purpose }),
      })
      const data = await res.json()
      if (!res.ok || !data.ok) {
        throw new Error(data.message || "验证码发送失败")
      }
      toast.success(data.message || "验证码已成功发送至邮箱，请查收！")
      setCooldown(60)
    } catch (err: any) {
      setError(err.message || "发信出错")
    } finally {
      setSendingCode(false)
    }
  }

  // 用户登录
  async function handleUserLogin(e: React.FormEvent) {
    e.preventDefault()
    setBusy(true)
    setError("")
    try {
      const res = await fetch("/api/proxy/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      })
      const data = await res.json().catch(() => ({}))
      if (!res.ok || !data.ok) {
        throw new Error(data.message || data.error || "登录失败，请检查账号密码")
      }
      onDone()
    } catch (err: any) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  // 邮箱注册
  async function handleRegister(e: React.FormEvent) {
    e.preventDefault()
    if (!code || code.length !== 6) {
      setError("请输入 6 位数字验证码")
      return
    }
    if (password.length < 6) {
      setError("密码长度至少 6 位")
      return
    }
    setBusy(true)
    setError("")
    try {
      const res = await fetch("/api/proxy/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, code, password }),
      })
      const data = await res.json()
      if (!res.ok || !data.ok) {
        throw new Error(data.message || "注册失败")
      }
      toast.success("注册成功，已为您自动登录！")
      onDone()
    } catch (err: any) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  // 忘记密码重置
  async function handleResetPassword(e: React.FormEvent) {
    e.preventDefault()
    if (!code || code.length !== 6) {
      setError("请输入 6 位数字验证码")
      return
    }
    if (newPassword.length < 6) {
      setError("新密码长度至少 6 位")
      return
    }
    setBusy(true)
    setError("")
    try {
      const res = await fetch("/api/proxy/auth/reset-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, code, new_password: newPassword }),
      })
      const data = await res.json()
      if (!res.ok || !data.ok) {
        throw new Error(data.message || "密码重置失败")
      }
      toast.success("密码重置成功，请使用新密码登录！")
      setUsername(email)
      setPassword("")
      setUserMode("login")
    } catch (err: any) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  // 管理员应急登录
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
    <div className="grid min-h-svh place-items-center p-4 sm:p-6 overflow-x-hidden">
      <Card className="w-full max-w-sm gap-5 p-5 sm:p-6 shadow-lg border">
        <div className="space-y-1.5 text-center">
          <h1 className="text-xl font-bold tracking-tight">{authConfig.site_name}</h1>
          <p className="text-xs text-muted-foreground">
            {tab === "admin"
              ? "管理员控制台安全入口"
              : userMode === "register"
              ? "新用户邮箱自主注册"
              : userMode === "reset"
              ? "通过邮箱验证码找回密码"
              : "用户登录以获取订阅配置与流量中心"}
          </p>
        </div>

        {/* 角色切换选项卡 */}
        <div className="grid grid-cols-2 rounded-lg bg-muted p-1 text-xs">
          <button
            type="button"
            className={`flex items-center justify-center gap-1.5 py-1.5 rounded-md transition-all ${
              tab === "user"
                ? "bg-background text-foreground shadow-sm font-semibold"
                : "text-muted-foreground hover:text-foreground"
            }`}
            onClick={() => {
              setTab("user")
              setError("")
            }}
          >
            <User className="size-3.5" /> 用户服务
          </button>
          <button
            type="button"
            className={`flex items-center justify-center gap-1.5 py-1.5 rounded-md transition-all ${
              tab === "admin"
                ? "bg-background text-foreground shadow-sm font-semibold"
                : "text-muted-foreground hover:text-foreground"
            }`}
            onClick={() => {
              setTab("admin")
              setError("")
            }}
          >
            <Shield className="size-3.5" /> 管理员登录
          </button>
        </div>

        {error && (
          <p className="rounded-md bg-destructive/10 px-3 py-2 text-xs text-destructive leading-relaxed">
            {error}
          </p>
        )}

        {tab === "user" ? (
          <div>
            {userMode === "login" && (
              <form onSubmit={handleUserLogin} className="space-y-3 pt-1">
                <div className="space-y-1.5">
                  <Label htmlFor="username" className="text-xs">用户名 或 邮箱</Label>
                  <Input
                    id="username"
                    type="text"
                    placeholder="输入用户名或注册邮箱"
                    className="h-9 text-xs"
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    autoComplete="username"
                    autoFocus
                    required
                  />
                </div>

                <div className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <Label htmlFor="password" className="text-xs">密码</Label>
                    <button
                      type="button"
                      onClick={() => {
                        setUserMode("reset")
                        setError("")
                      }}
                      className="text-[11px] text-primary hover:underline"
                    >
                      忘记密码？
                    </button>
                  </div>
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

                <Button
                  type="submit"
                  className="w-full h-9 text-xs font-medium"
                  disabled={busy || !username || !password}
                >
                  {busy ? "登录中…" : "登录用户中心"}
                </Button>

                <div className="pt-2 text-center">
                  <span className="text-xs text-muted-foreground">还没有账号？</span>
                  <button
                    type="button"
                    onClick={() => {
                      setUserMode("register")
                      setError("")
                    }}
                    className="ml-1 text-xs text-primary font-semibold hover:underline"
                  >
                    立即注册账号
                  </button>
                </div>
              </form>
            )}

            {userMode === "register" && (
              <div className="space-y-3 pt-1">
                {!authConfig.register_enabled ? (
                  <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-center space-y-2">
                    <p className="text-xs font-semibold text-amber-600 dark:text-amber-400">
                      ⚠️ 系统暂未开放自主注册
                    </p>
                    <p className="text-[11px] text-muted-foreground leading-relaxed">
                      当前管理员尚未开放新用户自主注册通道。如需开通节点加速账号，请联系站点管理员！
                    </p>
                    {authConfig.support_tg_enabled && authConfig.support_tg_url && (
                      <div className="pt-1">
                        <a
                          href={authConfig.support_tg_url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md bg-sky-500 text-white hover:bg-sky-600 transition"
                        >
                          联系 Telegram 客服开通
                        </a>
                      </div>
                    )}
                  </div>
                ) : (
                  <form onSubmit={handleRegister} className="space-y-3">
                    <div className="space-y-1.5">
                      <Label className="text-xs">电子邮箱</Label>
                      <div className="flex gap-2">
                        <Input
                          type="email"
                          placeholder="your_email@gmail.com"
                          className="h-9 text-xs flex-1"
                          value={email}
                          onChange={(e) => setEmail(e.target.value)}
                          required
                          autoFocus
                        />
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => handleSendCode("register")}
                          disabled={sendingCode || cooldown > 0 || !email}
                          className="h-9 text-xs shrink-0 px-2.5"
                        >
                          {sendingCode ? "发送中..." : cooldown > 0 ? `${cooldown}s` : "获取验证码"}
                        </Button>
                      </div>
                    </div>

                    <div className="space-y-1.5">
                      <Label className="text-xs">6 位数字验证码</Label>
                      <Input
                        type="text"
                        maxLength={6}
                        placeholder="请输入邮箱收到的 6 位验证码"
                        className="h-9 text-xs font-mono tracking-widest text-center"
                        value={code}
                        onChange={(e) => setCode(e.target.value.trim())}
                        required
                      />
                    </div>

                    <div className="space-y-1.5">
                      <Label className="text-xs">设置登录密码</Label>
                      <Input
                        type="password"
                        placeholder="密码长度至少 6 位"
                        className="h-9 text-xs"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        required
                      />
                    </div>

                    <Button
                      type="submit"
                      className="w-full h-9 text-xs font-medium"
                      disabled={busy || !email || !code || !password}
                    >
                      {busy ? "注册中…" : "完成注册并自动登录"}
                    </Button>
                  </form>
                )}

                <div className="pt-2 text-center">
                  <button
                    type="button"
                    onClick={() => {
                      setUserMode("login")
                      setError("")
                    }}
                    className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
                  >
                    <ArrowLeft className="size-3" /> 返回已有账号登录
                  </button>
                </div>
              </div>
            )}

            {userMode === "reset" && (
              <div className="space-y-3 pt-1">
                {!authConfig.smtp_enabled ? (
                  <div className="rounded-lg border border-amber-500/30 bg-amber-500/10 p-4 text-center space-y-2">
                    <p className="text-xs font-semibold text-amber-600 dark:text-amber-400">
                      ⚠️ 邮箱找回密码未开启
                    </p>
                    <p className="text-[11px] text-muted-foreground leading-relaxed">
                      当前系统管理员尚未配置或开启邮件发信服务，无法自动通过邮箱找回密码。请直接联系管理员帮您重置密码！
                    </p>
                    {authConfig.support_tg_enabled && authConfig.support_tg_url && (
                      <div className="pt-1">
                        <a
                          href={authConfig.support_tg_url}
                          target="_blank"
                          rel="noreferrer"
                          className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md bg-sky-500 text-white hover:bg-sky-600 transition"
                        >
                          联系 Telegram 客服重置
                        </a>
                      </div>
                    )}
                  </div>
                ) : (
                  <form onSubmit={handleResetPassword} className="space-y-3">
                    <div className="space-y-1.5">
                      <Label className="text-xs">注册邮箱</Label>
                      <div className="flex gap-2">
                        <Input
                          type="email"
                          placeholder="请输入您的注册邮箱"
                          className="h-9 text-xs flex-1"
                          value={email}
                          onChange={(e) => setEmail(e.target.value)}
                          required
                          autoFocus
                        />
                        <Button
                          type="button"
                          variant="outline"
                          size="sm"
                          onClick={() => handleSendCode("reset_password")}
                          disabled={sendingCode || cooldown > 0 || !email}
                          className="h-9 text-xs shrink-0 px-2.5"
                        >
                          {sendingCode ? "发送中..." : cooldown > 0 ? `${cooldown}s` : "获取验证码"}
                        </Button>
                      </div>
                    </div>

                <div className="space-y-1.5">
                  <Label className="text-xs">6 位数字验证码</Label>
                  <Input
                    type="text"
                    maxLength={6}
                    placeholder="请输入邮箱收到的 6 位验证码"
                    className="h-9 text-xs font-mono tracking-widest text-center"
                    value={code}
                    onChange={(e) => setCode(e.target.value.trim())}
                    required
                  />
                </div>

                <div className="space-y-1.5">
                  <Label className="text-xs">设置新密码</Label>
                  <Input
                    type="password"
                    placeholder="请输入重置后的新密码"
                    className="h-9 text-xs"
                    value={newPassword}
                    onChange={(e) => setNewPassword(e.target.value)}
                    required
                  />
                </div>

                <Button
                  type="submit"
                  className="w-full h-9 text-xs font-medium"
                  disabled={busy || !email || !code || !newPassword}
                >
                  {busy ? "重置中…" : "确认重置密码"}
                </Button>
              </form>
            )}

            <div className="pt-2 text-center">
              <button
                type="button"
                onClick={() => {
                  setUserMode("login")
                  setError("")
                }}
                className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
              >
                <ArrowLeft className="size-3" /> 返回登录
              </button>
            </div>
          </div>
        )}
      </div>
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

        {/* Telegram 在线客服入口（管理员开启时展示，默认关闭时 100% 隐藏） */}
        {authConfig.support_tg_enabled && authConfig.support_tg_url && (
          <div className="pt-2 border-t text-center">
            <a
              href={authConfig.support_tg_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1.5 text-xs text-muted-foreground hover:text-[#229ED9] transition-colors"
            >
              <Send className="size-3 text-[#229ED9] fill-[#229ED9]" />
              <span>联系 Telegram 在线客服</span>
            </a>
          </div>
        )}
      </Card>
    </div>
  )
}
