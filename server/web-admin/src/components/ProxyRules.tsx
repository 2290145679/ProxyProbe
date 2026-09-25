import { useEffect, useState } from "react"
import {
  Check,
  Code2,
  Copy,
  Eye,
  Globe,
  Plus,
  RefreshCw,
  Save,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Zap,
} from "lucide-react"
import { toast } from "sonner"
import { copyToClipboard } from "@/lib/clipboard"

import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import { Card } from "@/components/ui/card"
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog"

export type RulePreset = {
  id: "smart" | "minimal" | "global" | "custom"
  name: string
  desc: string
  badge: string
  clash_rules: string
  singbox_rules: string
}

export function ProxyRules() {
  const [mode, setMode] = useState<"smart" | "minimal" | "global" | "custom">("smart")
  const [clashRules, setClashRules] = useState("")
  const [singboxRules, setSingboxRules] = useState("")
  const [presets, setPresets] = useState<RulePreset[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [activeTab, setActiveTab] = useState<"clash" | "singbox">("clash")

  // 预览弹窗
  const [previewOpen, setPreviewOpen] = useState(false)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [previewTab, setPreviewTab] = useState<"clash" | "singbox">("clash")
  const [previewData, setPreviewData] = useState<{ clash_yaml: string; singbox_json: string } | null>(null)

  // 加载当前规则配置
  useEffect(() => {
    fetch("/api/proxy/rules/config")
      .then((res) => res.json())
      .then((data) => {
        if (data.ok) {
          setMode(data.mode || "smart")
          setClashRules(data.clash_rules || "")
          setSingboxRules(data.singbox_rules || "")
          if (Array.isArray(data.presets)) {
            setPresets(data.presets)
          }
        }
      })
      .catch((err) => {
        console.error("加载分流规则失败:", err)
        toast.error("加载分流规则失败")
      })
      .finally(() => setLoading(false))
  }, [])

  // 选择预设
  const handleSelectPreset = (p: RulePreset) => {
    setMode(p.id)
    if (p.id !== "custom") {
      setClashRules(p.clash_rules)
      setSingboxRules(p.singbox_rules)
      toast.info(`已切换至预设：${p.name}`)
    } else {
      toast.info("已切换至自定义专家模式，可自由编辑下方规则")
    }
  }

  // 恢复默认预设
  const handleResetDefault = () => {
    const smartPreset = presets.find((p: RulePreset) => p.id === "smart")
    if (smartPreset) {
      setMode("smart")
      setClashRules(smartPreset.clash_rules)
      setSingboxRules(smartPreset.singbox_rules)
      toast.success("已恢复为推荐默认预设（国内外智能分流）")
    }
  }

  // 保存规则
  const handleSave = async () => {
    // 验证 Singbox JSON 格式
    if (mode === "custom" || activeTab === "singbox") {
      try {
        if (singboxRules.trim()) {
          JSON.parse(singboxRules)
        }
      } catch (err: unknown) {
        const msg = err instanceof Error ? err.message : String(err)
        toast.error(`Sing-box 规则 JSON 语法有误: ${msg}`)
        setActiveTab("singbox")
        return
      }
    }

    setSaving(true)
    try {
      const res = await fetch("/api/proxy/rules/config", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          mode,
          clash_rules: clashRules,
          singbox_rules: singboxRules,
        }),
      })
      const data = await res.json()
      if (data.ok) {
        toast.success(data.message || "分流规则配置保存成功！订阅已即时生效")
      } else {
        toast.error(data.error || "保存失败")
      }
    } catch {
      toast.error("保存失败，请检查网络连接")
    } finally {
      setSaving(false)
    }
  }

  // 快速插入规则行到 Clash 文本框
  const handleInsertClashRule = (ruleText: string) => {
    setMode("custom")
    setClashRules((prev: string) => {
      const trimmed = prev.trim()
      if (!trimmed) return ruleText
      return `${trimmed}\n${ruleText}`
    })
    toast.success("已追加规则")
  }

  // 格式化 Singbox JSON
  const handleFormatSingboxJson = () => {
    try {
      const obj = JSON.parse(singboxRules)
      setSingboxRules(JSON.stringify(obj, null, 2))
      toast.success("JSON 格式化成功")
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : String(err)
      toast.error(`JSON 解析失败: ${msg}`)
    }
  }

  // 加载订阅实时预览
  const handleOpenPreview = async () => {
    setPreviewOpen(true)
    setPreviewLoading(true)
    try {
      const res = await fetch("/api/proxy/rules/preview")
      const data = await res.json()
      if (data.ok) {
        setPreviewData(data)
      } else {
        toast.error(data.error || "获取预览失败")
      }
    } catch {
      toast.error("获取预览失败")
    } finally {
      setPreviewLoading(false)
    }
  }

  // 计算有效规则行数
  const clashRuleCount = clashRules
    .split("\n")
    .map((l: string) => l.trim())
    .filter((l: string) => l && !l.startsWith("#")).length

  if (loading) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-muted-foreground">
        <RefreshCw className="mr-2 size-4 animate-spin text-primary" />
        加载分流规则中…
      </div>
    )
  }

  return (
    <div className="space-y-4 sm:space-y-6 max-w-full overflow-hidden">
      {/* 顶部标题与主要操作按钮栏 */}
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between border-b pb-3 sm:pb-4">
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <SlidersHorizontal className="size-5 text-primary shrink-0" />
            <h2 className="text-lg sm:text-xl font-bold tracking-tight">分流规则配置</h2>
            <Badge variant="outline" className="text-xs font-mono">
              Clash / Sing-box
            </Badge>
          </div>
          <p className="text-xs text-muted-foreground leading-relaxed">
            自定义聚合订阅中下发的分流与路由策略。内置开箱即用的专业预设，即使不懂规则也能稳定使用，支持自由定制。
          </p>
        </div>

        <div className="grid grid-cols-3 gap-1.5 w-full sm:flex sm:w-auto sm:items-center sm:gap-2 shrink-0">
          <Button
            variant="outline"
            size="sm"
            onClick={handleResetDefault}
            className="h-8 px-2 sm:px-3 gap-1 sm:gap-1.5 text-xs text-muted-foreground hover:text-foreground justify-center"
            title="恢复为系统推荐默认（国内外智能分流）"
          >
            <RefreshCw className="size-3.5 shrink-0" />
            <span className="sm:hidden">恢复默认</span>
            <span className="hidden sm:inline">恢复默认预设</span>
          </Button>

          <Button
            variant="outline"
            size="sm"
            onClick={handleOpenPreview}
            className="h-8 px-2 sm:px-3 gap-1 sm:gap-1.5 text-xs justify-center"
            title="查看当前节点与规则生成的完整订阅预览"
          >
            <Eye className="size-3.5 text-primary shrink-0" />
            <span className="sm:hidden">预览配置</span>
            <span className="hidden sm:inline">实时预览订阅</span>
          </Button>

          <Button
            size="sm"
            onClick={handleSave}
            disabled={saving}
            className="h-8 px-2 sm:px-3 gap-1 sm:gap-1.5 text-xs shadow-sm bg-primary text-primary-foreground hover:bg-primary/90 justify-center"
          >
            {saving ? (
              <RefreshCw className="size-3.5 animate-spin shrink-0" />
            ) : (
              <Save className="size-3.5 shrink-0" />
            )}
            <span className="sm:hidden">保存配置</span>
            <span className="hidden sm:inline">保存规则配置</span>
          </Button>
        </div>
      </div>

      {/* 预设策略卡片网格 */}
      <div className="space-y-2.5 sm:space-y-3">
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-muted-foreground flex items-center gap-1.5">
            <Sparkles className="size-3.5 text-amber-500 shrink-0" /> 预设策略模式 (点击快速切换)
          </span>
          <span className="text-[11px] text-muted-foreground">
            当前生效：
            <strong className="text-primary ml-1">
              {presets.find((p: RulePreset) => p.id === mode)?.name || "自定义模式"}
            </strong>
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2 sm:gap-3">
          {presets.map((p: RulePreset) => {
            const isSelected = mode === p.id
            return (
              <Card
                key={p.id}
                onClick={() => handleSelectPreset(p)}
                className={`cursor-pointer p-3 sm:p-4 transition-all duration-200 border relative flex flex-col justify-between hover:shadow-sm ${
                  isSelected
                    ? "border-primary bg-primary/5 shadow-sm ring-1 ring-primary/40"
                    : "hover:border-primary/40 bg-card"
                }`}
              >
                <div className="space-y-1.5">
                  <div className="flex items-center justify-between gap-1">
                    <span className="font-semibold text-xs sm:text-sm flex items-center gap-1.5 truncate">
                      {p.id === "smart" && <Sparkles className="size-3.5 text-amber-500 shrink-0" />}
                      {p.id === "minimal" && <Zap className="size-3.5 text-blue-500 shrink-0" />}
                      {p.id === "global" && <Globe className="size-3.5 text-emerald-500 shrink-0" />}
                      {p.id === "custom" && <Code2 className="size-3.5 text-purple-500 shrink-0" />}
                      <span className="truncate">{p.name}</span>
                    </span>
                    <Badge
                      variant={isSelected ? "default" : "secondary"}
                      className={`text-[10px] px-1.5 py-0 shrink-0 ${
                        isSelected ? "bg-primary text-primary-foreground" : ""
                      }`}
                    >
                      {p.badge}
                    </Badge>
                  </div>
                  <p className="text-xs text-muted-foreground leading-relaxed line-clamp-2 sm:line-clamp-3">
                    {p.desc}
                  </p>
                </div>

                <div className="pt-2 sm:pt-3 flex items-center justify-between text-[11px] text-muted-foreground border-t border-border/50 mt-2 sm:mt-3">
                  <span>{p.id === "custom" ? "全自由编辑" : "开箱即用"}</span>
                  {isSelected && (
                    <span className="inline-flex items-center gap-1 font-medium text-primary">
                      <Check className="size-3.5" /> 已启用
                    </span>
                  )}
                </div>
              </Card>
            )
          })}
        </div>
      </div>

      {/* 规则编辑工作区 */}
      <Card className="p-3 sm:p-5 space-y-3 sm:space-y-4 border shadow-sm max-w-full overflow-hidden">
        {/* 编辑器 Tab 栏 (移动端采用 100% 分段控制器，杜绝横向溢出) */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2.5 border-b pb-3">
          <div className="w-full sm:w-auto flex rounded-lg bg-muted/60 p-1 gap-1">
            <button
              type="button"
              onClick={() => setActiveTab("clash")}
              className={`flex-1 sm:flex-none flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-md text-xs font-medium transition-all ${
                activeTab === "clash"
                  ? "bg-background text-foreground shadow-xs font-semibold"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <span className="sm:hidden">Clash 规则</span>
              <span className="hidden sm:inline">Clash / Verge 规则 (rules)</span>
              <Badge variant="outline" className="text-[10px] py-0 px-1 font-mono">
                {clashRuleCount} 条
              </Badge>
            </button>

            <button
              type="button"
              onClick={() => setActiveTab("singbox")}
              className={`flex-1 sm:flex-none flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-md text-xs font-medium transition-all ${
                activeTab === "singbox"
                  ? "bg-background text-foreground shadow-xs font-semibold"
                  : "text-muted-foreground hover:text-foreground"
              }`}
            >
              <span className="sm:hidden">Sing-box 规则</span>
              <span className="hidden sm:inline">Sing-box 路由规则 (route.rules)</span>
              <Badge variant="outline" className="text-[10px] py-0 px-1 font-mono">
                JSON
              </Badge>
            </button>
          </div>

          {activeTab === "singbox" && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleFormatSingboxJson}
              className="h-7 sm:h-8 text-xs gap-1 w-full sm:w-auto justify-center"
            >
              <Code2 className="size-3.5" /> 格式化 JSON
            </Button>
          )}
        </div>

        {/* Clash 编辑器视图 */}
        {activeTab === "clash" && (
          <div className="space-y-3">
            {/* 常用规则一键追加快捷栏 */}
            <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
              <span className="text-[11px] text-muted-foreground mr-0.5 flex items-center gap-1 w-full sm:w-auto font-medium">
                <Plus className="size-3" /> 快捷追加规则:
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleInsertClashRule("- GEOIP,LAN,DIRECT")}
                className="h-6 px-2 text-[11px] text-muted-foreground hover:text-foreground rounded-full"
              >
                局域网 (LAN)
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleInsertClashRule("- GEOIP,CN,DIRECT")}
                className="h-6 px-2 text-[11px] text-muted-foreground hover:text-foreground rounded-full"
              >
                国内直连 (CN)
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleInsertClashRule("- DOMAIN-SUFFIX,cn,DIRECT")}
                className="h-6 px-2 text-[11px] text-muted-foreground hover:text-foreground rounded-full"
              >
                .cn 域名直连
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleInsertClashRule("- DOMAIN-SUFFIX,openai.com,节点选择\n- DOMAIN-SUFFIX,chatgpt.com,节点选择\n- DOMAIN-SUFFIX,anthropic.com,节点选择\n- DOMAIN-SUFFIX,claude.ai,节点选择\n- DOMAIN-KEYWORD,gemini,节点选择")}
                className="h-6 px-2 text-[11px] text-muted-foreground hover:text-foreground rounded-full"
                title="追加 ChatGPT, Claude, Gemini 等 AI 域名"
              >
                <span className="sm:hidden">+ 常用 AI</span>
                <span className="hidden sm:inline">+ 常用 AI (ChatGPT/Claude/Gemini)</span>
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleInsertClashRule("- DOMAIN-SUFFIX,google.com,节点选择\n- DOMAIN-SUFFIX,youtube.com,节点选择\n- DOMAIN-SUFFIX,github.com,节点选择\n- DOMAIN-SUFFIX,twitter.com,节点选择\n- DOMAIN-SUFFIX,x.com,节点选择\n- DOMAIN-SUFFIX,telegram.org,节点选择")}
                className="h-6 px-2 text-[11px] text-muted-foreground hover:text-foreground rounded-full"
                title="追加 Google, YouTube, GitHub, Twitter, Telegram 等常用外网域名"
              >
                <span className="sm:hidden">+ 常用外网</span>
                <span className="hidden sm:inline">+ 常用外网 (Google/YouTube/TG)</span>
              </Button>
              <Button
                variant="outline"
                size="sm"
                onClick={() => handleInsertClashRule("- MATCH,节点选择")}
                className="h-6 px-2 text-[11px] text-muted-foreground hover:text-foreground rounded-full"
              >
                兜底代理 (MATCH)
              </Button>
            </div>

            {/* 规则文本框 */}
            <div className="relative w-full overflow-hidden">
              <textarea
                value={clashRules}
                onChange={(e) => {
                  setClashRules(e.target.value)
                  if (mode !== "custom") setMode("custom")
                }}
                rows={12}
                className="w-full min-w-0 resize-y rounded-md border border-input bg-muted/20 px-2.5 py-2 sm:px-3 sm:py-2.5 text-xs font-mono leading-relaxed placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary shadow-xs box-border overflow-x-auto whitespace-pre sm:rows-16"
                placeholder="# 每行一条规则，如：&#10;- GEOIP,LAN,DIRECT&#10;- DOMAIN-SUFFIX,google.com,节点选择&#10;- GEOIP,CN,DIRECT&#10;- MATCH,节点选择"
                spellCheck={false}
              />
            </div>

            {/* 底部移动端快捷保存与状态栏 */}
            <div className="flex items-center justify-between pt-2 border-t sm:hidden">
              <span className="text-[11px] text-muted-foreground">
                {clashRuleCount} 条有效规则
              </span>
              <Button
                size="sm"
                onClick={handleSave}
                disabled={saving}
                className="h-8 gap-1.5 text-xs bg-primary text-primary-foreground"
              >
                {saving ? <RefreshCw className="size-3.5 animate-spin" /> : <Save className="size-3.5" />}
                <span>保存配置</span>
              </Button>
            </div>

            <div className="rounded-md bg-muted/30 p-2 sm:p-2.5 text-[11px] text-muted-foreground space-y-1">
              <div>
                💡 语法参考：<code>DOMAIN-SUFFIX,domain,策略组</code> | <code>DOMAIN-KEYWORD,keyword,策略组</code> | <code>IP-CIDR,ip/mask,DIRECT</code> | <code>GEOIP,code,策略组</code> | <code>MATCH,策略组</code>
              </div>
              <div>
                支持策略组：<code>节点选择</code>（代理）、<code>自动选择</code>、<code>DIRECT</code>（直连）、<code>REJECT</code>（拦截）
              </div>
            </div>
          </div>
        )}

        {/* Sing-box 编辑器视图 */}
        {activeTab === "singbox" && (
          <div className="space-y-3">
            <div className="relative w-full overflow-hidden">
              <textarea
                value={singboxRules}
                onChange={(e) => {
                  setSingboxRules(e.target.value)
                  if (mode !== "custom") setMode("custom")
                }}
                rows={12}
                className="w-full min-w-0 resize-y rounded-md border border-input bg-muted/20 px-2.5 py-2 sm:px-3 sm:py-2.5 text-xs font-mono leading-relaxed placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-primary shadow-xs box-border overflow-x-auto whitespace-pre sm:rows-16"
                placeholder="[&#10;  { &quot;protocol&quot;: &quot;dns&quot;, &quot;outbound&quot;: &quot;dns-out&quot; },&#10;  { &quot;geoip&quot;: [&quot;cn&quot;], &quot;outbound&quot;: &quot;DIRECT&quot; },&#10;  { &quot;outbound&quot;: &quot;PROXY&quot; }&#10;]"
                spellCheck={false}
              />
            </div>

            {/* 底部移动端快捷保存 */}
            <div className="flex items-center justify-between pt-2 border-t sm:hidden">
              <span className="text-[11px] text-muted-foreground">
                Sing-box JSON 路由规则
              </span>
              <Button
                size="sm"
                onClick={handleSave}
                disabled={saving}
                className="h-8 gap-1.5 text-xs bg-primary text-primary-foreground"
              >
                {saving ? <RefreshCw className="size-3.5 animate-spin" /> : <Save className="size-3.5" />}
                <span>保存配置</span>
              </Button>
            </div>

            <div className="rounded-md bg-muted/30 p-2 sm:p-2.5 text-[11px] text-muted-foreground space-y-1">
              <div>
                💡 语法参考：数组格式 <code>route.rules</code>。常用 Outbound 包括：<code>PROXY</code>、<code>AUTO</code>、<code>DIRECT</code>、<code>BLOCK</code>、<code>dns-out</code>。
              </div>
              <div>
                点击上方「格式化 JSON」可自动校验与排版。
              </div>
            </div>
          </div>
        )}
      </Card>

      {/* 常见问题与说明小贴士 */}
      <Card className="p-3.5 sm:p-4 bg-muted/15 border text-xs text-muted-foreground space-y-2">
        <div className="flex items-center gap-1.5 font-semibold text-foreground">
          <ShieldCheck className="size-4 text-emerald-500 shrink-0" /> 关于分流规则对各客户端的生效机制
        </div>
        <ul className="list-disc list-inside space-y-1 pl-1 text-[11px] sm:text-xs">
          <li>
            <strong>Clash / Mihomo / Verge / Flclash</strong>：订阅自动嵌入上方配置的 Clash <code>rules</code>，客户端刷新订阅即刻获得最新路由分流规则。
          </li>
          <li>
            <strong>Sing-box / SFA / SFI</strong>：订阅自动载入 <code>route.rules</code>，支持 DNS 劫持与域名/IP 规则智能分流。
          </li>
          <li>
            <strong>Shadowrocket / v2rayN</strong>：该类客户端基于 Base64 节点链，客户端本地自带内置规则集（如小火箭配置中的国内直连或全局路由），不受服务端配置影响。
          </li>
          <li>
            <strong>开箱即用保障</strong>：默认使用推荐的「国内外智能分流」规则，无须手动调整即可顺畅使用海外 AI、主流流媒体与国内网站。
          </li>
        </ul>
      </Card>

      {/* 实时预览弹窗 */}
      <Dialog open={previewOpen} onOpenChange={setPreviewOpen}>
        <DialogContent className="w-[96vw] max-w-3xl max-h-[85vh] flex flex-col p-3.5 sm:p-6 overflow-hidden">
          <DialogHeader className="space-y-2">
            <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
              <DialogTitle className="text-sm sm:text-base font-bold flex items-center gap-1.5">
                <Eye className="size-4 text-primary shrink-0" /> 订阅输出实时预览
              </DialogTitle>
              <div className="flex items-center gap-1.5 self-start sm:self-auto">
                <Button
                  variant={previewTab === "clash" ? "secondary" : "ghost"}
                  size="sm"
                  onClick={() => setPreviewTab("clash")}
                  className="h-7 text-xs px-2.5"
                >
                  Clash YAML
                </Button>
                <Button
                  variant={previewTab === "singbox" ? "secondary" : "ghost"}
                  size="sm"
                  onClick={() => setPreviewTab("singbox")}
                  className="h-7 text-xs px-2.5"
                >
                  Sing-box JSON
                </Button>
              </div>
            </div>
            <DialogDescription className="text-xs text-muted-foreground">
              基于当前服务器已启用的节点与当前配置的规则动态实时渲染。
            </DialogDescription>
          </DialogHeader>

          <div className="flex-1 min-h-0 relative flex flex-col overflow-hidden">
            {previewLoading ? (
              <div className="flex h-64 items-center justify-center text-xs text-muted-foreground">
                <RefreshCw className="mr-2 size-4 animate-spin text-primary shrink-0" /> 生成预览中…
              </div>
            ) : previewData ? (
              <div className="flex-1 flex flex-col min-h-0 space-y-2">
                <div className="flex justify-end">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={async () => {
                      const text = previewTab === "clash" ? previewData.clash_yaml : previewData.singbox_json
                      const ok = await copyToClipboard(text)
                      if (ok) toast.success("预览内容已复制")
                      else toast.error("复制失败")
                    }}
                    className="h-7 text-xs gap-1"
                  >
                    <Copy className="size-3" /> 复制配置文本
                  </Button>
                </div>
                <pre className="flex-1 max-h-[50vh] overflow-x-auto overflow-y-auto rounded-lg border bg-muted/40 p-2.5 sm:p-3 text-[11px] sm:text-xs font-mono leading-relaxed select-all">
                  {previewTab === "clash" ? previewData.clash_yaml : previewData.singbox_json}
                </pre>
              </div>
            ) : (
              <div className="py-12 text-center text-xs text-muted-foreground">暂无预览内容</div>
            )}
          </div>
        </DialogContent>
      </Dialog>
    </div>
  )
}
