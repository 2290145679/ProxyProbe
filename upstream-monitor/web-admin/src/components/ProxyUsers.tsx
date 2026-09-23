import { useEffect, useState } from "react"
import {
  AlertCircle,
  Copy,
  Edit2,
  KeyRound,
  Plus,
  RefreshCw,
  RotateCcw,
  Trash2,
  Users,
} from "lucide-react"
import { toast } from "sonner"

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
import { Label } from "@/components/ui/label"
import { Switch } from "@/components/ui/switch"

export type ManagedUser = {
  id: number
  username: string
  is_admin: number
  sub_token: string
  sub_url: string
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
  return new Date(ts * 1000).toLocaleDateString()
}

export function ProxyUsers() {
  const [users, setUsers] = useState<ManagedUser[]>([])
  const [loading, setLoading] = useState(false)

  // 新建用户弹窗状态
  const [createOpen, setCreateOpen] = useState(false)
  const [createForm, setCreateForm] = useState({
    username: "",
    password: "",
    traffic_limit_gb: "200",
    expires_days: "30",
    device_limit: "0",
  })
  const [creating, setCreating] = useState(false)

  // 编辑用户弹窗状态
  const [editOpen, setEditOpen] = useState(false)
  const [editingUser, setEditingUser] = useState<ManagedUser | null>(null)
  const [editForm, setEditForm] = useState({
    traffic_limit_gb: "",
    expires_date: "",
    password: "",
    device_limit: "0",
  })
  const [savingEdit, setSavingEdit] = useState(false)

  const loadUsers = async () => {
    setLoading(true)
    try {
      const res = await fetch("/api/proxy/users")
      const data = await res.json()
      if (data.ok && Array.isArray(data.users)) {
        setUsers(data.users)
      }
    } catch {
      toast.error("加载用户列表失败")
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    loadUsers()
    const timer = setInterval(() => {
      if (!createOpen && !editOpen) {
        fetch("/api/proxy/users")
          .then(res => res.json())
          .then(data => {
            if (data.ok && Array.isArray(data.users)) {
              setUsers(data.users)
            }
          })
          .catch(() => {})
      }
    }, 4000)
    return () => clearInterval(timer)
  }, [createOpen, editOpen])

  // 创建用户
  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault()
    setCreating(true)
    try {
      const res = await fetch("/api/proxy/users", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: createForm.username,
          password: createForm.password,
          traffic_limit_gb: parseFloat(createForm.traffic_limit_gb) || 200,
          expires_days: parseInt(createForm.expires_days) || 0,
          device_limit: parseInt(createForm.device_limit) || 0,
        }),
      })
      const data = await res.json()
      if (data.ok) {
        toast.success("用户创建成功！")
        setCreateOpen(false)
        setCreateForm({ username: "", password: "", traffic_limit_gb: "200", expires_days: "30", device_limit: "0" })
        loadUsers()
      } else {
        toast.error(data.message || "创建失败")
      }
    } catch {
      toast.error("网络请求错误")
    } finally {
      setCreating(false)
    }
  }

  // 打开编辑用户
  const openEdit = (user: ManagedUser) => {
    setEditingUser(user)
    const limitGb = user.traffic_limit_bytes > 0 ? (user.traffic_limit_bytes / (1024 * 1024 * 1024)).toFixed(0) : "0"
    const dateStr = user.expires_at > 0 ? new Date(user.expires_at * 1000).toISOString().split("T")[0] : ""
    setEditForm({
      traffic_limit_gb: limitGb,
      expires_date: dateStr,
      password: "",
      device_limit: (user.device_limit ?? 0).toString(),
    })
    setEditOpen(true)
  }

  // 保存编辑
  const handleSaveEdit = async (e: React.FormEvent) => {
    e.preventDefault()
    if (!editingUser) return
    setSavingEdit(true)
    try {
      let expTs = 0
      if (editForm.expires_date) {
        expTs = Math.floor(new Date(editForm.expires_date).getTime() / 1000)
      }
      const res = await fetch(`/api/proxy/users/${editingUser.id}/edit`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          traffic_limit_gb: parseFloat(editForm.traffic_limit_gb) || 0,
          expires_at: expTs,
          password: editForm.password,
          device_limit: parseInt(editForm.device_limit) || 0,
        }),
      })
      const data = await res.json()
      if (data.ok) {
        toast.success("用户信息已更新")
        setEditOpen(false)
        loadUsers()
      } else {
        toast.error(data.message || "更新失败")
      }
    } catch {
      toast.error("网络请求错误")
    } finally {
      setSavingEdit(false)
    }
  }

  // 重置已用流量
  const handleResetTraffic = async (userId: number, username: string) => {
    if (!confirm(`确定将用户【${username}】的已用流量重置为 0 吗？`)) return
    try {
      const res = await fetch(`/api/proxy/users/${userId}/reset-traffic`, { method: "POST" })
      const data = await res.json()
      if (data.ok) {
        toast.success(`用户【${username}】流量已重置为 0`)
        loadUsers()
      } else {
        toast.error(data.message || "操作失败")
      }
    } catch {
      toast.error("网络错误")
    }
  }

  // 重置订阅 Token
  const handleResetToken = async (userId: number, username: string) => {
    if (!confirm(`确定重新生成用户【${username}】的订阅链接吗？原链接将立即失效。`)) return
    try {
      const res = await fetch(`/api/proxy/users/${userId}/reset-token`, { method: "POST" })
      const data = await res.json()
      if (data.ok) {
        toast.success(`用户【${username}】的订阅链接已重新生成`)
        loadUsers()
      } else {
        toast.error(data.message || "操作失败")
      }
    } catch {
      toast.error("网络错误")
    }
  }

  // 启用/禁用切换
  const handleToggle = async (userId: number) => {
    try {
      const res = await fetch(`/api/proxy/users/${userId}/toggle`, { method: "POST" })
      const data = await res.json()
      if (data.ok) {
        toast.success("用户状态已更新")
        loadUsers()
      } else {
        toast.error(data.message || "操作失败")
      }
    } catch {
      toast.error("网络错误")
    }
  }

  // 删除用户
  const handleDelete = async (userId: number, username: string) => {
    if (!confirm(`危险操作：确定要彻底删除用户【${username}】吗？此操作无法撤销。`)) return
    try {
      const res = await fetch(`/api/proxy/users/${userId}`, { method: "DELETE" })
      const data = await res.json()
      if (data.ok) {
        toast.success(`用户【${username}】已删除`)
        loadUsers()
      } else {
        toast.error(data.message || "删除失败")
      }
    } catch {
      toast.error("网络错误")
    }
  }

  return (
    <div className="space-y-6">
      {/* 顶部标题与新建按钮 */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <h2 className="text-xl font-bold tracking-tight flex items-center gap-2">
            <Users className="size-5 text-primary" /> 用户与订阅管理
          </h2>
          <p className="text-xs text-muted-foreground mt-1">
            机场式多用户面板管理，分配独立订阅链接、流量额度与有效期。
          </p>
        </div>

        <div className="flex items-center gap-2">
          <Button variant="outline" size="sm" onClick={loadUsers} disabled={loading} className="gap-1.5 text-xs">
            <RefreshCw className={`size-3.5 ${loading ? "animate-spin" : ""}`} /> 刷新
          </Button>
          <Button size="sm" onClick={() => setCreateOpen(true)} className="gap-1.5 text-xs">
            <Plus className="size-3.5" /> 新建用户
          </Button>
        </div>
      </div>

      {/* 用户列表 */}
      <Card className="overflow-hidden border shadow-sm">
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="bg-muted/50 border-b text-muted-foreground">
              <tr>
                <th className="py-3 px-4 font-semibold w-14">ID</th>
                <th className="py-3 px-4 font-semibold">用户名</th>
                <th className="py-3 px-4 font-semibold">流量使用情况</th>
                <th className="py-3 px-4 font-semibold">设备限制</th>
                <th className="py-3 px-4 font-semibold">到期时间</th>
                <th className="py-3 px-4 font-semibold">账户状态</th>
                <th className="py-3 px-4 font-semibold">专属订阅链接</th>
                <th className="py-3 px-4 font-semibold text-right">操作</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-border">
              {users.map((u) => {
                const limit = u.traffic_limit_bytes
                const used = u.total_used_bytes
                const percent = limit > 0 ? Math.min(100, Math.round((used / limit) * 100)) : 0
                let barColor = "bg-emerald-500"
                if (percent >= 90) barColor = "bg-red-500"
                else if (percent >= 70) barColor = "bg-amber-500"

                return (
                  <tr key={u.id} className="hover:bg-muted/30 transition-colors">
                    <td className="py-3.5 px-4 font-mono text-muted-foreground">{u.id}</td>

                    <td className="py-3.5 px-4">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold">{u.username}</span>
                        {Boolean(u.is_admin) ? (
                          <Badge variant="outline" className="text-[10px] py-0 px-1 text-primary border-primary/40">
                            管理员
                          </Badge>
                        ) : (
                          <Badge variant="secondary" className="text-[10px] py-0 px-1">
                            普通用户
                          </Badge>
                        )}
                      </div>
                    </td>

                    <td className="py-3.5 px-4 min-w-[200px]">
                      <div className="space-y-1.5">
                        <div className="flex justify-between text-[11px]">
                          <span className="font-medium">{formatBytes(used)}</span>
                          <span className="text-muted-foreground">
                            {limit > 0 ? `${formatBytes(limit)} (${percent}%)` : "不限量"}
                          </span>
                        </div>
                        <div className="h-1.5 w-full rounded-full bg-muted overflow-hidden">
                          <div
                            className={`h-full rounded-full ${barColor}`}
                            style={{ width: `${limit > 0 ? percent : 0}%` }}
                          />
                        </div>
                      </div>
                    </td>

                    <td className="py-3.5 px-4 font-mono text-muted-foreground whitespace-nowrap">
                      <div className="flex items-center gap-1.5">
                        <span className={`font-semibold ${(u.device_limit && u.device_limit > 0 && (u.online_devices || 0) > u.device_limit) ? "text-red-500 font-bold" : "text-foreground"}`}>
                          {u.online_devices ?? 0}
                        </span>
                        <span>/</span>
                        <span>{(u.device_limit && u.device_limit > 0) ? `${u.device_limit} 台` : "不限"}</span>
                        {(u.device_limit && u.device_limit > 0 && (u.online_devices || 0) > u.device_limit) && (
                          <Badge variant="destructive" className="text-[9px] py-0 px-1">超限</Badge>
                        )}
                      </div>
                    </td>

                    <td className="py-3.5 px-4 text-muted-foreground font-mono">
                      {formatDate(u.expires_at)}
                    </td>

                    <td className="py-3.5 px-4">
                      <div className="flex items-center gap-2">
                        <Switch
                          checked={u.enabled === 1}
                          onCheckedChange={() => handleToggle(u.id)}
                          aria-label="切换状态"
                        />
                        <span className={`text-[11px] font-medium ${u.enabled === 1 ? "text-emerald-600 dark:text-emerald-400" : "text-muted-foreground"}`}>
                          {u.enabled === 1 ? "启用" : "禁用"}
                        </span>
                      </div>
                    </td>

                    <td className="py-3.5 px-4 max-w-[220px]">
                      <div className="flex items-center gap-1.5">
                        <span className="font-mono text-[11px] truncate text-muted-foreground select-all">
                          {u.sub_token.slice(0, 10)}…
                        </span>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="size-7 shrink-0"
                          title="复制完整订阅链接"
                          onClick={() => {
                            navigator.clipboard.writeText(u.sub_url)
                            toast.success(`已复制用户【${u.username}】的订阅链接！`)
                          }}
                        >
                          <Copy className="size-3.5" />
                        </Button>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="size-7 shrink-0 text-muted-foreground hover:text-foreground"
                          title="重新生成订阅Token"
                          onClick={() => handleResetToken(u.id, u.username)}
                        >
                          <KeyRound className="size-3.5" />
                        </Button>
                      </div>
                    </td>

                    <td className="py-3.5 px-4 text-right">
                      <div className="flex items-center justify-end gap-1">
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 px-2 text-xs gap-1"
                          onClick={() => openEdit(u)}
                        >
                          <Edit2 className="size-3.5" /> 编辑
                        </Button>
                        <Button
                          variant="ghost"
                          size="sm"
                          className="h-7 px-2 text-xs gap-1 text-amber-600 hover:text-amber-700 hover:bg-amber-500/10"
                          onClick={() => handleResetTraffic(u.id, u.username)}
                          title="重置已用流量为0"
                        >
                          <RotateCcw className="size-3.5" /> 清零流量
                        </Button>
                        {u.id !== 1 && (
                          <Button
                            variant="ghost"
                            size="sm"
                            className="h-7 px-2 text-xs gap-1 text-destructive hover:bg-destructive/10"
                            onClick={() => handleDelete(u.id, u.username)}
                          >
                            <Trash2 className="size-3.5" /> 删除
                          </Button>
                        )}
                      </div>
                    </td>
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </Card>

      {/* 新建用户弹窗 */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="text-base font-bold">新建机场用户</DialogTitle>
            <DialogDescription className="text-xs">
              创建独立账号，自动生成专属聚合订阅并设定流量限额。
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleCreate} className="space-y-4 py-2">
            <div className="space-y-1.5">
              <Label className="text-xs">用户名</Label>
              <Input
                className="text-xs h-9"
                placeholder="如：client_01"
                value={createForm.username}
                onChange={e => setCreateForm(prev => ({ ...prev, username: e.target.value }))}
                required
              />
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs">登录密码</Label>
              <Input
                type="password"
                className="text-xs h-9"
                placeholder="设置该用户的面板登录密码"
                value={createForm.password}
                onChange={e => setCreateForm(prev => ({ ...prev, password: e.target.value }))}
                required
              />
            </div>

            <div className="grid grid-cols-3 gap-2">
              <div className="space-y-1.5">
                <Label className="text-xs">流量限额 (GB)</Label>
                <Input
                  type="number"
                  min="0"
                  step="1"
                  className="text-xs h-9"
                  placeholder="默认 200 (0为不限)"
                  value={createForm.traffic_limit_gb}
                  onChange={e => setCreateForm(prev => ({ ...prev, traffic_limit_gb: e.target.value }))}
                  required
                />
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs">有效期限 (天)</Label>
                <Input
                  type="number"
                  min="0"
                  step="1"
                  className="text-xs h-9"
                  placeholder="默认 30 (0为永久)"
                  value={createForm.expires_days}
                  onChange={e => setCreateForm(prev => ({ ...prev, expires_days: e.target.value }))}
                  required
                />
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs">设备限制 (台)</Label>
                <Input
                  type="number"
                  min="0"
                  step="1"
                  className="text-xs h-9"
                  placeholder="0为不限"
                  value={createForm.device_limit}
                  onChange={e => setCreateForm(prev => ({ ...prev, device_limit: e.target.value }))}
                />
              </div>
            </div>

            <div className="rounded-md bg-muted/50 p-2.5 text-[11px] text-muted-foreground flex items-center gap-2">
              <AlertCircle className="size-4 shrink-0 text-primary" />
              <span>超过流量限额、到期或同时在线客户端超过限制后，系统将自动熔断切断连接。</span>
            </div>

            <DialogFooter className="pt-2">
              <Button type="button" variant="outline" size="sm" onClick={() => setCreateOpen(false)}>
                取消
              </Button>
              <Button type="submit" size="sm" disabled={creating}>
                {creating ? "创建中…" : "确认创建"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>

      {/* 编辑用户弹窗 */}
      <Dialog open={editOpen} onOpenChange={setEditOpen}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle className="text-base font-bold">编辑用户：{editingUser?.username}</DialogTitle>
            <DialogDescription className="text-xs">
              修改该用户的流量限额、有效期或重设密码。
            </DialogDescription>
          </DialogHeader>

          <form onSubmit={handleSaveEdit} className="space-y-4 py-2">
            <div className="grid grid-cols-2 gap-3">
              <div className="space-y-1.5">
                <Label className="text-xs">流量限额 (GB)</Label>
                <Input
                  type="number"
                  min="0"
                  step="1"
                  className="text-xs h-9"
                  placeholder="0 为无限制"
                  value={editForm.traffic_limit_gb}
                  onChange={e => setEditForm(prev => ({ ...prev, traffic_limit_gb: e.target.value }))}
                  required
                />
              </div>

              <div className="space-y-1.5">
                <Label className="text-xs">设备限制 (台)</Label>
                <Input
                  type="number"
                  min="0"
                  step="1"
                  className="text-xs h-9"
                  placeholder="0 为无限制"
                  value={editForm.device_limit}
                  onChange={e => setEditForm(prev => ({ ...prev, device_limit: e.target.value }))}
                />
              </div>
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs">到期时间 (留空为永久有效)</Label>
              <Input
                type="date"
                className="text-xs h-9"
                value={editForm.expires_date}
                onChange={e => setEditForm(prev => ({ ...prev, expires_date: e.target.value }))}
              />
            </div>

            <div className="space-y-1.5">
              <Label className="text-xs">重置密码 (留空则不修改)</Label>
              <Input
                type="password"
                className="text-xs h-9"
                placeholder="留空保持原密码不变"
                value={editForm.password}
                onChange={e => setEditForm(prev => ({ ...prev, password: e.target.value }))}
              />
            </div>

            <DialogFooter className="pt-2">
              <Button type="button" variant="outline" size="sm" onClick={() => setEditOpen(false)}>
                取消
              </Button>
              <Button type="submit" size="sm" disabled={savingEdit}>
                {savingEdit ? "保存中…" : "保存修改"}
              </Button>
            </DialogFooter>
          </form>
        </DialogContent>
      </Dialog>
    </div>
  )
}
