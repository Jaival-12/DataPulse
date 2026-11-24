import { Activity, ArrowDownToLine, ArrowRight, ArrowUpRight, Database, FileCheck2, Layers3, Rows3, UploadCloud } from 'lucide-react'
import { Link } from 'react-router-dom'
import { useEffect, useState } from 'react'
import { api } from '../services/api'
import type { Dataset } from '../types/dataset'

const fmt = (n: number) => new Intl.NumberFormat().format(n)
const size = (n: number) => n < 1024 ? `${n} B` : n < 1048576 ? `${(n/1024).toFixed(1)} KB` : `${(n/1048576).toFixed(1)} MB`
export function Overview() {
  const [datasets,setDatasets] = useState<Dataset[]>([])
  const [totals,setTotals] = useState({ datasets: 0, records: 0 })
  const [dbState,setDbState] = useState('connecting')
  const [error,setError] = useState('')
  useEffect(() => { Promise.all([api.overview(),api.health()]).then(([overview,health]) => { setDatasets(overview.recent_datasets); setTotals({ datasets: overview.dataset_count, records: overview.record_count }); setDbState(health.database ?? 'connected') }).catch(e => { setDbState('disconnected'); setError(e.message) }) }, [])
  return <div className="page-content">
    <div className="page-heading"><div><div className="eyebrow"><span className="eyebrow-dot"/> DATA OPERATIONS</div><h1>Overview</h1><p className="subtitle">Your data workspace at a glance.</p></div><Link className="primary-button" to="/datasets"><UploadCloud size={16}/> Upload dataset</Link></div>
    {error && <div className="error-banner">Could not reach the API: {error}. Start the backend to load live workspace data.</div>}
    <section className="metric-grid">
      <Metric icon={<Database size={17}/>} label="Total datasets" value={fmt(totals.datasets)} trend="Available in workspace" tone="purple"/>
      <Metric icon={<Rows3 size={17}/>} label="Records ingested" value={fmt(totals.records)} trend="Across uploaded datasets" tone="blue"/>
      <Metric icon={<Layers3 size={17}/>} label="Processed records" value="—" trend="Available in Phase 3" tone="cyan"/>
      <Metric icon={<FileCheck2 size={17}/>} label="Database status" value={dbState === 'connected' ? 'Connected' : dbState === 'connecting' ? 'Checking' : 'Offline'} trend={dbState === 'connected' ? 'API health check passed' : 'Waiting for backend'} tone={dbState === 'connected' ? 'green' : 'amber'}/>
    </section>
    <div className="content-grid">
      <section className="panel recent-panel"><div className="panel-header"><div><h2>Recent datasets</h2><p>Your latest ingested data</p></div><Link className="text-link" to="/datasets">View all <ArrowRight size={14}/></Link></div>
        {datasets.length ? <div className="dataset-table"><div className="table-head"><span>NAME</span><span>ROWS</span><span>SIZE</span><span>ADDED</span></div>{datasets.slice(0,5).map(d => <Link to="/datasets" key={d.id} className="table-row"><span className="file-cell"><i className={`file-icon ${d.format}`}>{d.format === 'csv' ? 'C' : '{ }'}</i><span><b>{d.name}</b><small>{d.column_count} columns · {d.format.toUpperCase()}</small></span></span><span>{fmt(d.row_count)}</span><span>{size(d.size_bytes)}</span><span>{new Date(d.created_at).toLocaleDateString()}</span></Link>)}</div> : <div className="empty-inline"><div className="empty-glyph"><Database size={19}/></div><b>No datasets yet</b><p>Upload a CSV or JSON file to see it appear here.</p><Link to="/datasets" className="text-link">Open datasets <ArrowRight size={14}/></Link></div>}
      </section>
      <section className="panel activity-panel"><div className="panel-header"><div><h2>Pipeline activity</h2><p>Execution health over time</p></div><span className="future-badge">COMING IN PHASE 6</span></div><div className="activity-empty"><div className="pipeline-empty-icon"><Activity size={20}/></div><b>No pipeline runs yet</b><p>Execution history and trends will appear here when pipeline orchestration is added.</p><span className="phase-tag"><ArrowUpRight size={12}/> PHASE 6 · ORCHESTRATION</span></div></section>
    </div>
    <section className="panel lower-panel"><div className="panel-header"><div><h2>Data quality overview</h2><p>Quality checks across your workspace</p></div><span className="future-badge">COMING IN PHASE 4</span></div><div className="quality-placeholder"><div className="quality-wheel"><span>—<small>/ 100</small></span></div><div className="quality-copy"><b>Quality reports will show here</b><p>Completeness, validity, uniqueness and consistency scores will be calculated as datasets are profiled.</p></div><div className="quality-stats"><div><i className="quality-dot purple-dot"/>Completeness <span>—</span></div><div><i className="quality-dot blue-dot"/>Validity <span>—</span></div><div><i className="quality-dot green-dot"/>Uniqueness <span>—</span></div></div></div></section>
    <div className="footnote"><span><ArrowDownToLine size={13}/> Live data from your workspace</span><span className={`connection ${dbState}`}><i/>{dbState === 'connected' ? 'API connected' : dbState === 'connecting' ? 'Connecting' : 'API offline'}</span></div>
  </div>
}
function Metric({icon,label,value,trend,tone}:{icon:React.ReactNode;label:string;value:string;trend:string;tone:string}) { return <div className="metric-card"><div className="metric-top"><span className={`metric-icon ${tone}`}>{icon}</span><span className="metric-context">PHASE 1</span></div><div className="metric-label">{label}</div><div className="metric-value">{value}</div><div className="metric-trend">{trend}</div></div> }
