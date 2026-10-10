import { ArrowDownToLine, ArrowUpFromLine, Gauge, Plug, Sun, X } from 'lucide-react'
import { one } from '../../format'
import { useT } from '../../i18n'
import type { HomeNow } from './StreetView'
import { homeClass } from './voltage'

type Props = {
  home: number
  phase: string
  kwp: number
  now: HomeNow
  shared: boolean
  limits: { min: number; max: number }
  onClose: () => void
}

const STATUS: Record<string, 'v_ok' | 'v_near' | 'v_over' | 'v_under' | 'v_none'> = {
  'v-ok': 'v_ok', 'v-near': 'v_near', 'v-over': 'v_over', 'v-under': 'v_under', 'v-none': 'v_none',
}

/** One home at this quarter hour: what its panels make, what it uses, which way its wire carries the difference,
 *  and its voltage against the rule. */
export default function HomeCard({ home, phase, kwp, now, shared, limits, onClose }: Props) {
  const t = useT()
  const cls = homeClass(now.v, limits)
  const back = now.net < -0.02
  const by = now.v === null ? 0 : now.v > limits.max ? now.v - limits.max : now.v < limits.min ? limits.min - now.v : 0
  return (
    <div className={`home-card ${cls}`} role="status">
      <div className="hc-head">
        <span className={`hc-ph ph-${phase.toLowerCase()}`}>{phase}</span>
        <b>{t('player.home_detail', { home: home + 1 })}</b>
        <span className="muted">{kwp > 0 ? t('player.home_solar', { kwp: one(kwp) }) : t('player.home_nosolar')}</span>
        <button className="hc-close" onClick={onClose} aria-label={t('player.close')}><X size={16} /></button>
      </div>
      <div className="hc-grid">
        <div><Sun size={18} className="i-sun" /><span className="k">{t('sv.solar_now')}</span><span className="v">{one(now.solar)} kW</span></div>
        <div><Plug size={18} className="i-plug" /><span className="k">{t('sv.demand_now')}</span><span className="v">{one(now.demand)} kW</span></div>
        <div className={back ? 'back' : 'draw'}>
          {back ? <ArrowUpFromLine size={18} /> : <ArrowDownToLine size={18} />}
          <span className="k">{back ? t('sv.reverse') : t('sv.forward')}</span>
          <span className="v">{one(Math.abs(now.net))} kW</span>
        </div>
        <div className={cls}>
          <Gauge size={18} />
          <span className="k">{t('player.home_v')}</span>
          <span className="v">{now.v === null ? '—' : `${one(now.v)} V`}</span>
        </div>
      </div>
      <p className="hc-say">
        {t(`player.${STATUS[cls]}` as 'player.v_ok')}
        {by > 0 && ` · ${t('sv.beyond', { v: one(by) })}`}
        {back && ` · ${t('sv.cause')}`}
      </p>
      {shared && <p className="muted hc-note">{t('sv.shared')}</p>}
    </div>
  )
}
