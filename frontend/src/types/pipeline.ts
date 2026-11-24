export type PipelineOperation =
  | 'remove_duplicates' | 'fill_missing' | 'rename_columns' | 'remove_columns'
  | 'reorder_columns' | 'filter_rows' | 'convert_type' | 'trim_whitespace'
  | 'lowercase' | 'uppercase' | 'title_case' | 'add_calculated_column'

export type PipelineStepConfig = Record<string, unknown>
export type PipelineStepInput = { operation: PipelineOperation; config: PipelineStepConfig }
export type PipelineStep = {
  id: string
  operation: PipelineOperation
  configuration: PipelineStepConfig
  execution_order: number
  created_at: string
}

export type Pipeline = {
  id: string
  name: string
  description: string | null
  source_dataset_id: string
  configuration: { output_format?: 'csv' | 'json'; [key: string]: unknown }
  created_at: string
  updated_at: string
  steps: PipelineStep[]
}
export type PipelinePage = { items: Pipeline[]; total: number; limit: number; offset: number }
export type PipelineWrite = {
  name: string
  description?: string | null
  source_dataset_id: string
  output_format: 'csv' | 'json'
  steps: PipelineStepInput[]
}
export type PipelineUpdate = Partial<PipelineWrite>

export type ExecutionStatus = 'pending' | 'running' | 'success' | 'failed'
export type ExecutionLog = {
  step_id?: string
  step_index?: number | null
  operation: string
  status: ExecutionStatus
  duration?: number
  input_rows?: number
  output_rows?: number
  error?: string
  [key: string]: unknown
}
export type ProcessedDataset = {
  id: string
  execution_id: string
  source_dataset_id: string
  filename: string
  file_type: 'csv' | 'json'
  file_size: number
  row_count: number
  column_count: number
  storage_path: string
  created_at: string
}
export type PipelineExecution = {
  id: string
  pipeline_id: string
  source_dataset_id: string
  status: ExecutionStatus
  started_at: string
  completed_at: string | null
  duration: number | null
  total_input_rows: number | null
  total_output_rows: number | null
  error_message: string | null
  execution_summary: { step_count?: number; logs?: ExecutionLog[]; [key: string]: unknown }
  processed_dataset: ProcessedDataset | null
}
export type PipelineExecutionPage = { items: PipelineExecution[]; total: number; limit: number; offset: number }
export type ExecutionLogs = { execution_id: string; logs: ExecutionLog[] }
export type ProcessedDatasetPage = { items: ProcessedDataset[]; total: number; limit: number; offset: number }
export type ProcessedDatasetPreview = { dataset: ProcessedDataset; rows: Record<string, unknown>[] }
export type DownloadedFile = { blob: Blob; filename: string }
