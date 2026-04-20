/** Backend success envelope (unwrapped by axios interceptor). */
export interface ApiEnvelope<T = unknown> {
  success: boolean
  message: string
  data: T
  errors: unknown[]
  meta: Record<string, unknown>
}

export interface DocumentUploadData {
  document_id: string
  filename: string
  content_type?: string
  size?: number
  status?: string
  created_at?: string
}

export interface WorkflowCreateData {
  workflow_run_id: string
  status: string
  current_phase: string
  overall_progress_percent: number
  document_id: string
  template_id: string | null
  output_id: string | null
  dispatch_mode?: string | null
  created_at?: string
  updated_at?: string
  [key: string]: unknown
}

export interface AssembledSectionRow {
  section_id: string
  title: string
  execution_order?: number
  output_type?: string
  content?: string | null
  metadata?: Record<string, unknown>
}

export interface AssembledDocumentData {
  workflow_run_id: string
  template_id: string | null
  total_sections: number
  title: string
  sections: AssembledSectionRow[]
}

export interface WorkflowStatusData extends Record<string, unknown> {
  workflow_run_id: string
  status: string
  current_phase: string
  overall_progress_percent: number
  current_step_label?: string | null
  document_id: string
  template_id: string | null
  output_id: string | null
  assembled_document?: AssembledDocumentData | null
}

export interface TemplateDto {
  template_id: string
  filename: string
  template_type: string | null
  version: string | null
  status: string
  created_at: string
  updated_at: string
  compile_job_id: string | null
  compiled_artifacts: unknown[]
}

export interface TemplateListData {
  items: TemplateDto[]
  total: number
}
