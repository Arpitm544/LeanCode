/** Cue Foundations cue102 · Minimal AI Dev Workspace, adapted to LeanCode's live agent. */
import { useCallback, useEffect, useRef, useState } from 'react'
import { Activity, ArrowRight, ArrowUp, Asterisk, BookOpen, Check, ChevronDown, Circle, Code2, FileCode2, Folder, GitBranch, Globe, History, LayoutGrid, Loader2, LogOut, Menu, Plus, Search, ShieldCheck, Terminal, X, Zap } from 'lucide-react'
import { request, streamEvents } from '../../api'
import type { Action, AgentEvent, Bootstrap, Session } from '../../api'

type ViewId = 'workspace' | 'repositories' | 'pipelines' | 'history' | 'documentation' | 'benchmarks'
const money = (micro = 0) => `$${(micro / 1_000_000).toFixed(micro > 0 && micro < 1000 ? 6 : 4)}`
const count = (value = 0) => value.toLocaleString()
const terminalStatuses = ['completed', 'failed', 'blocked', 'rejected', 'interrupted']
const workflows = [
  { title: 'Fix a bug', desc: 'Trace a failing test and propose the smallest correct fix.', prompt: 'Find the cause of the failing test and propose the smallest fix. Preserve existing behavior.', icon: FileCode2 },
  { title: 'Generate unit tests', desc: 'Cover the important behavior and edge cases in your code.', prompt: 'Inspect this Python repository and add focused unittest coverage for an untested edge case.', icon: Search },
  { title: 'Refactor code', desc: 'Simplify duplicated logic while preserving existing behavior.', prompt: 'Find duplicated logic and propose a small refactor that preserves behavior, with tests.', icon: Code2 },
]
const nav = [
  { id: 'workspace', label: 'Code Copilot', icon: LayoutGrid },
  { id: 'repositories', label: 'Repositories', icon: Folder },
  { id: 'pipelines', label: 'Agent runs', icon: GitBranch },
  { id: 'history', label: 'Build History', icon: History },
  { id: 'documentation', label: 'Documentation', icon: BookOpen },
] as const
const labels = { workspace: 'Code Copilot', repositories: 'Repositories', pipelines: 'Agent runs', history: 'Build History', documentation: 'Documentation', benchmarks: 'Benchmarks' }

