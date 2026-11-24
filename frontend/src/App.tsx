import { lazy, Suspense } from 'react'
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AppLayout } from './layouts/AppLayout'
import { Overview } from './pages/Overview'
import { Datasets } from './pages/Datasets'
import './styles.css'
import './activity.css'

const DatasetDetail = lazy(() => import('./pages/DatasetDetail').then(module => ({ default: module.DatasetDetail })))
const Pipelines = lazy(() => import('./pages/Pipelines').then(module => ({ default: module.Pipelines })))
const PipelineDetail = lazy(() => import('./pages/PipelineDetail').then(module => ({ default: module.PipelineDetail })))
const ProcessedDatasets = lazy(() => import('./pages/ProcessedDatasets').then(module => ({ default: module.ProcessedDatasets })))
const ProcessedDatasetDetail = lazy(() => import('./pages/ProcessedDatasetDetail').then(module => ({ default: module.ProcessedDatasetDetail })))
const Quality = lazy(() => import('./pages/Quality').then(module => ({ default: module.Quality })))
const Analytics = lazy(() => import('./pages/Analytics').then(module => ({ default: module.Analytics })))

export default function App() { return <BrowserRouter><Routes><Route element={<AppLayout/>}><Route path="/" element={<Overview/>}/><Route path="/datasets" element={<Datasets/>}/><Route path="/datasets/:datasetId" element={<Suspense fallback={<div className="page-content detail-loading">Loading dataset tools…</div>}><DatasetDetail/></Suspense>}/><Route path="/analytics" element={<Suspense fallback={<div className="page-content detail-loading">Loading analytics…</div>}><Analytics/></Suspense>}/><Route path="/quality" element={<Suspense fallback={<div className="page-content detail-loading">Loading quality reports…</div>}><Quality/></Suspense>}/><Route path="/pipelines" element={<Suspense fallback={<div className="page-content detail-loading">Loading pipelines…</div>}><Pipelines/></Suspense>}/><Route path="/pipelines/new" element={<Suspense fallback={<div className="page-content detail-loading">Loading builder…</div>}><PipelineDetail isNewPipeline/></Suspense>}/><Route path="/pipelines/:pipelineId" element={<Suspense fallback={<div className="page-content detail-loading">Loading pipeline…</div>}><PipelineDetail/></Suspense>}/><Route path="/processed-datasets" element={<Suspense fallback={<div className="page-content detail-loading">Loading processed datasets…</div>}><ProcessedDatasets/></Suspense>}/><Route path="/processed-datasets/:processedDatasetId" element={<Suspense fallback={<div className="page-content detail-loading">Loading processed data…</div>}><ProcessedDatasetDetail/></Suspense>}/><Route path="*" element={<Overview/>}/></Route></Routes></BrowserRouter> }
