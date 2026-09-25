// Every figure on the page passes through this file, making it the one place
// worth a check. Run it with `npm test`: Node strips the types itself, so this
// requires no runner, framework or dependency.
//
// Nothing imports it, so the bundle never includes it.
import {
  axisBytes, axisTop, bytes, cpuName, daysUntil, despike, osName, pair, quarters, timeTicks, uptime,
} from "./format.ts"

let failed = 0
function eq(got: unknown, want: unknown, what: string) {
  const [a, b] = [JSON.stringify(got), JSON.stringify(want)]
  if (a !== b) {
    failed++
    console.error(`✗ ${what}\n    得到 ${a}\n    期望 ${b}`)
  }
}

// bytes: the significant-digit ladder, and the sub-byte case that would
// otherwise print "512 undefined".
eq(bytes(0), "0 B", "bytes(0)")
eq(bytes(0.5), "0 B", "bytes(0.5) 不能落到 UNITS[-1]")
eq(bytes(-1), "0 B", "bytes(负数)")
eq(bytes(1023), "1023 B", "bytes 在 B 档不带小数")
eq(bytes(1024), "1.00 KB", "bytes(1 KiB)")
eq(bytes(10 * 1024), "10.0 KB", "两位数留一位小数")
eq(bytes(100 * 1024), "100 KB", "三位数不留小数")
eq(bytes(1024, 1), "1.0 KB", "digits 覆盖默认档位")

// pair: one unit when both sides share it, two when they do not.
eq(pair(300 * 1024 ** 2, 900 * 1024 ** 2), "300.00 / 900.00 MB", "同单位只写一次")
eq(pair(300 * 1024 ** 2, 3 * 1024 ** 3), "300 MB / 3.00 GB", "跨单位各写各的")

// axisBytes: ticks under three digits keep one decimal, or a narrow axis repeats
// a label; a trailing .0 adds nothing.
eq(axisBytes(3.2 * 1024 ** 3), "3.2 GB", "窄轴刻度保留一位")
eq(axisBytes(2 * 1024 ** 3), "2 GB", "整数刻度不写 .0")
eq(axisBytes(0), "0 B", "零刻度")

// axisTop: the top is derived from a round gridline, so quarters() lands on round
// values in the unit the axis is printed in.
eq(axisTop(0.4, 4, 10, 100), 4, "闲置机器拿到地板值")
eq(axisTop(63, 4, 10, 100), 80, "63% -> 0/20/40/60/80")
eq(axisTop(200, 4, 10, 100), 100, "百分比封顶")
eq(axisTop(25_000_000, 1024, 1024), 32 * 1024 ** 2, "字节轴按 1024 取整")
eq(quarters(32 * 1024 ** 2).map(axisBytes), ["0 B", "8 MB", "16 MB", "24 MB", "32 MB"], "四条网格线都是整值")
// 四条刻度为 step·[1,2,3,4]，约束落在第三条：3m 必须能被 axisBytes 精确打印，
// 而它只保留一位小数。2 的幂均满足；半档 384 与 768 不满足，其第三条刻度为
// 1.125 Ki 与 2.25 Ki，将被打印为 "1.1" 与 "2.3"。这两档恰好覆盖 1–1.5 MB/s
// 与 2–3 MB/s。断言针对标签本身，仅比较轴顶比例无法发现该问题。
eq(quarters(axisTop(2_621_440, 1024, 1024)).map(axisBytes),
   ["0 B", "1 MB", "2 MB", "3 MB", "4 MB"], "峰值 2.5 MB/s 的四条刻度")
eq(quarters(axisTop(1_258_291, 1024, 1024)).map(axisBytes),
   ["0 B", "512 KB", "1 MB", "1.5 MB", "2 MB"], "峰值 1.2 MB/s 的四条刻度")
