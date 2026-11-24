import { ArrowLeft, CheckCircle2, ChevronLeft, ChevronRight, CirclePlay, Clock3, GitBranch, LoaderCircle, Plus, Save, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { ExecutionDetails } from '../components/ExecutionDetails'
import { PipelineStepEditor } from '../components/PipelineStepEditor'
import { api } from '../services/api'
import type { Dataset } from '../types/dataset'
import type { ExecutionLog, Pipeline, PipelineExecution, PipelineOperation, PipelineStepConfig, PipelineWrite } from '../types/pipeline'
import { columnsBeforeStep, createStep, normalizeStep, operationChoices, validateStep, type EditableStep } from '../utils/pipelineBuilder'
import { StatusPill } from './Pipelines'
import './pipeline.css'

const RUN_PAGE_SIZE=20
const time=(value:string|null|undefined)=>value?new Date(value).toLocaleString():'—'
const duration=(value:number|null|undefined)=>value===null||value===undefined?'—':value<1?`${Math.round(value*1000)} ms`:`${value.toFixed(2)} s`

export function PipelineDetail({isNewPipeline=false}:{isNewPipeline?:boolean}) {
  const {pipelineId=''}=useParams()
  const isNew=isNewPipeline||pipelineId==='new'
  const navigate=useNavigate()
  const [datasets,setDatasets]=useState<Dataset[]>([])
  const [pipeline,setPipeline]=useState<Pipeline|null>(null)
  const [name,setName]=useState('')
  const [description,setDescription]=useState('')
  const [sourceId,setSourceId]=useState('')
  const [outputFormat,setOutputFormat]=useState<'csv'|'json'>('csv')
  const [steps,setSteps]=useState<EditableStep[]>([])
  const [tab,setTab]=useState<'builder'|'runs'>('builder')
  const [addOperation,setAddOperation]=useState('')
  const [loading,setLoading]=useState(true)
  const [saving,setSaving]=useState(false)
  const [running,setRunning]=useState(false)
  const [error,setError]=useState('')
  const [notice,setNotice]=useState('')
  const [formErrors,setFormErrors]=useState<string[]>([])
  const [history,setHistory]=useState<PipelineExecution[]>([])
  const [historyTotal,setHistoryTotal]=useState(0)
  const [historyOffset,setHistoryOffset]=useState(0)
  const [historyLoading,setHistoryLoading]=useState(false)
  const [latest,setLatest]=useState<PipelineExecution|null>(null)
  const [selectedExecution,setSelectedExecution]=useState<PipelineExecution|null>(null)
  const [selectedLogs,setSelectedLogs]=useState<ExecutionLog[]>([])
  const [executionLoading,setExecutionLoading]=useState(false)

  const refreshHistory=useCallback(async (id:string,offset=0) => {
    const page=await api.pipelineExecutions(id,RUN_PAGE_SIZE,offset)
    setHistory(page.items);setHistoryTotal(page.total);setHistoryOffset(offset)
    if(offset===0)setLatest(page.items[0]??null)
    return page.items
  },[])

  const refreshPipeline=useCallback(async (id:string) => {
    const saved=await api.pipeline(id)
    setPipeline(saved);setName(saved.name);setDescription(saved.description??'');setSourceId(saved.source_dataset_id);setOutputFormat(saved.configuration.output_format??'csv')
    setSteps(saved.steps.slice().sort((a,b)=>a.execution_order-b.execution_order).map(step=>({operation:step.operation,config:step.configuration})))
    await refreshHistory(id,0)
  },[refreshHistory])

  useEffect(()=>{
    let cancelled=false
    setLoading(true);setError('');setPipeline(null);setSteps([]);setSelectedExecution(null)
    const load=async()=>{
      try{
        const datasetPage=await api.datasets('')
        if(cancelled)return
        setDatasets(datasetPage.items)
        if(isNew){setSourceId(current=>current||datasetPage.items[0]?.id||'');setLoading(false);return}
        const saved=await api.pipeline(pipelineId)
        if(cancelled)return
        setPipeline(saved);setName(saved.name);setDescription(saved.description??'');setSourceId(saved.source_dataset_id);setOutputFormat(saved.configuration.output_format??'csv')
        setSteps(saved.steps.slice().sort((a,b)=>a.execution_order-b.execution_order).map(step=>({operation:step.operation,config:step.configuration})))
        const page=await api.pipelineExecutions(pipelineId,RUN_PAGE_SIZE,0)
        if(cancelled)return
        setHistory(page.items);setHistoryTotal(page.total);setHistoryOffset(0);setLatest(page.items[0]??null)
      }catch(e){if(!cancelled)setError(e instanceof Error?e.message:'Pipeline details could not be loaded.')}
      finally{if(!cancelled)setLoading(false)}
    }
    void load()
    return()=>{cancelled=true}
  },[pipelineId,isNew])

  const sourceDataset=datasets.find(dataset=>dataset.id===sourceId)
  const allStepErrors=useMemo(()=>steps.map((step,index)=>validateStep(step,columnsBeforeStep(sourceDataset?.columns??[],steps,index))),[sourceDataset,steps])
  const anyStepErrors=allStepErrors.some(list=>list.length>0)

  function updateStep(index:number,operation:PipelineOperation,config:PipelineStepConfig){setSteps(current=>current.map((step,i)=>i===index?{operation,config}:step));setFormErrors([])}
  function moveStep(index:number,direction:-1|1){setSteps(current=>{const next=[...current];const target=index+direction;if(target<0||target>=next.length)return current;[next[index],next[target]]=[next[target],next[index]];return next})}
  function addStep(){
    const choice=operationChoices.find(item=>item.value===addOperation)
    if(!choice)return
    const columns=columnsBeforeStep(sourceDataset?.columns??[],steps,steps.length)
    setSteps(current=>[...current,createStep(choice.operation,columns)])
    setAddOperation('');setFormErrors([])
  }

  async function savePipeline(event:React.FormEvent){
    event.preventDefault();setError('');setNotice('')
    const errors:string[]=[]
    if(!name.trim())errors.push('Enter a pipeline name.')
    if(!sourceId)errors.push('Select a source dataset.')
    steps.forEach((step,index)=>validateStep(step,columnsBeforeStep(sourceDataset?.columns??[],steps,index)).forEach(message=>errors.push(`Step ${index+1}: ${message}`)))
    if(errors.length){setFormErrors(errors);return}
    const payload:PipelineWrite={name:name.trim(),description:description.trim()||null,source_dataset_id:sourceId,output_format:outputFormat,steps:steps.map((step,index)=>normalizeStep(step,columnsBeforeStep(sourceDataset?.columns??[],steps,index)))}
    setSaving(true);setFormErrors([])
    try{
      const savedPipelineId=pipeline?.id
      const saved=savedPipelineId?await api.updatePipeline(savedPipelineId,payload):await api.createPipeline(payload)
      if(!saved.id)throw new Error('The server saved the pipeline but did not return its ID.')
      setPipeline(saved);setNotice('Pipeline saved.')
      if(!savedPipelineId)navigate(`/pipelines/${encodeURIComponent(saved.id)}`,{replace:true})
      else await refreshPipeline(saved.id)
    }catch(e){setError(e instanceof Error?e.message:'Pipeline could not be saved.')}
    finally{setSaving(false)}
  }

  async function runPipeline(){
    if(!pipeline)return
    setRunning(true);setError('');setNotice('');setTab('builder')
    try{
      const result=await api.executePipeline(pipeline.id)
      setLatest(result);setNotice(result.status==='success'?'Pipeline completed successfully.':'Pipeline execution failed. Review the execution logs below.')
      await refreshPipeline(pipeline.id)
      setLatest(result)
    }catch(e){setError(e instanceof Error?e.message:'Pipeline could not be executed.')}
    finally{setRunning(false)}
  }

  async function changeHistoryPage(offset:number){
    if(!pipeline)return
    setHistoryLoading(true)
    try{await refreshHistory(pipeline.id,offset)}catch(e){setError(e instanceof Error?e.message:'Execution history could not be loaded.')}
    finally{setHistoryLoading(false)}
  }

  async function openExecution(item:PipelineExecution){
    setExecutionLoading(true);setSelectedExecution(item);setSelectedLogs([]);setError('')
    try{
      const [detail,logs]=await Promise.all([api.execution(item.id),api.executionLogs(item.id)])
      setSelectedExecution(detail);setSelectedLogs(logs.logs)
    }catch(e){setError(e instanceof Error?e.message:'Execution details could not be loaded.')}
    finally{setExecutionLoading(false)}
  }

  if(loading)return <div className="page-content"><div className="page-loading"><LoaderCircle size={18} className="spin"/> Loading pipeline…</div></div>
  if(!isNew&&!pipeline)return <div className="page-content"><Link to="/pipelines" className="detail-back"><ArrowLeft size={14}/> All pipelines</Link><div className="error-banner">{error||'Pipeline not found.'}</div></div>

  const visibleExecution=latest
  return <div className="page-content pipeline-page pipeline-detail-page">
    <Link to="/pipelines" className="detail-back"><ArrowLeft size={14}/> All pipelines</Link>
    <div className="page-heading pipeline-detail-heading"><div><div className="eyebrow"><span className="eyebrow-dot"/> PIPELINE BUILDER</div><h1>{isNew?'New pipeline':pipeline?.name}</h1><p className="subtitle">{isNew?'Configure an ordered transformation flow.':pipeline?.description||'Configure transformations and inspect real execution results.'}</p></div>
      {!isNew&&<button className="primary-button" onClick={()=>void runPipeline()} disabled={running||saving||anyStepErrors}>{running?<LoaderCircle size={15} className="spin"/>:<CirclePlay size={16}/>} {running?'Executing synchronously…':'Run pipeline'}</button>}
    </div>
    {(error||notice)&&<div className={error?'error-banner':'success-banner'} role={error?'alert':'status'}>{error||<><CheckCircle2 size={14}/>{notice}</>}<button aria-label="Dismiss" onClick={()=>{setError('');setNotice('')}}><X size={14}/></button></div>}
    {!datasets.length?<div className="panel pipeline-no-datasets"><div className="pipeline-empty-icon"><GitBranch size={20}/></div><h2>Upload a source dataset first</h2><p>Pipelines transform uploaded CSV or JSON datasets into separate processed outputs.</p><Link className="secondary-button" to="/datasets">Open datasets</Link></div>:<>
      {!isNew&&<div className="pipeline-tabs" role="tablist" aria-label="Pipeline sections"><button role="tab" aria-selected={tab==='builder'} className={tab==='builder'?'active':''} onClick={()=>setTab('builder')}><GitBranch size={14}/> Builder</button><button role="tab" aria-selected={tab==='runs'} className={tab==='runs'?'active':''} onClick={()=>setTab('runs')}><Clock3 size={14}/> Runs <span>{historyTotal}</span></button></div>}
      {visibleExecution&&<div className="latest-run-card"><div className="latest-run-leading"><StatusPill status={visibleExecution.status}/><div><b>{visibleExecution.status==='success'?'Last run completed':visibleExecution.status==='failed'?'Last run failed':'Execution result'}</b><small>{time(visibleExecution.started_at)} · {duration(visibleExecution.duration)}</small></div></div><div className="latest-run-stats"><span>{visibleExecution.total_input_rows?.toLocaleString()??'—'} input rows</span><b>→</b><span>{visibleExecution.total_output_rows?.toLocaleString()??'—'} output rows</span></div>{visibleExecution.processed_dataset&&<Link to={`/processed-datasets/${encodeURIComponent(visibleExecution.processed_dataset.id)}`}>Open output <ArrowLeft size={12}/></Link>}</div>}
      {tab==='builder'&&<form className="pipeline-builder" onSubmit={event=>void savePipeline(event)}>
        <section className="panel builder-basics"><div className="panel-header"><div><h2>Pipeline details</h2><p>Name the flow and choose the dataset it reads.</p></div><span className="phase-tag">PHASE 3A ENGINE</span></div><div className="builder-basics-grid">
          <label className="builder-field"><span>Pipeline name</span><input aria-label="Pipeline name" value={name} onChange={event=>setName(event.target.value)} placeholder="e.g. Clean customer exports" maxLength={255}/></label>
          <label className="builder-field"><span>Source dataset</span><select aria-label="Source dataset" value={sourceId} onChange={event=>setSourceId(event.target.value)}><option value="">Select a dataset…</option>{datasets.map(dataset=><option value={dataset.id} key={dataset.id}>{dataset.name} · {dataset.row_count.toLocaleString()} rows</option>)}</select></label>
          <label className="builder-field builder-description-field"><span>Description <small>Optional</small></span><textarea aria-label="Pipeline description" rows={2} value={description} onChange={event=>setDescription(event.target.value)} placeholder="What should this pipeline prepare?"/></label>
          <label className="builder-field"><span>Output format</span><select aria-label="Output format" value={outputFormat} onChange={event=>setOutputFormat(event.target.value as 'csv'|'json')}><option value="csv">CSV</option><option value="json">JSON</option></select></label>
        </div></section>
        <section className="steps-section"><div className="steps-section-heading"><div><div className="eyebrow"><span className="eyebrow-dot"/> TRANSFORMATIONS</div><h2>Build your pipeline</h2><p>Add and configure each step in the order it should run.</p></div><span className="step-count">{steps.length} {steps.length===1?'step':'steps'}</span></div>
          {!steps.length&&<div className="empty-steps"><div className="pipeline-empty-icon"><GitBranch size={19}/></div><b>No steps added</b><p>Start with one transformation. You can reorder it later.</p></div>}
          <div className="step-list">{steps.map((step,index)=><PipelineStepEditor key={`${index}-${step.operation}`} index={index} operation={step.operation} config={step.config} columns={columnsBeforeStep(sourceDataset?.columns??[],steps,index)} errors={allStepErrors[index]} canMoveUp={index>0} canMoveDown={index<steps.length-1} onChange={(operation,config)=>updateStep(index,operation,config)} onMoveUp={()=>moveStep(index,-1)} onMoveDown={()=>moveStep(index,1)} onRemove={()=>setSteps(current=>current.filter((_,i)=>i!==index))}/>)}</div>
          <div className="add-step-row"><label htmlFor="add-pipeline-step">Add a transformation</label><div><select id="add-pipeline-step" aria-label="Transformation to add" value={addOperation} onChange={event=>setAddOperation(event.target.value)}><option value="">Choose a step…</option>{operationChoices.map(choice=><option key={choice.value} value={choice.value}>{choice.label}</option>)}</select><button type="button" className="secondary-button" onClick={addStep} disabled={!addOperation}><Plus size={14}/> Add step</button></div></div>
        </section>
        {formErrors.length>0&&<ul className="builder-errors" role="alert">{formErrors.map((message,index)=><li key={`${message}-${index}`}>{message}</li>)}</ul>}
        <div className="builder-footer"><span>Steps execute in order. The source upload is never overwritten.</span><button className="primary-button" type="submit" disabled={saving||running}>{saving?<LoaderCircle size={14} className="spin"/>:<Save size={14}/>} {saving?'Saving…':isNew?'Create pipeline':'Save changes'}</button></div>
      </form>}
      {!isNew&&tab==='runs'&&<section className="panel run-history-panel"><div className="panel-header"><div><h2>Execution history</h2><p>Each run is synchronous and reports its completed result.</p></div><span className="detail-count">{historyTotal} total</span></div>{historyLoading?<div className="page-loading"><LoaderCircle size={17} className="spin"/> Loading runs…</div>:<div className="history-layout"><div className="history-table-wrap"><div className="history-table-head"><span>EXECUTION</span><span>STATUS</span><span>STARTED</span><span>DURATION</span><span>ROWS</span></div>{history.map(item=><button type="button" className={`history-row${selectedExecution?.id===item.id?' selected':''}`} key={item.id} onClick={()=>void openExecution(item)}><span className="history-id">{item.id.slice(0,8)}</span><StatusPill status={item.status}/><span>{time(item.started_at)}</span><span>{duration(item.duration)}</span><span>{item.total_input_rows?.toLocaleString()??'—'} → {item.total_output_rows?.toLocaleString()??'—'}</span></button>)}{!history.length&&<div className="detail-empty">No runs yet. Save the pipeline and run it to create the first execution.</div>}<div className="history-pagination"><span>Showing {history.length?historyOffset+1:0}–{Math.min(historyOffset+history.length,historyTotal)} of {historyTotal}</span><div><button aria-label="Previous execution page" disabled={historyOffset===0||historyLoading} onClick={()=>void changeHistoryPage(Math.max(0,historyOffset-RUN_PAGE_SIZE))}><ChevronLeft size={14}/></button><button aria-label="Next execution page" disabled={historyOffset+RUN_PAGE_SIZE>=historyTotal||historyLoading} onClick={()=>void changeHistoryPage(historyOffset+RUN_PAGE_SIZE)}><ChevronRight size={14}/></button></div></div></div><div className="history-detail-pane">{executionLoading?<div className="page-loading"><LoaderCircle size={17} className="spin"/> Loading execution…</div>:selectedExecution?<ExecutionDetails execution={selectedExecution} logs={selectedLogs}/>:<div className="detail-empty">Select an execution to inspect its step logs.</div>}</div></div>}</section>}
    </>}
  </div>
}
