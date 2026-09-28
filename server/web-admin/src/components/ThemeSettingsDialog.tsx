import { Check, Palette } from "lucide-react"

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

export function ThemeSettingsDialog({
  open,
  onOpenChange,
  themeStyle,
  onThemeStyleChange,
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  themeStyle: "default" | "sakura"
  onThemeStyleChange: (style: "default" | "sakura") => void
  dark?: boolean
  onToggleDark?: () => void
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 text-base font-bold">
            <Palette className="size-4 text-primary" />
            <span>界面主题与外观设置</span>
          </DialogTitle>
          <DialogDescription className="text-xs text-muted-foreground">
            自定义控制面板配色风格，设置将跟随您的账号实时同步。
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* 主题风格选择 */}
          <div className="space-y-2">
            <label className="text-xs font-semibold text-foreground">
              选择主题风格
            </label>
            <div className="grid grid-cols-2 gap-3">
              {/* 默认经典主题 */}
              <button
                type="button"
                onClick={() => onThemeStyleChange("default")}
                className={`relative flex flex-col items-start gap-1.5 rounded-xl border p-3.5 text-left transition-all cursor-pointer ${
                  themeStyle === "default"
                    ? "border-primary bg-primary/5 ring-2 ring-primary/20 shadow-sm"
                    : "border-border hover:bg-muted/50"
                }`}
              >
                <div className="flex w-full items-center justify-between">
                  <div className="flex items-center gap-1.5 font-bold text-sm">
                    <span className="size-2.5 rounded-full bg-slate-500" />
                    <span>默认经典</span>
                  </div>
                  {themeStyle === "default" && (
                    <Check className="size-4 text-primary" />
                  )}
                </div>
                <p className="text-[11px] text-muted-foreground leading-snug">
                  沉稳黑灰蓝调，极简清晰
                </p>
                <div className="flex items-center gap-1 mt-1">
                  <div className="size-3 rounded-full bg-slate-800 border border-slate-700" />
                  <div className="size-3 rounded-full bg-slate-200 border border-slate-300" />
                  <div className="size-3 rounded-full bg-emerald-500" />
                </div>
              </button>

              {/* 浪漫樱花主题 */}
              <button
                type="button"
                onClick={() => onThemeStyleChange("sakura")}
                className={`relative flex flex-col items-start gap-1.5 rounded-xl border p-3.5 text-left transition-all cursor-pointer ${
                  themeStyle === "sakura"
                    ? "border-rose-400 bg-rose-500/10 ring-2 ring-rose-400/20 shadow-sm"
                    : "border-border hover:bg-muted/50"
                }`}
              >
                <div className="flex w-full items-center justify-between">
                  <div className="flex items-center gap-1.5 font-bold text-sm text-rose-600 dark:text-rose-400">
                    <span className="text-sm">🌸</span>
                    <span>浪漫樱花</span>
                  </div>
                  {themeStyle === "sakura" && (
                    <Check className="size-4 text-rose-500" />
                  )}
                </div>
                <p className="text-[11px] text-muted-foreground leading-snug">
                  绯樱粉润轻盈，夜樱幽雅沉醉
                </p>
                <div className="flex items-center gap-1 mt-1">
                  <div className="size-3 rounded-full bg-rose-500" />
                  <div className="size-3 rounded-full bg-rose-200 border border-rose-300" />
                  <div className="size-3 rounded-full bg-purple-900 border border-purple-800" />
                </div>
              </button>
            </div>
          </div>

          <div className="rounded-lg bg-muted/60 p-2.5 text-[11px] text-muted-foreground text-center">
            💡 主题首选项已与您的账号绑定，在任何设备登录都会自动还原。
          </div>
        </div>
      </DialogContent>
    </Dialog>
  )
}
