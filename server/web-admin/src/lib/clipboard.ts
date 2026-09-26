/**
 * 跨浏览器与跨协议 (HTTP / HTTPS) 通用剪贴板复制工具
 * 完美解决非安全上下文 (如纯 IP 访问 http://156.226.173.102:80) 下
 * 现代浏览器禁用 navigator.clipboard 导致 writeText 报 undefined 错误的问题。
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  if (!text) return false

  // 1. 若原生现代 Clipboard API 可用，优先尝试
  if (typeof navigator !== "undefined" && navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch {
      // 若因权限、非安全上下文 (HTTP) 或其他原因失败，无缝降级到 fallback 机制
    }
  }

  // 2. 兜底方案：创建不可见 textarea 配合 document.execCommand('copy')
  try {
    const textArea = document.createElement("textarea")
    textArea.value = text

    // 关键点：如果当前有弹窗/Modal/Dialog (如 Radix UI Dialog)，必须将 textarea 挂载到该弹窗内部，
    // 否则 Radix 的 FocusScope (焦点陷阱) 会在 textArea.focus() 时立即将焦点抢回弹窗内部，
    // 导致选区丢失，document.execCommand('copy') 虽返回 true 但实际剪贴板内容为空！
    const activeEl = document.activeElement as HTMLElement | null
    const container =
      activeEl?.closest('[role="dialog"]') ||
      document.querySelector('[role="dialog"]') ||
      document.body

    // 关键点：不要使用 left: -9999px 或 display: none，也不要加 readonly！
    // 某些浏览器对负坐标离屏或只读的 textarea 会禁止选区复制。
    // 使用 fixed 定位在当前视口左上角，高宽微小，微透明，阻止鼠标事件。
    textArea.style.position = "fixed"
    textArea.style.top = "0"
    textArea.style.left = "0"
    textArea.style.width = "20px"
    textArea.style.height = "20px"
    textArea.style.padding = "0"
    textArea.style.border = "none"
    textArea.style.outline = "none"
    textArea.style.boxShadow = "none"
    textArea.style.background = "transparent"
    textArea.style.opacity = "0.01"
    textArea.style.zIndex = "999999"
    textArea.style.pointerEvents = "none"
    textArea.setAttribute("tabindex", "-1")
    textArea.setAttribute("aria-hidden", "true")

    container.appendChild(textArea)
    textArea.focus({ preventScroll: true })
    textArea.select()
    textArea.setSelectionRange(0, text.length)

    const successful = document.execCommand("copy")
    container.removeChild(textArea)

    if (activeEl && typeof activeEl.focus === "function") {
      try {
        activeEl.focus({ preventScroll: true })
      } catch {
        // ignore
      }
    }

    return successful
  } catch (err) {
    console.error("[copyToClipboard fallback failed]", err)
    return false
  }
}
