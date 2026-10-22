import { useState } from "react"
import { KeyRound, Eye, EyeOff } from "lucide-react"
import { toast } from "sonner"
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
} from "@/components/ui/dialog"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { api } from "@/lib/api"

export function ChangePasswordDialog({
  open,
  onOpenChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
}) {
  const [password, setPassword] = useState("")
  const [confirmPassword, setConfirmPassword] = useState("")
  const [showPassword, setShowPassword] = useState(false)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState("")

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError("")

    if (!password) {
      setError("请输入新密码")
      return
    }
    if (password.length < 6) {
      setError("密码长度至少需 6 位")
      return
    }
    if (password !== confirmPassword) {
      setError("两次输入的密码不一致，请重新核对")
      return
    }

    setSaving(true)
    try {
      await api("/settings", {
        method: "PUT",
        body: JSON.stringify({ admin_password: password }),
      })
      toast.success("管理员登录密码修改成功！")
      setPassword("")
      setConfirmPassword("")
      onOpenChange(false)
    } catch (err: any) {
      setError(err?.message || "密码修改失败，请重试")
    } finally {
      setSaving(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={(v) => {
      if (!v) {
        setPassword("")
        setConfirmPassword("")
        setError("")
      }
      onOpenChange(v)
    }}>
      <DialogContent className="w-[94vw] max-w-md p-5 sm:p-6 space-y-4 max-h-[88vh] overflow-y-auto overflow-x-hidden">
        <DialogHeader>
          <DialogTitle className="text-base font-bold flex items-center gap-2">
            <KeyRound className="size-4 text-primary" />
            <span>修改管理员密码</span>
          </DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground leading-relaxed">
            修改超级管理员后台的登录凭据。保存后立即生效，其它设备登录会话将即时失效。
          </DialogDescription>
        </DialogHeader>

        <form onSubmit={handleSubmit} className="space-y-4 pt-1">
          <div className="space-y-1.5">
            <Label className="text-xs font-medium">新密码</Label>
            <div className="relative">
              <Input
                type={showPassword ? "text" : "password"}
                value={password}
                onChange={(e) => {
                  setPassword(e.target.value)
                  setError("")
                }}
                placeholder="请输入新密码（建议 8 位以上英数组合）"
                autoComplete="new-password"
                className="text-xs h-9 pr-9"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground cursor-pointer"
              >
                {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
              </button>
            </div>
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs font-medium">确认新密码</Label>
            <Input
              type={showPassword ? "text" : "password"}
              value={confirmPassword}
              onChange={(e) => {
                setConfirmPassword(e.target.value)
                setError("")
              }}
              placeholder="请再次输入新密码"
              autoComplete="new-password"
              className="text-xs h-9"
            />
            {error && (
              <p className="text-[11px] text-destructive pt-0.5 font-medium">{error}</p>
            )}
          </div>

          <DialogFooter className="pt-2 gap-2 sm:gap-0">
            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => onOpenChange(false)}
              className="h-8 text-xs cursor-pointer"
            >
              取消
            </Button>
            <Button
              type="submit"
              size="sm"
              disabled={saving}
              className="h-8 text-xs cursor-pointer"
            >
              {saving ? "正在保存..." : "确认修改"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
