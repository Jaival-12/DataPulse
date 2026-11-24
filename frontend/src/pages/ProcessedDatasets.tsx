import { ArrowRight, ChevronLeft, ChevronRight, Database, FileJson2, FileSpreadsheet, LoaderCircle, RefreshCw, X } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../services/api'
import type { Dataset } from '../types/dataset'
import type { Pipeline, ProcessedDataset } from '../types/pipeline'
import './processed-dataset.css'

const PAGE_SIZE=20
const when=(value:string)=>new Date(value).toLocaleString()
const size=(bytes:number)=>bytes<1024?`${bytes} B`:bytes<1048576?`${(bytes/1024).toFixed(1)} KB`:`${(bytes/1048576).toFixed(1)} MB`

export function ProcessedDatasets() {
  const [items,setItems]=useState<ProcessedDataset[]>([])
  const [sources,setSources]=useState<Record<string,Dataset>>({})
  const [pipelines,setPipelines]=useState<Record<string,Pipeline>>({})
  const [total,setTotal]=useState(0)
  const [offset,setOffset]=useState(0)
  const [loading,setLoading]=useState(true)
  const [error,setError]=useState('')

  const refresh=useCallback(async()=>{
    setLoading(true);setError('')
    try{
      const [page,datasetPage]=await Promise.all([api.processedDatasets(PAGE_SIZE,offset),api.datasets('')])
      setItems(page.items);setTotal(page.total);setSources(Object.fromEntries(datasetPage.items.map(item=>[item.id,item])))
      const executions=await Promise.all(page.items.map(async item=>{
        try{return [item.execution_id,await api.execution(item.execution_id)] as const}catch{return [item.execution_id,null] as const}
      }))
      const pipelineIds=[...new Set(executions.flatMap(([,execution])=>execution?[execution.pipeline_id]:[]))]
      const found=await Promise.all(pipelineIds.map(async id=>{try{return [id,await api.pipeline(id)] as const}catch{return [id,null] as const}}))
      const pipelineById=Object.fromEntries(found.filter((entry):entry is readonly [string,Pipeline]=>entry[1]!==null))
      const executionById=Object.fromEntries(executions)
      const pipelineByOutput:Record<string,Pipeline>={}
      for(const item of page.items){const pipelineId=executionById[item.execution_id]?.pipeline_id;const found=pipelineId?pipelineById[pipelineId]:undefined;if(found)pipelineByOutput[item.id]=found}
      setPipelines(pipelineByOutput)
    }catch(e){setError(e instanceof Error?e.message:'Processed datasets could not be loaded.')}
    finally{setLoading(false)}
  },[offset])
  useEffect(()=>{void refresh()},[refresh])

  return <div className="page-content processed-page">
    <div className="page-heading"><div><div className="eyebrow"><span className="eyebrow-dot"/> PIPELINE OUTPUTS</div><h1>Processed datasets</h1><p className="subtitle">Browse, preview and download files produced by pipeline runs.</p></div><button className="secondary-button" onClick={()=>void refresh()} disabled={loading}><RefreshCw size={14}/> Refresh</button></div>
    {error&&<div className="error-banner" role="alert">{error}<button aria-label="Dismiss" onClick={()=>setError('')}><X size={14}/></button></div>}
    <div className="processed-toolbar"><span>{total.toLocaleString()} processed datasets</span><span className="processed-note">Outputs are stored separately from their source uploads.</span></div>
    <section className="panel processed-list-panel"><div className="processed-list-head"><span>PROCESSED DATASET</span><span>SOURCE</span><span>PIPELINE</span><span>FORMAT</span><span>RECORDS</span><span>COLUMNS</span><span>CREATED</span><span/></div>
      {loading?<div className="page-loading"><LoaderCircle size={18} className="spin"/> Loading processed datasets…</div>:items.map(item=><div className="processed-list-row" key={item.id}>
        <Link to={`/processed-datasets/${encodeURIComponent(item.id)}`} className="processed-file-cell"><i className={`file-icon ${item.file_type}`}>{item.file_type==='csv'?<FileSpreadsheet size={16}/>:<FileJson2 size={16}/>}</i><span><b>{item.filename}</b><small>{size(item.file_size)}</small></span></Link>
        <Link className="processed-related-link" to={`/datasets/${encodeURIComponent(item.source_dataset_id)}`}>{sources[item.source_dataset_id]?.name??item.source_dataset_id.slice(0,8)}</Link>
        <Link className="processed-related-link" to={pipelines[item.id]?`/pipelines/${encodeURIComponent(pipelines[item.id].id)}`:'#'}>{pipelines[item.id]?.name??`Run ${item.execution_id.slice(0,8)}`}</Link>
        <span><span className={`format-label ${item.file_type}`}>{item.file_type.toUpperCase()}</span></span><span>{item.row_count.toLocaleString()}</span><span>{item.column_count}</span><span>{when(item.created_at)}</span><Link className="processed-open" to={`/processed-datasets/${encodeURIComponent(item.id)}`} aria-label={`Open ${item.filename}`}><ArrowRight size={15}/></Link>
      </div>)}
      {!loading&&!items.length&&<div className="processed-empty"><div className="pipeline-empty-icon"><Database size={20}/></div><b>No processed outputs yet</b><p>Run a saved pipeline to create a separate processed dataset.</p><Link to="/pipelines" className="secondary-button">Open pipelines</Link></div>}
      <div className="table-footer"><span>Showing {items.length?offset+1:0}–{Math.min(offset+items.length,total)} of {total}</span><div><button aria-label="Previous processed datasets" disabled={offset===0||loading} onClick={()=>setOffset(Math.max(0,offset-PAGE_SIZE))}><ChevronLeft size={15}/></button><button className="page-number">{Math.floor(offset/PAGE_SIZE)+1}</button><button aria-label="Next processed datasets" disabled={offset+PAGE_SIZE>=total||loading} onClick={()=>setOffset(offset+PAGE_SIZE)}><ChevronRight size={15}/></button></div></div>
    </section>
  </div>
}
