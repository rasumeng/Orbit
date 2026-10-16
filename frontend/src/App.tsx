import { useEffect, useMemo, useRef, useState, type FormEvent } from 'react'
import {
  ArrowDownRight,
  ArrowUpRight,
  ChevronLeft,
  ChevronRight,
  CalendarDays,
  Check,
  CircleCheck,
  Clock3,
  Copy,
  FolderPlus,
  LayoutDashboard,
  List,
  Orbit as OrbitIcon,
  Plus,
  RefreshCw,
  Sparkles,
  Upload,
  Users,
} from 'lucide-react'

type Category = 'school' | 'work' | 'leadership' | 'projects' | 'personal'
type Priority = 'low' | 'medium' | 'high'
type Item = { id: string; title: string; description?: string; category?: Category; priority?: Priority; dueAt?: string; status?: 'pending' | 'completed'; source?: string; projectId?: string; assignee?: string }
type Project = { id: string; name: string; inviteCode: string; members: string[]; createdAt: string }

const API = (import.meta.env.VITE_API_URL ?? '').replace(/\/$/, '')
const categories: Category[] = ['school', 'work', 'leadership', 'projects', 'personal']

async function authorizedFetch(url: string, init?: RequestInit) {
  const headers = new Headers(init?.headers)
  const accessCode = window.localStorage.getItem('orbit.accessCode')
  if (accessCode) headers.set('x-orbit-access-code', accessCode)
  const response = await fetch(url, { ...init, headers })
  if (response.status === 401) window.dispatchEvent(new Event('orbit-session-expired'))
  return response
}

function formatDueDate(value: string) {
  return new Date(value).toLocaleString([], { weekday: 'short', month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })
}

