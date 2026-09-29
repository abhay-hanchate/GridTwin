export type ScenarioId = 'S1' | 'S2' | 'S3' | 'S4' | 'S5'

export interface Scenario {
  id: ScenarioId
  name: string
  pv_share: number
  band: '10' | '6'
  default_date: string
}

export interface Violation {
  type: 'overvoltage' | 'undervoltage' | 'line_overload' | 'trafo_overload'
  element: string
  id: number
  value: number
  limit: number
}

export interface Step {
  t: string
  max_vm_pu: number
  min_vm_pu: number
  trafo_loading_pct: number
  pv_kw: number
  load_kw: number
  upstream_vm_pu: number
  violations: Violation[]
  bus_vm_pu: Record<string, number>
  line_loading_pct: Record<string, number>
  solver_failed?: boolean
}

export interface RunResult {
  scenario_id: ScenarioId
  name: string
  pv_share: number
  band: string
  date: string
  limits: { vm_min_pu: number; vm_max_pu: number; loading_max_pct: number }
  steps: Step[]
  summary: {
    max_vm_pu: number
    min_vm_pu: number
    violation_steps: number
    violation_steps_without_solar: number
    violation_steps_from_solar: number
    solver_failed_steps: number
    pv_kwh: number
    curtailed_kwh: number
    losses_kwh: number
    homes_profiled: number
  }
  provenance: Record<string, string>
}

export interface GridTopology {
  buses: { id: number; x: number; y: number; house: boolean; pv: boolean }[]
  lines: { id: number; from: number; to: number; length_m: number }[]
  trafo: { lv_bus: number; sn_kva: number }
}

export interface Snapshot {
  max_vm_pu: number
  min_vm_pu: number
  violation_steps: number
}

export interface ActionResult {
  action_id: string
  label: string
  kind: string
  params: Record<string, number>
  acceptable: boolean
  remaining_violation_steps: number
  before: Snapshot
  after: Snapshot
  cost: { curtailed_kwh: number; losses_kwh: number; battery_throughput_kwh: number }
  rank: number | null
  reason_codes: string[]
}

export interface ActionsResult {
  scenario_id: ScenarioId
  date: string
  band: string
  worst_bus: number
  before: Snapshot
  actions: ActionResult[]
  verdict: { safe_action_found: boolean; recommended: string | null; message: string }
}

export interface ForecastResult {
  target: 'solar' | 'demand'
  unit: string
  date: string
  points: { t: string; p10: number; p50: number; p90: number; actual: number }[]
}

export interface ModelMetrics {
  mae_p50: number
  p10_p90_coverage: number
  mae_persistence: number
  skill_vs_persistence: number
  train: string
  test: string
  [key: string]: number | string
}

export interface EarlyWarning {
  date: string
  risk_band: 'p10' | 'p50' | 'p90'
  demand_mode: 'historical_proxy'
  demand_proxy_date: string
  cases: Record<'p10' | 'p50' | 'p90' | 'actual', {
    violation_steps: number
    max_vm_pu: number
    first_unsafe: string | null
    unsafe_times: string[]
  }>
  provenance: Record<string, string>
}

export interface LiveForecast {
  target: string
  unit: string
  date: string
  generated_at: string
  weather_source: string
  weather_url: string
  model: string
  points: { t: string; p10: number; p50: number; p90: number }[]
}

export interface LiveWarning {
  date: string
  risk_band: 'p10' | 'p50' | 'p90'
  demand_mode: string
  demand_proxy_date: string
  pv_share: number
  band: string
  cases: Record<'p10' | 'p50' | 'p90', {
    violation_steps: number
    max_vm_pu: number
    first_unsafe: string | null
    unsafe_times: string[]
  }>
  predicted: {
    violation_steps: number
    max_vm_pu: number
    first_unsafe: string | null
    unsafe_times: string[]
  }
  provenance: Record<string, string>
}

export interface SimStep {
  max_vm_pu: number
  min_vm_pu: number
  pv_kw: number
  pv_available_kw: number
  load_kw: number
  inverter_kvar: number
  battery_kw: number
  tap_pos: number
  unsafe: boolean
}

export interface SimSide {
  vm: (number[] | null)[]
  steps: SimStep[]
  summary: RunResult['summary']
}

/** The same day simulated twice (left vs right), step by step. */
export interface SimResult {
  date: string
  limits: { vm_min_pu: number; vm_max_pu: number }
  times: string[]
  bus_ids: number[]
  before: SimSide
  after: SimSide
  action_id?: string
  label?: string
  kind?: string
}

export interface SummaryRow {
  id: ScenarioId
  name: string
  pv_share: number
  band: string
  limits: { vm_min_pu: number; vm_max_pu: number }
  max_vm_pu: number
  min_vm_pu: number
  violation_steps: number
  violation_steps_without_solar: number
  violation_steps_from_solar: number
  pv_kwh: number
}

export interface Insights {
  meters: number
  readings: number
  median_v: number
  share_above_6pct: number
  share_above_10pct: number
  share_below_10pct: number
}

export interface HostingCapacityPoint {
  pv_share: number
  solar_homes: number
  installed_kw: number
  unsafe_steps_without_fix: number
  unsafe_steps_with_fix: number
  solver_failed_steps_without_fix: number
  solver_failed_steps_with_fix: number
  max_voltage_without_fix: number
  max_voltage_with_fix: number
  safe_without_fix: boolean
  safe_with_fix: boolean
}

export interface HostingCapacitySummary {
  pv_share: number
  solar_homes: number
  installed_kw: number
  unsafe_steps: number
  found_safe_level: boolean
}

export interface HostingCapacityResult {
  date: string
  band: string
  total_homes: number
  kw_per_solar_home: number
  resolution_percent: number
  baseline_unsafe_steps: number
  recommended_action: string
  criteria: { without_fix: string; with_fix: string }
  capacity: { without_fix: HostingCapacitySummary; with_fix: HostingCapacitySummary }
  points: HostingCapacityPoint[]
}
