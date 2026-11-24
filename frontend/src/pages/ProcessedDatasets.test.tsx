// @vitest-environment jsdom
import { cleanup, render, screen } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { afterEach, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { ProcessedDatasets } from './ProcessedDatasets'

afterEach(()=>{cleanup();vi.unstubAllGlobals()})

it('resolves source and pipeline names for processed output rows',async()=>{
  const output={id:'out-1',execution_id:'run-1',source_dataset_id:'src-1',filename:'clean.csv',file_type:'csv',file_size:12,row_count:4,column_count:2,storage_path:'hidden',created_at:'2026-11-11T12:00:00Z'}
  const fetchMock=vi.fn(async(input:RequestInfo|URL)=>{const url=String(input);if(url.includes('/processed-datasets?'))return new Response(JSON.stringify({items:[output],total:1,limit:20,offset:0}));if(url.includes('/datasets?'))return new Response(JSON.stringify({items:[{id:'src-1',name:'source.csv',format:'csv',size_bytes:12,row_count:5,column_count:2,created_at:'2026-11-11T00:00:00Z',columns:[]}],total:1,limit:100,offset:0}));if(url.endsWith('/executions/run-1'))return new Response(JSON.stringify({id:'run-1',pipeline_id:'pipe-1',source_dataset_id:'src-1',status:'success',started_at:'2026-11-11T11:00:00Z',completed_at:'2026-11-11T11:00:01Z',duration:1,total_input_rows:5,total_output_rows:4,error_message:null,execution_summary:{logs:[]},processed_dataset:output}));if(url.endsWith('/pipelines/pipe-1'))return new Response(JSON.stringify({id:'pipe-1',name:'Prepare source',description:null,source_dataset_id:'src-1',configuration:{output_format:'csv'},created_at:'',updated_at:'',steps:[]}));throw new Error(`Unexpected request: ${url}`)})
  vi.stubGlobal('fetch',fetchMock)
  render(<MemoryRouter><ProcessedDatasets/></MemoryRouter>)
  expect(await screen.findByText('clean.csv')).toBeInTheDocument()
  expect(screen.getByText('source.csv')).toBeInTheDocument()
  expect(screen.getByText('Prepare source')).toBeInTheDocument()
})
