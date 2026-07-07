export interface SchemaColumn {
  name: string
  dtype: string
  null_count: number
  non_null_count: number
}

export interface SchemaProfile {
  row_count: number
  column_count: number
  columns: SchemaColumn[]
  categorical_samples?: Record<string, string[]>
  numeric_summary?: Record<string, { min: number; max: number; mean: number; std: number; median: number }>
}

export interface SessionData {
  session_id: string
  filename: string
  row_count: number
  column_count: number
  schema_profile: SchemaProfile
  warnings: string[]
}

export interface ApiEnvelope<T> {
  data: T | null
  error: string | null
}

export type QuestionStatus = 'completed' | 'gave_up'

export interface QuestionResponseData {
  question: string
  status: QuestionStatus
  answer: string
  code: string | null
  retry_count: number
  cost_estimate_usd: number | null
  chart_spec: unknown | null
  table: unknown | null
}

/** One entry in the on-screen chat thread. */
export interface ChatTurn {
  id: string
  question: string
  /** 'loading' while the request is in flight; otherwise mirrors the outcome. */
  state: 'loading' | 'completed' | 'gave_up' | 'error'
  answer?: string
  code?: string | null
  errorMessage?: string
}
