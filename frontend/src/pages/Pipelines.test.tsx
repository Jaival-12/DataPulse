// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { afterEach, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { Pipelines } from './Pipelines'

afterEach(()=>{cleanup();vi.unstubAllGlobals()})

it('lists a pipeline with its source and latest synchronous execution result',async()=>{
  const pipeline={id:'pipe-1',name:'Clean sales',description:'Normalize sales',source_dataset_id:'ds-1',configuration:{output_format:'csv'},created_at:'2026-11-11T10:00:00Z',updated_at:'2026-11-11T10:00:00Z',steps:[{id:'step-1',operation:'trim_whitespace',configuration:{columns:['city']},execution_order:0,created_at:'2026-11-11T10:00:00Z'}]}
  const execution={id:'run-1',pipeline_id:'pipe-1',source_dataset_id:'ds-1',status:'success',started_at:'2026-11-11T11:00:00Z',completed_at:'2026-11-11T11:00:01Z',duration:1,total_input_rows:10,total_output_rows:9,error_message:null,execution_summary:{step_count:1,logs:[]},processed_dataset:null}
  const fetchMock=vi.fn(async(input:RequestInfo|URL)=>{const url=String(input);if(url.includes('/pipelines?'))return new Response(JSON.stringify({items:[pipeline],total:1,limit:20,offset:0}));if(url.includes('/datasets?'))return new Response(JSON.stringify({items:[{id:'ds-1',name:'sales.csv',format:'csv',size_bytes:10,row_count:10,column_count:1,created_at:'2026-11-11T00:00:00Z',columns:[]}],total:1,limit:100,offset:0}));if(url.endsWith('/pipelines/pipe-1/executions?limit=1&offset=0'))return new Response(JSON.stringify({items:[execution],total:1,limit:1,offset:0}));throw new Error(`Unexpected request: ${url}`)})
  vi.stubGlobal('fetch',fetchMock)
  render(<MemoryRouter><Pipelines/></MemoryRouter>)
  expect(await screen.findByText('Clean sales')).toBeInTheDocument()
  expect(screen.getByText('sales.csv')).toBeInTheDocument()
  expect(screen.getByText('Success')).toBeInTheDocument()
  expect(screen.getByText('10 → 9 rows')).toBeInTheDocument()
})