// 轴顶必须取自梯子而非数据本身。十进制梯子配合 1024 进制的 scale 最大仅到
// 10·1024^k，越过该档后 find 落空，`?? target` 将轴顶回退为 max，网格线随之变为
// max/4 这类非整值，正是本函数要避免的情形。该回退仅在 [4,40)·1024^k 的窄带内
// 不出问题，而 40 KB/s–4 MB/s 恰是 VPS 最常见的区间。
for (const max of [3_000, 300_000, 3_000_000, 300_000_000]) {
  const top = axisTop(max, 1024, 1024)
  eq(top > max, true, `${max} B/s 的轴顶不能等于数据本身`)
  // 上界为 2 而非 1.5：梯子移除半档后，最坏情况是下一档 2 的幂。
  eq(top / max < 2, true, `${max} B/s 的轴顶不能浪费整块面板`)
}

// timeTicks: round clock values, phased on local midnight rather than the epoch,
// and never more than requested.
{
  const day = 86_400_000
  const to = Date.now()
  const ticks = timeTicks(to - day, to)
  eq(ticks.length <= 8, true, `24 小时窗最多 8 个刻度（得到 ${ticks.length}）`)
  eq(
    ticks.every((t) => new Date(t).getMinutes() === 0 && new Date(t).getSeconds() === 0),
    true,
    "刻度落在整点上",
  )
  eq(
    ticks.every((t, i) => i === 0 || t - ticks[i - 1] === ticks[1] - ticks[0]),
    true,
    "刻度间距均匀",
  )
  eq(timeTicks(to, to - day), [], "反向区间不产出刻度")
}

// daysUntil: whole days, negative once past, null when there is no date.
{
  const at = (days: number) => {
    const d = new Date()
    d.setDate(d.getDate() + days)
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`
  }
  eq(daysUntil(at(10)), 10, "十天后")
  eq(daysUntil(at(-3)), -3, "已过期为负")
  eq(daysUntil(null), null, "无到期日")
  eq(daysUntil("不是日期"), null, "无法解析的日期")
}

eq(uptime(0), "—", "没上报过就不写时长")
eq(uptime(90), "1 分", "不足一小时")
eq(uptime(3 * 3600 + 25 * 60), "3 小时 25 分", "不足一天")
eq(uptime(2 * 86400 + 5 * 3600), "2 天 5 小时", "超过一天不再写分钟")

// despike：孤立的尖峰被拉回邻域，持续的高延迟保留，超时仍是缺口。
{
  const flat = [20, 21, 20, 22, 21, 20, 21]
  eq(despike(flat), flat, "没有离群点就原样返回")
  eq(despike([20, 21, 20, 900, 21, 20, 21])[3], 21, "孤立尖峰替换为窗口中位数")
  // 一段持续的高延迟是真实状况而非尖峰：窗口内多数样本同样高，中位数随之抬高。
  // 只断言尖峰那一点会漏掉这条——滑动中位数同样能通过前一条断言。
  eq(despike([20, 21, 300, 310, 305, 300, 21, 20]).slice(2, 6), [300, 310, 305, 300], "持续升高不被削掉")
  eq(despike([20, null, 900, null, 21]), [20, null, 21, null, 21], "超时保持为缺口，不参与比较")
  // 延迟以整毫秒存储，稳定线路的窗口内多数样本完全相同，绝对中位差为 0。不设下限
  // 时这条断言会失败，而它正是削峰要处理的形状：平直的线加一个 2 秒的桶。
  eq(despike([180, 180, 181, 180, 2000, 180, 180, 181, 180])[4], 180, "平直线路上的尖峰同样被削掉")
  // 下限不能低到把正常抖动也当成尖峰：整毫秒的数据里 1 ms 的起伏是常态。
  eq(despike([180, 181, 180, 180, 181, 180, 180]), [180, 181, 180, 180, 181, 180, 180], "1 ms 抖动原样保留")
}

eq(osName("Debian GNU/Linux 12 (bookworm)"), "Debian 12", "发行版名去掉代号")
eq(cpuName("Intel(R) Xeon(R) CPU E5-2680 8-Core Processor"), "Intel Xeon E5-2680", "CPU 名去掉商标和核数")

if (failed) {
  console.error(`\n${failed} 项不通过`)
  throw new Error("format 校验未通过")
}
console.log("format 校验通过")