export default function DevAgentWorkspace() {
  const [token, setToken] = useState(() => sessionStorage.getItem('leancode-token') || '')
  const [tokenInput, setTokenInput] = useState('')
  const [data, setData] = useState<Bootstrap | null>(null)
  const [session, setSession] = useState<Session | null>(null)
  const [repo, setRepo] = useState('')
  const [task, setTask] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [live, setLive] = useState(false)
  const [tab, setTab] = useState<'activity' | 'changes'>('activity')
  const [view, setView] = useState<ViewId>('workspace')
  const [results, setResults] = useState<Record<string, unknown>[]>([])
  const [reconnecting, setReconnecting] = useState(false)
  const lastEvent = useRef(0)
  const bottom = useRef<HTMLDivElement>(null)
  const taskInput = useRef<HTMLTextAreaElement>(null)
  const navigation = useRef<HTMLElement>(null)
  const [navigationOpen, setNavigationOpen] = useState(false)
  const [filter, setFilter] = useState('')

  const refresh = useCallback(async () => {
    const next = await request<Bootstrap>('/bootstrap', token)
    setData(next)
    setRepo(current => current || next.repositories[0]?.id || '')
    return next
  }, [token])

  useEffect(() => {
    if (!token) return
    refresh().then(next => {
      const saved = localStorage.getItem('leancode-session')
      const current = next.sessions.find(item => item.id === saved) || next.sessions[0]
      if (current) request<Session>(`/sessions/${current.id}`, token).then(next => { setSession(next); setRepo(next.repository) }).catch(e => setError(e.message))
    }).catch(e => { setError(e.message); setData(null) })
  }, [token, refresh])

  const sessionId = session?.id
  useEffect(() => {
    if (!sessionId || !token) return
    localStorage.setItem('leancode-session', sessionId)
    const controller = new AbortController()
    lastEvent.current = 0
    async function connect() {
      while (!controller.signal.aborted) {
        try {
          setReconnecting(false)
          await streamEvents(sessionId!, token, lastEvent.current, controller.signal, event => {
            setLive(true); setReconnecting(false)
            lastEvent.current = Math.max(lastEvent.current, event.id)
            setSession(current => current && current.id === sessionId ? {
              ...current, events: [...current.events.filter(e => e.id !== event.id), event].sort((a, b) => a.id - b.id),
            } : current)
            if (['status', 'action', 'usage', 'model'].includes(event.kind)) {
              request<Session>(`/sessions/${sessionId}`, token).then(next => {
                if (!controller.signal.aborted) setSession(next)
              }).catch(e => { if (!controller.signal.aborted) setError(e.message) })
              refresh().catch(() => {})
            }
          })
          const latest = await request<Session>(`/sessions/${sessionId}`, token)
          if (terminalStatuses.includes(latest.status)) { setLive(false); return }
        } catch { if (controller.signal.aborted) return; setLive(false); setReconnecting(true) }
        if (!controller.signal.aborted) await new Promise(resolve => setTimeout(resolve, 2000))
      }
    }
    connect()
    return () => { controller.abort(); setLive(false) }
  }, [sessionId, session?.status, token, refresh])

  useEffect(() => {
    const panel = bottom.current?.closest('.dw-scrollable-area')
    if (panel) {
      const review = panel.querySelector('.dw-approval')
      panel.scrollTop = review ? panel.scrollTop + review.getBoundingClientRect().top - panel.getBoundingClientRect().top - 16 : panel.scrollHeight
    }
  }, [session?.id, session?.status, session?.events.length])

  useEffect(() => {
    const input = taskInput.current
    if (input) { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, 180) + 'px' }
  }, [task])

  useEffect(() => {
    if (!navigationOpen) return
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    navigation.current?.querySelector<HTMLButtonElement>('.dw-close-nav')?.focus()
    const close = (event: KeyboardEvent) => { if (event.key === 'Escape') setNavigationOpen(false) }
    document.addEventListener('keydown', close)
    return () => { document.removeEventListener('keydown', close); previousFocus?.focus() }
  }, [navigationOpen])

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!data || busy || !repo || task.trim().length < 5 || inProgress || repositoryBusy) return
    setBusy(true); setError('')
    try {
      const next = await request<Session>('/sessions', token, { method: 'POST', body: JSON.stringify({ repository: repo, task, mode: 'optimized', request_id: crypto.randomUUID() }) })
      setSession(next); setTask(''); setTab('activity'); await refresh()
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  async function decide(actionId: string, approve: boolean) {
    setBusy(true); setError('')
    try {
      await request(`/sessions/${session!.id}/actions/${actionId}/decision`, token, { method: 'POST', body: JSON.stringify({ approve }) })
      setSession(await request<Session>(`/sessions/${session!.id}`, token))
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  const repository = data?.repositories.find(item => item.id === repo)
  const pending = session?.actions.filter(action => action.status === 'pending') || []
  const inProgress = !!session && !terminalStatuses.includes(session.status)
  const repositoryBusy = !!data?.sessions.some(item => item.repository === repo && !terminalStatuses.includes(item.status) && item.id !== session?.id)
  const usage = session?.state
  const budget = data?.user
  const available = Math.max(0, (budget?.limit_micro || 0) - (budget?.spent_micro || 0) - (budget?.reserved_micro || 0))
  const sessions = (data?.sessions || []).filter(item => `${item.task} ${item.repository}`.toLowerCase().includes(filter.toLowerCase()))
  const repositories = (data?.repositories || []).filter(item => item.name.toLowerCase().includes(filter.toLowerCase()))

  async function navigate(next: ViewId) {
    setView(next); setNavigationOpen(false); setFilter('')
    if (next === 'benchmarks' && data) {
      try { setResults(await request('/benchmarks', token)) } catch (e) { setError((e as Error).message) }
    }
  }

  function newChat() {
    setSession(null); setTask(''); setError(''); setTab('activity')
    localStorage.removeItem('leancode-session')
    if (data) void refresh().catch(e => setError((e as Error).message))
    void navigate('workspace')
  }

  async function openSession(id: string) {
    try {
      const next = await request<Session>(`/sessions/${id}`, token)
      setSession(next); setRepo(next.repository); setError(''); setTab('activity')
      void navigate('workspace')
    } catch (e) { setError((e as Error).message) }
  }

  function chooseRepository(id: string) {
    const active = data?.sessions.find(item => item.repository === id && !terminalStatuses.includes(item.status))
    if (active) { void openSession(active.id); return }
    newChat(); setRepo(id)
  }

  async function resume() {
    if (!session) return
    setBusy(true); setError('')
    try {
      setSession(await request<Session>(`/sessions/${session.id}/resume`, token, { method: 'POST' }))
      await refresh()
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  function logout() {
    sessionStorage.removeItem('leancode-token')
    setToken(''); setData(null); setSession(null); setRepo(''); setError('')
    void navigate('workspace')
  }

  return <div className={`dw-scope ${session ? 'dw-chat-active' : ''} ${navigationOpen ? 'dw-nav-open' : ''}`}>
    {navigationOpen && <button className="dw-nav-backdrop" tabIndex={-1} aria-label="Close navigation" onClick={() => setNavigationOpen(false)}/>}
    <aside ref={navigation} className="dw-sidebar" aria-label="Workspace navigation">
      <div className="dw-sidebar-header"><a className="dw-logo-box" href="#" aria-label="LeanCode home" onClick={e => { e.preventDefault(); void navigate('workspace') }}>LC</a><div className="dw-header-actions"><button aria-label="Search session history" onClick={() => void navigate('history')}><Search/></button><button className="dw-close-nav" aria-label="Close navigation" onClick={() => setNavigationOpen(false)}><X/></button></div></div>
      <button className="dw-company-name" onClick={() => void navigate('repositories')}>LeanCode Studio<ChevronDown size={14}/></button>
      <button className="dw-btn-create" onClick={newChat}><Plus size={16}/>New chat</button>
      <nav className="dw-nav-list">{nav.map(item => <div key={item.id}><button className={`dw-nav-item ${view === item.id ? 'dw-active' : ''}`} onClick={() => void navigate(item.id)}><item.icon/>{item.label}</button>{item.id === 'pipelines' && <div className="dw-nav-sublist"><button className={`dw-nav-subitem ${view === 'benchmarks' ? 'dw-active' : ''}`} onClick={() => void navigate('benchmarks')}>Benchmarks</button></div>}</div>)}</nav>
      <div className="dw-recent"><span>Recent sessions</span>{data?.sessions.slice(0, 5).map(item => <button key={item.id} className={item.id === session?.id ? 'dw-recent-active' : ''} onClick={() => void openSession(item.id)}><span className={`dw-status-dot dw-${item.status}`}/><span>{item.task}</span></button>)}{!data?.sessions.length && <p>Your work will appear here.</p>}</div>
      <div className="dw-sidebar-footer"><div className="dw-profile"><span className="dw-profile-avatar">{(data?.user.id || 'L').slice(0, 1).toUpperCase()}</span><div>{data?.user.id || 'Local workspace'}<small>{money(available)} available budget</small></div></div><button className="dw-nav-item dw-text-danger" disabled={!data} onClick={logout}><LogOut/>Disconnect</button></div>
    </aside>

    <main className="dw-main-content" inert={navigationOpen}>
      <div className="dw-workspace-bar"><div><button className="dw-open-nav" aria-label="Open navigation" aria-expanded={navigationOpen} onClick={() => setNavigationOpen(true)}><Menu size={18}/></button><span>{labels[view]}</span></div><span className="dw-connection"><span className={`dw-status-dot ${data ? 'dw-completed' : ''}`}/>{data ? 'Backend connected' : 'Not connected'}</span></div>
      {error && <div role="alert" className="dw-error"><span>{error}</span><button aria-label="Dismiss error" onClick={() => setError('')}><X size={15}/></button></div>}

      {view === 'workspace' ? <div className="dw-app-view dw-active-view">
        <div className="dw-scrollable-area">
          {!session ? <>
            <div className="dw-landing-view dw-center-container"><Asterisk className="dw-main-icon" strokeWidth={1.4}/><h1 className="dw-title">Welcome to LeanCode</h1><p className="dw-subtitle">Your coding, debugging, and testing. A little more thoughtful.</p></div>
            {!data && <section className="dw-connect dw-center-container"><div><ShieldCheck size={18}/><h2>Connect your local workspace</h2></div><p>Use the access token in <code>.leancode/access-token</code>. Model API keys stay in your backend.</p><form onSubmit={e => { e.preventDefault(); sessionStorage.setItem('leancode-token', tokenInput); setToken(tokenInput); setError('') }}><input aria-label="Local access token" type="password" autoComplete="off" value={tokenInput} onChange={e => setTokenInput(e.target.value)} placeholder="Local access token" required/><button className="dw-btn-create dw-btn-create-inline">Connect<ArrowRight size={14}/></button></form></section>}
            <div className="dw-context-pills" aria-label="Configured integrations">{(data?.integrations || [{ name: 'Bifrost', configured: false }, { name: 'Tavily', configured: false }, { name: 'Local inference', configured: false }]).map(item => <button key={item.name} className={`dw-pill-dashed ${item.configured ? 'dw-selected' : ''}`} title={item.configured ? 'Configured; availability is checked when used' : 'Not configured'} onClick={() => void navigate('documentation')}>{item.name}<span className={`dw-status-dot ${item.configured ? 'dw-completed' : ''}`}/></button>)}</div>
            <section className="dw-workflows-section"><h2 className="dw-workflows-header"><Zap size={14}/>Recommended workflows</h2><div className="dw-workflow-grid">{workflows.map(workflow => <button key={workflow.title} className="dw-workflow-card" disabled={!data || busy || repositoryBusy} onClick={() => { setTask(workflow.prompt); taskInput.current?.focus() }}><span className="dw-card-icon"><workflow.icon/></span><span><h3>{workflow.title}</h3><p>{workflow.desc}</p></span></button>)}</div></section>
          </> : <div className="dw-chat-history-view">
            <div className="dw-thread-meta"><span><Folder size={13}/>{session.repository}</span><span className={`dw-badge dw-state-${session.status} execution-status`}>{session.status.replaceAll('_', ' ')}</span></div>
            <div className="dw-chat-message dw-user"><div className="dw-message-content"><p>{session.task}</p></div></div>
            <div className="dw-chat-message dw-ai"><span className="dw-message-avatar dw-ai-avatar">LC</span><div className="dw-message-content">
              {pending.map(action => <Approval key={action.id} action={action} busy={busy} decide={decide}/>)}
              {inProgress && !pending.length && <p className="dw-thinking-pulse"><Loader2 className="dw-loader" size={13}/>Working on your task…</p>}
              <div className="dw-thread-tabs" role="tablist" aria-label="Execution views"><button role="tab" aria-selected={tab === 'activity'} onClick={() => setTab('activity')}><Terminal size={13}/>Activity</button><button role="tab" aria-selected={tab === 'changes'} onClick={() => setTab('changes')}><FileCode2 size={13}/>Changes {session.actions.filter(action => action.kind === 'patch').length || ''}</button></div>
              {tab === 'activity' ? <div className="dw-reasoning-block" role="log" aria-live="polite">{session.events.map(event => <EventRow key={event.id} event={event}/>)}</div> : <div className="dw-changes">{session.actions.filter(action => action.kind === 'patch').map(action => <section key={action.id}><div className="dw-change-title"><FileCode2 size={13}/>Proposed patch<span>{action.status}</span></div><Diff text={action.payload.diff || ''}/></section>)}{!session.actions.some(action => action.kind === 'patch') && <p className="dw-muted">No proposed patches yet.</p>}</div>}
              {['blocked', 'interrupted', 'failed'].includes(session.status) && <button className="dw-pill-btn dw-btn-gray dw-resume" disabled={busy} onClick={() => void resume()}>Resume saved session<ArrowRight size={13}/></button>}
              <div className="dw-thread-footer"><span className={`dw-status-dot ${live ? 'dw-completed' : ''}`}/>{reconnecting ? 'Reconnecting…' : live ? 'Live session' : 'Saved locally'}</div>
            </div></div><div ref={bottom}/>
          </div>}
        </div>

        <div className="dw-chat-input-wrapper"><div className="dw-center-container">
          {repositoryBusy && <p className="dw-composer-hint">This repository has a task awaiting attention. Open it from Agent runs or Build History.</p>}
          <form className="dw-chat-box" onSubmit={submit}>
            <div className="dw-chat-top-bar"><label className="dw-repo-select"><Folder size={14}/><span className="sr-only">Repository</span><select aria-label="Repository" value={repo} disabled={!data || inProgress} onChange={e => setRepo(e.target.value)}>{!data?.repositories.length && <option value="">Select repository</option>}{data?.repositories.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></label><span className="dw-policy-label"><ShieldCheck size={13}/>{repository?.confidential ? 'Local models only' : 'Approval required'}</span><span className="dw-model-select" title="Model selection is controlled by backend policy"><Asterisk size={15}/>{usage?.model || 'Policy-selected model'}</span></div>
            <textarea ref={taskInput} className="dw-textarea" aria-label="Coding task" value={task} onChange={e => setTask(e.target.value)} onKeyDown={e => { if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) { e.preventDefault(); e.currentTarget.form?.requestSubmit() } }} placeholder="Ask LeanCode to fix a bug, write tests, or improve your code…" spellCheck={false} rows={2} minLength={5} maxLength={12000} required disabled={!data || busy}/>
            <div className="dw-chat-bottom-bar"><button className="dw-pill-btn dw-btn-gray" type="button" onClick={() => void navigate('repositories')}><Folder size={14}/>Repository context</button><button className="dw-pill-btn dw-btn-blue" type="button" onClick={() => void navigate('documentation')}><Globe size={14}/>Documentation</button><button className={`dw-btn-submit ${data && repo && task.trim().length >= 5 && !inProgress && !repositoryBusy ? 'dw-active' : ''}`} aria-label="Run agent" title="Run agent · Enter to send, Shift+Enter for a new line" disabled={!data || !repo || task.trim().length < 5 || busy || inProgress || repositoryBusy}>{busy ? <Loader2 className="dw-loader" size={16}/> : <ArrowUp size={16}/>}</button></div>
          </form>
          <div className="dw-usage-strip"><span><Zap size={11}/>{count((usage?.input_tokens || 0) + (usage?.output_tokens || 0))} tokens<span className="dw-usage-divider">·</span>{money(usage?.cost_micro)} reported cost</span><span>{money(available)} available<span className="dw-usage-divider">·</span>{money(budget?.reserved_micro)} reserved</span></div>
          <p className="dw-composer-note">Review every patch and command before execution. Enter to send · Shift + Enter for a new line.</p>
        </div></div>
      </div> : <div className="dw-app-view dw-active-view">
        <div className="dw-view-header"><h1 className="dw-view-title">{labels[view]}</h1>{['repositories', 'history', 'pipelines'].includes(view) && <label className="dw-search-bar"><Search/><input autoFocus={view === 'history'} aria-label={`Search ${labels[view].toLowerCase()}`} placeholder={`Search ${labels[view].toLowerCase()}…`} value={filter} onChange={e => setFilter(e.target.value)}/></label>}</div>
        <div className="dw-view-content">
          {view === 'repositories' && <><p className="dw-view-intro">Registered local repositories. Select one to start a task or return to its active session.</p><div className="dw-repo-grid">{repositories.map(item => <button className="dw-repo-card" key={item.id} onClick={() => chooseRepository(item.id)}><span className="dw-repo-title"><Folder/>{item.name}</span><span className="dw-repo-desc">{item.confidential ? 'Confidential code is processed only by allowed local models. External documentation search is disabled.' : 'Public workspace. Cloud models and approved documentation topics are available under your budget.'}</span><span className="dw-repo-meta"><span><ShieldCheck size={12}/>{item.confidential ? 'Local only' : 'Cloud permitted'}</span><span>Open workspace<ArrowRight size={12}/></span></span></button>)}</div>{!repositories.length && <Empty icon={Folder} title="No matching repositories" text="Register repositories in your backend configuration, or adjust your search."/>}</>}
          {view === 'pipelines' && <><p className="dw-view-intro">Actual agent sessions and their reviewed development actions.</p><div className="dw-pipeline-list">{sessions.filter(item => !terminalStatuses.includes(item.status)).map(item => <button className="dw-pipeline-item" key={item.id} onClick={() => void openSession(item.id)}><span className="dw-pipe-left"><span className={`dw-status-icon ${item.status === 'awaiting_approval' ? 'dw-status-review' : 'dw-status-running'}`}>{item.status === 'awaiting_approval' ? <ShieldCheck size={16}/> : <Loader2 size={16}/>}</span><span className="dw-pipe-details"><h2>{item.task}</h2><span><Folder size={12}/>{item.repository}</span></span></span><span className="dw-pipe-right"><span className="dw-pipe-status">{item.status.replaceAll('_', ' ')}</span><span>Open session<ArrowRight size={12}/></span></span></button>)}</div>{!sessions.some(item => !terminalStatuses.includes(item.status)) && <Empty icon={GitBranch} title="No active runs" text="Start a task in Code Copilot. Its progress and pending approvals will appear here."/>}</>}
          {view === 'history' && (sessions.length ? <div className="dw-history-table-wrapper"><table className="dw-history-table"><thead><tr><th>Task</th><th>Repository</th><th>Status</th><th>Created</th><th><span className="sr-only">Open</span></th></tr></thead><tbody>{sessions.map(item => <tr key={item.id}><td>{item.task}</td><td>{item.repository}</td><td><span className={`dw-badge dw-state-${item.status}`}>{item.status.replaceAll('_', ' ')}</span></td><td className="dw-mono">{item.created_at}</td><td><button className="dw-text-button" onClick={() => void openSession(item.id)}>Open<ArrowRight size={12}/></button></td></tr>)}</tbody></table></div> : <Empty icon={History} title="A clean slate" text="Your saved sessions will appear here. Try another search if you already have work in progress."/>)}
          {view === 'documentation' && <><p className="dw-view-intro">Public documentation and the policies that govern your workspace. Opening this page makes no paid search requests.</p><div className="dw-doc-grid"><a className="dw-doc-folder" href="https://docs.python.org/3/library/unittest.html" target="_blank" rel="noreferrer"><BookOpen/><span>Python unittest</span><span className="dw-doc-meta">Approved public documentation topic</span></a><a className="dw-doc-folder" href="https://docs.getbifrost.ai/quickstart/gateway/setting-up" target="_blank" rel="noreferrer"><GitBranch/><span>Bifrost gateway</span><span className="dw-doc-meta">Model routing and provider setup</span></a><a className="dw-doc-folder" href="https://docs.tavily.com/documentation/quickstart" target="_blank" rel="noreferrer"><Globe/><span>Tavily search</span><span className="dw-doc-meta">Public documentation retrieval</span></a></div><section className="dw-policy-card"><h2><ShieldCheck size={17}/>Your workspace policies</h2><p>Confidential repositories use local inference only. Every write, shell command, and Git operation requires an exact approval. The backend reserves request costs before dispatch, and unknown charges remain reserved.</p><p>Documentation searches use approved public topics. They are disabled for confidential code.</p><div className="dw-integration-list">{data?.integrations.map(item => <div key={item.name}><span>{item.name}</span><span className="dw-muted">{item.configured ? 'Configured · availability checked when used' : 'Not configured'}</span></div>)}</div></section></>}
          {view === 'benchmarks' && (results.length ? <div className="dw-history-table-wrapper"><table className="dw-history-table"><thead><tr><th>Task</th><th>Variant</th><th>Outcome</th><th>Tokens</th><th>Reported cost</th></tr></thead><tbody>{results.map((row, index) => <tr key={index}><td>{String(row.task)}</td><td>{String(row.variant)}</td><td>{String(row.outcome)}</td><td>{String(row.tokens ?? 'Unknown')}</td><td>{money(Number(row.cost_micro || 0))}</td></tr>)}</tbody></table></div> : <Empty icon={Activity} title="Let the results do the talking." text="No live benchmark runs recorded. Compare matched tasks to measure correctness, token usage, and cost."/>)}
        </div>
      </div>}
    </main>
  </div>
}

function Approval({ action, busy, decide }: { action: Action; busy: boolean; decide: (id: string, approve: boolean) => Promise<void> }) {
  return <section className="dw-approval"><header><ShieldCheck size={17}/><div><h2>Review proposed {action.kind}</h2><p>{action.payload.reason || 'Approve this exact action before it executes.'}</p></div><span className="dw-badge dw-state-awaiting_approval">Your review</span></header>{action.kind === 'patch' ? <Diff text={action.payload.diff || ''}/> : <pre className="dw-command">{JSON.stringify(action.payload.command)}</pre>}<footer><span>Nothing executes without your approval.</span><button className="dw-pill-btn dw-btn-gray" disabled={busy} onClick={() => void decide(action.id, false)}><X size={13}/>Reject</button><button className="dw-approve-button" disabled={busy} onClick={() => void decide(action.id, true)}><Check size={13}/>Approve {action.kind}</button></footer></section>
}

function EventRow({ event }: { event: AgentEvent }) {
  return <div className={`dw-event dw-event-${event.kind}`}><span className="dw-event-icon">{event.kind === 'error' ? <X size={12}/> : event.kind === 'action' ? <ShieldCheck size={12}/> : <Circle size={7}/>}</span><div><p>{String(event.data.message || event.data.reason || event.kind)}</p>{event.data.output != null && String(event.data.output) && <details className="dw-tool-output"><summary>Tool output</summary><pre>{String(event.data.output)}</pre></details>}</div><time>{event.created_at?.slice(11, 19)}</time></div>
}

function Diff({ text }: { text: string }) {
  return <pre className="dw-diff diff" aria-label="Patch diff">{text.split('\n').map((line, index) => <span key={index} className={line.startsWith('+') ? 'added' : line.startsWith('-') ? 'removed' : line.startsWith('@@') ? 'hunk' : ''}>{line || ' '}</span>)}</pre>
}

function Empty({ icon: Icon, title, text }: { icon: typeof Activity; title: string; text: string }) {
  return <section className="dw-empty"><Icon size={27} strokeWidth={1.4}/><h2>{title}</h2><p>{text}</p></section>
}
