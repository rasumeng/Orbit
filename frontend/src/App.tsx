import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { CalendarDays, CircleCheck, Layers3, Plus, RefreshCw } from 'lucide-react'

type Category = 'school' | 'work' | 'leadership' | 'projects' | 'personal'
type Priority = 'low' | 'medium' | 'high'
type Item = { id: string; title: string; category?: Category; priority?: Priority; dueAt?: string; status?: 'pending' | 'completed'; source?: string }
const API = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '')
const categories: Category[] = ['school', 'work', 'leadership', 'projects', 'personal']

export default function App() {
  const [items, setItems] = useState<Item[]>([])
  const [title, setTitle] = useState('')
  const [category, setCategory] = useState<Category>('school')
  const [priority, setPriority] = useState<Priority>('medium')
  const [dueAt, setDueAt] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [filter, setFilter] = useState('all')
  async function load() {
    if (!API) { setError('Set VITE_API_URL in frontend/.env first.'); return }
    try {
      setError('')
      const r = await fetch(`${API}/items`)
      if (!r.ok) throw Error(`API returned ${r.status}`)
      const data = await r.json()
      setItems(data.items ?? [])
    } catch (e) { setError(String(e)) }
  }
  useEffect(() => { void load() }, [])
  async function create(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    try {
      const payload = { title, category, priority, ...(dueAt ? { dueAt: new Date(dueAt).toISOString() } : {}) }
      const r = await fetch(`${API}/items`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
      if (!r.ok) throw Error((await r.json()).error || `API returned ${r.status}`)
      setTitle('')
      await load()
    } catch (e) { setError(String(e)) } finally { setBusy(false) }
  }
  async function toggle(item: Item) {
    setBusy(true)
    try {
      const r = await fetch(`${API}/items/${encodeURIComponent(item.id)}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: (item.status ?? 'pending') === 'completed' ? 'pending' : 'completed' }) })
      if (!r.ok) throw Error(`API returned ${r.status}`)
      await load()
    } catch (e) { setError(String(e)) } finally { setBusy(false) }
  }
  const upcoming = useMemo(() => items.filter(i => (i.status ?? 'pending') === 'pending'), [items])
  const visible = useMemo(() => items.filter(i => filter === 'all' || i.category === filter).sort((a, b) => (a.dueAt ?? '').localeCompare(b.dueAt ?? '')), [items, filter])
  const next7 = upcoming.filter(i => i.dueAt && new Date(i.dueAt).getTime() <= Date.now() + 7 * 86400000 && new Date(i.dueAt).getTime() >= Date.now()).length
  return <div className="shell">
    <aside className="sidebar"><h2><Layers3 size={25}/> Orbit</h2><p className="tagline">Everything on your plate, in one place.</p><div className="nav active"><CalendarDays size={18}/> Overview</div><small>Midpoint prototype • demo data only</small></aside>
    <main className="content"><header><div><p className="eyebrow">YOUR COMMAND CENTER</p><h1>Stay on top of everything.</h1><p className="muted">School, work, leadership, projects and life — together.</p></div><button className="secondary" onClick={load}><RefreshCw size={16}/> Refresh</button></header>
      {error && <div className="error">{error}</div>}
      <section className="stats"><div className="tile"><span>Open responsibilities</span><strong>{upcoming.length}</strong></div><div className="tile"><span>Due in next 7 days</span><strong>{next7}</strong></div><div className="tile"><span>Completed</span><strong>{items.filter(i => i.status === 'completed').length}</strong></div></section>
      <section className="columns"><div className="panel"><div className="panel-heading"><h2>Your responsibilities</h2><select aria-label="Filter category" value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">All categories</option>{categories.map(c=><option key={c} value={c}>{c}</option>)}</select></div>
        {visible.length === 0 ? <p className="empty">No responsibilities yet. Create one to get started.</p> : <div className="entries">{visible.map(item=><div className="entry" key={item.id}><button disabled={busy} className={'check '+((item.status ?? 'pending') === 'completed' ? 'checked' : '')} aria-label={`Toggle ${item.title}`} onClick={()=>toggle(item)}><CircleCheck size={20}/></button><div className="entry-main"><strong className={(item.status ?? 'pending') === 'completed' ? 'done' : ''}>{item.title}</strong><div className="meta"><span className={'category '+(item.category ?? 'personal')}>{item.category ?? 'uncategorized'}</span><span>{item.dueAt ? new Date(item.dueAt).toLocaleString([], {dateStyle:'medium',timeStyle:'short'}) : 'No due date'}</span><span>Priority: {item.priority ?? 'medium'}</span></div></div></div>)}</div>}
      </div><div className="panel"><h2>Add a responsibility</h2><p className="muted">Capture it here so you don't have to keep it in your head.</p><form onSubmit={create}><label>What needs to get done?<input required maxLength={120} value={title} onChange={e=>setTitle(e.target.value)} placeholder="Finish cloud architecture diagram"/></label><label>Category<select value={category} onChange={e=>setCategory(e.target.value as Category)}>{categories.map(c=><option key={c}>{c}</option>)}</select></label><label>Due date & time<input type="datetime-local" value={dueAt} onChange={e=>setDueAt(e.target.value)}/></label><label>Priority<select value={priority} onChange={e=>setPriority(e.target.value as Priority)}><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></select></label><button disabled={busy || !API} type="submit"><Plus size={17}/> Add responsibility</button></form></div></section>
      <footer>Orbit • CSE 4333 • AWS-powered midpoint prototype • Canvas ICS import planned</footer>
    </main></div>
}
