// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { afterEach, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { Quality } from './Quality'

afterEach(()=>{cleanup();vi.unstubAllGlobals()})

const report={id:'report-1',dataset_id:'dataset-1',processed_dataset_id:null,overall_score:84.25,quality_label:'Good',dimension_scores:{completeness:90,validity:75,uniqueness:100,consistency:80,rule_based_correctness:null},scoring_weights:{completeness:.25,validity:.25,uniqueness:.2,consistency:.15,rule_based_correctness:.15},methodology:{version:'datapulse-quality-v1'},rules:[],total_rows:20,total_columns:4,total_issues:2,status:'complete',created_at:'2026-11-18T09:00:00Z'}
const issues=[{id:'i1',report_id:'report-1',dimension:'validity',issue_type:'invalid_date',severity:'critical',column_name:'event_date',affected_rows:12,affected_percentage:60,description:'Impossible date values were found.',sample_values:['2026-13-40'],recommendation:'Correct the source dates.'},{id:'i2',report_id:'report-1',dimension:'completeness',issue_type:'missing_values',severity:'low',column_name:'email',affected_rows:1,affected_percentage:5,description:'A value is missing.',sample_values:[''],recommendation:'Review missing values.'}]

it('renders live quality scores and filters the issue explorer',async()=>{
  const fetchMock=vi.fn(async(input:RequestInfo|URL)=>{const url=new URL(String(input));if(url.pathname.endsWith('/quality/reports'))return new Response(JSON.stringify({items:[report],total:1,limit:20,offset:0}));if(url.pathname.endsWith('/quality/reports/report-1'))return new Response(JSON.stringify(report));if(url.pathname.endsWith('/issues')){const severity=url.searchParams.get('severity');const dimension=url.searchParams.get('dimension');const search=url.searchParams.get('search')?.toLowerCase();const found=issues.filter(issue=>(!severity||issue.severity===severity)&&(!dimension||issue.dimension===dimension)&&(!search||`${issue.issue_type} ${issue.column_name} ${issue.description}`.toLowerCase().includes(search)));return new Response(JSON.stringify({items:found,total:found.length,limit:Number(url.searchParams.get('limit')),offset:Number(url.searchParams.get('offset'))}))}throw new Error(`Unexpected request: ${url}`)})
  vi.stubGlobal('fetch',fetchMock)
  vi.stubGlobal('ResizeObserver',class{observe(){}unobserve(){}disconnect(){}})
  render(<MemoryRouter><Quality/></MemoryRouter>)
  expect(await screen.findByRole('heading',{name:'Data Quality'})).toBeInTheDocument()
  expect(await screen.findByText('84.3')).toBeInTheDocument()
  expect((await screen.findAllByText('Completeness')).length).toBeGreaterThan(0)
  expect(screen.getByText('2 issues')).toBeInTheDocument()
  expect(await screen.findByText('Correct the source dates.')).toBeInTheDocument()
  fireEvent.click(screen.getByRole('button',{name:'View details for invalid_date'}))
  expect(screen.getByRole('dialog')).toHaveTextContent('Impossible date values were found.')
  fireEvent.click(screen.getByRole('button',{name:'Close issue details'}))
  fireEvent.change(screen.getByLabelText('Severity filter'),{target:{value:'low'}})
  await waitFor(()=>expect(screen.getByText('Review missing values.')).toBeInTheDocument())
  expect(screen.queryByText('Correct the source dates.')).not.toBeInTheDocument()
})

it('shows a useful empty state before the first analysis',async()=>{
  const fetchMock=vi.fn(async()=>new Response(JSON.stringify({items:[],total:0,limit:20,offset:0})))
  vi.stubGlobal('fetch',fetchMock)
  render(<MemoryRouter><Quality/></MemoryRouter>)
  expect(await screen.findByText('No quality reports yet')).toBeInTheDocument()
})

it.each([100,83.8,50,0])('keeps the %s score centered and the denominator below it',async(value)=>{
  const scoredReport={...report,overall_score:value}
  const fetchMock=vi.fn(async(input:RequestInfo|URL)=>{const url=new URL(String(input));if(url.pathname.endsWith('/quality/reports'))return new Response(JSON.stringify({items:[scoredReport],total:1,limit:20,offset:0}));if(url.pathname.endsWith('/quality/reports/report-1'))return new Response(JSON.stringify(scoredReport));if(url.pathname.endsWith('/issues'))return new Response(JSON.stringify({items:[],total:0,limit:1,offset:0}));throw new Error(`Unexpected request: ${url}`)})
  vi.stubGlobal('fetch',fetchMock)
  vi.stubGlobal('ResizeObserver',class{observe(){}unobserve(){}disconnect(){}})
  render(<MemoryRouter><Quality/></MemoryRouter>)
  const gauge=await screen.findByRole('img',{name:`Overall quality score ${value.toFixed(1)} out of 100`})
  const scoreGroup=within(gauge).getByTestId('quality-score-value')
  expect(within(scoreGroup).getByText(value.toFixed(1))).toBeInTheDocument()
  expect(within(scoreGroup).getByText('/ 100')).toBeInTheDocument()
  expect(scoreGroup).toHaveClass('quality-score-value')
  expect(within(scoreGroup).getByText(value.toFixed(1),{selector:'b'})).toBeInTheDocument()
  expect(within(scoreGroup).getByText('/ 100',{selector:'small'})).toBeInTheDocument()
})
