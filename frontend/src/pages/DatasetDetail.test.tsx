// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { afterEach, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { DatasetDetail } from './DatasetDetail'

afterEach(() => { cleanup(); vi.unstubAllGlobals() })

it('generates a profile and renders its real row count in the data profile tab', async () => {
  const dataset = { id: 'dataset-1', name: 'orders.csv', format: 'csv', size_bytes: 32, row_count: 7, column_count: 1, created_at: '2026-11-11T00:00:00Z', columns: [{ name: 'amount', data_type: 'number', position: 0 }] }
  const profile = {
    id: 'profile-1', dataset_id: 'dataset-1', generated_at: '2026-11-11T00:00:00Z', updated_at: '2026-11-11T00:00:00Z',
    profile_data: { total_rows: 7, total_columns: 1, total_missing_cells: 0, missing_cell_percentage: 0, duplicate_rows: 0, duplicate_row_percentage: 0, unique_rows: 7, numeric_column_count: 1, categorical_column_count: 0, date_column_count: 0, boolean_column_count: 0, overall_completeness_percentage: 100, columns: [] },
  }
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input)
    if (url.endsWith('/datasets/dataset-1/profile') && init?.method === 'POST') return new Response(JSON.stringify(profile), { status: 200 })
    if (url.endsWith('/datasets/dataset-1/profile')) return new Response(JSON.stringify({ detail: 'Profile has not been generated yet.' }), { status: 404 })
    if (url.endsWith('/datasets/dataset-1')) return new Response(JSON.stringify(dataset), { status: 200 })
    throw new Error(`Unexpected request: ${url}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })

  render(<MemoryRouter initialEntries={['/datasets/dataset-1']}><Routes><Route path="/datasets/:datasetId" element={<DatasetDetail/>}/></Routes></MemoryRouter>)
  await screen.findByRole('heading', { name: 'orders.csv' })
  fireEvent.click(screen.getAllByRole('tab', { name: /Data profile/ })[0])
  fireEvent.click(screen.getByRole('button', { name: /Generate profile/ }))

  expect(await screen.findByText('Profile generated and saved.')).toBeInTheDocument()
  expect(screen.getByText('7')).toBeInTheDocument()
})

it('shows statistics matched to mixed numeric, date, and identifier columns', async () => {
  const dataset = { id: 'dataset-1', name: 'orders.csv', format: 'csv', size_bytes: 32, row_count: 5, column_count: 3, created_at: '2026-11-11T00:00:00Z', columns: [] }
  const profile = {
    id: 'profile-1', dataset_id: 'dataset-1', generated_at: '2026-11-11T00:00:00Z', updated_at: '2026-11-11T00:00:00Z',
    profile_data: { total_rows: 5, total_columns: 3, total_missing_cells: 0, missing_cell_percentage: 0, duplicate_rows: 0, duplicate_row_percentage: 0, unique_rows: 5, numeric_column_count: 1, categorical_column_count: 0, date_column_count: 1, boolean_column_count: 0, overall_completeness_percentage: 100, columns: [
      { name: 'quantity', detected_type: 'numeric_mixed', total_records: 5, non_null_count: 5, missing_count: 0, missing_percentage: 0, distinct_count: 4, unique_percentage: 80, numeric_statistics: { count: 3, valid_numeric_values: 3, invalid_numeric_values: 2, numeric_conversion_percentage: 60, mean: 5, median: 5, minimum: 2, maximum: 8, standard_deviation: 3, q25: 3, q50: 5, q75: 7, histogram: [{ bin_start: 2, bin_end: 5, count: 2 }, { bin_start: 5, bin_end: 8, count: 1 }] }, categorical_statistics: null },
      { name: 'event_date', detected_type: 'date', total_records: 5, non_null_count: 4, missing_count: 1, missing_percentage: 20, distinct_count: 3, unique_percentage: 75, numeric_statistics: null, categorical_statistics: null, date_statistics: { valid_date_count: 3, invalid_date_count: 1, missing_date_count: 1, earliest_date: '2026-05-14', latest_date: '2026-05-17' } },
      { name: 'customer_id', detected_type: 'identifier', total_records: 5, non_null_count: 4, missing_count: 1, missing_percentage: 20, distinct_count: 3, unique_percentage: 75, numeric_statistics: null, categorical_statistics: null, identifier_statistics: { duplicate_identifier_count: 1, sample_values: ['001', '001', '002', '003'] } },
    ] },
  }
  const fetchMock = vi.fn(async (input: RequestInfo | URL) => {
    const url = String(input)
    if (url.endsWith('/datasets/dataset-1/profile')) return new Response(JSON.stringify(profile), { status: 200 })
    if (url.endsWith('/datasets/dataset-1')) return new Response(JSON.stringify(dataset), { status: 200 })
    throw new Error(`Unexpected request: ${url}`)
  })
  vi.stubGlobal('fetch', fetchMock)
  vi.stubGlobal('ResizeObserver', class { observe() {} unobserve() {} disconnect() {} })

  render(<MemoryRouter initialEntries={['/datasets/dataset-1']}><Routes><Route path="/datasets/:datasetId" element={<DatasetDetail/>}/></Routes></MemoryRouter>)
  await screen.findByRole('heading', { name: 'orders.csv' })
  fireEvent.click(screen.getAllByRole('tab', { name: /Data profile/ })[0])

  expect(await screen.findByText(/numeric conversion/i)).toBeInTheDocument()
  expect(screen.getByText('2–5')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: /event_date/ }))
  expect(screen.getAllByText(/valid dates/i).length).toBeGreaterThan(0)
  expect(screen.getByText('2026-05-14')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button', { name: /customer_id/ }))
  expect(screen.getByText(/duplicate identifiers/i)).toBeInTheDocument()
  expect(screen.getByText('75.00%')).toBeInTheDocument()
  expect(screen.queryByText('Top values')).not.toBeInTheDocument()
})
