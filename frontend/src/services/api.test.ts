import { afterEach, describe, expect, it, vi } from 'vitest'
import { api } from './api'

afterEach(() => vi.unstubAllGlobals())

describe('dataset API client', () => {
  it('loads dataset metadata and calls profile generate, retrieve, and refresh endpoints', async () => {
    expect(api).toHaveProperty('dataset')
    expect(api).toHaveProperty('getProfile')
    expect(api).toHaveProperty('generateProfile')
    expect(api).toHaveProperty('refreshProfile')
    const profile = { id: 'profile-1', dataset_id: 'dataset-1', profile_data: {}, generated_at: '', updated_at: '' }
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(new Response(JSON.stringify(profile), { status: 200 })))
    vi.stubGlobal('fetch', fetchMock)

    await api.dataset('dataset-1')
    await api.getProfile('dataset-1')
    await api.generateProfile('dataset-1')
    await api.refreshProfile('dataset-1')

    expect(fetchMock.mock.calls.map(call => [call[0], call[1]?.method ?? 'GET'])).toEqual([
      ['http://localhost:8000/api/datasets/dataset-1', 'GET'],
      ['http://localhost:8000/api/datasets/dataset-1/profile', 'GET'],
      ['http://localhost:8000/api/datasets/dataset-1/profile', 'POST'],
      ['http://localhost:8000/api/datasets/dataset-1/profile/refresh', 'POST'],
    ])
  })

  it('requests the searchable dataset catalog with escaped query values', async () => {
    const page = { items: [], total: 0, limit: 100, offset: 0 }
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify(page), { status: 200 }))
    vi.stubGlobal('fetch', fetchMock)

    await expect(api.datasets('north & south')).resolves.toEqual(page)
    expect(fetchMock.mock.calls[0][0]).toContain('search=north%20%26%20south')
  })

  it('returns server validation details when an upload is rejected', async () => {
    const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ detail: 'Upload a CSV or JSON file.' }), { status: 415 }))
    vi.stubGlobal('fetch', fetchMock)
    const file = new File(['content'], 'notes.txt', { type: 'text/plain' })

    await expect(api.upload(file)).rejects.toThrow('Upload a CSV or JSON file.')
    expect(fetchMock.mock.calls[0][1]?.method).toBe('POST')
  })
})

