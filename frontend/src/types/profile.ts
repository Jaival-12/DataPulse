export type NumericStatistics = {
  count: number
  mean: number | null
  median: number | null
  minimum: number | null
  maximum: number | null
  standard_deviation: number | null
  q25: number | null
  q50: number | null
  q75: number | null
  valid_numeric_values?: number
  invalid_numeric_values?: number
  numeric_conversion_percentage?: number
  histogram?: { bin_start: number; bin_end: number; count: number }[]
}

export type CategoryValue = { value: string | number | boolean | null; count: number; percentage: number }
export type CategoricalStatistics = { distinct_count: number; top_values: CategoryValue[] }
export type DateStatistics = { valid_date_count: number; invalid_date_count: number; missing_date_count: number; earliest_date: string | null; latest_date: string | null }
export type IdentifierStatistics = { duplicate_identifier_count: number; sample_values: (string | number | boolean | null)[] }
export type ColumnProfile = {
  name: string
  detected_type: 'integer' | 'float' | 'number' | 'numeric_mixed' | 'string' | 'categorical' | 'identifier' | 'boolean' | 'date' | 'datetime' | 'mixed' | 'empty'
  total_records: number
  non_null_count: number
  missing_count: number
  missing_percentage: number
  distinct_count: number
  unique_percentage: number
  numeric_statistics: NumericStatistics | null
  categorical_statistics: CategoricalStatistics | null
  date_statistics?: DateStatistics | null
  identifier_statistics?: IdentifierStatistics | null
}
export type ProfileData = {
  total_rows: number
  total_columns: number
  total_missing_cells: number
  missing_cell_percentage: number
  duplicate_rows: number
  duplicate_row_percentage: number
  unique_rows: number
  numeric_column_count: number
  categorical_column_count: number
  date_column_count: number
  boolean_column_count: number
  overall_completeness_percentage: number
  columns: ColumnProfile[]
}
export type DatasetProfile = {
  id: string
  dataset_id: string
  profile_data: ProfileData
  generated_at: string
  updated_at: string
}
