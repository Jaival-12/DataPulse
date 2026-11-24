import { ArrowDownToLine, ArrowLeft, CalendarClock, Database, FileSpreadsheet, LoaderCircle, Rows3, X } from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api } from '../services/api'
import { QualityHistory } from '../components/QualityHistory'
import type { Dataset } from '../types/dataset'
import type { Pipeline, PipelineExecution, ProcessedDataset, ProcessedDatasetPreview } from '../types/pipeline'
import './processed-dataset.css'

const size=(bytes:number)=>bytes<1024?`${bytes} B`:bytes<1048576?`${(bytes/1024).toFixed(1)} KB`:`${(bytes/1048576).toFixed(1)} MB`

export function ProcessedDatasetDetail() {
  const {processedDatasetId=''}=useParams()
  const [dataset,setDataset]=useState<ProcessedDataset|null>(null)
  const [preview,setPreview]=useState<ProcessedDatasetPreview|null>(null)
  const [source,setSource]=useState<Dataset|null>(null)
  const [execution,setExecution]=useState<PipelineExecution|null>(null)
  const [pipeline,setPipeline]=useState<Pipeline|null>(null)
  const [loading,setLoading]=useState(true)
  const [downloading,setDownloading]=useState(false)
  const [error,setError]=useState('')
  const [notice,setNotice]=useState('')

  useEffect(()=>{
    let cancelled=false
    setLoading(true);setError('');setDataset(null);setPreview(null)
    const load=async()=>{
      try{
        const [detail,records]=await Promise.all([api.processedDataset(processedDatasetId),api.previewProcessedDataset(processedDatasetId,100)])
        if(cancelled)return
        setDataset(detail);setPreview(records)
        const [sourceData,run]=await Promise.all([api.dataset(detail.source_dataset_id),api.execution(detail.execution_id)])
        if(cancelled)return
        setSource(sourceData);setExecution(run)
        const pipelineData=await api.pipeline(run.pipeline_id)
        if(!cancelled)setPipeline(pipelineData)
      }catch(e){if(!cancelled)setError(e instanceof Error?e.message:'Processed dataset could not be loaded.')}
      finally{if(!cancelled)setLoading(false)}
    }
    void load()
    return()=>{cancelled=true}
  },[processedDatasetId])

  async function download(){
    setDownloading(true);setError('');setNotice('')
    try{
      const file=await api.downloadProcessedDataset(processedDatasetId)
      const url=URL.createObjectURL(file.blob)
      const anchor=document.createElement('a');anchor.href=url;anchor.download=file.filename;document.body.appendChild(anchor);anchor.click();anchor.remove();URL.revokeObjectURL(url)
      setNotice(`${file.filename} downloaded.`)
    }catch(e){setError(e instanceof Error?e.message:'Processed file could not be downloaded.')}
    finally{setDownloading(false)}
  }

  if(loading)return <div className="page-content"><div className="page-loading"><LoaderCircle size={18} className="spin"/> Loading processed dataset…</div></div>
  if(!dataset)return <div className="page-content"><Link to="/processed-datasets" className="detail-back"><ArrowLeft size={14}/> Processed datasets</Link><div className="error-banner">{error||'Processed dataset not found.'}</div></div>
  const columns=preview?.rows.length?Object.keys(preview.rows[0]):[]
  return <div className="page-content processed-page processed-detail-page">
    <Link to="/processed-datasets" className="detail-back"><ArrowLeft size={14}/> Processed datasets</Link>
    <div className="page-heading processed-detail-heading"><div><div className="eyebrow"><span className="eyebrow-dot"/> PROCESSED DATASET</div><h1>{dataset.filename}</h1><p className="subtitle">Created {new Date(dataset.created_at).toLocaleString()}</p></div><button className="primary-button" onClick={()=>void download()} disabled={downloading}>{downloading?<LoaderCircle className="spin" size={15}/>:<ArrowDownToLine size={15}/>} {downloading?'Preparing download…':'Download file'}</button></div>
    {(error||notice)&&<div className={error?'error-banner':'success-banner'} role={error?'alert':'status'}>{error||notice}<button aria-label="Dismiss" onClick={()=>{setError('');setNotice('')}}><X size={14}/></button></div>}
    <div className="processed-summary-grid"><Summary label="Format" value={dataset.file_type.toUpperCase()} icon={<FileSpreadsheet size={16}/>}/><Summary label="Records" value={dataset.row_count.toLocaleString()} icon={<Rows3 size={16}/>}/><Summary label="Columns" value={String(dataset.column_count)} icon={<Database size={16}/>}/><Summary label="File size" value={size(dataset.file_size)} icon={<CalendarClock size={16}/>}/></div>
    <section className="panel processed-origin-panel"><div className="panel-header"><div><h2>Lineage</h2><p>Processed output and the source pipeline that produced it.</p></div></div><div className="processed-lineage"><div><small>SOURCE DATASET</small>{source?<Link to={`/datasets/${encodeURIComponent(source.id)}`}>{source.name}</Link>:<span>{dataset.source_dataset_id}</span>}</div><span className="lineage-arrow">←</span><div><small>PIPELINE</small>{pipeline?<Link to={`/pipelines/${encodeURIComponent(pipeline.id)}`}>{pipeline.name}</Link>:<span>{execution?.pipeline_id??'Loading pipeline…'}</span>}</div><div><small>EXECUTION</small>{execution?<Link to={`/pipelines/${encodeURIComponent(execution.pipeline_id)}`} state={{tab:'runs'}}>{execution.id.slice(0,12)} · {execution.status}</Link>:<span>{dataset.execution_id}</span>}</div></div></section>
    <section className="panel processed-preview-panel"><div className="panel-header"><div><h2>Data preview</h2><p>Showing {preview?.rows.length??0} of {dataset.row_count.toLocaleString()} records</p></div><span className="detail-count">Up to 100 rows</span></div>
      {preview?.rows.length?<div className="processed-preview-scroll"><table className="preview-table"><thead><tr>{columns.map(column=><th key={column}>{column}</th>)}</tr></thead><tbody>{preview.rows.map((row,index)=><tr key={index}>{columns.map(column=><td key={column}>{row[column]===null||row[column]===undefined?<em>null</em>:String(row[column])}</td>)}</tr>)}</tbody></table></div>:<div className="detail-empty">This processed dataset contains no rows to preview.</div>}
    </section>
    <QualityHistory targetType="processed" targetId={dataset.id} columns={columns} sourceDatasetId={dataset.source_dataset_id}/>
  </div>
}

function Summary({label,value,icon}:{label:string;value:string;icon:React.ReactNode}){return <div className="processed-summary-card"><i>{icon}</i><small>{label}</small><b>{value}</b></div>}