function localDateKey(date: Date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

function parseCalendarDate(value: string, timeZone?: string) {
  const match = /^(\d{4})(\d{2})(\d{2})(?:T(\d{2})(\d{2})(\d{2})?(Z)?)?$/.exec(value)
  if (!match) return undefined
  const [, year, month, day, hour = '00', minute = '00', second = '00', utc] = match
  const parts = [Number(year), Number(month), Number(day), Number(hour), Number(minute), Number(second)]
  if (utc) return new Date(`${year}-${month}-${day}T${hour}:${minute}:${second}Z`)
  if (!timeZone || !value.includes('T')) return new Date(parts[0], parts[1] - 1, parts[2], parts[3], parts[4], parts[5])

  try {
    const formatter = new Intl.DateTimeFormat('en-US', {
      timeZone, year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
    })
    const targetAsUtc = Date.UTC(parts[0], parts[1] - 1, parts[2], parts[3], parts[4], parts[5])
    let instant = targetAsUtc
    for (let attempt = 0; attempt < 3; attempt += 1) {
      const zoned = Object.fromEntries(formatter.formatToParts(new Date(instant)).map(part => [part.type, part.value]))
      const representedAsUtc = Date.UTC(Number(zoned.year), Number(zoned.month) - 1, Number(zoned.day), Number(zoned.hour), Number(zoned.minute), Number(zoned.second))
      instant += targetAsUtc - representedAsUtc
    }
    return new Date(instant)
  } catch {
    return undefined
  }
}

function getMonthGrid(month: Date) {
  const first = new Date(month.getFullYear(), month.getMonth(), 1)
  const start = new Date(first.getFullYear(), first.getMonth(), 1 - first.getDay())
  return Array.from({ length: 42 }, (_, index) => new Date(start.getFullYear(), start.getMonth(), start.getDate() + index))
}

type CalendarEvent = { title: string; dueAt: string; sourceKey: string }

function parseIcsCalendar(text: string): CalendarEvent[] {
  const lines = text.replace(/\r?\n[ \t]/g, '').split(/\r?\n/)
  const events: CalendarEvent[] = []
  let current: Record<string, string> | null = null
  for (const line of lines) {
    if (line === 'BEGIN:VEVENT') { current = {}; continue }
    if (line === 'END:VEVENT') {
      if (current) {
        const title = current.SUMMARY?.replace(/\\([nN,;\\])/g, (_, char: string) => char.toLowerCase() === 'n' ? ' ' : char).trim()
        const start = current.DTSTART
        const uid = current.UID
        if (title && start && uid) {
          const date = parseCalendarDate(start, current.TZID)
          if (date && !Number.isNaN(date.getTime())) events.push({ title: title.slice(0, 120), dueAt: date.toISOString(), sourceKey: uid })
        }
      }
      current = null
      continue
    }
    if (!current) continue
    const colon = line.indexOf(':')
    if (colon < 0) continue
    const [property, ...params] = line.slice(0, colon).split(';')
    const value = line.slice(colon + 1)
    const key = property.toUpperCase()
    if (key === 'SUMMARY' || key === 'UID') current[key] = value
    if (key === 'DTSTART') {
      current.DTSTART = value
      const tzid = params.find(param => param.toUpperCase().startsWith('TZID='))?.slice(5).replace(/^"|"$/g, '')
      if (tzid) current.TZID = tzid
    }
  }
  return events
}

export default function App() {
  const [accessCode, setAccessCode] = useState(() => window.localStorage.getItem('orbit.accessCode') ?? '')
  const [gateCode, setGateCode] = useState('')
  const [spaceName, setSpaceName] = useState('')
  const [gateError, setGateError] = useState('')
  const [gateBusy, setGateBusy] = useState(false)
  const [createdAccessCode, setCreatedAccessCode] = useState('')
  const [showAccessCode, setShowAccessCode] = useState(false)
  const [accessCodeCopied, setAccessCodeCopied] = useState(false)
  const [items, setItems] = useState<Item[]>([])
  const [projects, setProjects] = useState<Project[]>([])
  const [selectedProject, setSelectedProject] = useState('all')
  const [projectName, setProjectName] = useState('')
  const [memberName, setMemberName] = useState(() => window.localStorage.getItem('orbit.memberName') ?? '')
  const [joinCode, setJoinCode] = useState('')
  const [copiedInviteCode, setCopiedInviteCode] = useState('')
  const [editingProjectTaskId, setEditingProjectTaskId] = useState('')
  const [editTaskTitle, setEditTaskTitle] = useState('')
  const [editTaskDescription, setEditTaskDescription] = useState('')
  const [editTaskDueAt, setEditTaskDueAt] = useState('')
  const [taskProjectId, setTaskProjectId] = useState('')
  const [assignee, setAssignee] = useState('')
  const [title, setTitle] = useState('')
  const [category, setCategory] = useState<Category>('school')
  const [priority, setPriority] = useState<Priority>('medium')
  const [dueAt, setDueAt] = useState('')
  const [busy, setBusy] = useState(false)
  const [togglingIds, setTogglingIds] = useState<Set<string>>(() => new Set())
  const [error, setError] = useState('')
  const [importStatus, setImportStatus] = useState('')
  const [filter, setFilter] = useState('all')
  const [workspaceTab, setWorkspaceTab] = useState<'overview' | 'tasks' | 'calendar' | 'projects'>('overview')
  const [showCompleted, setShowCompleted] = useState(false)
  const [calendarMonth, setCalendarMonth] = useState(() => {
    const now = new Date()
    return new Date(now.getFullYear(), now.getMonth(), 1)
  })
  const fileInput = useRef<HTMLInputElement>(null)
  const memberNameInput = useRef<HTMLInputElement>(null)

  function openPersonalWorkspace(tab: 'tasks' | 'calendar') {
    setSelectedProject('all')
    setTaskProjectId('')
    setWorkspaceTab(tab)
  }

  async function createOrbitSpace(e: FormEvent) {
    e.preventDefault()
    if (!API) { setGateError('Orbit API is not configured. Set VITE_API_URL first.'); return }
    setGateBusy(true)
    setGateError('')
    try {
      const r = await fetch(`${API}/spaces`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: spaceName.trim() }) })
      const data = await r.json()
      if (!r.ok) throw Error(data.error || `API returned ${r.status}`)
      window.localStorage.setItem('orbit.accessCode', data.accessCode)
      window.localStorage.setItem('orbit.memberName', spaceName.trim())
      setMemberName(spaceName.trim())
      setCreatedAccessCode(data.accessCode)
      setAccessCode(data.accessCode)
    } catch (e) { setGateError(String(e)) } finally { setGateBusy(false) }
  }

  async function openOrbitSpace(e: FormEvent) {
    e.preventDefault()
    if (!API) { setGateError('Orbit API is not configured. Set VITE_API_URL first.'); return }
    setGateBusy(true)
    setGateError('')
    const code = gateCode.replace(/\s+/g, '').toUpperCase()
    try {
      const r = await fetch(`${API}/spaces/open`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ accessCode: code }) })
      const data = await r.json()
      if (!r.ok) throw Error(data.error || `API returned ${r.status}`)
      window.localStorage.setItem('orbit.accessCode', code)
      window.localStorage.setItem('orbit.memberName', data.workspace.name)
      setMemberName(data.workspace.name)
      setAccessCode(code)
    } catch (e) { setGateError(String(e)) } finally { setGateBusy(false) }
  }

  function signOut() {
    window.localStorage.removeItem('orbit.accessCode')
    setAccessCode('')
    setCreatedAccessCode('')
    setGateCode('')
  }

  async function copyNewAccessCode() {
    setAccessCodeCopied(true)
    try {
      await navigator.clipboard.writeText(createdAccessCode || accessCode)
    } catch {
      setAccessCodeCopied(false)
      setGateError('Copy was blocked by the browser. Select the code and copy it manually.')
    }
  }

  async function load() {
    if (!API) { setError('Set VITE_API_URL in frontend/.env first.'); return }
    if (!accessCode) return
    try {
      setError('')
      const r = await authorizedFetch(`${API}/items`)
      if (!r.ok) throw Error(`API returned ${r.status}`)
      const data = await r.json()
      setItems(data.items ?? [])
    } catch (e) { setError(String(e)) }
  }

  useEffect(() => {
    const onExpired = () => {
      window.localStorage.removeItem('orbit.accessCode')
      setAccessCode('')
      setGateError('Your access code could not be verified. Enter it again to open your space.')
    }
    window.addEventListener('orbit-session-expired', onExpired)
    return () => window.removeEventListener('orbit-session-expired', onExpired)
  }, [])

  useEffect(() => { if (accessCode) void load() }, [accessCode])

  async function loadProjects() {
    if (!accessCode) return
    try {
      const r = await authorizedFetch(`${API}/projects`)
      if (!r.ok) throw Error(`API returned ${r.status}`)
      const data = await r.json()
      setProjects(data.projects ?? [])
    } catch (e) { setError(String(e)) }
  }

  useEffect(() => { if (API && accessCode) void loadProjects() }, [accessCode])

  useEffect(() => {
    if (workspaceTab !== 'projects' || !API || !accessCode) return
    const refreshSharedSpace = async () => {
      try {
        const [itemsResponse, projectsResponse] = await Promise.all([authorizedFetch(`${API}/items`), authorizedFetch(`${API}/projects`)])
        if (!itemsResponse.ok || !projectsResponse.ok) return
        const [itemsData, projectsData] = await Promise.all([itemsResponse.json(), projectsResponse.json()])
        setItems(itemsData.items ?? [])
        setProjects(projectsData.projects ?? [])
      } catch {
        // Keep the current view available when a background refresh briefly fails.
      }
    }
    const interval = window.setInterval(() => void refreshSharedSpace(), 20000)
    return () => window.clearInterval(interval)
  }, [workspaceTab, accessCode])

  async function createProject(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    try {
      const r = await authorizedFetch(`${API}/projects`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ name: projectName, memberName }) })
      const data = await r.json()
      if (!r.ok) throw Error(data.error || `API returned ${r.status}`)
      setProjectName('')
      await loadProjects()
      setSelectedProject(data.project.id)
      setTaskProjectId(data.project.id)
    } catch (e) { setError(String(e)) } finally { setBusy(false) }
  }

  async function joinProject(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    try {
      const r = await authorizedFetch(`${API}/projects/join`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ inviteCode: joinCode, memberName }) })
      const data = await r.json()
      if (!r.ok) throw Error(data.error || `API returned ${r.status}`)
      setJoinCode('')
      await loadProjects()
      setSelectedProject(data.project.id)
      setTaskProjectId(data.project.id)
    } catch (e) { setError(String(e)) } finally { setBusy(false) }
  }

  async function copyInviteCode(code: string) {
    try {
      await navigator.clipboard.writeText(code)
      setCopiedInviteCode(code)
      window.setTimeout(() => setCopiedInviteCode(current => current === code ? '' : current), 1800)
    } catch {
      setError('Could not copy the invite code. You can select and copy it manually.')
    }
  }

  async function create(e: FormEvent) {
    e.preventDefault()
    setBusy(true)
    try {
      const projectId = selectedProject === 'all' ? taskProjectId : selectedProject
      const payload = { title, category, priority, ...(dueAt ? { dueAt: new Date(dueAt).toISOString() } : {}), ...(projectId ? { projectId, ...(assignee.trim() ? { assignee: assignee.trim() } : {}) } : {}) }
      const r = await authorizedFetch(`${API}/items`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
      if (!r.ok) throw Error((await r.json()).error || `API returned ${r.status}`)
      setTitle('')
      setDueAt('')
      setAssignee('')
      await load()
    } catch (e) { setError(String(e)) } finally { setBusy(false) }
  }

  async function toggle(item: Item) {
    if (togglingIds.has(item.id)) return
    const previousStatus = item.status ?? 'pending'
    const nextStatus = previousStatus === 'completed' ? 'pending' : 'completed'
    setTogglingIds(current => new Set(current).add(item.id))
    setItems(current => current.map(existing => existing.id === item.id ? { ...existing, status: nextStatus } : existing))
    try {
      const r = await authorizedFetch(`${API}/items/${encodeURIComponent(item.id)}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ status: nextStatus }) })
      if (!r.ok) throw Error(`API returned ${r.status}`)
    } catch (e) {
      setItems(current => current.map(existing => existing.id === item.id ? { ...existing, status: previousStatus } : existing))
      setError(String(e))
    } finally {
      setTogglingIds(current => { const next = new Set(current); next.delete(item.id); return next })
    }
  }

  async function assignToMe(item: Item) {
    const assigneeName = memberName.trim()
    if (!assigneeName || item.assignee === assigneeName) return
    const previousAssignee = item.assignee
    setItems(current => current.map(existing => existing.id === item.id ? { ...existing, assignee: assigneeName } : existing))
    try {
      const r = await authorizedFetch(`${API}/items/${encodeURIComponent(item.id)}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ assignee: assigneeName }) })
      if (!r.ok) throw Error((await r.json()).error || `API returned ${r.status}`)
    } catch (e) {
      setItems(current => current.map(existing => existing.id === item.id ? { ...existing, assignee: previousAssignee } : existing))
      setError(String(e))
    }
  }

  function beginEditProjectTask(item: Item) {
    setEditingProjectTaskId(item.id)
    setEditTaskTitle(item.title)
    setEditTaskDescription(item.description ?? '')
    setEditTaskDueAt(item.dueAt ? new Date(new Date(item.dueAt).getTime() - new Date(item.dueAt).getTimezoneOffset() * 60000).toISOString().slice(0, 16) : '')
  }

  async function saveProjectTask(e: FormEvent, item: Item) {
    e.preventDefault()
    const updatedTitle = editTaskTitle.trim()
    if (!updatedTitle) return
    setBusy(true)
    try {
      const payload = { title: updatedTitle, description: editTaskDescription.trim(), dueAt: editTaskDueAt ? new Date(editTaskDueAt).toISOString() : '' }
      const r = await authorizedFetch(`${API}/items/${encodeURIComponent(item.id)}`, { method: 'PATCH', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) })
      const data = await r.json()
      if (!r.ok) throw Error(data.error || `API returned ${r.status}`)
      setItems(current => current.map(existing => existing.id === item.id ? { ...existing, title: data.item?.title ?? updatedTitle, description: data.item?.description ?? editTaskDescription.trim(), dueAt: data.item?.dueAt } : existing))
      setEditingProjectTaskId('')
    } catch (e) { setError(String(e)) } finally { setBusy(false) }
  }

  async function importCalendarFiles(fileList?: FileList | null) {
    const files = Array.from(fileList ?? [])
    if (!files.length) return
    setImportStatus('')
    setError('')
    if (files.some(file => !file.name.toLowerCase().endsWith('.ics') && file.type !== 'text/calendar')) {
      setError('Choose Apple or Google Calendar .ics files. Extract Google Calendar export ZIP files first.')
      return
    }
    if (files.reduce((total, file) => total + file.size, 0) > 20 * 1024 * 1024) {
      setError('Selected calendar files must total less than 20 MB.')
      return
    }
    setBusy(true)
    try {
      const events = (await Promise.all(files.map(async file => parseIcsCalendar(await file.text())))).flat()
      if (!events.length) throw Error('No calendar events with titles, dates, and IDs were found in the selected files.')
      let imported = 0
      let updated = 0
      let skipped = 0
      for (let index = 0; index < events.length; index += 250) {
        const r = await authorizedFetch(`${API}/items/import`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ items: events.slice(index, index + 250) }),
        })
        const result = await r.json()
        if (!r.ok) throw Error(result.error || `API returned ${r.status}`)
        imported += result.imported ?? 0
        updated += result.updated ?? 0
        skipped += result.skipped ?? 0
      }
      await load()
      setImportStatus(`Imported ${imported}${updated ? ` · updated ${updated}` : ''}${skipped ? ` · ${skipped} already current` : ''} from ${files.length} ${files.length === 1 ? 'calendar file' : 'calendar files'}.`)
    } catch (e) { setError(String(e)) } finally {
      setBusy(false)
      if (fileInput.current) fileInput.current.value = ''
    }
  }

  const upcoming = useMemo(() => items.filter(i => (i.status ?? 'pending') === 'pending'), [items])
  const completed = useMemo(() => items.filter(i => i.status === 'completed'), [items])
  const visible = useMemo(() => items.filter(i => (selectedProject === 'all' || i.projectId === selectedProject) && (showCompleted || i.status !== 'completed') && (filter === 'all' || i.category === filter)).sort((a, b) => (a.dueAt ?? '').localeCompare(b.dueAt ?? '')), [items, filter, showCompleted, selectedProject])
  const calendarVisible = useMemo(() => items.filter(i => (selectedProject === 'all' ? (!i.projectId || (!!memberName.trim() && i.assignee?.toLowerCase() === memberName.trim().toLowerCase())) : i.projectId === selectedProject) && (filter === 'all' || i.category === filter)).sort((a, b) => (a.dueAt ?? '').localeCompare(b.dueAt ?? '')), [items, filter, memberName, selectedProject])
  const calendarDays = useMemo(() => getMonthGrid(calendarMonth), [calendarMonth])
  const calendarEvents = useMemo(() => {
    const grouped = new Map<string, Item[]>()
    calendarVisible.forEach(item => {
      if (!item.dueAt) return
      const key = localDateKey(new Date(item.dueAt))
      grouped.set(key, [...(grouped.get(key) ?? []), item])
    })
    return grouped
  }, [calendarVisible])
  const selectedSpaceItems = useMemo(() => items.filter(item => item.projectId === selectedProject).sort((a, b) => (a.dueAt ?? '').localeCompare(b.dueAt ?? '')), [items, selectedProject])
  const selectedSpaceCalendar = useMemo(() => {
    const grouped = new Map<string, Item[]>()
    selectedSpaceItems.forEach(item => {
      if (!item.dueAt) return
      const key = localDateKey(new Date(item.dueAt))
      grouped.set(key, [...(grouped.get(key) ?? []), item])
    })
    return grouped
  }, [selectedSpaceItems])
  const selectedSpaceDueCount = calendarDays.reduce((count, day) => day.getMonth() === calendarMonth.getMonth() ? count + (selectedSpaceCalendar.get(localDateKey(day))?.length ?? 0) : count, 0)
  const monthEventCount = calendarDays.reduce((count, day) => day.getMonth() === calendarMonth.getMonth() ? count + (calendarEvents.get(localDateKey(day))?.length ?? 0) : count, 0)
  const todayKey = localDateKey(new Date())
  const next7 = upcoming.filter(i => i.dueAt && new Date(i.dueAt).getTime() <= Date.now() + 7 * 86400000 && new Date(i.dueAt).getTime() >= Date.now()).length
  const today = new Intl.DateTimeFormat([], { weekday: 'long', month: 'long', day: 'numeric' }).format(new Date())

  if (!accessCode) return <div className="auth-screen"><section className="auth-card"><a className="brand auth-brand" href="#top"><span className="brand-mark"><OrbitIcon size={21} strokeWidth={2.1} /></span><span>orbit<span className="brand-period">.</span></span></a><p className="section-kicker">YOUR SPACE, WHEREVER YOU ARE</p><h1>Pick up right where you left off.</h1><p className="auth-intro">Create an Orbit access code once, then use it to open your workspace on another device.</p>{gateError && <div className="error-banner" role="alert"><span>{gateError}</span></div>}
    <form className="auth-form" onSubmit={openOrbitSpace}><label>Already have an Orbit code?<input required maxLength={24} minLength={24} value={gateCode} onChange={e => setGateCode(e.target.value.toUpperCase().replace(/\s+/g, ''))} placeholder="24-character access code" autoComplete="off" /></label><button type="submit" disabled={gateBusy || !API}>{gateBusy ? 'Opening…' : 'Open my space'}<ArrowUpRight size={15} /></button></form>
    <div className="auth-divider"><span>NEW TO ORBIT?</span></div><form className="auth-form" onSubmit={createOrbitSpace}><label>Create your Orbit space<input required maxLength={60} value={spaceName} onChange={e => setSpaceName(e.target.value)} placeholder="Your name or workspace name" /></label><button type="submit" disabled={gateBusy || !API || !spaceName.trim()}>{gateBusy ? 'Creating…' : 'Create space and code'}<Plus size={15} /></button></form><p className="auth-footnote">Your code is the key to your workspace. Save it somewhere private; Orbit can’t recover a lost code.</p></section></div>

  return <div className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="#top" aria-label="Orbit home"><span className="brand-mark"><OrbitIcon size={21} strokeWidth={2.1} /></span><span>orbit<span className="brand-period">.</span></span></a>
      <p className="brand-caption">A little more room to think.</p>

      <nav className="side-nav" aria-label="Main navigation">
        <p className="nav-label">Workspace</p>
        <button className={`nav-item${workspaceTab === 'overview' ? ' active' : ''}`} onClick={() => setWorkspaceTab('overview')}><LayoutDashboard size={17} strokeWidth={1.9} /> Overview {workspaceTab === 'overview' && <span className="nav-active-dot" />}</button>
        <button className={`nav-item${workspaceTab === 'tasks' ? ' active' : ''}`} onClick={() => openPersonalWorkspace('tasks')}><List size={17} strokeWidth={1.9} /> Tasks {workspaceTab === 'tasks' && <span className="nav-active-dot" />}</button>
        <button className={`nav-item${workspaceTab === 'calendar' ? ' active' : ''}`} onClick={() => openPersonalWorkspace('calendar')}><CalendarDays size={17} strokeWidth={1.9} /> Calendar {workspaceTab === 'calendar' && <span className="nav-active-dot" />}</button>
        <button className={`nav-item${workspaceTab === 'projects' ? ' active' : ''}`} onClick={() => setWorkspaceTab('projects')}><Users size={17} strokeWidth={1.9} /> Project spaces {workspaceTab === 'projects' && <span className="nav-active-dot" />}</button>
      </nav>

      <div className="sidebar-note">
        <div className="note-icon"><Sparkles size={17} /></div>
        <p className="note-kicker">A gentle reminder</p>
        <p>Progress is made one small thing at a time.</p>
      </div>
      <div className="sidebar-bottom"><span className="sidebar-orbit"><OrbitIcon size={14} /></span><span>Made for the full plate.</span></div>
    </aside>

    <main className="main-content" id="top">
      <div className="page-wrap">
        <div className="topbar"><span className="today-label"><span className="today-dot" />{today}</span><div className="topbar-actions"><button className="refresh-button" type="button" onClick={load} title="Refresh responsibilities"><RefreshCw size={15} /><span>Refresh</span></button><button className="sign-out-button" type="button" onClick={() => { setAccessCodeCopied(false); setShowAccessCode(true) }}>Access code</button><button className="sign-out-button" type="button" onClick={signOut}>Sign out</button></div></div>
        {(createdAccessCode || showAccessCode) && <div className="auth-code-overlay"><section className="auth-code-card" role="dialog" aria-modal="true" aria-labelledby="access-code-title"><p className="section-kicker">{createdAccessCode ? 'SAVE THIS CODE' : 'YOUR WORKSPACE KEY'}</p><h2 id="access-code-title">Your Orbit access code</h2><p>This code opens your workspace on any device. Anyone with the code can access it, so keep it private.</p><code>{createdAccessCode || accessCode}</code><button type="button" onClick={() => void copyNewAccessCode()}>{accessCodeCopied ? <Check size={15} /> : <Copy size={15} />}{accessCodeCopied ? 'Copied' : 'Copy code'}</button><button className="auth-continue-button" type="button" onClick={() => { setCreatedAccessCode(''); setShowAccessCode(false) }}>{createdAccessCode ? 'I saved my code' : 'Close'}</button></section></div>}

        {workspaceTab === 'overview' && <><section className="welcome-card" aria-labelledby="welcome-title">
          <div className="welcome-copy">
            <span className="welcome-tag"><span className="tag-star">✳</span> YOUR STUDENT PLANNER</span>
            <h1 id="welcome-title">Your week,<br /><em>in orbit.</em></h1>
            <p>Classes, deadlines, and everything in between—<br className="desktop-break" />all with a little more breathing room.</p>
          </div>
          <div className="orbit-art" aria-hidden="true">
            <div className="orbit-ring ring-one" /><div className="orbit-ring ring-two" /><div className="orbit-ring ring-three" />
            <div className="orbit-sun"><OrbitIcon size={30} strokeWidth={1.6} /></div>
            <span className="planet planet-lime" /><span className="planet planet-coral" /><span className="planet planet-lilac" />
            <div className="orbit-caption"><CalendarDays size={15} /><span>Make space for what matters</span></div>
          </div>
          <div className="welcome-sparkle sparkle-one">✳</div><div className="welcome-sparkle sparkle-two">✳</div>
        </section>

        {error && <div className="error-banner" role="alert"><span>{error}</span><button onClick={() => setError('')} aria-label="Dismiss error">×</button></div>}

        <section className="stats-grid" aria-label="Responsibility summary">
          <article className="stat-card stat-open"><div className="stat-top"><span>Still in motion</span><span className="stat-icon"><ArrowUpRight size={17} /></span></div><div className="stat-number">{upcoming.length}</div><div className="stat-foot">open responsibilities</div></article>
          <article className="stat-card stat-soon"><div className="stat-top"><span>Coming up</span><span className="stat-icon"><Clock3 size={17} /></span></div><div className="stat-number">{next7}</div><div className="stat-foot">due in the next 7 days</div></article>
          <article className="stat-card stat-done"><div className="stat-top"><span>Look at you go</span><span className="stat-icon"><Check size={17} /></span></div><div className="stat-number">{completed.length}</div><div className="stat-foot">things already handled</div></article>
        </section>
        <section className="overview-shortcuts panel-card"><div><p className="section-kicker">YOUR WORKSPACE</p><h2>Pick up where you left off.</h2><p className="section-subtitle">Jump straight to the part of Orbit you need.</p></div><div className="shortcut-actions"><button type="button" onClick={() => openPersonalWorkspace('tasks')}><List size={16} /> Open tasks</button><button type="button" onClick={() => openPersonalWorkspace('calendar')}><CalendarDays size={16} /> View calendar</button><button type="button" onClick={() => setWorkspaceTab('projects')}><Users size={16} /> Team spaces</button></div></section></>}

        {workspaceTab === 'projects' && <section className="projects-panel panel-card" aria-labelledby="projects-title">
          <div className="projects-heading"><div><p className="section-kicker">BETTER TOGETHER</p><h2 id="projects-title">Project spaces<span className="heading-period">.</span></h2><p className="section-subtitle">Keep team plans and next steps in one shared place.</p></div><label className="member-name-field">Your name<input ref={memberNameInput} maxLength={40} value={memberName} onChange={e => { setMemberName(e.target.value); window.localStorage.setItem('orbit.memberName', e.target.value) }} placeholder="e.g. Emily" /></label></div>
          {error && <div className="error-banner" role="alert"><span>{error}</span><button onClick={() => setError('')} aria-label="Dismiss error">×</button></div>}
          <div className="project-controls">
            <form className="project-create-form" onSubmit={createProject}><FolderPlus size={16} /><input required maxLength={80} value={projectName} onChange={e => setProjectName(e.target.value)} placeholder="Name a project space" aria-label="New project space name" /><button disabled={busy || !API || !memberName.trim()} type="submit">Create space</button></form>
            <form className="project-join-form" onSubmit={joinProject}><Users size={16} /><input required maxLength={8} value={joinCode} onChange={e => setJoinCode(e.target.value.toUpperCase())} placeholder="8-character invite code" aria-label="Project invite code" /><button disabled={busy || !API || !memberName.trim()} type="submit">Join</button></form>
          </div>
          <div className="project-cards">
            {projects.map(project => <div className="project-card-wrap" key={project.id}><button type="button" className={`project-card${selectedProject === project.id ? ' project-selected' : ''}`} aria-pressed={selectedProject === project.id} onClick={() => { setSelectedProject(project.id); setTaskProjectId(project.id) }}><span className="project-card-icon"><Users size={17} /></span><span className="project-card-copy"><strong>{project.name}</strong><small>{project.members?.length ?? 1} {project.members?.length === 1 ? 'member' : 'members'} · invite {project.inviteCode}</small></span><span className="project-card-count">{items.filter(item => item.projectId === project.id && item.status !== 'completed').length}</span></button><button type="button" className={`project-copy-button${copiedInviteCode === project.inviteCode ? ' copied' : ''}`} onClick={() => void copyInviteCode(project.inviteCode)} aria-label={`Copy invite code ${project.inviteCode}`} title={copiedInviteCode === project.inviteCode ? 'Copied!' : 'Copy invite code'}>{copiedInviteCode === project.inviteCode ? <Check size={15} /> : <Copy size={15} />}</button>{copiedInviteCode === project.inviteCode && <span className="project-copy-status" role="status">Copied</span>}</div>)}
          </div>
          {projects.length === 0 && <p className="projects-empty">Create a space and share its invite code with your project team.</p>}
          {selectedProject !== 'all' && projects.some(project => project.id === selectedProject) && <section className="project-detail" aria-label={`${projects.find(project => project.id === selectedProject)?.name} workspace`}>
            <div className="project-detail-heading"><div><p className="section-kicker">SPACE WORK</p><h3>{projects.find(project => project.id === selectedProject)?.name}<span className="heading-period">.</span></h3><p className="section-subtitle">Tasks in this space stay separate from your personal list.</p></div><span className="project-detail-members"><Users size={14} /> {projects.find(project => project.id === selectedProject)?.members?.length ?? 1} members</span></div>
            <form className="project-task-form" onSubmit={create}><input required maxLength={120} value={title} onChange={e => setTitle(e.target.value)} placeholder="Add a task to this space" aria-label="Project task title" /><input type="datetime-local" value={dueAt} onChange={e => setDueAt(e.target.value)} aria-label="Task due date" /><button type="submit" disabled={busy || !API || !title.trim()}><Plus size={15} /> Add task</button></form>
            <div className="project-work-layout">
              <div className="project-board"><div className="project-board-heading"><h4>Team tasks</h4><span>{selectedSpaceItems.filter(item => item.status !== 'completed').length} open</span></div>
                {!memberName.trim() && <p className="projects-empty">Enter your name above to enable self-assignment.</p>}
                {selectedSpaceItems.length === 0 ? <p className="projects-empty">No tasks in this space yet. Add the first one above.</p> : <div className="project-task-list">{selectedSpaceItems.map(item => { const done = item.status === 'completed'; const editing = editingProjectTaskId === item.id; return <article className={`task-row project-task-row${done ? ' is-complete' : ''}${editing ? ' project-task-editing' : ''}`} key={item.id}><button disabled={togglingIds.has(item.id)} className={`task-check${done ? ' checked' : ''}`} aria-label={`${done ? 'Mark pending' : 'Mark complete'}: ${item.title}`} onClick={() => void toggle(item)}>{done ? <Check size={15} strokeWidth={2.5} /> : <CircleCheck size={19} strokeWidth={1.6} />}</button><div className="task-info"><div className="task-title-line"><button type="button" className={`task-edit-trigger${done ? ' done' : ''}`} onClick={() => editing ? setEditingProjectTaskId('') : beginEditProjectTask(item)} aria-expanded={editing}>{item.title}</button><span className={`priority-dot priority-${item.priority ?? 'medium'}`} title={`${item.priority ?? 'medium'} priority`} /></div>{item.description && <p className="project-task-description">{item.description}</p>}<div className="task-meta"><span className={`category-tag cat-${item.category ?? 'personal'}`}>{item.category ?? 'personal'}</span>{item.dueAt ? <span className="due-label"><CalendarDays size={13} />{formatDueDate(item.dueAt)}</span> : <span className="due-label no-date">No due date</span>}</div>{editing && <form className="project-task-edit-form" onSubmit={e => void saveProjectTask(e, item)}><label>Task title<input required maxLength={120} value={editTaskTitle} onChange={e => setEditTaskTitle(e.target.value)} autoFocus /></label><label>Details<textarea maxLength={2000} rows={4} value={editTaskDescription} onChange={e => setEditTaskDescription(e.target.value)} placeholder="Add notes or task details for your team" /></label><label>Due date<input type="datetime-local" value={editTaskDueAt} onChange={e => setEditTaskDueAt(e.target.value)} /></label><div className="project-task-edit-actions"><button type="button" onClick={() => setEditingProjectTaskId('')}>Cancel</button><button type="submit" disabled={busy || !editTaskTitle.trim()}><Check size={13} /> Save</button></div></form>}</div><div className="project-task-assignment"><span className="project-assignee">{item.assignee || 'Unassigned'}</span><button type="button" title={!memberName.trim() ? 'Enter your name above to assign this task' : undefined} disabled={!!memberName.trim() && item.assignee === memberName.trim()} onClick={() => { if (!memberName.trim()) { setError('Enter your name above to enable self-assignment.'); memberNameInput.current?.focus(); return } void assignToMe(item) }}>{item.assignee === memberName.trim() && memberName.trim() ? 'Assigned to you' : memberName.trim() ? 'Assign to me' : 'Set your name first'}</button></div></article>})}</div>}
              </div>
              <aside className="project-mini-calendar" aria-label="Project space calendar"><div className="mini-calendar-heading"><div><p className="calendar-label">SPACE DATES</p><h4>{calendarMonth.toLocaleDateString([], { month: 'long', year: 'numeric' })}</h4></div><div className="calendar-nav"><button type="button" aria-label="Previous month" onClick={() => setCalendarMonth(month => new Date(month.getFullYear(), month.getMonth() - 1, 1))}><ChevronLeft size={14} /></button><button type="button" aria-label="Next month" onClick={() => setCalendarMonth(month => new Date(month.getFullYear(), month.getMonth() + 1, 1))}><ChevronRight size={14} /></button></div></div><div className="mini-calendar-grid">{Array.from({ length: 7 }, (_, index) => <span className="mini-calendar-weekday" key={`mini-weekday-${index}`}>{new Date(2024, 0, 7 + index).toLocaleDateString([], { weekday: 'narrow' })}</span>)}{calendarDays.map(day => { const key = localDateKey(day); const dayItems = selectedSpaceCalendar.get(key) ?? []; return <div key={key} className={`mini-calendar-day${day.getMonth() !== calendarMonth.getMonth() ? ' outside-month' : ''}${key === todayKey ? ' is-today' : ''}`} title={dayItems.map(item => item.title).join(', ')}><span>{day.getDate()}</span>{dayItems.length > 0 && <i>{dayItems.length}</i>}</div>})}</div><p className="mini-calendar-summary">{selectedSpaceDueCount} {selectedSpaceDueCount === 1 ? 'team deadline' : 'team deadlines'} this month</p><div className="mini-calendar-upcoming">{selectedSpaceItems.filter(item => item.dueAt && localDateKey(new Date(item.dueAt)) >= todayKey).slice(0, 3).map(item => <div key={item.id}><span className="mini-calendar-dot" /><span>{item.title}</span><time>{new Date(item.dueAt!).toLocaleDateString([], { month: 'short', day: 'numeric' })}</time></div>)}</div></aside>
            </div>
          </section>}
        </section>}

        {(workspaceTab === 'tasks' || workspaceTab === 'calendar') && <section className={`dashboard-grid${workspaceTab === 'calendar' ? ' calendar-workspace-grid' : ''}`} aria-label={workspaceTab === 'calendar' ? 'Calendar workspace' : 'Task workspace'}>
          <div className="task-panel panel-card">
            <div className="section-heading">
              <div><p className="section-kicker">{workspaceTab === 'calendar' ? 'YOUR SCHEDULE' : 'TASK MANAGER'}</p><h2>{workspaceTab === 'calendar' ? 'Calendar overview' : 'On your plate'}<span className="heading-period">.</span></h2><p className="section-subtitle">{workspaceTab === 'calendar' ? 'Personal deadlines and team tasks assigned to you.' : selectedProject === 'all' ? 'A clear view of what’s next.' : projects.find(project => project.id === selectedProject)?.name}</p></div>
              <div className="task-actions">
                <input ref={fileInput} className="sr-only" type="file" accept=".ics,text/calendar" multiple aria-label="Choose Apple, Google, or Canvas calendar files" onChange={e => void importCalendarFiles(e.target.files)} />
                <button className="canvas-import-button" type="button" title="Choose Apple, Google, or Canvas .ics files; extract Google ZIP exports first" disabled={busy || !API} onClick={() => fileInput.current?.click()}><Upload size={14} /><span>Import Calendar</span></button>
                {workspaceTab === 'tasks' && completed.length > 0 && <button className="completed-toggle" type="button" aria-pressed={showCompleted} onClick={() => setShowCompleted(value => !value)}>{showCompleted ? 'Hide completed' : `Show completed (${completed.length})`}</button>}
                <label className="filter-label"><span className="sr-only">Filter by category</span><select aria-label="Filter category" value={filter} onChange={e => setFilter(e.target.value)}><option value="all">Everything</option>{categories.map(c => <option key={c} value={c}>{c[0].toUpperCase() + c.slice(1)}</option>)}</select></label>
              </div>
            </div>

            {importStatus && <p className="import-status" role="status">{importStatus}</p>}

            {workspaceTab === 'calendar' ? <div className="calendar-view">
              <div className="calendar-toolbar">
                <div><p className="calendar-label">YOUR SCHEDULE</p><h3>{calendarMonth.toLocaleDateString([], { month: 'long', year: 'numeric' })}</h3></div>
                <div className="calendar-nav">
                  <button type="button" aria-label="Previous month" onClick={() => setCalendarMonth(month => new Date(month.getFullYear(), month.getMonth() - 1, 1))}><ChevronLeft size={16} /></button>
                  <button type="button" className="today-button" onClick={() => { const now = new Date(); setCalendarMonth(new Date(now.getFullYear(), now.getMonth(), 1)) }}>Today</button>
                  <button type="button" aria-label="Next month" onClick={() => setCalendarMonth(month => new Date(month.getFullYear(), month.getMonth() + 1, 1))}><ChevronRight size={16} /></button>
                </div>
              </div>
              <div className="calendar-scroll"><div className="calendar-grid">
                {Array.from({ length: 7 }, (_, index) => <div className="calendar-weekday" key={`weekday-${index}`}>{new Date(2024, 0, 7 + index).toLocaleDateString([], { weekday: 'short' })}</div>)}
                {calendarDays.map(day => {
                  const key = localDateKey(day)
                  const dayItems = calendarEvents.get(key) ?? []
                  const inMonth = day.getMonth() === calendarMonth.getMonth()
                  return <div key={key} className={`calendar-day${inMonth ? '' : ' outside-month'}${key === todayKey ? ' is-today' : ''}`}>
                    <div className="calendar-day-head"><span className="calendar-day-number">{day.getDate()}</span>{dayItems.length > 0 && <span className="calendar-day-count">{dayItems.length}</span>}</div>
                    <div className="calendar-event-list">{dayItems.slice(0, 3).map(item => <button type="button" key={item.id} disabled={!item.projectId} onClick={() => { if (item.projectId) { setSelectedProject(item.projectId); setTaskProjectId(item.projectId); setWorkspaceTab('projects') } }} aria-label={item.projectId ? `Open ${projects.find(project => project.id === item.projectId)?.name ?? 'team'} project space: ${item.title}` : item.title} className={`calendar-event${item.projectId ? ' calendar-team-event' : ''}${item.status === 'completed' ? ' event-done' : ''} cat-event-${item.category ?? 'personal'}`} title={`${item.projectId ? `${projects.find(project => project.id === item.projectId)?.name ?? 'Team'} · ` : ''}${item.title}${item.dueAt ? ` · ${new Date(item.dueAt).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}` : ''}`}><span className="calendar-event-time">{new Date(item.dueAt!).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</span><span className="calendar-event-title">{item.projectId && <strong className="calendar-project-label">{projects.find(project => project.id === item.projectId)?.name ?? 'Team'} · </strong>}{item.title}</span></button>)}</div>
                    {dayItems.length > 3 && <span className="calendar-more">+{dayItems.length - 3} more</span>}
                  </div>
                })}
              </div></div>
              <div className="calendar-footer"><span className="list-footer-mark"><span /> {monthEventCount} {monthEventCount === 1 ? 'responsibility' : 'responsibilities'} this month</span><span>Undated tasks stay in List</span></div>
            </div> : visible.length === 0 ? <div className="empty-state"><div className="empty-orbit"><span /><OrbitIcon size={30} strokeWidth={1.5} /></div><h3>Nothing on the radar.</h3><p>Add a responsibility when you’re ready.<br />You’ve got room to breathe.</p></div> : <div className="task-list">{visible.map(item => {
              const isDone = (item.status ?? 'pending') === 'completed'
              const isOverdue = !isDone && item.dueAt && new Date(item.dueAt).getTime() < Date.now()
              return <article className={`task-row${isDone ? ' is-complete' : ''}`} key={item.id}>
                <button disabled={togglingIds.has(item.id)} className={`task-check${isDone ? ' checked' : ''}`} aria-label={`${isDone ? 'Mark pending' : 'Mark complete'}: ${item.title}`} onClick={() => toggle(item)}>{isDone ? <Check size={15} strokeWidth={2.5} /> : <CircleCheck size={19} strokeWidth={1.6} />}</button>
                <div className="task-info"><div className="task-title-line"><h3 className={isDone ? 'done' : ''}>{item.title}</h3><span className={`priority-dot priority-${item.priority ?? 'medium'}`} title={`${item.priority ?? 'medium'} priority`} /></div>
                  <div className="task-meta"><span className={`category-tag cat-${item.category ?? 'personal'}`}>{item.category ?? 'personal'}</span>{item.projectId && <span className="category-tag project-task-tag">{projects.find(project => project.id === item.projectId)?.name ?? 'Project'}</span>}{item.assignee && <span className="due-label">For {item.assignee}</span>}{item.dueAt ? <span className={`due-label${isOverdue ? ' overdue' : ''}`}>{isOverdue ? <ArrowDownRight size={13} /> : <CalendarDays size={13} />}{formatDueDate(item.dueAt)}</span> : <span className="due-label no-date">No due date</span>}</div>
                </div>
              </article>
            })}</div>}
            {workspaceTab === 'tasks' && <div className="list-footer"><span>{filter === 'all' ? `${visible.length} ${visible.length === 1 ? 'responsibility' : 'responsibilities'}` : `${visible.length} in ${filter}`}</span><span className="list-footer-mark"><span /> sorted by due date</span></div>}
          </div>

          {workspaceTab === 'tasks' && <div className="add-panel panel-card">
            <div className="add-heading"><div className="add-icon"><Plus size={18} /></div><div><p className="section-kicker">GET IT OUT OF YOUR HEAD</p><h2>Add a task<span className="heading-period">.</span></h2></div></div>
            <p className="add-intro">Capture it here. Future-you says thanks.</p>
            <form onSubmit={create}>
              <label className="form-field">What needs doing?<input required maxLength={120} value={title} onChange={e => setTitle(e.target.value)} placeholder="e.g. Finish the lab report" /></label>
              <label className="form-field">Category<select value={category} onChange={e => setCategory(e.target.value as Category)}>{categories.map(c => <option key={c} value={c}>{c[0].toUpperCase() + c.slice(1)}</option>)}</select></label>
              <label className="form-field">Project space<select disabled={selectedProject !== 'all'} value={selectedProject === 'all' ? taskProjectId : selectedProject} onChange={e => setTaskProjectId(e.target.value)}><option value="">Personal / ungrouped</option>{projects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label>
              {(selectedProject !== 'all' || taskProjectId) && <label className="form-field">Assign to <span className="optional-label">optional</span><input maxLength={40} value={assignee} onChange={e => setAssignee(e.target.value)} placeholder="Teammate name" /></label>}
              <label className="form-field">Due date <span className="optional-label">optional</span><input type="datetime-local" value={dueAt} onChange={e => setDueAt(e.target.value)} /></label>
              <label className="form-field">Priority<select value={priority} onChange={e => setPriority(e.target.value as Priority)}><option value="low">Low</option><option value="medium">Medium</option><option value="high">High</option></select></label>
              <button className="submit-button" disabled={busy || !API} type="submit"><Plus size={17} />{busy ? 'Adding…' : 'Add to Orbit'}<ArrowUpRight className="submit-arrow" size={16} /></button>
            </form>
            <p className="form-footnote"><Sparkles size={13} /> One less thing to keep in your head.</p>
          </div>}
        </section>}

        <footer className="page-footer"><span>ORBIT <span className="footer-period">✳</span> CSE 4333</span><span>A calmer way to keep everything moving.</span></footer>
      </div>
    </main>
  </div>
}
