export type DatasetColumn = { name: string; data_type: string; position: number }
export type Dataset = {
  id: string; name: string; format: 'csv' | 'json'; size_bytes: number
  row_count: number; column_count: number; created_at: string; columns: DatasetColumn[]
}
export type DatasetPage = { items: Dataset[]; total: number; limit: number; offset: number }
export type DatasetPreview = { dataset: Dataset; rows: Record<string, unknown>[] }
