import { AlertTriangle, ArrowRight, CalendarClock, ChevronLeft, ChevronRight, CircleAlert, Database, LoaderCircle, Search, ShieldCheck, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Bar, BarChart, CartesianGrid, Cell, Pie, PieChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../services/api'
import type { DataQualityIssue, DataQualityReport, QualityDimension, QualitySeverity } from '../types/quality'
import './quality.css'

const DIMENSIONS:QualityDimension[]=['completeness','validity','uniqueness','consistency','rule_based_correctness']
const SEVERITIES:QualitySeverity[]=['critical','high','medium','low']
const LABELS:Record<QualityDimension,string>={completeness:'Completeness',validity:'Validity',uniqueness:'Uniqueness',consistency:'Consistency',rule_based_correctness:'Rule-based correctness'}
const SEVERITY_COLORS:Record<QualitySeverity,string>={critical:'#f16b77',high:'#ec9a58',medium:'#e6bf64',low:'#66c898'}
const fmt=(value:number)=>new Intl.NumberFormat().format(value)
const score=(value:number|null)=>value===null?'—':`${value.toFixed(1)}%`
const PAGE_SIZE=20

export function Quality(){
  const [searchParams,setSearchParams]=useSearchParams()
  const requestedId=searchParams.get('report')??''
  const [reportPage,setReportPage]=useState({items:[],total:0,limit:PAGE_SIZE,offset:0} as {items:DataQualityReport[];total:number;limit:number;offset:number})
  const [activeId,setActiveId]=useState(requestedId)
  const [report,setReport]=useState<DataQualityReport|null>(null)
  const [issues,setIssues]=useState<DataQualityIssue[]>([])
  const [issueTotal,setIssueTotal]=useState(0)
  const [severityCounts,setSeverityCounts]=useState<Record<QualitySeverity,number>>({critical:0,high:0,medium:0,low:0})
  const [dimensionCounts,setDimensionCounts]=useState<Record<QualityDimension,number>>({completeness:0,validity:0,uniqueness:0,consistency:0,rule_based_correctness:0})
  const [severity,setSeverity]=useState('')
  const [dimension,setDimension]=useState('')
  const [search,setSearch]=useState('')
  const [issueOffset,setIssueOffset]=useState(0)
  const [reportLoading,setReportLoading]=useState(true)
  const [detailLoading,setDetailLoading]=useState(false)
  const [error,setError]=useState('')
  const [selectedIssue,setSelectedIssue]=useState<DataQualityIssue|null>(null)

  useEffect(()=>{
    let cancelled=false
    setReportLoading(true);setError('')
    api.qualityReports(PAGE_SIZE,reportPage.offset).then(page=>{
      if(cancelled)return
      setReportPage(page)
      if(!requestedId&&!activeId&&page.items.length)setActiveId(page.items[0].id)
      if(!page.items.length&&!requestedId)setActiveId('')
    }).catch(e=>{if(!cancelled)setError(e instanceof Error?e.message:'Quality reports could not be loaded.')}).finally(()=>{if(!cancelled)setReportLoading(false)})
    return()=>{cancelled=true}
  },[reportPage.offset,requestedId])

  useEffect(()=>{
    if(requestedId)setActiveId(requestedId)
  },[requestedId])

  useEffect(()=>{
    if(!activeId){setReport(null);setIssues([]);setIssueTotal(0);return}
    let cancelled=false
    setDetailLoading(true);setError('')
    api.qualityReport(activeId).then(value=>{if(!cancelled)setReport(value)}).catch(e=>{if(!cancelled)setError(e instanceof Error?e.message:'Quality report could not be loaded.')}).finally(()=>{if(!cancelled)setDetailLoading(false)})
    return()=>{cancelled=true}
  },[activeId])

  useEffect(()=>{
    if(!activeId){return}
    let cancelled=false
    const countsBySeverity=Promise.all(SEVERITIES.map(async item=>[item,(await api.qualityIssues(activeId,1,0,item)).total] as const))
    const countsByDimension=Promise.all(DIMENSIONS.map(async item=>[item,(await api.qualityIssues(activeId,1,0,undefined,item)).total] as const))
    api.qualityIssues(activeId,PAGE_SIZE,issueOffset,severity||undefined,dimension||undefined,search||undefined).then(page=>{
      if(!cancelled){setIssues(page.items);setIssueTotal(page.total);setSelectedIssue(null)}
    }).catch(e=>{if(!cancelled)setError(e instanceof Error?e.message:'Quality issues could not be loaded.')})
    Promise.all([countsBySeverity,countsByDimension]).then(([severityResult,dimensionResult])=>{
      if(cancelled)return
      setSeverityCounts(Object.fromEntries(severityResult) as Record<QualitySeverity,number>)
      setDimensionCounts(Object.fromEntries(dimensionResult) as Record<QualityDimension,number>)
    }).catch(e=>{if(!cancelled)setError(e instanceof Error?e.message:'Issue summaries could not be loaded.')})
    return()=>{cancelled=true}
  },[activeId,issueOffset,severity,dimension,search])

  const dimensionData=useMemo(()=>DIMENSIONS.filter(key=>report?.dimension_scores[key]!==null&&report?.dimension_scores[key]!==undefined).map(key=>({name:LABELS[key],score:report?.dimension_scores[key]??0})),[report])
  const severityData=SEVERITIES.map(key=>({name:key,count:severityCounts[key],color:SEVERITY_COLORS[key]})).filter(item=>item.count>0)
  const dimensionIssueData=DIMENSIONS.map(key=>({name:LABELS[key],count:dimensionCounts[key]})).filter(item=>item.count>0)

  function selectReport(id:string){setActiveId(id);setSearchParams({report:id});setIssueOffset(0);setSeverity('');setDimension('');setSearch('')}
  function changeReportPage(offset:number){setReportPage(current=>({...current,offset:Math.max(0,offset)}))}

  return <div className="page-content quality-page">
    <div className="page-heading"><div><div className="eyebrow"><span className="eyebrow-dot"/> DATA OBSERVABILITY</div><h1>Data Quality</h1><p className="subtitle">Review measured quality dimensions, rule checks and detected issues.</p></div><span className="quality-policy-tag"><ShieldCheck size={13}/> Rule-based correctness is not ground-truth accuracy</span></div>
    {error&&<div className="error-banner" role="alert">{error}<button aria-label="Dismiss error" onClick={()=>setError('')}><X size={14}/></button></div>}
    {reportLoading&&!reportPage.items.length?<div className="panel quality-empty"><LoaderCircle className="spin" size={20}/> Loading quality reports…</div>:!reportPage.total&&!activeId?<div className="panel quality-empty"><div className="quality-empty-icon"><ShieldCheck size={22}/></div><b>No quality reports yet</b><p>Run an analysis from an uploaded dataset or a processed dataset to see its score and issues here.</p><Link className="secondary-button" to="/datasets"><Database size={14}/> Open datasets</Link></div>:<>
      <div className="quality-report-toolbar"><div><span>{reportPage.total.toLocaleString()} saved reports</span>{report&&<small>Selected report · {new Date(report.created_at).toLocaleString()}</small>}</div><div className="quality-report-paging"><button aria-label="Previous report page" disabled={!reportPage.offset} onClick={()=>changeReportPage(reportPage.offset-PAGE_SIZE)}><ChevronLeft size={14}/></button><button aria-label="Next report page" disabled={reportPage.offset+PAGE_SIZE>=reportPage.total} onClick={()=>changeReportPage(reportPage.offset+PAGE_SIZE)}><ChevronRight size={14}/></button></div></div>
      <div className="quality-layout">
        <div className="quality-main">
          {detailLoading?<div className="panel quality-loading"><LoaderCircle size={18} className="spin"/> Loading report…</div>:report&&<>
            <section className="quality-overview-grid">
              <article className="panel quality-score-card"><div className="quality-score-ring" role="img" aria-label={`Overall quality score ${report.overall_score===null?'not scored':report.overall_score.toFixed(1)} out of 100`} style={{'--score-angle':`${(report.overall_score??0)*3.6}deg`,'--score-color':report.overall_score===null?'#555460':report.overall_score>=90?'#44c995':report.overall_score>=75?'#a68aff':report.overall_score>=50?'#e5bb62':'#ef777f'} as React.CSSProperties}><div className="quality-score-value" data-testid="quality-score-value"><b>{report.overall_score===null?'—':report.overall_score.toFixed(1)}</b><small>/ 100</small></div></div><div><span className={`quality-label quality-${report.quality_label.toLowerCase().replace(/ /g,'-')}`}>{report.quality_label}</span><h2>Overall quality</h2><p>Weighted score using the dimensions that were measured.</p></div></article>
              <Metric icon={<CircleAlert size={16}/>} label="Detected issues" value={fmt(report.total_issues)} tone={report.total_issues?'warning':'success'}/>
              <Metric icon={<AlertTriangle size={16}/>} label="Critical issues" value={fmt(severityCounts.critical)} tone={severityCounts.critical?'danger':'success'}/>
              <Metric icon={<Database size={16}/>} label="Rows analyzed" value={fmt(report.total_rows)} tone="normal"/>
              <Metric icon={<CalendarClock size={16}/>} label="Last analysis" value={new Date(report.created_at).toLocaleDateString()} tone="normal"/>
            </section>
            <section className="quality-dimensions"><div className="quality-section-heading"><div><h2>Dimension scores</h2><p>Unmeasured dimensions are shown as not evaluated.</p></div><span>{report.methodology.version as string}</span></div><div className="dimension-score-grid">{DIMENSIONS.map(item=><div className="panel dimension-score-card" key={item}><div><span>{LABELS[item]}</span><b>{score(report.dimension_scores[item])}</b></div><div className="dimension-track"><i style={{width:`${report.dimension_scores[item]??0}%`}} className={report.dimension_scores[item]===null?'unmeasured':`dimension-${item}`}/></div><small>{report.dimension_scores[item]===null?'Not evaluated':`${Math.round((report.scoring_weights[item]??0)*100)}% configured weight`}</small></div>)}</div></section>
            <section className="quality-charts-grid">
              <div className="panel quality-chart-panel"><div className="panel-header"><div><h2>Quality dimensions</h2><p>Scores from the selected report</p></div></div>{dimensionData.length?<ResponsiveContainer width="100%" height={230}><BarChart data={dimensionData} margin={{top:15,right:12,bottom:25,left:0}}><CartesianGrid stroke="#292933" vertical={false}/><XAxis dataKey="name" tick={{fill:'#898997',fontSize:9}} angle={-12} textAnchor="end" interval={0} axisLine={false} tickLine={false}/><YAxis domain={[0,100]} tick={{fill:'#777785',fontSize:9}} axisLine={false} tickLine={false}/><Tooltip contentStyle={{background:'#1d1d27',border:'1px solid #373743',borderRadius:6,color:'#e6e6ee',fontSize:10}} formatter={(value:number)=>[`${value.toFixed(1)}%`,'Score']}/><Bar dataKey="score" fill="#9878fb" radius={[4,4,0,0]} barSize={34}/></BarChart></ResponsiveContainer>:<ChartEmpty>No dimensions were measurable.</ChartEmpty>}</div>
              <div className="panel quality-chart-panel"><div className="panel-header"><div><h2>Issues by severity</h2><p>{report.total_issues} persisted findings</p></div></div>{severityData.length?<div className="severity-chart-layout"><ResponsiveContainer width="55%" height={205}><PieChart><Pie data={severityData} dataKey="count" nameKey="name" innerRadius={53} outerRadius={80} paddingAngle={3}>{severityData.map(item=><Cell key={item.name} fill={item.color}/>)}</Pie><Tooltip contentStyle={{background:'#1d1d27',border:'1px solid #373743',borderRadius:6,color:'#e6e6ee',fontSize:10}}/></PieChart></ResponsiveContainer><div className="severity-legend">{SEVERITIES.map(item=><div key={item}><i style={{background:SEVERITY_COLORS[item]}}/><span>{item}</span><b>{severityCounts[item]}</b></div>)}</div></div>:<ChartEmpty>No detected issues.</ChartEmpty>}</div>
              <div className="panel quality-chart-panel dimension-issue-chart"><div className="panel-header"><div><h2>Issues by dimension</h2><p>Dimensions with persisted findings</p></div></div>{dimensionIssueData.length?<ResponsiveContainer width="100%" height={220}><BarChart data={dimensionIssueData} margin={{top:10,right:10,bottom:25,left:0}}><CartesianGrid stroke="#292933" vertical={false}/><XAxis dataKey="name" tick={{fill:'#898997',fontSize:9}} angle={-12} textAnchor="end" interval={0} axisLine={false} tickLine={false}/><YAxis allowDecimals={false} tick={{fill:'#777785',fontSize:9}} axisLine={false} tickLine={false}/><Tooltip contentStyle={{background:'#1d1d27',border:'1px solid #373743',borderRadius:6,color:'#e6e6ee',fontSize:10}}/><Bar dataKey="count" fill="#56b9b4" radius={[4,4,0,0]} barSize={30}/></BarChart></ResponsiveContainer>:<ChartEmpty>No dimension issues to chart.</ChartEmpty>}</div>
            </section>
            <section className="panel issue-explorer"><div className="panel-header"><div><h2>Issue explorer</h2><p>Search findings and filter by dimension or severity.</p></div><span className="detail-count">{issueTotal} issues</span></div><div className="issue-filters"><label className="issue-search"><Search size={14}/><input aria-label="Search issues" value={search} onChange={event=>{setSearch(event.target.value);setIssueOffset(0)}} placeholder="Search issue, column, or description"/></label><label><span>Severity</span><select aria-label="Severity filter" value={severity} onChange={event=>{setSeverity(event.target.value);setIssueOffset(0)}}><option value="">All severities</option>{SEVERITIES.map(value=><option key={value} value={value}>{value}</option>)}</select></label><label><span>Dimension</span><select aria-label="Dimension filter" value={dimension} onChange={event=>{setDimension(event.target.value);setIssueOffset(0)}}><option value="">All dimensions</option>{DIMENSIONS.map(value=><option key={value} value={value}>{LABELS[value]}</option>)}</select></label></div>
              <div className="issue-table-scroll"><table className="quality-issue-table"><thead><tr><th>SEVERITY</th><th>DIMENSION</th><th>ISSUE TYPE</th><th>COLUMN</th><th>AFFECTED ROWS</th><th>AFFECTED</th><th>RECOMMENDATION</th><th/></tr></thead><tbody>{issues.map(issue=><tr key={issue.id} onClick={()=>setSelectedIssue(issue)}><td><span className={`quality-severity severity-${issue.severity}`}><i/>{issue.severity}</span></td><td>{LABELS[issue.dimension]}</td><td>{issue.issue_type.replace(/_/g,' ')}</td><td>{issue.column_name??'—'}</td><td>{fmt(issue.affected_rows)}</td><td>{issue.affected_percentage.toFixed(1)}%</td><td className="recommendation-cell">{issue.recommendation}</td><td><button aria-label={`View details for ${issue.issue_type}`} onClick={event=>{event.stopPropagation();setSelectedIssue(issue)}}><ArrowRight size={14}/></button></td></tr>)}</tbody></table>{!issues.length&&<div className="quality-table-empty">No issues match these filters.</div>}</div>
              <div className="table-footer"><span>Showing {issues.length?issueOffset+1:0}–{Math.min(issueOffset+issues.length,issueTotal)} of {issueTotal}</span><div><button aria-label="Previous issue page" disabled={!issueOffset} onClick={()=>setIssueOffset(Math.max(0,issueOffset-PAGE_SIZE))}><ChevronLeft size={14}/></button><button aria-label="Next issue page" disabled={issueOffset+PAGE_SIZE>=issueTotal} onClick={()=>setIssueOffset(issueOffset+PAGE_SIZE)}><ChevronRight size={14}/></button></div></div>
            </section>
          </>}
        </div>
        <aside className="panel quality-history-panel"><div className="panel-header"><div><h2>Report history</h2><p>Select an analysis to inspect its results.</p></div></div>{reportPage.items.map(item=><button key={item.id} className={`quality-history-item${activeId===item.id?' active':''}`} onClick={()=>selectReport(item.id)}><span className={`history-grade grade-${item.quality_label.toLowerCase().replace(/ /g,'-')}`}>{item.overall_score===null?'—':item.overall_score.toFixed(1)}</span><span><b>{item.quality_label}</b><small>{new Date(item.created_at).toLocaleString()}</small><small>{item.total_issues} issues · {item.total_rows.toLocaleString()} rows</small></span><ArrowRight size={14}/></button>)}{!reportPage.items.length&&!reportLoading&&<div className="quality-table-empty">No reports on this page.</div>}</aside>
      </div>
    </>}
    {selectedIssue&&<div className="modal-backdrop" role="presentation" onMouseDown={event=>{if(event.target===event.currentTarget)setSelectedIssue(null)}}><section className="modal quality-issue-modal" role="dialog" aria-modal="true" aria-label="Quality issue details"><button className="icon-button quality-close" aria-label="Close issue details" onClick={()=>setSelectedIssue(null)}><X size={16}/></button><span className={`quality-severity severity-${selectedIssue.severity}`}><i/>{selectedIssue.severity}</span><h2>{selectedIssue.issue_type.replace(/_/g,' ')}</h2><p>{selectedIssue.description}</p><div className="issue-modal-meta"><span>{LABELS[selectedIssue.dimension]}</span><span>{selectedIssue.column_name??'Dataset-level'}</span><span>{fmt(selectedIssue.affected_rows)} rows · {selectedIssue.affected_percentage.toFixed(1)}%</span></div><h3>Examples</h3><div className="issue-samples">{selectedIssue.sample_values.length?selectedIssue.sample_values.map((value,index)=><code key={`${index}-${String(value)}`}>{value===null?'null':String(value)}</code>):<span>No sample values</span>}</div><h3>Recommendation</h3><p>{selectedIssue.recommendation}</p></section></div>}
  </div>
}

function Metric({icon,label,value,tone}:{icon:React.ReactNode;label:string;value:string;tone:string}){return <div className={`panel quality-metric metric-${tone}`}><i>{icon}</i><small>{label}</small><b>{value}</b></div>}
function ChartEmpty({children}:{children:string}){return <div className="quality-chart-empty">{children}</div>}
