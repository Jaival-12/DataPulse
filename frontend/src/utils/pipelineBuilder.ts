import type { DatasetColumn } from '../types/dataset'
import type { PipelineOperation, PipelineStepConfig, PipelineStepInput } from '../types/pipeline'

export type EditableStep = { operation: PipelineOperation; config: PipelineStepConfig }

export const operationChoices: { value: string; label: string; operation: PipelineOperation }[] = [
  { value: 'remove_duplicates', label: 'Remove duplicates', operation: 'remove_duplicates' },
  { value: 'fill_missing', label: 'Handle missing values', operation: 'fill_missing' },
  { value: 'rename_columns', label: 'Rename column', operation: 'rename_columns' },
  { value: 'remove_columns', label: 'Remove columns', operation: 'remove_columns' },
  { value: 'reorder_columns', label: 'Reorder columns', operation: 'reorder_columns' },
  { value: 'filter_rows', label: 'Filter rows', operation: 'filter_rows' },
  { value: 'convert_type', label: 'Convert data type', operation: 'convert_type' },
  { value: 'standardize_text', label: 'Standardize text', operation: 'trim_whitespace' },
  { value: 'add_calculated_column', label: 'Add calculated column', operation: 'add_calculated_column' },
]

export const operationNames: Record<PipelineOperation, string> = {
  remove_duplicates: 'Remove duplicates', fill_missing: 'Handle missing values',
  rename_columns: 'Rename column', remove_columns: 'Remove columns',
  reorder_columns: 'Reorder columns', filter_rows: 'Filter rows',
  convert_type: 'Convert data type', trim_whitespace: 'Standardize text',
  lowercase: 'Standardize text', uppercase: 'Standardize text', title_case: 'Standardize text',
  add_calculated_column: 'Add calculated column',
}
export const textOperations: PipelineOperation[] = ['trim_whitespace', 'lowercase', 'uppercase', 'title_case']

export function createStep(operation: PipelineOperation, columns: DatasetColumn[]): EditableStep {
  const first = columns[0]?.name ?? ''
  switch (operation) {
    case 'remove_duplicates': return { operation, config: { subset: [] } }
    case 'fill_missing': return { operation, config: { strategy: 'drop_rows' } }
    case 'rename_columns': return { operation, config: { mapping: first ? { [first]: '' } : {} } }
    case 'remove_columns': return { operation, config: { columns: first ? [first] : [] } }
    case 'reorder_columns': return { operation, config: { columns: columns.map(column => column.name) } }
    case 'filter_rows': return { operation, config: { column: first, operator: 'is_not_null' } }
    case 'convert_type': return { operation, config: { column: first, target_type: 'string' } }
    case 'trim_whitespace': case 'lowercase': case 'uppercase': case 'title_case':
      return { operation, config: { columns: first ? [first] : [] } }
    case 'add_calculated_column': return { operation, config: { name: '', left: first ? { column: first } : 0, operator: 'add', right: 0 } }
  }
}

function applySchemaStep(columns: DatasetColumn[], step: EditableStep): DatasetColumn[] {
  const config = step.config
  if (step.operation === 'rename_columns') {
    const mapping = (config.mapping ?? {}) as Record<string, string>
    return columns.map(column => ({ ...column, name: mapping[column.name] || column.name }))
  }
  if (step.operation === 'remove_columns') {
    const removed = new Set((config.columns ?? []) as string[])
    return columns.filter(column => !removed.has(column.name))
  }
  if (step.operation === 'reorder_columns') {
    const order = config.columns as string[] | undefined
    if (!order) return columns
    return order.flatMap(name => {
      const column = columns.find(item => item.name === name)
      return column ? [column] : []
    })
  }
  if (step.operation === 'add_calculated_column') {
    const name = String(config.name ?? '').trim()
    return name && !columns.some(column => column.name === name) ? [...columns, { name, data_type: 'number', position: columns.length }] : columns
  }
  return columns
}

export function columnsBeforeStep(source: DatasetColumn[], steps: EditableStep[], index: number): DatasetColumn[] {
  return steps.slice(0, index).reduce(applySchemaStep, source)
}

function scalarForType(value: unknown, dataType: string): unknown {
  if (typeof value !== 'string') return value
  if (dataType === 'integer') return value.trim() === '' ? value : Number.parseInt(value, 10)
  if (dataType === 'number') return value.trim() === '' ? value : Number(value)
  if (dataType === 'boolean') return value === 'true'
  return value
}

function normalizeOperand(value: unknown): unknown {
  if (value && typeof value === 'object' && 'column' in value) return { column: String((value as { column: unknown }).column) }
  if (typeof value === 'string') return value.trim() === '' ? value : Number(value)
  return value
}

