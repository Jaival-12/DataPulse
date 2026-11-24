// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { Analytics } from './Analytics'

afterEach(()=>{cleanup();vi.unstubAllGlobals()})
const original={id:'src-1',name:'orders.csv',format:'csv',size_bytes:2048,row_count:4,column_count:3,created_at:'2026-11-01T00:00:00Z',columns:[]}
const processed={id:'out-1',execution_id:'run-1',source_dataset_id:'src-1',filename:'orders-clean.csv',file_type:'csv',file_size:1024,row_count:3,column_count:3,storage_path:'hidden',created_at:'2026-11-02T00:00:00Z'}
const overview={source_id:'src-1',source_type:'original',total_records:4,total_columns:3,numeric_columns:['amount'],categorical_columns:['status'],date_columns:['created'],missing_cells:1,duplicate_records:0,dataset_size_bytes:2048,generated_at:''}
const columns={source_id:'src-1',source_type:'original',columns:[{name:'amount',detected_type:'numeric',non_null_count:4,missing_count:0,distinct_count:3,invalid_count:1},{name:'status',detected_type:'categorical',non_null_count:4,missing_count:0,distinct_count:2,invalid_count:0},{name:'created',detected_type:'date',non_null_count:3,missing_count:1,distinct_count:3,invalid_count:0}],generated_at:''}
const numeric={source_id:'src-1',source_type:'original',name:'amount',detected_type:'numeric',non_null_count:4,missing_count:0,distinct_count:3,invalid_count:1,numeric:{count:3,missing_count:0,invalid_count:1,mean:25,median:20,minimum:10,maximum:45,range:35,standard_deviation:17.5,variance:306.25,q25:15,q50:20,q75:32.5,distinct_count:3,histogram:[{bin_start:10,bin_end:20,count:2},{bin_start:20,bin_end:45,count:1}]},categorical:null,date:null,generated_at:''}
const categorical={source_id:'src-1',source_type:'original',name:'status',detected_type:'categorical',non_null_count:4,missing_count:0,distinct_count:2,invalid_count:0,numeric:null,categorical:{non_null_count:4,distinct_count:2,top_values:[{value:'paid',count:3,percentage:75},{value:'open',count:1,percentage:25}],missing_count:0,cardinality:'low'},date:null,generated_at:''}
const date={source_id:'src-1',source_type:'original',name:'created',detected_type:'date',non_null_count:3,missing_count:1,distinct_count:3,invalid_count:0,numeric:null,categorical:null,date:{valid_count:3,invalid_count:0,missing_count:1,earliest:'2026-01-01',latest:'2026-03-01'},generated_at:''}
const correlation={source_id:'src-1',source_type:'original',numeric_columns:['amount','tax'],correlations:{amount:{amount:1,tax:.8},tax:{amount:.8,tax:1}},pair_counts:{amount:{amount:3,tax:3},tax:{amount:3,tax:3}},generated_at:''}
const insights={source_id:'src-1',source_type:'original',insights:[{insight_type:'dominant_category',title:'Status is concentrated',description:'Paid makes up most rows.',severity:'warning',columns:['status'],evidence:{share:.75}}],generated_at:''}
const comparison={left:{total_records:4,total_columns:3,missing_cells:1,duplicate_records:0},right:{total_records:3,total_columns:3,missing_cells:0,duplicate_records:0},row_count_change:-1,column_count_change:0,missing_cells_change:-1,duplicate_records_change:0,common_columns:['amount','status','created'],added_columns:[],removed_columns:[],possible_renames:[],numeric_changes:{amount:{left:{mean:25},right:{mean:27},mean_change:2,minimum_change:0,maximum_change:3}},categorical_changes:{},generated_at:''}

function analyticsFetch(){return vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{const url=new URL(String(input));const path=url.pathname
  if(path==='/api/datasets')return new Response(JSON.stringify({items:[original],total:1,limit:100,offset:0}))
  if(path==='/api/processed-datasets')return new Response(JSON.stringify({items:[processed],total:1,limit:100,offset:0}))
  if(path==='/api/analytics/compare')return new Response(JSON.stringify(comparison))
  const sourceType=path.includes('/processed-datasets/')?'processed':'original';const id=sourceType==='processed'?'out-1':'src-1';const base=`/api/analytics/${sourceType==='processed'?'processed-datasets':'datasets'}/${id}`
  if(path===`${base}/overview`)return new Response(JSON.stringify({...overview,source_id:id,source_type:sourceType}))
  if(path===`${base}/columns`)return new Response(JSON.stringify({...columns,source_id:id,source_type:sourceType}))
  if(path===`${base}/correlation`)return new Response(JSON.stringify({...correlation,source_id:id,source_type:sourceType}))
  if(path===`${base}/insights`)return new Response(JSON.stringify({...insights,source_id:id,source_type:sourceType}))
  if(path.startsWith(`${base}/columns/`)){const name=decodeURIComponent(path.split('/').pop()!);return new Response(JSON.stringify({...({amount:numeric,status:categorical,created:date}[name as 'amount'|'status'|'created']),source_id:id,source_type:sourceType}))}
  if(path===`${base}/timeseries`)return new Response(JSON.stringify({source_id:id,source_type:sourceType,date_column:'created',granularity:'monthly',measure_column:null,aggregation:'count',valid_date_count:3,invalid_date_count:0,missing_date_count:1,invalid_measure_count:0,total_periods:3,truncated:false,points:[{period:'2026-01',record_count:1,aggregate_value:1},{period:'2026-02',record_count:2,aggregate_value:2}],generated_at:''}))
  if(path===`${base}/aggregate`)return new Response(JSON.stringify({source_id:id,source_type:sourceType,group_by:'status',operation:'count',measure_column:null,date_granularity:null,total_groups:2,truncated:false,dropped_missing_group_values:0,dropped_invalid_group_values:0,groups:[{group:'paid',record_count:3,aggregate_value:3,valid_count:3,missing_count:0,invalid_count:0}],generated_at:''}))
  throw new Error(`Unexpected request: ${path} ${init?.method??'GET'}`)
})}

