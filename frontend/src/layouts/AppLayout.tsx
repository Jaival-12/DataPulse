import { Activity, ChartNoAxesCombined, CircleHelp, Database, Gauge, GitBranch, PackageCheck, Settings2, ShieldCheck } from 'lucide-react'
import { NavLink, Outlet, useLocation } from 'react-router-dom'

const nav = [
  { to: '/', label: 'Overview', icon: Gauge },
  { to: '/datasets', label: 'Datasets', icon: Database },
  { to: '/analytics', label: 'Analytics', icon: ChartNoAxesCombined },
  { to: '/pipelines', label: 'Pipelines', icon: GitBranch },
  { to: '/processed-datasets', label: 'Processed data', icon: PackageCheck },
  { to: '/quality', label: 'Data quality', icon: ShieldCheck },
]

export function AppLayout() {
  const location = useLocation()
  const current = location.pathname.startsWith('/datasets') ? 'Datasets'
      : location.pathname.startsWith('/analytics') ? 'Analytics'
      : location.pathname.startsWith('/pipelines') ? 'Pipelines'
      : location.pathname.startsWith('/processed-datasets') ? 'Processed datasets'
        : location.pathname.startsWith('/quality') ? 'Data quality' : 'Overview'
  return <div className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="/"><span className="brand-mark"><Activity size={18}/></span><span>data<span className="brand-accent">pulse</span></span></a>
      <div className="workspace"><div className="workspace-icon">D</div><div><b>Data workspace</b><small>Local environment</small></div><span className="chevron">⌄</span></div>
      <div className="nav-label">WORKSPACE</div>
      <nav>{nav.map(({to,label,icon:Icon}) => <NavLink key={to} to={to} end={to === '/'} className={({isActive}) => `nav-link${isActive ? ' active' : ''}`}><Icon size={17}/><span className="nav-link-label">{label}</span>{label === 'Datasets' && <span className="nav-count">•</span>}</NavLink>)}</nav>
      <div className="nav-label section-gap">SYSTEM</div>
      <div className="nav-link muted-link"><Settings2 size={17}/>Settings<span className="soon">Soon</span></div>
      <div className="sidebar-bottom"><div className="help-card"><div className="help-icon"><CircleHelp size={16}/></div><b>Getting started</b><p>Upload your first dataset to begin exploring.</p><NavLink to="/datasets">Browse datasets <span>↗</span></NavLink></div><div className="user-row"><div className="avatar">DP</div><div><b>DataPulse</b><small>Personal workspace</small></div><span className="more">···</span></div></div>
    </aside>
    <main className="main-area"><header className="topbar"><div className="breadcrumbs"><span>Workspace</span><span className="slash">/</span><b>{current}</b></div><div className="top-actions"><div className="system-status"><i/> System operational</div><button className="icon-button" aria-label="Activity"><Activity size={17}/></button><div className="avatar small-avatar">DP</div></div></header><Outlet/></main>
  </div>
}
