import { ArrowRight, ChevronLeft, ChevronRight, GitBranch, LoaderCircle, Play, Plus, RefreshCw, Trash2, X } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api } from '../services/api'
import type { Dataset } from '../types/dataset'
import type { Pipeline, PipelineExecution } from '../types/pipeline'
import './pipeline.css'

const PAGE_SIZE = 20
const count = (value:number|null|undefined) => value === null || value === undefined ? '—' : value.toLocaleString()
const date = (value:string|null|undefined) => value ? new Date(value).toLocaleString() : '—'

export function Pipelines() {
  const [items,setItems] = useState<Pipeline[]>([])
  const [latest,setLatest] = useState<Record<string,PipelineExecution|null>>({})
  const [datasets,setDatasets] = useState<Record<string,Dataset>>({})
  const [total,setTotal] = useState(0)
  const [offset,setOffset] = useState(0)
  const [loading,setLoading] = useState(true)
  const [error,setError] = useState('')
  const [deleting,setDeleting] = useState<Pipeline|null>(null)
  const [busy,setBusy] = useState(false)

  const refresh = useCallback(async () => {
    setLoading(true); setError('')
    try {
      const [page,datasetPage] = await Promise.all([api.pipelines(PAGE_SIZE,offset),api.datasets('')])
      setItems(page.items); setTotal(page.total)
      setDatasets(Object.fromEntries(datasetPage.items.map(dataset=>[dataset.id,dataset])))
      const histories = await Promise.all(page.items.map(async pipeline => {
        try { return [pipeline.id,(await api.pipelineExecutions(pipeline.id,1,0)).items[0]??null] as const }
        catch { return [pipeline.id,null] as const }
      }))
      setLatest(Object.fromEntries(histories))
    } catch(e) { setError(e instanceof Error?e.message:'Pipelines could not be loaded.') }
    finally { setLoading(false) }
  },[offset])

  useEffect(()=>{void refresh()},[refresh])

  async function deletePipeline() {
    if(!deleting)return
    setBusy(true);setError('')
    try { await api.removePipeline(deleting.id);setDeleting(null);await refresh() }
    catch(e){setError(e instanceof Error?e.message:'Pipeline could not be deleted.');setDeleting(null)}
    finally{setBusy(false)}
  }

  return <div className="page-content pipeline-page">
    <div className="page-heading"><div><div className="eyebrow"><span className="eyebrow-dot"/> AUTOMATION</div><h1>Pipelines</h1><p className="subtitle">Prepare, run and track transformations on your datasets.</p></div><Link className="primary-button" to="/pipelines/new"><Plus size={15}/> New pipeline</Link></div>
    {error&&<div className="error-banner" role="alert">{error}<button aria-label="Dismiss" onClick={()=>setError('')}><X size={14}/></button></div>}
    <div className="pipeline-toolbar"><span>{total.toLocaleString()} pipelines</span><button className="secondary-button" onClick={()=>void refresh()} disabled={loading}><RefreshCw size={14}/> Refresh</button></div>
    <section className="panel pipeline-list-panel"><div className="pipeline-list-head"><span>PIPELINE</span><span>SOURCE</span><span>STEPS</span><span>LAST EXECUTION</span><span>STATUS</span><span/></div>
      {loading?<div className="page-loading"><LoaderCircle size={18} className="spin"/> Loading pipelines…</div>:items.map(pipeline=>{
        const execution=latest[pipeline.id]
        const source=datasets[pipeline.source_dataset_id]
        return <div className="pipeline-list-row" key={pipeline.id}>
          <Link to={`/pipelines/${encodeURIComponent(pipeline.id)}`} className="pipeline-name-cell"><span className="pipeline-symbol"><GitBranch size={16}/></span><span><b>{pipeline.name}</b><small>{pipeline.description||'No description'}</small></span></Link>
          <span className="pipeline-source-cell">{source?.name??pipeline.source_dataset_id.slice(0,10)}</span><span>{pipeline.steps.length} steps</span>
          <span className="pipeline-last-run">{execution?<><small>{date(execution.started_at)}</small><span>{count(execution.total_input_rows)} → {count(execution.total_output_rows)} rows</span></>:'Not run yet'}</span>
          <span>{execution?<StatusPill status={execution.status}/>:<StatusPill status="ready"/>}</span>
          <span className="pipeline-row-actions"><Link to={`/pipelines/${encodeURIComponent(pipeline.id)}`} aria-label={`Open ${pipeline.name}`} title="Open pipeline"><ArrowRight size={15}/></Link><button aria-label={`Delete ${pipeline.name}`} title="Delete pipeline" onClick={()=>setDeleting(pipeline)}><Trash2 size={14}/></button></span>
        </div>
      })}
      {!loading&&!items.length&&<div className="pipeline-empty-state"><div className="pipeline-empty-icon"><GitBranch size={21}/></div><b>No pipelines yet</b><p>Create a pipeline to configure and run transformations against an uploaded dataset.</p><Link className="secondary-button" to="/pipelines/new"><Plus size={14}/> Create your first pipeline</Link></div>}
      <div className="table-footer"><span>Showing {items.length?offset+1:0}–{Math.min(offset+items.length,total)} of {total}</span><div><button aria-label="Previous pipelines" disabled={offset===0||loading} onClick={()=>setOffset(Math.max(0,offset-PAGE_SIZE))}><ChevronLeft size={15}/></button><button className="page-number" aria-label={`Pipeline page ${Math.floor(offset/PAGE_SIZE)+1}`}>{Math.floor(offset/PAGE_SIZE)+1}</button><button aria-label="Next pipelines" disabled={offset+PAGE_SIZE>=total||loading} onClick={()=>setOffset(offset+PAGE_SIZE)}><ChevronRight size={15}/></button></div></div>
    </section>
    <div className="pipeline-footnote"><Play size={13}/> Runs execute synchronously on the backend. No background progress is simulated.</div>
    {deleting&&<div className="modal-backdrop" role="presentation"><section className="modal confirm-modal" role="dialog" aria-modal="true" aria-labelledby="delete-pipeline-heading"><div className="danger-icon"><Trash2 size={18}/></div><button className="icon-button close-confirm" aria-label="Close" onClick={()=>setDeleting(null)}><X size={16}/></button><h2 id="delete-pipeline-heading">Delete pipeline?</h2><p><b>{deleting.name}</b>, its execution history and processed dataset records will be deleted.</p><div className="confirm-actions"><button className="secondary-button" onClick={()=>setDeleting(null)} disabled={busy}>Cancel</button><button className="danger-button" onClick={()=>void deletePipeline()} disabled={busy}>{busy?<LoaderCircle size={14} className="spin"/>:'Delete pipeline'}</button></div></section></div>}
  </div>
}

export function StatusPill({status}:{status:string}) { return <span className={`run-status status-${status}`}><i/>{status==='success'?'Success':status==='failed'?'Failed':status==='running'?'Running':status==='pending'?'Pending':'Ready'}</span> }
