// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { afterEach, expect, it, vi } from 'vitest'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { PipelineDetail } from './PipelineDetail'

afterEach(()=>{cleanup();vi.unstubAllGlobals()})

const dataset={id:'ds-1',name:'sales.csv',format:'csv',size_bytes:10,row_count:2,column_count:1,created_at:'2026-11-18T00:00:00Z',columns:[{name:'city',data_type:'string',position:0}]}
const saved=(id:string,name='Pipeline')=>({id,name,description:null,source_dataset_id:'ds-1',configuration:{output_format:'csv'},created_at:'2026-11-18T00:00:00Z',updated_at:'2026-11-18T00:00:00Z',steps:[]})
const page={items:[],total:0,limit:20,offset:0}

it('creates a pipeline from the new route with POST and then navigates using the returned ID',async()=>{
  const createResponse=saved('created-1','New sales flow')
  const fetchMock=vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{const url=String(input);if(url.includes('/datasets?'))return new Response(JSON.stringify({items:[dataset],total:1,limit:100,offset:0}));if(url.endsWith('/api/pipelines')&&init?.method==='POST')return new Response(JSON.stringify(createResponse),{status:201});if(url.endsWith('/api/pipelines/created-1'))return new Response(JSON.stringify(createResponse));if(url.endsWith('/executions?limit=20&offset=0'))return new Response(JSON.stringify(page));throw new Error(`Unexpected request: ${init?.method??'GET'} ${url}`)})
  vi.stubGlobal('fetch',fetchMock)
  render(<MemoryRouter initialEntries={['/pipelines/new']}><Routes><Route path="/pipelines/new" element={<PipelineDetail isNewPipeline/>}/><Route path="/pipelines/:pipelineId" element={<PipelineDetail/>}/></Routes></MemoryRouter>)
  fireEvent.change(await screen.findByLabelText('Pipeline name'),{target:{value:'New sales flow'}})
  fireEvent.click(screen.getByRole('button',{name:'Create pipeline'}))
  await screen.findByRole('heading',{name:'New sales flow'})
  await waitFor(()=>expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/api/pipelines',{method:'POST',headers:{'Content-Type':'application/json'},body:expect.any(String)}))
  expect(fetchMock.mock.calls.some(([url,init])=>String(url).endsWith('/api/pipelines/')&&init?.method==='PUT')).toBe(false)
})

it('updates an existing pipeline with PUT to its ID-specific URL',async()=>{
  const existing=saved('pipe-42','Existing flow')
  const fetchMock=vi.fn(async(input:RequestInfo|URL,init?:RequestInit)=>{const url=String(input);if(url.includes('/datasets?'))return new Response(JSON.stringify({items:[dataset],total:1,limit:100,offset:0}));if(url.endsWith('/api/pipelines/pipe-42')&&init?.method==='PUT')return new Response(JSON.stringify({...existing,name:'Renamed flow'}));if(url.endsWith('/api/pipelines/pipe-42'))return new Response(JSON.stringify(existing));if(url.endsWith('/executions?limit=20&offset=0'))return new Response(JSON.stringify(page));throw new Error(`Unexpected request: ${init?.method??'GET'} ${url}`)})
  vi.stubGlobal('fetch',fetchMock)
  render(<MemoryRouter initialEntries={['/pipelines/pipe-42']}><Routes><Route path="/pipelines/:pipelineId" element={<PipelineDetail/>}/></Routes></MemoryRouter>)
  fireEvent.change(await screen.findByLabelText('Pipeline name'),{target:{value:'Renamed flow'}})
  fireEvent.click(screen.getByRole('button',{name:'Save changes'}))
  await waitFor(()=>expect(fetchMock).toHaveBeenCalledWith('http://localhost:8000/api/pipelines/pipe-42',{method:'PUT',headers:{'Content-Type':'application/json'},body:expect.any(String)}))
})
