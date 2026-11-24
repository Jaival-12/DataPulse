// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { afterEach, expect, it, vi } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { api } from '../services/api'
import { QualityHistory } from './QualityHistory'

afterEach(()=>{cleanup();vi.restoreAllMocks()})
const report=(id:string,dataset_id:string|null,processed_dataset_id:string|null,score:number)=>({id,dataset_id,processed_dataset_id,overall_score:score,quality_label:'Good',dimension_scores:{completeness:score,validity:score,uniqueness:score,consistency:score,rule_based_correctness:null},scoring_weights:{completeness:.25,validity:.25,uniqueness:.2,consistency:.15,rule_based_correctness:.15},methodology:{version:'v1'},rules:[],total_rows:4,total_columns:1,total_issues:0,status:'complete' as const,created_at:'2026-11-18T10:00:00Z'})
const page=(items:ReturnType<typeof report>[])=>({items,total:items.length,limit:20,offset:0})

it('runs a selected rule on the original dataset and shows its report history',async()=>{
  const saved=report('new-report','source-1',null,90)
  const history=vi.spyOn(api,'datasetQualityReports').mockResolvedValue(page([saved]))
  const analyze=vi.spyOn(api,'analyzeDatasetQuality').mockResolvedValue(saved)
  render(<MemoryRouter><QualityHistory targetType="dataset" targetId="source-1" columns={['price']}/></MemoryRouter>)
  fireEvent.change(screen.getByLabelText('Quality rule type'),{target:{value:'non_negative'}})
  fireEvent.click(screen.getByRole('button',{name:'Add rule'}))
  fireEvent.click(screen.getByRole('button',{name:'Run quality analysis'}))
  expect(await screen.findByText('Quality analysis completed.')).toBeInTheDocument()
  expect(analyze).toHaveBeenCalledWith('source-1',[{type:'non_negative',column:'price'}])
  expect(history).toHaveBeenCalledWith('source-1')
  expect(screen.getByRole('link',{name:/Good/})).toHaveAttribute('href','/quality?report=new-report')
})

it('compares processed output only with its declared source lineage and reports negative deltas',async()=>{
  const output=report('processed-report',null,'processed-1',68)
  const source=report('source-report','source-1',null,80)
  const processedHistory=vi.spyOn(api,'processedQualityReports').mockResolvedValue(page([output]))
  const sourceHistory=vi.spyOn(api,'datasetQualityReports').mockResolvedValue(page([source]))
  render(<MemoryRouter><QualityHistory targetType="processed" targetId="processed-1" columns={['price']} sourceDatasetId="source-1"/></MemoryRouter>)
  expect((await screen.findAllByText('-12.0 pts')).length).toBe(4)
  expect(processedHistory).toHaveBeenCalledWith('processed-1')
  expect(sourceHistory).toHaveBeenCalledWith('source-1')
  expect(screen.getByText('Latest original source versus latest processed output report.')).toBeInTheDocument()
})

it('does not compare a source report with mismatched lineage',async()=>{
  const output=report('processed-report',null,'processed-1',68)
  const wrongSource=report('wrong-source','other-source',null,80)
  vi.spyOn(api,'processedQualityReports').mockResolvedValue(page([output]))
  vi.spyOn(api,'datasetQualityReports').mockResolvedValue(page([wrongSource]))
  render(<MemoryRouter><QualityHistory targetType="processed" targetId="processed-1" columns={['price']} sourceDatasetId="source-1"/></MemoryRouter>)
  expect(await screen.findByText('Run an analysis on both this output and its original source to compare their measured dimensions.')).toBeInTheDocument()
  expect(screen.queryByText('-12.0 pts')).not.toBeInTheDocument()
})
