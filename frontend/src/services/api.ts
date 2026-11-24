import type { Dataset, DatasetPage, DatasetPreview } from '../types/dataset'
import type { DatasetProfile } from '../types/profile'
import type { DataQualityReport, QualityIssuePage, QualityReportPage, QualityRule } from '../types/quality'
import type { AggregateAnalytics, AggregateRequest, AnalyticsColumn, AnalyticsColumns, AnalyticsComparison, AnalyticsOverview, AnalyticsSource, AnalyticsInsights, CorrelationAnalytics, TimeSeriesAnalytics, TimeSeriesRequest } from '../types/analytics'
import type { DownloadedFile, ExecutionLogs, Pipeline, PipelineExecution, PipelineExecutionPage, PipelinePage, PipelineUpdate, PipelineWrite, ProcessedDataset, ProcessedDatasetPage, ProcessedDatasetPreview } from '../types/pipeline'

const API = (import.meta.env.VITE_API_URL ?? 'http://localhost:8000/api').replace(/\/+$/, '')
export class ApiError extends Error {
  constructor(message: string, public readonly status: number) { super(message); this.name = 'ApiError' }
}
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, init)
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    const detail = body.detail
    const message = Array.isArray(detail) ? detail.map(item => item.msg ?? 'Invalid request').join(' · ') : detail
    throw new ApiError(typeof message === 'string' ? message : `Request failed (${response.status})`, response.status)
  }
  if (response.status === 204) return undefined as T
  return response.json() as Promise<T>
}
async function requestFile(path: string): Promise<DownloadedFile> {
  const response = await fetch(`${API}${path}`)
  if (!response.ok) {
    const body = await response.json().catch(() => ({}))
    const detail = body.detail
    const message = Array.isArray(detail) ? detail.map(item => item.msg ?? 'Invalid request').join(' · ') : detail
    throw new ApiError(typeof message === 'string' ? message : `Request failed (${response.status})`, response.status)
  }
  const disposition = response.headers.get('content-disposition') ?? ''
  const match = disposition.match(/filename\*?=(?:UTF-8''|\")?([^\";]+)/i)
  const filename = match ? decodeURIComponent(match[1].replace(/\"$/, '')) : 'processed-dataset'
  return { blob: await response.blob(), filename }
}
export const api = {
  health: () => request<{ status: string; database?: string }>('/health/db'),
  overview: () => request<{ dataset_count: number; record_count: number; recent_datasets: Dataset[] }>('/overview'),
  datasets: (search = '') => request<DatasetPage>(`/datasets?limit=100&search=${encodeURIComponent(search)}`),
  dataset: (id: string) => request<Dataset>(`/datasets/${encodeURIComponent(id)}`),
  getProfile: (id: string) => request<DatasetProfile>(`/datasets/${encodeURIComponent(id)}/profile`),
  generateProfile: (id: string) => request<DatasetProfile>(`/datasets/${encodeURIComponent(id)}/profile`, { method: 'POST' }),
  refreshProfile: (id: string) => request<DatasetProfile>(`/datasets/${encodeURIComponent(id)}/profile/refresh`, { method: 'POST' }),
  upload: (file: File) => {
    const form = new FormData(); form.append('file', file)
    return request<Dataset>('/datasets', { method: 'POST', body: form })
  },
  preview: (id: string) => request<DatasetPreview>(`/datasets/${id}/preview`),
  remove: (id: string) => request<void>(`/datasets/${id}`, { method: 'DELETE' }),
  pipelines: (limit = 20, offset = 0) => request<PipelinePage>(`/pipelines?limit=${limit}&offset=${offset}`),
  pipeline: (id: string) => {
    if (!id.trim()) return Promise.reject(new Error('Pipeline ID is required to fetch a pipeline.'))
    return request<Pipeline>(`/pipelines/${encodeURIComponent(id)}`)
  },
  createPipeline: (data: PipelineWrite) => request<Pipeline>('/pipelines', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) }),
  updatePipeline: (id: string, data: PipelineUpdate) => {
    if (!id.trim()) return Promise.reject(new Error('Pipeline ID is required to update a pipeline.'))
    return request<Pipeline>(`/pipelines/${encodeURIComponent(id)}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) })
  },
  removePipeline: (id: string) => request<void>(`/pipelines/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  executePipeline: (id: string) => {
    if (!id.trim()) return Promise.reject(new Error('Pipeline ID is required to execute a pipeline.'))
    return request<PipelineExecution>(`/pipelines/${encodeURIComponent(id)}/execute`, { method: 'POST' })
  },
  pipelineExecutions: (id: string, limit = 20, offset = 0) => request<PipelineExecutionPage>(`/pipelines/${encodeURIComponent(id)}/executions?limit=${limit}&offset=${offset}`),
  execution: (id: string) => request<PipelineExecution>(`/executions/${encodeURIComponent(id)}`),
  executionLogs: (id: string) => request<ExecutionLogs>(`/executions/${encodeURIComponent(id)}/logs`),
  processedDatasets: (limit = 20, offset = 0) => request<ProcessedDatasetPage>(`/processed-datasets?limit=${limit}&offset=${offset}`),
  processedDataset: (id: string) => request<ProcessedDataset>(`/processed-datasets/${encodeURIComponent(id)}`),
  previewProcessedDataset: (id: string, limit = 100) => request<ProcessedDatasetPreview>(`/processed-datasets/${encodeURIComponent(id)}/preview?limit=${limit}`),
  downloadProcessedDataset: (id: string) => requestFile(`/processed-datasets/${encodeURIComponent(id)}/download`),
  analyzeDatasetQuality: (id:string,rules:QualityRule[]=[]) => request<DataQualityReport>(`/quality/datasets/${encodeURIComponent(id)}/analyze`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({rules})}),
  analyzeProcessedQuality: (id:string,rules:QualityRule[]=[]) => request<DataQualityReport>(`/quality/processed-datasets/${encodeURIComponent(id)}/analyze`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({rules})}),
  qualityReports: (limit=20,offset=0) => request<QualityReportPage>(`/quality/reports?limit=${limit}&offset=${offset}`),
  qualityReport: (id:string) => request<DataQualityReport>(`/quality/reports/${encodeURIComponent(id)}`),
  qualityIssues: (id:string,limit=20,offset=0,severity?:string,dimension?:string,search?:string) => {
    const params=new URLSearchParams({limit:String(limit),offset:String(offset)})
    if(severity)params.set('severity',severity)
    if(dimension)params.set('dimension',dimension)
    if(search)params.set('search',search)
    return request<QualityIssuePage>(`/quality/reports/${encodeURIComponent(id)}/issues?${params.toString()}`)
  },
  datasetQualityReports: (id:string,limit=20,offset=0) => request<QualityReportPage>(`/quality/datasets/${encodeURIComponent(id)}/reports?limit=${limit}&offset=${offset}`),
  processedQualityReports: (id:string,limit=20,offset=0) => request<QualityReportPage>(`/quality/processed-datasets/${encodeURIComponent(id)}/reports?limit=${limit}&offset=${offset}`),
  analyticsOverview: (source: AnalyticsSource) => request<AnalyticsOverview>(`${source.type === 'original' ? '/analytics/datasets' : '/analytics/processed-datasets'}/${encodeURIComponent(source.id)}/overview`),
  analyticsColumns: (source: AnalyticsSource) => request<AnalyticsColumns>(`${source.type === 'original' ? '/analytics/datasets' : '/analytics/processed-datasets'}/${encodeURIComponent(source.id)}/columns`),
  analyticsColumn: (source: AnalyticsSource, name: string) => request<AnalyticsColumn>(`${source.type === 'original' ? '/analytics/datasets' : '/analytics/processed-datasets'}/${encodeURIComponent(source.id)}/columns/${encodeURIComponent(name)}`),
  analyticsCorrelation: (source: AnalyticsSource) => request<CorrelationAnalytics>(`${source.type === 'original' ? '/analytics/datasets' : '/analytics/processed-datasets'}/${encodeURIComponent(source.id)}/correlation`),
  analyticsInsights: (source: AnalyticsSource) => request<AnalyticsInsights>(`${source.type === 'original' ? '/analytics/datasets' : '/analytics/processed-datasets'}/${encodeURIComponent(source.id)}/insights`),
  analyticsTimeseries: (source: AnalyticsSource, body: TimeSeriesRequest) => request<TimeSeriesAnalytics>(`${source.type === 'original' ? '/analytics/datasets' : '/analytics/processed-datasets'}/${encodeURIComponent(source.id)}/timeseries`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body) }),
  analyticsAggregate: (source: AnalyticsSource, body: AggregateRequest) => request<AggregateAnalytics>(`${source.type === 'original' ? '/analytics/datasets' : '/analytics/processed-datasets'}/${encodeURIComponent(source.id)}/aggregate`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body) }),
  compareAnalytics: (body: { left: AnalyticsSource; right: AnalyticsSource }) => request<AnalyticsComparison>('/analytics/compare', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body) }),
}
