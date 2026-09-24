/**
 * 跨浏览器与跨协议 (HTTP / HTTPS) 通用剪贴板复制工具
 * 完美解决非安全上下文 (如纯 IP 访问 http://156.226.173.102:80) 下
 * 现代浏览器禁用 navigator.clipboard 导致 writeText 报 undefined 错误的问题。
 */
export async function copyToClipboard(text: string): Promise<boolean> {
  if (!text) return false

  // 1. 若处于安全上下文 (HTTPS 或 localhost)，优先使用原生现代 Clipboard API
  if (typeof navigator !== "undefined" && navigator.clipboard && window.isSecureContext) {
    try {
      await navigator.clipboard.writeText(text)
      return true
    } catch {
      // 若因权限或其他原因失败，无缝降级到 fallback 机制
    }
  }

  // 2. 兜底方案：创建不可见 textarea 配合 document.execCommand('copy')
  try {
    const textArea = document.createElement("textarea")
    textArea.value = text

    // 固定定位并移除视觉干扰，防止移动端滚动跳跃
    textArea.style.position = "fixed"
    textArea.style.top = "0"
    textArea.style.left = "-9999px"
    textArea.style.width = "2em"
    textArea.style.height = "2em"
    textArea.style.padding = "0"
    textArea.style.border = "none"
    textArea.style.outline = "none"
    textArea.style.boxShadow = "none"
    textArea.style.background = "transparent"
    textArea.style.opacity = "0"
    textArea.setAttribute("readonly", "")

    document.body.appendChild(textArea)
    textArea.focus()
    textArea.select()
    textArea.setSelectionRange(0, text.length)

    const successful = document.execCommand("copy")
    document.body.removeChild(textArea)
    return successful
  } catch (err) {
    console.error("[copyToClipboard fallback failed]", err)
    return false
  }
}
