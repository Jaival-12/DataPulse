import { useEffect, useMemo, useState } from 'react'
import { ArrowRight, LoaderCircle, Plus, ShieldCheck, Trash2 } from 'lucide-react'
import { Link } from 'react-router-dom'
import { api } from '../services/api'
import type { DataQualityReport, QualityRule } from '../types/quality'

type Props={targetType:'dataset'|'processed';targetId:string;columns:string[];sourceDatasetId?:string}
const score=(r:DataQualityReport|undefined,key:keyof DataQualityReport['dimension_scores'])=>r?.dimension_scores[key]

export function QualityHistory({targetType,targetId,columns,sourceDatasetId}:Props){
  const [reports,setReports]=useState<DataQualityReport[]>([])
  const [originalReports,setOriginalReports]=useState<DataQualityReport[]>([])
  const [rules,setRules]=useState<QualityRule[]>([])
  const [ruleType,setRuleType]=useState('not_null')
  const [column,setColumn]=useState(columns[0]??'')
  const [busy,setBusy]=useState(false)
  const [error,setError]=useState('')
  const [notice,setNotice]=useState('')
  const load=()=>{
    const history=targetType==='dataset'?api.datasetQualityReports(targetId):api.processedQualityReports(targetId)
    history.then(page=>setReports(page.items)).catch(e=>setError(e instanceof Error?e.message:'Quality report history could not be loaded.'))
    if(targetType==='processed'&&sourceDatasetId)api.datasetQualityReports(sourceDatasetId).then(page=>setOriginalReports(page.items)).catch(()=>setOriginalReports([]))
  }
  useEffect(()=>{setColumn(columns[0]??'');load()},[targetId,targetType,sourceDatasetId])
  const latest=reports[0]
  const original=originalReports[0]
  const canCompare=targetType==='processed'&&Boolean(sourceDatasetId)&&latest?.processed_dataset_id===targetId&&original?.dataset_id===sourceDatasetId
  const compareKeys=useMemo(()=>(['completeness','validity','uniqueness','consistency','rule_based_correctness'] as const),[])
  async function analyze(){setBusy(true);setError('');setNotice('');try{const report=targetType==='dataset'?await api.analyzeDatasetQuality(targetId,rules):await api.analyzeProcessedQuality(targetId,rules);setReports(current=>[report,...current.filter(item=>item.id!==report.id)]);setNotice(report.status==='not_scored'?'Analysis saved; no dimensions could be scored.':'Quality analysis completed.')}catch(e){setError(e instanceof Error?e.message:'Quality analysis failed.')}finally{setBusy(false)}}
  function addRule(){if(!column)return;let rule:QualityRule;if(ruleType==='required_columns')rule={type:'required_columns',columns:[column]};else if(ruleType==='greater_than')rule={type:'greater_than',column,value:0};else if(ruleType==='range')rule={type:'range',column,min_value:0,max_value:100};else rule={type:ruleType as 'not_null'|'unique'|'non_negative',column};setRules(current=>[...current,rule])}
  return <div className="detail-section quality-history-detail">
    <section className="panel detail-panel quality-action-panel"><div className="panel-header"><div><h2>Data quality analysis</h2><p>Analyze the {targetType==='dataset'?'original upload':'processed output'} without changing its contents.</p></div><ShieldCheck size={18}/></div>
      <div className="quality-rule-toolbar"><label>Rule type<select aria-label="Quality rule type" value={ruleType} onChange={e=>setRuleType(e.target.value)}><option value="not_null">Not null</option><option value="unique">Unique</option><option value="non_negative">Non-negative</option><option value="greater_than">Greater than 0</option><option value="range">Range 0 to 100</option><option value="required_columns">Required column</option></select></label><label>Column<select aria-label="Quality rule column" value={column} onChange={e=>setColumn(e.target.value)}>{columns.map(name=><option key={name} value={name}>{name}</option>)}</select></label><button className="secondary-button" onClick={addRule} disabled={!columns.length}><Plus size={14}/> Add rule</button></div>
      {rules.length>0&&<div className="quality-rule-list">{rules.map((rule,index)=><div key={`${rule.type}-${index}`}><span>{rule.type.replace(/_/g,' ')} · {'column' in rule?rule.column:rule.columns.join(', ')}</span><button aria-label={`Remove rule ${index+1}`} onClick={()=>setRules(current=>current.filter((_,i)=>i!==index))}><Trash2 size={13}/></button></div>)}</div>}
      {error&&<div className="error-banner" role="alert">{error}</div>}{notice&&<div className="success-banner" role="status">{notice}</div>}
      <div className="quality-run-row"><span>Findings and scores are stored as a new report.</span><button className="primary-button" disabled={busy} onClick={()=>void analyze()}>{busy?<LoaderCircle size={14} className="spin"/>:<ShieldCheck size={14}/>} {busy?'Analyzing…':'Run quality analysis'}</button></div>
    </section>
    <section className="panel quality-local-history"><div className="panel-header"><div><h2>Analysis history</h2><p>Reports for this exact data source.</p></div><span className="detail-count">{reports.length} reports</span></div>{reports.map(report=><Link className="quality-local-report" key={report.id} to={`/quality?report=${encodeURIComponent(report.id)}`}><span className="history-grade">{report.overall_score===null?'—':report.overall_score.toFixed(1)}</span><span><b>{report.quality_label}</b><small>{new Date(report.created_at).toLocaleString()} · {report.total_issues} issues</small></span><ArrowRight size={14}/></Link>)}{!reports.length&&<div className="detail-empty">No analyses have been run for this source.</div>}</section>
    {targetType==='processed'&&sourceDatasetId&&<section className="panel quality-comparison"><div className="panel-header"><div><h2>Same-lineage comparison</h2><p>Latest original source versus latest processed output report.</p></div></div>{canCompare?<><div className="quality-comparison-head"><span>Dimension</span><span>Original</span><span>Processed</span><span>Change</span></div>{compareKeys.map(key=>{const before=score(original,key);const after=score(latest,key);return <div className="quality-comparison-row" key={key}><span>{key.replace(/_/g,' ')}</span><span>{before==null?'Not evaluated':`${before.toFixed(1)}%`}</span><span>{after==null?'Not evaluated':`${after.toFixed(1)}%`}</span><b>{before==null||after==null?'—':`${after-before>=0?'+':''}${(after-before).toFixed(1)} pts`}</b></div>})}</>:<div className="detail-empty">Run an analysis on both this output and its original source to compare their measured dimensions.</div>}</section>}
  </div>
}