export function normalizeStep(step: EditableStep, columns: DatasetColumn[]): PipelineStepInput {
  const config = step.config
  if (step.operation === 'remove_duplicates') {
    const subset = (config.subset ?? []) as string[]
    return { operation: step.operation, config: subset.length ? { subset } : {} }
  }
  if (step.operation === 'fill_missing') {
    const strategy = String(config.strategy ?? 'drop_rows')
    if (strategy === 'drop_rows') {
      const selected = (config.columns ?? []) as string[]
      return { operation: step.operation, config: { strategy, ...(selected.length ? { columns: selected } : {}) } }
    }
    const column = String(config.column ?? '')
    const base: Record<string, unknown> = { column, strategy }
    if (strategy === 'constant') base.value = scalarForType(config.value, columns.find(item => item.name === column)?.data_type ?? 'string')
    return { operation: step.operation, config: base }
  }
  if (step.operation === 'filter_rows') {
    const operator = String(config.operator ?? 'is_not_null')
    const column = String(config.column ?? '')
    const base: Record<string, unknown> = { column, operator }
    if (operator !== 'is_null' && operator !== 'is_not_null') {
      const type = columns.find(item => item.name === column)?.data_type ?? 'string'
      base.value = operator === 'contains' || operator === 'not_contains' ? String(config.value ?? '') : scalarForType(config.value, type)
    }
    return { operation: step.operation, config: base }
  }
  if (step.operation === 'add_calculated_column') {
    return { operation: step.operation, config: { ...config, name: String(config.name ?? '').trim(), left: normalizeOperand(config.left), right: normalizeOperand(config.right) } }
  }
  if (step.operation === 'rename_columns') {
    const mapping = Object.fromEntries(Object.entries((config.mapping ?? {}) as Record<string, string>).map(([oldName, newName]) => [oldName, newName.trim()]))
    return { operation: step.operation, config: { mapping } }
  }
  return { operation: step.operation, config }
}

export function validateStep(step: EditableStep, columns: DatasetColumn[]): string[] {
  const config = step.config
  const errors: string[] = []
  const available = new Set(columns.map(column => column.name))
  const requireColumn = (name: unknown, label = 'Column') => {
    if (typeof name !== 'string' || !available.has(name)) errors.push(`${label} must be selected from the available columns.`)
  }
  if (step.operation === 'remove_duplicates') {
    const selected = (config.subset ?? []) as string[]
    if (selected.some(name => !available.has(name))) errors.push('Duplicate subset contains an unavailable column.')
  } else if (step.operation === 'fill_missing') {
    const strategy = config.strategy
    if (strategy === 'drop_rows') {
      if (((config.columns ?? []) as string[]).some(name => !available.has(name))) errors.push('Missing-value columns contain an unavailable column.')
    } else {
      requireColumn(config.column)
      if (!['constant', 'mean', 'median', 'mode'].includes(String(strategy))) errors.push('Select a missing-value strategy.')
      if (strategy === 'constant' && (config.value === undefined || String(config.value).trim() === '')) errors.push('Enter a fill value.')
    }
  } else if (step.operation === 'rename_columns') {
    const mapping = (config.mapping ?? {}) as Record<string, string>
    const entries = Object.entries(mapping)
    if (!entries.length) errors.push('Add a column to rename.')
    entries.forEach(([oldName, newName]) => {
      requireColumn(oldName, 'Column to rename')
      if (!newName.trim()) errors.push(`Enter a new name for ${oldName}.`)
    })
    const outputs = columns.map(column => mapping[column.name]?.trim() || column.name)
    if (new Set(outputs).size !== outputs.length) errors.push('Renamed columns must have unique names.')
  } else if (step.operation === 'remove_columns') {
    const selected = (config.columns ?? []) as string[]
    if (!selected.length) errors.push('Select at least one column to remove.')
    if (selected.length >= columns.length) errors.push('At least one column must remain.')
    if (selected.some(name => !available.has(name))) errors.push('Selected columns include an unavailable column.')
  } else if (step.operation === 'reorder_columns') {
    const order = (config.columns ?? []) as string[]
    if (order.length !== columns.length || new Set(order).size !== columns.length || order.some(name => !available.has(name))) errors.push('Reorder must include every available column exactly once.')
  } else if (step.operation === 'filter_rows') {
    requireColumn(config.column)
    const operator = String(config.operator ?? '')
    if (!['equals', 'not_equals', 'greater_than', 'less_than', 'greater_than_or_equal', 'less_than_or_equal', 'contains', 'not_contains', 'is_null', 'is_not_null'].includes(operator)) errors.push('Select a filter operator.')
    if (operator !== 'is_null' && operator !== 'is_not_null') {
      if (config.value === undefined || String(config.value).trim() === '') errors.push('Enter a filter value.')
      if (['greater_than', 'less_than', 'greater_than_or_equal', 'less_than_or_equal'].includes(operator) && !Number.isFinite(Number(config.value))) errors.push('Enter a numeric comparison value.')
    }
  } else if (step.operation === 'convert_type') {
    requireColumn(config.column)
    if (!['string', 'integer', 'float', 'boolean', 'date'].includes(String(config.target_type))) errors.push('Select a target data type.')
  } else if (textOperations.includes(step.operation)) {
    const selected = (config.columns ?? []) as string[]
    if (!selected.length) errors.push('Select at least one text column.')
    if (selected.some(name => !available.has(name))) errors.push('Selected columns include an unavailable column.')
  } else if (step.operation === 'add_calculated_column') {
    if (!String(config.name ?? '').trim()) errors.push('Enter a calculated column name.')
    if (available.has(String(config.name ?? '').trim())) errors.push('Calculated column name already exists.')
    for (const key of ['left', 'right'] as const) {
      const operand = config[key]
      if (operand && typeof operand === 'object' && 'column' in operand) requireColumn((operand as { column: string }).column, 'Operand column')
      else if (!Number.isFinite(Number(operand))) errors.push(`Enter a finite number or choose a column for the ${key} operand.`)
    }
    if (!['add', 'subtract', 'multiply', 'divide'].includes(String(config.operator))) errors.push('Select an arithmetic operator.')
    if (config.operator === 'divide' && typeof config.right === 'number' && config.right === 0) errors.push('Cannot divide by zero.')
  }
  return [...new Set(errors)]
}
