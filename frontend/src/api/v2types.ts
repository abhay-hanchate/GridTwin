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
  p_unsafe_without_solar?: number[]        // the same scenarios with every panel off
  t?: string[]                             // HH:MM per step
  thresholds?: { watch: number; act: number }
  expected_unsafe_hours: { mean: number; p10: number; p90: number }
  first_watch: string | null
  first_act: string | null
  peak_voltage_v: { p10: number; p50: number; p90: number }
  window_risk: Record<string, number>
  shares: Partial<Record<LimitType, number>>
  n_scenarios?: number
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
  voltage?: { t: string[]; before_max_v: (number | null)[]; after_max_v: (number | null)[] }
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

/** GET /catalog: every registered change and fix with the JSON schema of its parameters (feature F4). */
export interface ParamSchema {
  type: 'number' | 'integer' | string
  title?: string
  description?: string
  default?: number
  minimum?: number
  maximum?: number
  exclusiveMinimum?: number
  exclusiveMaximum?: number
}

export interface CatalogEntry {
  id: string
  kind: 'change' | 'fix' | string
  label: string
  description: string
  params: { properties?: Record<string, ParamSchema> }
}

/** Engine day summary (engine.violations.summarise), as sent by /whatif and /simulate. */
export interface DaySummary {
  max_vm_pu: number
  min_vm_pu: number
  violation_steps: number
  solver_failed_steps: number
  max_trafo_loading_pct: number
  max_line_loading_pct: number
  curtailed_kwh: number
  [field: string]: number
}

export interface WhatIfRun {
  summary: DaySummary
  unsafe: boolean[]
  max_v: (number | null)[]
  node_max_v: (number | null)[][]   // [step][node]; null where the power flow failed
}

export interface WhatIfResult {
  date: string
  rule: string
  changes: string[]
  fixes: string[]
  t: string[]
  limits_v: { min: number; max: number }
  nodes: number[]
  provenance: Record<string, string>
  today?: WhatIfRun                 // the street as it is (absent in results cached before it was added)
  before: WhatIfRun                 // with the changes, no fix
  after: WhatIfRun                  // with the changes and the fixes
}

export interface Quantiles { p10: number; p50: number; p90: number }

/** GET /headroom (engine.headroom.headroom): extra kW per probe location and phase, beside the flat state caps. */
export interface HeadroomPhase { no_worse_kw: number; strict_kw: number; binding_limit: BindingLimit | null }
export interface Headroom {
  date: string
  rule: string
  adoption: number
  baseline_unsafe_steps: number
  locations: Record<string, { node: number; phases: Record<string, HeadroomPhase> }>
  installed_kw: number
  flat_caps: Record<string, { cap_pct: number; cap_kw: number; installed_share_of_cap: number; tag: string }>
  provenance: Record<string, string>
}

/** GET /hosting (engine.hosting.hosting_capacity): share of homes and kW the street takes, over random placements. */
export interface HostingRun { adoption_share: Quantiles; installed_kw: Quantiles; draws: number; binding: string | null }
export interface Hosting { date: string; rule: string; without_fix: HostingRun; with_volt_var: HostingRun; provenance: Record<string, string> }

/** POST /connection-check (engine.headroom.check_connection). */
export interface ConnectionCheck {
  node: number
  kw: number
  count: number
  phase: string
  rule: string
  decision: 'approve' | 'approve_with_conditions' | 'refuse'
  conditions: string[]
  binding_limit: BindingLimit | null
  largest_kw_that_passes?: number
  evidence: { baseline_unsafe_steps: number; unsafe_steps_with_request: number; worsened_steps: number; per_phase_worsened_steps: Record<string, number> }
  regulatory_status: string
}

/** GET /meter-sites (engine.planning_extra.rank_meter_sites): where one smart meter reveals the most. */
export interface MeterSite { node: number; dv_per_kw_v: number; homes_downstream: number; distance_m: number; score: number }
export interface MeterSites { date: string; network: string; rule: string; adoption: number; sites: MeterSite[]; n_candidates: number; probe_kw: number; provenance: Record<string, string> }

/** GET /rx-map (engine.planning_extra.rx_map): peak voltage with and without Volt/VAR as line R and X are scaled. */
export interface RxCell { r_scale: number; x_scale: number; r_over_x: number; peak_v_without: number; peak_v_volt_var: number; volt_var_reduction_v: number }
export interface RxMap { date: string; network: string; rule: string; adoption: number; vmax_v: number; cells: RxCell[]; note: string; provenance: Record<string, string> }

/** GET /transformers (engine.planning_extra.rank_transformers over the street archetypes). */
export interface TransformerRank {
  id: string
  label: string
  connected_kw: number
  headroom_kw: number
  at_search_limit: boolean
  share_of_headroom_used: number
  metered: boolean
  score: number
  trafo_kva: number
}
export interface Transformers { date: string; rule: string; adoption: number; transformers: TransformerRank[]; search_limit_kw: number; metering: string; provenance: Record<string, string> }

/** GET /street (engine.street + compute.street_payload): the street as a schematic and the design day step by step. */
export interface StreetLayout {
  root: number
  rows: number
  nodes: { id: number; x: number; y: number }[]
  lines: { line: number; from: number; to: number }[]
}
export interface StreetRun {
  home_v: (number | null)[][]        // [step][home] volts on the home's own phase; null where the power flow failed
  home_phase: ('A' | 'B' | 'C')[]
  line_phase_kw: number[][][]        // [step][line][phase] kW, positive = towards the homes
  line_neutral_a: number[][]         // [step][line] A, estimated
  line_loading_pct: number[][]
  trafo_kw: number[]                 // positive = from the grid into the street
  trafo_loading_pct: number[]
  solar_kw: number[]
  neutral_a: number[]
  unsafe: boolean[]
  summary: DaySummary
}
export interface Street {
  date: string
  network: string
  rule: string
  fix: string
  fix_label?: string
  t: string[]
  limits_v: { min: number; max: number }
  layout: StreetLayout
  homes: { node: number; kwp: number }[]
  trafo_kva: number
  before: StreetRun
  after?: StreetRun
  flow_method: string
  provenance: Record<string, string>
}

/** GET /calendar */
export interface Calendar { tomorrow: string; archive: { first: string; last: string }; ready: string[]; offline: boolean }
