/** Response shapes of /api/v2 (plan section 9 and task P8.3; verdict fields from engine/verdict.py). */

export type Provenance = 'observed' | 'modeled' | 'benchmark'
export type Level = 'ok' | 'watch' | 'act'
export type LimitType = 'overvoltage' | 'undervoltage' | 'line_overload' | 'trafo_overload' | 'solver_failure'

export interface Rule {
  id: string
  label: string
  vmin_v: number
  vmax_v: number
  region: string
  source: string
  verification: string
}

export interface Risk {
  date: string
  network: string
  rule: string
  level: Level
  p_unsafe: number[]                       // 96 steps
  t?: string[]                             // HH:MM per step
  thresholds?: { watch: number; act: number }
  expected_unsafe_hours: { mean: number; p10: number; p90: number }
  first_watch: string | null
  first_act: string | null
  peak_voltage_v: { p10: number; p50: number; p90: number }
  window_risk: Record<string, number>
  shares: Partial<Record<LimitType, number>>
  provenance: Record<string, string>
  calibration?: { reliable?: boolean; raw: number[]; calibrated: number[] }
}

export interface BindingLimit {
  type: LimitType
  steps: number
  worst: { value: number; limit: number }  // per unit of 230 V for voltage, percent for loading
}

export interface Verdict {
  safe_action_found: boolean
  recommended: string | null
  closest: string | null
  binding_limit: BindingLimit | null
  still_needs?: string
  baseline_unsafe_steps: number
}

export interface OutcomeDetails {
  phase_moves?: { home: number; from: string; to: string }[]
  export_limits?: { homes: number[]; t: string[]; kw: number[][] }   // kw[home][step]
  voltage?: { t: string[]; before_max_v: number[]; after_max_v: number[] }
}

export interface Outcome {
  id: string
  label: string
  kind: string
  safe: boolean
  unsafe_steps: number
  rank: number | null
  cost: { curtailed_kwh: number; operations: number; battery_throughput_kwh: number; margin_v: number }
  binding_limit: BindingLimit | null
  details?: OutcomeDetails
}

export interface Fixes {
  date?: string
  network?: string
  rule?: string
  baseline_unsafe_steps: number
  verdict: Verdict
  outcomes: Outcome[]
}

/** GET /results: data/results/results.json, written by `python -m scripts.evaluate` (P10.4). */
export type GateStatus = 'pass' | 'fail' | 'conditional' | 'not_run' | 'missing'

export interface Gate {
  gate: string
  name: string
  status: GateStatus
  passed: boolean | null
  measured: unknown
  threshold: string
  provenance: string
  source: string
  command: string
  note: string
}

export interface Bakeoff {
  component: string
  winner: string | Record<string, string>
  rule: string
  split: string
  git_hash: string
  source: string
}

export interface DemoResult {
  route: string
  date: string
  day_type: string
  rule: string
  [field: string]: unknown
}

export interface Results {
  generated_at: string
  git_hash: string
  summary: Record<GateStatus, number>
  gates: Gate[]
  bakeoffs: Bakeoff[]
  headlines: { demo?: { code_version: string; results: DemoResult[] }; [name: string]: unknown }
}
