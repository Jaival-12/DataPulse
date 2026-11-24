import { AlertTriangle, Check, Clock3, Rows3 } from 'lucide-react'
import type { ExecutionLog, PipelineExecution } from '../types/pipeline'
import { operationNames } from '../utils/pipelineBuilder'
import { StatusPill } from '../pages/Pipelines'

const number = (value:number|null|undefined) => value===null||value===undefined?'—':value.toLocaleString()
const time = (value:string|null|undefined) => value?new Date(value).toLocaleString():'—'
const duration = (value:number|null|undefined) => value===null||value===undefined?'—':value<1?`${Math.round(value*1000)} ms`:`${value.toFixed(2)} s`
function stepName(operation:string) { return operation in operationNames?operationNames[operation as keyof typeof operationNames]:operation.replace(/_/g,' ') }

export function ExecutionDetails({execution,logs}:{execution:PipelineExecution;logs:ExecutionLog[]}) {
  const successCount=logs.filter(log=>log.status==='success').length
  const failedCount=logs.filter(log=>log.status==='failed').length
  return <div className="execution-detail-view">
    <div className="execution-detail-heading"><div><div className="eyebrow"><span className="eyebrow-dot"/> EXECUTION DETAIL</div><h3>Run {execution.id.slice(0,8)}</h3><p>{time(execution.started_at)}</p></div><StatusPill status={execution.status}/></div>
    <div className="execution-metrics"><Metric icon={<Clock3 size={15}/>} label="Duration" value={duration(execution.duration)}/><Metric icon={<Rows3 size={15}/>} label="Input rows" value={number(execution.total_input_rows)}/><Metric icon={<Rows3 size={15}/>} label="Output rows" value={number(execution.total_output_rows)}/><Metric icon={<Check size={15}/>} label="Successful steps" value={String(successCount)}/><Metric icon={<AlertTriangle size={15}/>} label="Failed steps" value={String(failedCount)}/></div>
    <div className="execution-times"><span>Started <b>{time(execution.started_at)}</b></span><span>Completed <b>{time(execution.completed_at)}</b></span><span>Execution ID <code>{execution.id}</code></span></div>
    {execution.error_message&&<div className="run-error" role="alert"><AlertTriangle size={15}/><div><b>Execution failed</b><p>{execution.error_message}</p></div></div>}
    <div className="logs-heading"><div><h4>Step logs</h4><p>{logs.length} recorded {logs.length===1?'step':'steps'}</p></div></div>
    {logs.length?<div className="execution-log-list">{logs.map((log,index)=><div className={`execution-log-row log-${log.status}`} key={`${log.step_id??log.step_index??index}-${index}`}>
      <div className="log-index">{log.step_index===null||log.step_index===undefined?'—':String(log.step_index+1).padStart(2,'0')}</div><div className="log-operation"><b>{stepName(log.operation)}</b><small>{log.operation}</small></div><StatusPill status={log.status}/><span className="log-rows">{number(log.input_rows)} → {number(log.output_rows)} rows</span><span className="log-duration">{duration(log.duration)}</span>{log.error&&<p className="log-error">{log.error}</p>}
    </div>)}</div>:<div className="detail-empty">No step logs were returned for this execution.</div>}
    {execution.processed_dataset&&<div className="execution-output-link"><Check size={14}/> Processed output <b>{execution.processed_dataset.filename}</b></div>}
  </div>
}

function Metric({icon,label,value}:{icon:React.ReactNode;label:string;value:string}) {return <div className="execution-metric"><i>{icon}</i><small>{label}</small><b>{value}</b></div>}