describe('Analytics workspace',()=>{
  it('loads API overview, numeric distributions, correlation and backend insights',async()=>{
    const fetchMock=analyticsFetch();vi.stubGlobal('fetch',fetchMock);vi.stubGlobal('ResizeObserver',class{observe(){}unobserve(){}disconnect(){}})
    render(<MemoryRouter><Analytics/></MemoryRouter>)
    expect(await screen.findByRole('heading',{name:'Analytics'})).toBeInTheDocument()
    expect(await screen.findByText('4',{selector:'.analytics-metric b'})).toBeInTheDocument()
    expect(await screen.findByText('25',{selector:'.analytics-stat b'})).toBeInTheDocument()
    expect(await screen.findByTestId('correlation-amount-tax')).toHaveTextContent('0.80')
    expect(await screen.findByText('Status is concentrated')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/api/analytics/datasets/src-1/overview',undefined)
  })
  it('supports source and column selection with type-specific category and date profiles',async()=>{
    vi.stubGlobal('fetch',analyticsFetch());vi.stubGlobal('ResizeObserver',class{observe(){}unobserve(){}disconnect(){}})
    render(<MemoryRouter><Analytics/></MemoryRouter>);await screen.findByText('25',{selector:'.analytics-stat b'})
    fireEvent.change(screen.getByLabelText('Analytics column'),{target:{value:'status'}})
    expect(await screen.findByText('paid')).toBeInTheDocument();expect(await screen.findByText('75.0%')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Analytics column'),{target:{value:'created'}})
    expect(await screen.findByText('2026-01-01')).toBeInTheDocument();expect(await screen.findByText('Invalid dates')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Dataset source type'),{target:{value:'processed'}})
    expect(await screen.findByText('PROCESSED OUTPUT')).toBeInTheDocument()
    await waitFor(()=>expect(screen.getByLabelText('Dataset')).toHaveValue('processed:out-1'))
  })
  it('submits time series, aggregation, and lineage comparison requests from their controls',async()=>{
    const fetchMock=analyticsFetch();vi.stubGlobal('fetch',fetchMock);vi.stubGlobal('ResizeObserver',class{observe(){}unobserve(){}disconnect(){}})
    render(<MemoryRouter><Analytics/></MemoryRouter>);await screen.findByRole('heading',{name:'Analytics'})
    fireEvent.click(screen.getByRole('button',{name:'Explore trend'}));expect(await screen.findByText(/3 valid dates/)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button',{name:'Run aggregation'}));expect(await screen.findByText(/2 groups/)).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Comparison left dataset'),{target:{value:'original:src-1'}})
    fireEvent.change(screen.getByLabelText('Comparison right dataset'),{target:{value:'processed:out-1'}})
    fireEvent.click(screen.getByRole('button',{name:'Compare datasets'}));expect(await screen.findByText('Numeric changes')).toBeInTheDocument()
    const posts=fetchMock.mock.calls.filter(([,init])=>init?.method==='POST')
    expect(posts.map(([url])=>new URL(String(url)).pathname)).toEqual(['/api/analytics/datasets/src-1/timeseries','/api/analytics/datasets/src-1/aggregate','/api/analytics/compare'])
    expect(JSON.parse(String(posts[0][1]?.body))).toMatchObject({date_column:'created',granularity:'monthly',aggregation:'count'})
  })
  it('shows empty catalog and API errors without fabricating values',async()=>{
    const fetchMock=vi.fn(async(input:RequestInfo|URL)=>{const path=new URL(String(input)).pathname;if(path==='/api/datasets'||path==='/api/processed-datasets')return new Response(JSON.stringify({items:[],total:0,limit:100,offset:0}));throw new Error('should not request analytics without a source')})
    vi.stubGlobal('fetch',fetchMock);render(<MemoryRouter><Analytics/></MemoryRouter>);expect(await screen.findByText('No datasets available')).toBeInTheDocument()
    const failure=vi.fn(async(input:RequestInfo|URL)=>{const path=new URL(String(input)).pathname;if(path==='/api/datasets')return new Response(JSON.stringify({items:[original],total:1,limit:100,offset:0}));if(path==='/api/processed-datasets')return new Response(JSON.stringify({items:[],total:0,limit:100,offset:0}));return new Response(JSON.stringify({detail:'Dataset file is unavailable.'}),{status:404})})
    cleanup();vi.stubGlobal('fetch',failure);render(<MemoryRouter><Analytics/></MemoryRouter>);expect(await screen.findByRole('alert')).toHaveTextContent('Dataset file is unavailable.')
  })
  it('shows a catalog loading state while source requests are pending',async()=>{
    vi.stubGlobal('fetch',vi.fn(()=>new Promise<Response>(()=>{})))
    render(<MemoryRouter><Analytics/></MemoryRouter>)
    expect(screen.getByText('Loading dataset catalog…')).toBeInTheDocument()
  })
})