describe('pipeline and processed dataset API client', () => {
  it('uses the pipeline, execution, and processed output endpoints with JSON payloads', async () => {
    const responses = [
      {items:[],total:0,limit:20,offset:0}, {id:'p 1'}, {id:'p 1'}, {id:'p 1'}, undefined, {id:'run-1'},
      {items:[],total:0,limit:20,offset:0}, {id:'run-1'}, {execution_id:'run-1',logs:[]},
      {items:[],total:0,limit:20,offset:0}, {id:'out-1'}, {dataset:{id:'out-1'},rows:[]},
    ]
    const fetchMock=vi.fn().mockImplementation(async()=>{const value=responses.shift();return new Response(value===undefined?null:JSON.stringify(value),{status:value===undefined?204:200})})
    vi.stubGlobal('fetch',fetchMock)
    const write={name:'Clean',source_dataset_id:'src',output_format:'json' as const,steps:[{operation:'trim_whitespace' as const,config:{columns:['city']}}]}
    await api.pipelines(20,40);await api.createPipeline(write);await api.pipeline('p 1');await api.updatePipeline('p 1',write);await api.removePipeline('p 1');await api.executePipeline('p 1')
    await api.pipelineExecutions('p 1');await api.execution('run-1');await api.executionLogs('run-1');await api.processedDatasets();await api.processedDataset('out-1');await api.previewProcessedDataset('out-1')
    expect(fetchMock.mock.calls.map(call=>call[0])).toEqual([
      'http://localhost:8000/api/pipelines?limit=20&offset=40','http://localhost:8000/api/pipelines','http://localhost:8000/api/pipelines/p%201','http://localhost:8000/api/pipelines/p%201','http://localhost:8000/api/pipelines/p%201','http://localhost:8000/api/pipelines/p%201/execute',
      'http://localhost:8000/api/pipelines/p%201/executions?limit=20&offset=0','http://localhost:8000/api/executions/run-1','http://localhost:8000/api/executions/run-1/logs','http://localhost:8000/api/processed-datasets?limit=20&offset=0','http://localhost:8000/api/processed-datasets/out-1','http://localhost:8000/api/processed-datasets/out-1/preview?limit=100',
    ])
    expect(JSON.parse(fetchMock.mock.calls[1][1].body)).toEqual(write)
    expect(fetchMock.mock.calls.map(call=>call[1]?.method??'GET').slice(0,6)).toEqual(['GET','POST','GET','PUT','DELETE','POST'])
    expect(fetchMock.mock.calls.every(([url])=>!String(url).endsWith('/'))).toBe(true)
  })

  it('downloads processed output as a blob and extracts its filename', async () => {
    const fetchMock=vi.fn().mockResolvedValue(new Response('a,b\n1,2',{status:200,headers:{'content-disposition':'attachment; filename="clean.csv"'}}))
    vi.stubGlobal('fetch',fetchMock)
    const result=await api.downloadProcessedDataset('out-1')
    expect(result.filename).toBe('clean.csv')
    expect(await result.blob.text()).toBe('a,b\n1,2')
    expect(fetchMock.mock.calls[0][0]).toBe('http://localhost:8000/api/processed-datasets/out-1/download')
  })

  it('refuses to send an update request when a pipeline ID is missing', async () => {
    const fetchMock=vi.fn()
    vi.stubGlobal('fetch',fetchMock)
    await expect(api.updatePipeline('',{name:'Missing ID'})).rejects.toThrow('Pipeline ID is required to update a pipeline.')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('refuses to fetch a pipeline without an ID instead of requesting the collection URL', async () => {
    const fetchMock=vi.fn()
    vi.stubGlobal('fetch',fetchMock)
    await expect(api.pipeline('')).rejects.toThrow('Pipeline ID is required to fetch a pipeline.')
    expect(fetchMock).not.toHaveBeenCalled()
  })
})

describe('data quality API client',()=>{
  it('analyzes each source type and retrieves reports, histories, and filtered issue pages',async()=>{
    const responses=[{id:'r1'},{id:'r2'},{items:[],total:0,limit:20,offset:0},{id:'r1'},{items:[],total:0,limit:10,offset:20},{items:[],total:0,limit:20,offset:0},{items:[],total:0,limit:20,offset:0}]
    const fetchMock=vi.fn(async(_input:RequestInfo|URL,_init?:RequestInit)=>new Response(JSON.stringify(responses.shift()),{status:200}))
    vi.stubGlobal('fetch',fetchMock)
    const rules=[{type:'non_negative' as const,column:'price'}]
    await api.analyzeDatasetQuality('source-1',rules)
    await api.analyzeProcessedQuality('processed-1',rules)
    await api.qualityReports(20,0)
    await api.qualityReport('r1')
    await api.qualityIssues('r1',10,20,'critical','validity')
    await api.datasetQualityReports('source-1')
    await api.processedQualityReports('processed-1')
    expect(fetchMock.mock.calls.map(([url,init])=>[url,init?.method??'GET'])).toEqual([
      ['http://localhost:8000/api/quality/datasets/source-1/analyze','POST'],
      ['http://localhost:8000/api/quality/processed-datasets/processed-1/analyze','POST'],
      ['http://localhost:8000/api/quality/reports?limit=20&offset=0','GET'],
      ['http://localhost:8000/api/quality/reports/r1','GET'],
      ['http://localhost:8000/api/quality/reports/r1/issues?limit=10&offset=20&severity=critical&dimension=validity','GET'],
      ['http://localhost:8000/api/quality/datasets/source-1/reports?limit=20&offset=0','GET'],
      ['http://localhost:8000/api/quality/processed-datasets/processed-1/reports?limit=20&offset=0','GET'],
    ])
    expect(JSON.parse(String(fetchMock.mock.calls[0][1]?.body))).toEqual({rules})
    expect(JSON.parse(String(fetchMock.mock.calls[1][1]?.body))).toEqual({rules})
  })
})

describe('analytics API client',()=>{
  it('uses Phase 5A paths, methods, and request bodies for both source types',async()=>{
    const responses=[{},{columns:[]},{},{},{},{},{},{},{},{},{},{}]
    const fetchMock=vi.fn(async(_input:RequestInfo|URL,_init?:RequestInit)=>new Response(JSON.stringify(responses.shift()??{}),{status:200}))
    vi.stubGlobal('fetch',fetchMock)
    const source={type:'original' as const,id:'source 1'}
    await api.analyticsOverview(source);await api.analyticsColumns(source);await api.analyticsColumn(source,'net total')
    await api.analyticsCorrelation(source);await api.analyticsInsights(source)
    const series={date_column:'created',granularity:'monthly' as const,measure_column:'amount',aggregation:'sum' as const,limit:30}
    const aggregate={group_by:'region',operation:'average' as const,measure_column:'amount',limit:25}
    await api.analyticsTimeseries(source,series);await api.analyticsAggregate(source,aggregate)
    const processed={type:'processed' as const,id:'output-1'}
    await api.analyticsOverview(processed);await api.analyticsColumns(processed);await api.analyticsColumn(processed,'status')
    await api.analyticsCorrelation(processed);await api.analyticsInsights(processed)
    await api.analyticsTimeseries(processed,series);await api.analyticsAggregate(processed,aggregate)
    const comparison={left:source,right:processed};await api.compareAnalytics(comparison)
    expect(fetchMock.mock.calls.map(([url,init])=>[url,init?.method??'GET'])).toEqual([
      ['http://localhost:8000/api/analytics/datasets/source%201/overview','GET'],['http://localhost:8000/api/analytics/datasets/source%201/columns','GET'],['http://localhost:8000/api/analytics/datasets/source%201/columns/net%20total','GET'],['http://localhost:8000/api/analytics/datasets/source%201/correlation','GET'],['http://localhost:8000/api/analytics/datasets/source%201/insights','GET'],['http://localhost:8000/api/analytics/datasets/source%201/timeseries','POST'],['http://localhost:8000/api/analytics/datasets/source%201/aggregate','POST'],
      ['http://localhost:8000/api/analytics/processed-datasets/output-1/overview','GET'],['http://localhost:8000/api/analytics/processed-datasets/output-1/columns','GET'],['http://localhost:8000/api/analytics/processed-datasets/output-1/columns/status','GET'],['http://localhost:8000/api/analytics/processed-datasets/output-1/correlation','GET'],['http://localhost:8000/api/analytics/processed-datasets/output-1/insights','GET'],['http://localhost:8000/api/analytics/processed-datasets/output-1/timeseries','POST'],['http://localhost:8000/api/analytics/processed-datasets/output-1/aggregate','POST'],['http://localhost:8000/api/analytics/compare','POST'],
    ])
    expect(JSON.parse(String(fetchMock.mock.calls[5][1]?.body))).toEqual(series)
    expect(JSON.parse(String(fetchMock.mock.calls[6][1]?.body))).toEqual(aggregate)
    expect(JSON.parse(String(fetchMock.mock.calls[14][1]?.body))).toEqual(comparison)
  })
})
