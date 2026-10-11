import { useId } from 'react'

/** Small SVG charts for the Evidence page, drawn to scale with one x and one y scale each, in the dashboard's
 *  green-gradient style. They only draw what they are given; every number comes from the API. */

const W = 960
type Pad = { l: number; r: number; t: number; b: number }
const PAD: Pad = { l: 56, r: 24, t: 34, b: 30 }

export type Series = { id: string; label: string; values: (number | null)[]; tone: Tone; dashed?: boolean; area?: boolean }
export type Tone = 'deep' | 'leaf' | 'mint' | 'sun' | 'coral' | 'steel' | 'ink'
export type Ref = { y: number; label: string; tone: Tone }

function niceTicks(lo: number, hi: number, n = 4): number[] {
  if (!Number.isFinite(lo) || !Number.isFinite(hi) || lo === hi) return [lo]
  const raw = (hi - lo) / n
  const mag = 10 ** Math.floor(Math.log10(raw))
  const step = [1, 2, 2.5, 5, 10].map((k) => k * mag).find((s) => s >= raw) ?? raw
  const out: number[] = []
  for (let v = Math.ceil(lo / step) * step; v <= hi + 1e-9; v += step) out.push(Number(v.toFixed(6)))
  return out
}

function Defs({ id }: { id: string }) {
  return (
    <defs>
      <linearGradient id={`${id}-deep`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#5d7a5e" /><stop offset="1" stopColor="#3f5a45" /></linearGradient>
      <linearGradient id={`${id}-leaf`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#91ae6e" /><stop offset="1" stopColor="#689d4b" /></linearGradient>
      <linearGradient id={`${id}-mint`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#d2edd7" /><stop offset="1" stopColor="#a9c8a6" /></linearGradient>
      <linearGradient id={`${id}-sun`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#ecc985" /><stop offset="1" stopColor="#e3a83f" /></linearGradient>
      <linearGradient id={`${id}-coral`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#e8a1a1" /><stop offset="1" stopColor="#d96868" /></linearGradient>
      <linearGradient id={`${id}-steel`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#8fb6cc" /><stop offset="1" stopColor="#5b93b0" /></linearGradient>
      <linearGradient id={`${id}-ink`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#8d9d8f" /><stop offset="1" stopColor="#5c695f" /></linearGradient>
      {(['deep', 'leaf', 'sun', 'coral', 'steel'] as const).map((tone) => (
        <linearGradient key={tone} id={`${id}-${tone}-area`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" className={`ev-stop tone-${tone}`} stopOpacity="0.32" /><stop offset="1" className={`ev-stop tone-${tone}`} stopOpacity="0" />
        </linearGradient>
      ))}
    </defs>
  )
}

function Legend({ items }: { items: { label: string; tone: Tone; dashed?: boolean }[] }) {
  return (
    <ul className="ev-legend">
      {items.map((it) => <li key={it.label}><i className={`tone-${it.tone} ${it.dashed ? 'dashed' : ''}`} />{it.label}</li>)}
    </ul>
  )
}

/** Lines over time (or any ordered x), with optional limit lines and a soft area under chosen series. */
export function LineChart({ x, series, refs = [], height = 240, yFmt = (v) => String(v), label, yMin, yMax, width = W, title }: {
  x: string[]; series: Series[]; refs?: Ref[]; height?: number; yFmt?: (v: number) => string; label: string; yMin?: number; yMax?: number
  /** drawing width: narrower for a chart that sits in half a column, so its text stays readable */
  width?: number; title?: string
}) {
  const id = useId().replace(/:/g, '')
  const vals = series.flatMap((s) => s.values).filter((v): v is number => v !== null && Number.isFinite(v)).concat(refs.map((r) => r.y))
  const lo0 = yMin ?? Math.min(...vals)
  const hi0 = yMax ?? Math.max(...vals)
  const padY = (hi0 - lo0) * 0.08 || 1
  const lo = yMin ?? lo0 - padY
  const hi = yMax ?? hi0 + padY
  const n = x.length
  const px = (i: number) => PAD.l + (i * (width - PAD.l - PAD.r)) / Math.max(1, n - 1)
  const py = (v: number) => PAD.t + (1 - (v - lo) / (hi - lo || 1)) * (height - PAD.t - PAD.b)
  const every = Math.max(1, Math.round(n / 8))
  const path = (v: (number | null)[]) => v.map((p, i) => (p === null ? '' : `${i && v[i - 1] !== null ? 'L' : 'M'}${px(i).toFixed(1)},${py(p).toFixed(1)}`)).join('')
  const areaPath = (v: (number | null)[]) => {
    const pts = v.map((p, i) => (p === null ? null : [px(i), py(p)] as const)).filter((p): p is readonly [number, number] => p !== null)
    if (pts.length < 2) return ''
    return `M${pts[0][0]},${py(lo)} ${pts.map(([a, b]) => `L${a.toFixed(1)},${b.toFixed(1)}`).join(' ')} L${pts[pts.length - 1][0]},${py(lo)}Z`
  }
  return (
    <figure className="ev-chart">
      {title && <figcaption className="ev-cap">{title}</figcaption>}
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={label}>
        <Defs id={id} />
        <rect x={PAD.l} y={PAD.t} width={W - PAD.l - PAD.r} height={height - PAD.t - PAD.b} rx={8} className="ev-plot" />
        {niceTicks(lo, hi).map((v) => (
          <g key={v}><line x1={PAD.l} x2={width - PAD.r} y1={py(v)} y2={py(v)} className="ev-grid" />
            <text x={PAD.l - 8} y={py(v) + 4} textAnchor="end" className="ev-tick">{yFmt(v)}</text></g>
        ))}
        {x.map((t, i) => (i % every === 0 || i === n - 1 ? (
          <text key={`${t}-${i}`} x={px(i)} y={height - 8} textAnchor={i === 0 ? 'start' : i === n - 1 ? 'end' : 'middle'} className="ev-tick"
            display={i !== n - 1 && n - 1 - i < every / 2 ? 'none' : undefined}>{t}</text>) : null))}
        {series.filter((s) => s.area).map((s) => <path key={`a-${s.id}`} d={areaPath(s.values)} fill={`url(#${id}-${s.tone}-area)`} />)}
        {refs.map((r) => (
          <g key={r.label}><line x1={PAD.l} x2={width - PAD.r} y1={py(r.y)} y2={py(r.y)} className={`ev-ref tone-${r.tone}`} />
            <text x={PAD.l + 8} y={py(r.y) - 6} textAnchor="start" className={`ev-ref-label tone-${r.tone}`}>{r.label}</text></g>
        ))}
        {series.map((s) => <path key={s.id} d={path(s.values)} className={`ev-line tone-${s.tone} ${s.dashed ? 'dashed' : ''}`} />)}
      </svg>
      <Legend items={series.map((s) => ({ label: s.label, tone: s.tone, dashed: s.dashed }))} />
    </figure>
  )
}

/** One bar per category, coloured per bar, with an optional reference line (a limit or a target). */
export function BarChart({ labels, values, tones, refs = [], height = 220, yFmt = (v) => String(v), label, valueFmt }: {
  labels: string[]; values: number[]; tones: Tone[]; refs?: Ref[]; height?: number; yFmt?: (v: number) => string; label: string
  valueFmt?: (v: number) => string
}) {
  const id = useId().replace(/:/g, '')
  const all = values.concat(refs.map((r) => r.y))
  const hi = Math.max(...all, 0) * 1.12 || 1
  const lo = Math.min(0, ...all)
  const n = labels.length
  const slot = (W - PAD.l - PAD.r) / n
  const bw = Math.min(64, slot * 0.62)
  const py = (v: number) => PAD.t + (1 - (v - lo) / (hi - lo || 1)) * (height - PAD.t - PAD.b)
  return (
    <figure className="ev-chart">
      <svg viewBox={`0 0 ${W} ${height}`} role="img" aria-label={label}>
        <Defs id={id} />
        <rect x={PAD.l} y={PAD.t} width={W - PAD.l - PAD.r} height={height - PAD.t - PAD.b} rx={8} className="ev-plot" />
        {niceTicks(lo, hi).map((v) => (
          <g key={v}><line x1={PAD.l} x2={W - PAD.r} y1={py(v)} y2={py(v)} className="ev-grid" />
            <text x={PAD.l - 8} y={py(v) + 4} textAnchor="end" className="ev-tick">{yFmt(v)}</text></g>
        ))}
        {values.map((v, i) => {
          const cx = PAD.l + slot * (i + 0.5)
          return (
            <g key={labels[i]}>
              <rect x={cx - bw / 2} y={Math.min(py(v), py(0))} width={bw} height={Math.max(1, Math.abs(py(0) - py(v)))} rx={5} fill={`url(#${id}-${tones[i]})`}>
                <title>{`${labels[i]}: ${valueFmt ? valueFmt(v) : v}`}</title></rect>
              <text x={cx} y={Math.min(py(v), py(0)) - 6} textAnchor="middle" className="ev-val">{valueFmt ? valueFmt(v) : v}</text>
              <text x={cx} y={height - 8} textAnchor="middle" className="ev-tick">{labels[i]}</text>
            </g>
          )
        })}
        {refs.map((r) => (
          <g key={r.label}><line x1={PAD.l} x2={W - PAD.r} y1={py(r.y)} y2={py(r.y)} className={`ev-ref tone-${r.tone}`} />
            <text x={PAD.l + 8} y={py(r.y) - 6} textAnchor="start" className={`ev-ref-label tone-${r.tone}`}>{r.label}</text></g>
        ))}
      </svg>
    </figure>
  )
}

/** Groups of bars side by side (for example, each model's error on each street), with an optional target line. */
export function GroupedBars({ groups, series, refs = [], height = 240, yFmt = (v) => String(v), label, valueFmt = (v) => String(v) }: {
  groups: string[]; series: { label: string; tone: Tone; values: (number | null)[] }[]; refs?: Ref[]; height?: number
  yFmt?: (v: number) => string; label: string; valueFmt?: (v: number) => string
}) {
  const id = useId().replace(/:/g, '')
  const vals = series.flatMap((s) => s.values).filter((v): v is number => v !== null).concat(refs.map((r) => r.y))
  const hi = Math.max(...vals, 0) * 1.15 || 1
  const slot = (W - PAD.l - PAD.r) / groups.length
  const bw = Math.min(30, (slot * 0.78) / series.length)
  const py = (v: number) => PAD.t + (1 - v / hi) * (height - PAD.t - PAD.b)
  return (
    <figure className="ev-chart">
      <svg viewBox={`0 0 ${W} ${height}`} role="img" aria-label={label}>
        <Defs id={id} />
        <rect x={PAD.l} y={PAD.t} width={W - PAD.l - PAD.r} height={height - PAD.t - PAD.b} rx={8} className="ev-plot" />
        {niceTicks(0, hi).map((v) => (
          <g key={v}><line x1={PAD.l} x2={W - PAD.r} y1={py(v)} y2={py(v)} className="ev-grid" />
            <text x={PAD.l - 8} y={py(v) + 4} textAnchor="end" className="ev-tick">{yFmt(v)}</text></g>
        ))}
        {groups.map((g, gi) => {
          const cx = PAD.l + slot * (gi + 0.5)
          const start = cx - (bw * series.length) / 2
          return (
            <g key={g}>
              {series.map((s, si) => {
                const v = s.values[gi]
                if (v === null || v === undefined) return null
                return <rect key={s.label} x={start + si * bw + 1} y={py(v)} width={bw - 2} height={Math.max(1, py(0) - py(v))} rx={4}
                  fill={`url(#${id}-${s.tone})`}><title>{`${g} · ${s.label}: ${valueFmt(v)}`}</title></rect>
              })}
              <text x={cx} y={height - 8} textAnchor="middle" className="ev-tick">{g}</text>
            </g>
          )
        })}
        {refs.map((r) => (
          <g key={r.label}><line x1={PAD.l} x2={W - PAD.r} y1={py(r.y)} y2={py(r.y)} className={`ev-ref tone-${r.tone}`} />
            <text x={PAD.l + 8} y={py(r.y) - 6} textAnchor="start" className={`ev-ref-label tone-${r.tone}`}>{r.label}</text></g>
        ))}
      </svg>
      <Legend items={series.map((s) => ({ label: s.label, tone: s.tone }))} />
    </figure>
  )
}

/** Horizontal stacked bars: each row a whole (for example a street's states), each part a share of it. */
export function StackedRows({ rows, parts, label, fmt = (v) => v.toLocaleString('en-IN') }: {
  rows: { label: string; values: number[] }[]; parts: { label: string; tone: Tone }[]; label: string; fmt?: (v: number) => string
}) {
  const max = Math.max(...rows.map((r) => r.values.reduce((a, b) => a + b, 0)), 1)
  return (
    <figure className="ev-chart">
      <div className="ev-stack" role="img" aria-label={label}>
        {rows.map((r) => {
          const total = r.values.reduce((a, b) => a + b, 0)
          return (
            <div key={r.label} className="ev-stack-row">
              <span className="ev-stack-label">{r.label}</span>
              <span className="ev-stack-track">
                {r.values.map((v, i) => v > 0 && (
                  <span key={parts[i].label} className={`ev-seg tone-${parts[i].tone}`} style={{ width: `${(v / max) * 100}%` }}
                    title={`${parts[i].label}: ${fmt(v)}`} />
                ))}
              </span>
              <span className="ev-stack-total num">{fmt(total)}</span>
            </div>
          )
        })}
      </div>
      <Legend items={parts.map((p) => ({ label: p.label, tone: p.tone }))} />
    </figure>
  )
}

/** Two values per row on a logarithmic axis (for example screen and solver time), with the ratio between them. */
export function LogPairs({ rows, a, b, label, unit }: {
  rows: { label: string; a: number; b: number }[]; a: { label: string; tone: Tone }; b: { label: string; tone: Tone }; label: string; unit: string
}) {
  const vals = rows.flatMap((r) => [r.a, r.b]).filter((v) => v > 0)
  const lo = 10 ** Math.floor(Math.log10(Math.min(...vals)))
  const hi = 10 ** Math.ceil(Math.log10(Math.max(...vals)))
  const rowH = 34
  const height = PAD.t + rows.length * rowH + PAD.b
  const L = 200
  const px = (v: number) => L + ((Math.log10(v) - Math.log10(lo)) / (Math.log10(hi) - Math.log10(lo) || 1)) * (W - L - 90)
  const decades: number[] = []
  for (let d = lo; d <= hi * 1.0001; d *= 10) decades.push(d)
  return (
    <figure className="ev-chart">
      <svg viewBox={`0 0 ${W} ${height}`} role="img" aria-label={label}>
        <rect x={L} y={PAD.t - 8} width={W - L - 90} height={rows.length * rowH + 8} rx={8} className="ev-plot" />
        {decades.map((d) => (
          <g key={d}><line x1={px(d)} x2={px(d)} y1={PAD.t - 8} y2={PAD.t + rows.length * rowH} className="ev-grid" />
            <text x={px(d)} y={height - 8} textAnchor="middle" className="ev-tick">{`${d} ${unit}`}</text></g>
        ))}
        {rows.map((r, i) => {
          const y = PAD.t + i * rowH + rowH / 2 - 4
          return (
            <g key={r.label}>
              <text x={L - 10} y={y + 4} textAnchor="end" className="ev-tick ev-row-label">{r.label}</text>
              <line x1={px(Math.min(r.a, r.b))} x2={px(Math.max(r.a, r.b))} y1={y} y2={y} className="ev-span" />
              <circle cx={px(r.a)} cy={y} r={7} className={`ev-dot tone-${a.tone}`}><title>{`${a.label}: ${r.a} ${unit}`}</title></circle>
              <circle cx={px(r.b)} cy={y} r={7} className={`ev-dot tone-${b.tone}`}><title>{`${b.label}: ${r.b} ${unit}`}</title></circle>
              <text x={W - 84} y={y + 4} className="ev-val">{`${Math.round((r.b / r.a) * 10) / 10}×`}</text>
            </g>
          )
        })}
      </svg>
      <Legend items={[a, b]} />
    </figure>
  )
}
