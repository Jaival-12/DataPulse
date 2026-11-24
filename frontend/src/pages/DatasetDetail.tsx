import { ArrowLeft, BarChart3, CalendarDays, CheckCircle2, CircleAlert, Database, LoaderCircle, RefreshCw, Search, Sparkles, Table2, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Link, useParams } from 'react-router-dom'
import { api, ApiError } from '../services/api'
import type { Dataset, DatasetPreview } from '../types/dataset'
import type { ColumnProfile, DatasetProfile } from '../types/profile'
import { QualityHistory } from '../components/QualityHistory'
import './dataset-detail.css'

type Tab = 'overview' | 'preview' | 'profile' | 'quality'
const fmt = (value: number) => new Intl.NumberFormat().format(value)
const pct = (value: number) => `${value.toFixed(2)}%`
const size = (bytes: number) => bytes < 1024 ? `${bytes} B` : bytes < 1048576 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1048576).toFixed(1)} MB`

export function DatasetDetail() {
  const { datasetId = '' } = useParams()
  const [dataset, setDataset] = useState<Dataset | null>(null)
  const [preview, setPreview] = useState<DatasetPreview | null>(null)
  const [profile, setProfile] = useState<DatasetProfile | null>(null)
  const [tab, setTab] = useState<Tab>('overview')
  const [selectedColumn, setSelectedColumn] = useState('')
  const [columnSearch, setColumnSearch] = useState('')
  const [loading, setLoading] = useState(true)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [profileLoading, setProfileLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const [profileError, setProfileError] = useState('')
  const [notice, setNotice] = useState('')

  useEffect(() => {
    let cancelled = false
    setLoading(true); setDataset(null); setPreview(null); setProfile(null); setTab('overview'); setError(''); setProfileError('')
    api.dataset(datasetId).then(data => { if (!cancelled) setDataset(data) }).catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : 'Dataset could not be loaded.') }).finally(() => { if (!cancelled) setLoading(false) })
    setProfileLoading(true)
    api.getProfile(datasetId).then(data => { if (!cancelled) { setProfile(data); setSelectedColumn(data.profile_data.columns[0]?.name ?? '') } }).catch(e => {
      if (cancelled) return
      if (e instanceof ApiError && e.status === 404 && e.message === 'Profile has not been generated yet.') setProfile(null)
      else setProfileError(e instanceof Error ? e.message : 'Saved profile could not be loaded.')
    }).finally(() => { if (!cancelled) setProfileLoading(false) })
    return () => { cancelled = true }
  }, [datasetId])

  useEffect(() => {
    if (tab !== 'preview' || preview || !dataset) return
    let cancelled = false
    setPreviewLoading(true)
    api.preview(datasetId).then(data => { if (!cancelled) setPreview(data) }).catch(e => { if (!cancelled) setError(e instanceof Error ? e.message : 'Data preview could not be loaded.') }).finally(() => { if (!cancelled) setPreviewLoading(false) })
    return () => { cancelled = true }
  }, [tab, preview, dataset, datasetId])

  async function generateProfile() {
    setSaving(true); setProfileError(''); setNotice('')
    try {
      const saved = profile ? await api.refreshProfile(datasetId) : await api.generateProfile(datasetId)
      setProfile(saved); setSelectedColumn(saved.profile_data.columns[0]?.name ?? ''); setNotice(profile ? 'Profile refreshed from the original dataset.' : 'Profile generated and saved.')
    } catch (e) { setProfileError(e instanceof Error ? e.message : 'Profile could not be generated.') }
    finally { setSaving(false) }
  }

  if (loading) return <div className="page-content"><div className="detail-loading"><LoaderCircle className="spin" size={20}/> Loading dataset…</div></div>
  if (!dataset) return <div className="page-content"><Link to="/datasets" className="detail-back"><ArrowLeft size={14}/> All datasets</Link><div className="error-banner detail-error">{error || 'Dataset not found.'}</div></div>

  return <div className="page-content detail-page">
    <Link to="/datasets" className="detail-back"><ArrowLeft size={14}/> All datasets</Link>
    <div className="page-heading detail-heading"><div><div className="eyebrow"><span className="eyebrow-dot"/> DATASET</div><h1>{dataset.name}</h1><p className="subtitle">{dataset.format.toUpperCase()} · {dataset.row_count.toLocaleString()} records · {dataset.column_count} columns</p></div><div className="detail-actions"><span className={`format-label ${dataset.format}`}>{dataset.format.toUpperCase()}</span><span className="detail-size">{size(dataset.size_bytes)}</span></div></div>
    {(error || (notice && tab !== 'profile')) && <div className={error ? 'error-banner' : 'success-banner'}>{error || notice}<button aria-label="Dismiss" onClick={() => { setError(''); setNotice('') }}><X size={14}/></button></div>}
    <div className="detail-tabs" role="tablist" aria-label="Dataset sections">
      <TabButton active={tab === 'overview'} onClick={() => setTab('overview')} icon={<Database size={15}/>} label="Overview"/>
      <TabButton active={tab === 'preview'} onClick={() => setTab('preview')} icon={<Table2 size={15}/>} label="Data preview"/>
      <TabButton active={tab === 'profile'} onClick={() => setTab('profile')} icon={<BarChart3 size={15}/>} label="Data profile"/>
      <TabButton active={tab === 'quality'} onClick={() => setTab('quality')} icon={<CircleAlert size={15}/>} label="Data quality"/>
    </div>
    {tab === 'overview' && <OverviewTab dataset={dataset} profile={profile} profileLoading={profileLoading} onOpenProfile={() => setTab('profile')}/>}
    {tab === 'preview' && <PreviewTab dataset={dataset} preview={preview} loading={previewLoading} error={error}/>}
    {tab === 'profile' && <ProfileTab profile={profile} loading={profileLoading} saving={saving} error={profileError} notice={notice} search={columnSearch} setSearch={setColumnSearch} selectedName={selectedColumn} setSelectedName={setSelectedColumn} onGenerate={() => void generateProfile()}/>}
    {tab === 'quality' && <QualityHistory targetType="dataset" targetId={dataset.id} columns={dataset.columns.map(column=>column.name)}/>}
  </div>
}

function TabButton({active,onClick,icon,label}:{active:boolean;onClick:()=>void;icon:React.ReactNode;label:string}) {
  return <button role="tab" aria-selected={active} className={`detail-tab${active?' active':''}`} onClick={onClick}>{icon}{label}</button>
}

function OverviewTab({dataset,profile,profileLoading,onOpenProfile}:{dataset:Dataset;profile:DatasetProfile|null;profileLoading:boolean;onOpenProfile:()=>void}) {
  const p = profile?.profile_data
  const inferredTypes = new Map(p?.columns.map(column => [column.name, column.detected_type]) ?? [])
  return <div className="detail-section">
    <div className="detail-summary-grid">
      <SummaryCard label="Total records" value={fmt(dataset.row_count)} icon={<Table2 size={16}/>}/>
      <SummaryCard label="Columns" value={fmt(dataset.column_count)} icon={<Database size={16}/>}/>
      <SummaryCard label="Missing cells" value={profileLoading ? 'Loading…' : p ? fmt(p.total_missing_cells) : 'Not profiled'} icon={<CircleAlert size={16}/>}/>
      <SummaryCard label="Completeness" value={profileLoading ? 'Loading…' : p ? pct(p.overall_completeness_percentage) : 'Not profiled'} icon={<CheckCircle2 size={16}/>}/>
    </div>
    <section className="panel detail-panel"><div className="panel-header"><div><h2>Dataset schema</h2><p>Column names and ingested types, refined by a saved profile</p></div><button className="secondary-button" onClick={onOpenProfile}><BarChart3 size={14}/> Open profile</button></div>
      <div className="schema-detail-grid">{dataset.columns.map(column=><div className="schema-detail-item" key={column.position}><span className="schema-index">{String(column.position+1).padStart(2,'0')}</span><span className="schema-name">{column.name}</span><span className="type-pill">{inferredTypes.get(column.name) ?? column.data_type}</span></div>)}{!dataset.columns.length&&<div className="detail-empty">No columns were detected.</div>}</div>
    </section>
    <section className="panel detail-panel"><div className="panel-header"><div><h2>Source details</h2><p>Original upload metadata</p></div></div><div className="source-details"><div><small>FILE FORMAT</small><b>{dataset.format.toUpperCase()}</b></div><div><small>FILE SIZE</small><b>{size(dataset.size_bytes)}</b></div><div><small>UPLOADED</small><b><CalendarDays size={13}/>{new Date(dataset.created_at).toLocaleString()}</b></div><div><small>PROFILE REPORT</small><b>{profile ? `Last generated ${new Date(profile.generated_at).toLocaleString()}` : 'Not generated yet'}</b></div></div></section>
  </div>
}

function PreviewTab({dataset,preview,loading,error}:{dataset:Dataset;preview:DatasetPreview|null;loading:boolean;error:string}) {
  if (loading) return <div className="detail-loading"><LoaderCircle className="spin" size={18}/> Loading preview…</div>
  if (error) return <div className="error-banner">{error}</div>
  if (!preview) return <div className="panel detail-empty">Preview unavailable.</div>
  return <section className="panel detail-panel profile-table-panel"><div className="panel-header"><div><h2>Data preview</h2><p>Showing {preview.rows.length} of {dataset.row_count.toLocaleString()} records</p></div><span className="detail-count">{preview.dataset.columns.length} columns</span></div><div className="preview-scroll detail-preview-scroll"><table className="preview-table"><thead><tr>{preview.dataset.columns.map(column=><th key={column.position}>{column.name}</th>)}</tr></thead><tbody>{preview.rows.map((row,index)=><tr key={index}>{preview.dataset.columns.map(column=><td key={column.position}>{row[column.name]===null||row[column.name]===undefined?<em>null</em>:String(row[column.name])}</td>)}</tr>)}</tbody></table></div></section>
}

function ProfileTab({profile,loading,saving,error,notice,search,setSearch,selectedName,setSelectedName,onGenerate}:{profile:DatasetProfile|null;loading:boolean;saving:boolean;error:string;notice:string;search:string;setSearch:(value:string)=>void;selectedName:string;setSelectedName:(value:string)=>void;onGenerate:()=>void}) {
  const data = profile?.profile_data
  const filtered = useMemo(() => data?.columns.filter(column => column.name.toLowerCase().includes(search.toLowerCase())) ?? [], [data,search])
  const selected = filtered.find(column => column.name === selectedName) ?? filtered[0]
  if (loading) return <div className="detail-loading"><LoaderCircle className="spin" size={18}/> Checking for a saved profile…</div>
  return <div className="detail-section profile-section">
    <div className="profile-toolbar"><div><h2>Data profile</h2><p>{profile ? `Generated ${new Date(profile.generated_at).toLocaleString()}` : 'Profile the original file to inspect completeness and distributions.'}</p></div><button className="primary-button" onClick={onGenerate} disabled={saving}>{saving?<LoaderCircle className="spin" size={15}/>:profile?<RefreshCw size={15}/>:<Sparkles size={15}/>} {saving?'Working…':profile?'Refresh profile':'Generate profile'}</button></div>
    {error&&<div className="error-banner">{error}</div>}{notice&&<div className="success-banner"><CheckCircle2 size={14}/>{notice}</div>}
    {!data ? <div className="panel profile-empty"><div className="profile-empty-icon"><BarChart3 size={22}/></div><h3>No profile report yet</h3><p>Generate a profile from the preserved source file. It will report missing values, duplicates, type distributions, and column statistics.</p><small>Use the Generate profile button above. Reports can be refreshed later; no quality score is calculated in this phase.</small></div> : <>
      <div className="detail-summary-grid profile-metrics">
        <SummaryCard label="Total rows" value={fmt(data.total_rows)} icon={<Table2 size={16}/>}/>
        <SummaryCard label="Total columns" value={fmt(data.total_columns)} icon={<Database size={16}/>}/>
        <SummaryCard label="Missing cells" value={fmt(data.total_missing_cells)} icon={<CircleAlert size={16}/>} tone={data.total_missing_cells?'warning':'success'}/>
        <SummaryCard label="Duplicate rows" value={fmt(data.duplicate_rows)} icon={<CircleAlert size={16}/>} tone={data.duplicate_rows?'warning':'success'}/>
        <SummaryCard label="Completeness" value={pct(data.overall_completeness_percentage)} icon={<CheckCircle2 size={16}/>}/>
      </div>
      <div className="issue-strip"><span className="issue-heading">Observed indicators</span><Severity count={data.total_missing_cells} label={`${fmt(data.total_missing_cells)} missing cells`} rate={data.missing_cell_percentage}/><Severity count={data.duplicate_rows} label={`${fmt(data.duplicate_rows)} duplicate rows`} rate={data.duplicate_row_percentage}/><span className="no-score-note">Phase 4 quality scoring is not enabled.</span></div>
      <section className="panel profile-table-panel"><div className="panel-header"><div><h2>Column profiles</h2><p>Choose a column to inspect its values and statistics</p></div><span className="detail-count">{data.columns.length} columns</span></div>
        <div className="column-search"><Search size={15}/><input value={search} onChange={event=>setSearch(event.target.value)} placeholder="Search columns…"/><kbd>{filtered.length} shown</kbd></div>
        <div className="profile-columns-layout"><div className="profile-column-list"><div className="profile-column-head"><span>COLUMN</span><span>TYPE</span><span>NON-NULL</span><span>MISSING</span><span>DISTINCT</span></div>{filtered.map(column=><button key={column.name} className={`profile-column-row${selected?.name===column.name?' selected':''}`} onClick={()=>setSelectedName(column.name)}><span className="profile-column-name">{column.name}</span><span><TypeBadge type={column.detected_type}/></span><span>{fmt(column.non_null_count)}</span><span>{fmt(column.missing_count)} <small>{pct(column.missing_percentage)}</small></span><span>{fmt(column.distinct_count)}</span></button>)}{!filtered.length&&<div className="detail-empty">No columns match that search.</div>}</div>
          {selected&&<ColumnDetails column={selected}/>}
        </div>
      </section>
    </>}
  </div>
}

function SummaryCard({label,value,icon,tone='normal'}:{label:string;value:string;icon:React.ReactNode;tone?:'normal'|'warning'|'success'}) { return <div className="detail-summary-card"><div className={`detail-summary-icon ${tone}`}>{icon}</div><span>{label}</span><b>{value}</b></div> }
function Severity({count,label,rate}:{count:number;label:string;rate:number}) { const level=count===0?'clear':rate>=20?'high':'moderate'; return <span className={`severity ${level}`}><i/>{count===0?'Clear':level==='high'?'High':'Observed'} · {label}</span> }
function TypeBadge({type}:{type:ColumnProfile['detected_type']}) { return <span className={`type-pill type-${type}`}>{type}</span> }

function ColumnDetails({column}:{column:ColumnProfile}) {
  const numeric = column.numeric_statistics
  const categorical = column.categorical_statistics
  const chartData = categorical?.top_values.map(item=>({...item,displayValue:item.value===null?'null':String(item.value)})) ?? []
  const numericChart = numeric?.histogram?.map(item=>({...item,displayValue:`${item.bin_start.toLocaleString()}–${item.bin_end.toLocaleString()}`})) ?? []
  const dates = column.date_statistics
  const identifier = column.identifier_statistics
  const isNumeric = ['integer','float','number','numeric_mixed'].includes(column.detected_type)
  return <aside className="column-details"><div className="column-details-heading"><div><span className="eyebrow">SELECTED COLUMN</span><h3>{column.name}</h3></div><TypeBadge type={column.detected_type}/></div>
    <div className="column-detail-summary"><div><small>NON-NULL</small><b>{fmt(column.non_null_count)}</b></div><div><small>MISSING</small><b>{fmt(column.missing_count)} <em>({pct(column.missing_percentage)})</em></b></div><div><small>DISTINCT</small><b>{fmt(column.distinct_count)}</b></div></div>
    {numeric&&<><h4>Numeric statistics</h4><div className="numeric-stat-grid">{[['Count',numeric.count],['Mean',numeric.mean],['Median',numeric.median],['Minimum',numeric.minimum],['Maximum',numeric.maximum],['Std. deviation',numeric.standard_deviation],['25th percentile',numeric.q25],['50th percentile',numeric.q50],['75th percentile',numeric.q75]].map(([label,value])=><div key={String(label)}><small>{label}</small><b>{value===null?'—':typeof value==='number'?new Intl.NumberFormat(undefined,{maximumFractionDigits:4}).format(value):value}</b></div>)}</div></>}
    {numeric&&(column.detected_type==='numeric_mixed'||(numeric.invalid_numeric_values??0)>0)&&<div className="profile-type-stats"><div><small>VALID NUMERIC VALUES</small><b>{fmt(numeric.valid_numeric_values??numeric.count)}</b></div><div><small>INVALID NUMERIC VALUES</small><b>{fmt(numeric.invalid_numeric_values??0)}</b></div><div><small>NUMERIC CONVERSION</small><b>{pct(numeric.numeric_conversion_percentage??0)}</b></div></div>}
    {isNumeric&&numericChart.length>0&&<><h4>Numeric distribution</h4><div className="category-chart"><ResponsiveContainer width="100%" height={Math.max(170,numericChart.length*28)}><BarChart data={numericChart} layout="vertical" margin={{top:4,right:12,bottom:2,left:2}}><CartesianGrid stroke="#2b2b36" horizontal={false}/><XAxis type="number" tick={{fill:'#777786',fontSize:9}} axisLine={false} tickLine={false}/><YAxis type="category" dataKey="displayValue" width={120} tick={{fill:'#b8b8c5',fontSize:9}} axisLine={false} tickLine={false}/><Tooltip contentStyle={{background:'#1d1d27',border:'1px solid #373743',borderRadius:6,color:'#e6e6ee',fontSize:10}} formatter={(value:number)=>[`${value} rows`,'Frequency']}/><Bar dataKey="count" fill="#9270f2" radius={[0,4,4,0]} barSize={12}/></BarChart></ResponsiveContainer></div><div className="numeric-bin-list">{numericChart.map((bin,index)=><div key={`${bin.displayValue}-${index}`}><span>{bin.displayValue}</span><b>{fmt(bin.count)}</b></div>)}</div></>}
    {dates&&<><h4>Date statistics</h4><div className="profile-type-stats"><div><small>VALID DATES</small><b>{fmt(dates.valid_date_count)}</b></div><div><small>INVALID DATES</small><b>{fmt(dates.invalid_date_count)}</b></div><div><small>MISSING DATES</small><b>{fmt(dates.missing_date_count)}</b></div><div><small>EARLIEST</small><b>{dates.earliest_date??'—'}</b></div><div><small>LATEST</small><b>{dates.latest_date??'—'}</b></div></div></>}
    {identifier&&<><h4>Identifier statistics</h4><div className="profile-type-stats"><div><small>UNIQUENESS</small><b>{pct(column.unique_percentage)}</b></div><div><small>DUPLICATE IDENTIFIERS</small><b>{fmt(identifier.duplicate_identifier_count)}</b></div></div><div className="identifier-samples"><small>SAMPLE IDENTIFIERS</small><div>{identifier.sample_values.map((value,index)=><code key={`${String(value)}-${index}`}>{String(value)}</code>)}</div></div></>}
    {categorical&&<><div className="category-heading"><h4>{column.detected_type==='boolean'?'Value frequency':'Top values'}</h4><span>{fmt(categorical.distinct_count)} distinct values · showing up to 10</span></div>{chartData.length?<><div className="category-chart"><ResponsiveContainer width="100%" height={Math.max(170,chartData.length*28)}><BarChart data={chartData} layout="vertical" margin={{top:4,right:12,bottom:2,left:2}}><CartesianGrid stroke="#2b2b36" horizontal={false}/><XAxis type="number" tick={{fill:'#777786',fontSize:9}} axisLine={false} tickLine={false}/><YAxis type="category" dataKey="displayValue" width={92} tick={{fill:'#b8b8c5',fontSize:9}} axisLine={false} tickLine={false}/><Tooltip contentStyle={{background:'#1d1d27',border:'1px solid #373743',borderRadius:6,color:'#e6e6ee',fontSize:10}} formatter={(value:number)=>[`${value} rows`,'Frequency']}/><Bar dataKey="count" fill="#9270f2" radius={[0,4,4,0]} barSize={12}/></BarChart></ResponsiveContainer></div><div className="top-values-list"><div><span>VALUE</span><span>COUNT</span><span>SHARE</span></div>{categorical.top_values.map((item,index)=><div key={`${String(item.value)}-${index}`}><span>{item.value===null?<em>null</em>:String(item.value)}</span><b>{fmt(item.count)}</b><span>{pct(item.percentage)}</span></div>)}</div></>:<div className="detail-empty">No non-missing values to chart.</div>}</>}
    {!numeric&&!categorical&&!dates&&!identifier&&<div className="detail-empty column-type-note">{column.detected_type==='empty'?'All records are missing for this column.':column.detected_type==='string'?'Text values are available without a reliable frequency profile.':'No type-specific statistics are available for this column.'}</div>}
  </aside>
}
