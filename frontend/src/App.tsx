import { useCallback, useEffect, useRef, useState } from 'react'
import { Activity, ArrowDownRight, ArrowRight, Check, CheckCircle2, ChevronRight, Circle, Code2, Command, FileCode2, GitBranch, History, Layers, Loader2, LockKeyhole, Play, Radio, ShieldCheck, Terminal, Unplug, Wallet, X, Zap } from 'lucide-react'
import { request, streamEvents } from './api'
import type { AgentEvent, Bootstrap, Session } from './api'

const money = (micro = 0) => `$${(micro / 1_000_000).toFixed(4)}`
const count = (n = 0) => n.toLocaleString()
const terminalStatuses = ['completed', 'failed', 'blocked', 'rejected', 'interrupted']

export default function App() {
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
  const [view, setView] = useState<'workspace' | 'benchmarks'>('workspace')
  const [results, setResults] = useState<Record<string, unknown>[]>([])
  const [reconnecting, setReconnecting] = useState(false)
  const lastEvent = useRef(0)
  const bottom = useRef<HTMLDivElement>(null)

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
      if (current) request<Session>(`/sessions/${current.id}`, token).then(setSession).catch(e => setError(e.message))
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
        } catch { if (controller.signal.aborted) return; setLive(false); setReconnecting(true) }
        if (!controller.signal.aborted) await new Promise(resolve => setTimeout(resolve, 2000))
      }
    }
    connect()
    return () => { controller.abort(); setLive(false) }
  }, [sessionId, token, refresh])

  useEffect(() => { bottom.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' }) }, [session?.events.length])

  async function submit(e: React.FormEvent) {
    e.preventDefault(); setBusy(true); setError('')
    try {
      const next = await request<Session>('/sessions', token, { method: 'POST', body: JSON.stringify({ repository: repo, task, mode: 'optimized', request_id: crypto.randomUUID() }) })
      setSession(next); setTab('activity'); await refresh()
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  async function decide(actionId: string, approve: boolean) {
    setBusy(true); setError('')
    try {
      await request(`/sessions/${session!.id}/actions/${actionId}/decision`, token, { method: 'POST', body: JSON.stringify({ approve }) })
      setSession(await request<Session>(`/sessions/${session!.id}`, token))
    } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
  }

  const repository = data?.repositories.find(item => item.id === (session?.repository || repo))
  const pending = session?.actions.filter(action => action.status === 'pending') || []
  const inProgress = !!session && !terminalStatuses.includes(session.status)
  const usage = session?.state
  const budget = data?.user
  const available = Math.max(0, (budget?.limit_micro || 0) - (budget?.spent_micro || 0) - (budget?.reserved_micro || 0))

  return <div className="app-shell">
    <aside className="sidebar">
      <a className="brand" href="#" aria-label="LeanCode home"><span className="brand-mark"><Layers size={20}/></span>lean<span>code</span><span className="beta">BETA</span></a>
      <div className="workspace-label">YOUR WORKSPACE</div>
      <button className={`nav-item ${view === 'workspace' ? 'active' : ''}`} onClick={() => setView('workspace')}><Terminal size={17}/> Agent workspace <span className="keycap">1</span></button>
      <button className={`nav-item ${view === 'benchmarks' ? 'active' : ''}`} onClick={async () => {
        setView('benchmarks'); if (data) try { setResults(await request('/benchmarks', token)) } catch (e) { setError((e as Error).message) }
      }}><Activity size={17}/> Benchmarks</button>
      <div className="sidebar-divider"/>
      <div className="workspace-label history-label">RECENT SESSIONS <History size={13}/></div>
      <div className="session-list">{data?.sessions.length ? data.sessions.map(item => <button key={item.id} className={`session-link ${item.id === session?.id ? 'selected' : ''}`} onClick={async () => {
        try { setSession(await request<Session>(`/sessions/${item.id}`, token)); setView('workspace') } catch (e) { setError((e as Error).message) }
      }}><span className={`status-dot ${item.status}`}/><span>{item.task}</span></button>) : <p className="sidebar-empty">Your sessions will appear here.</p>}</div>
      <div className="sidebar-bottom"><div className="local-badge"><ShieldCheck size={16}/><div>Local workspace<small>Your code. Your control.</small></div><span className="status-dot completed"/></div><div className="profile"><span className="avatar">L</span><div>Local developer<small>Personal workspace</small></div>{data && <button className="icon-button" title="Disconnect workspace" onClick={() => { sessionStorage.removeItem('leancode-token'); setToken(''); setData(null); setSession(null) }}><Unplug size={16}/></button>}</div></div>
    </aside>

    <main className="main">
      <header className="topbar"><div><span className="muted">Workspace</span><ChevronRight size={14}/><span>{view === 'workspace' ? 'Agent workspace' : 'Benchmarks'}</span></div><span className="connection"><span className={`status-dot ${data ? 'completed' : ''}`}/>{data ? 'Backend connected' : 'Not connected'}</span></header>
      <div className="page-content">
        <div className="page-heading"><div><div className="eyebrow"><Zap size={13}/> LESS CONTEXT. MORE PROGRESS.</div><h1>{view === 'workspace' ? 'Every token counts.' : 'Evidence, not estimates.'}</h1><p>{view === 'workspace' ? 'Real code changes. Measured efficiency. You stay in control.' : 'Compare correctness, tokens, and cost across matched coding tasks.'}</p></div><span className="version">v0.1 <span>EARLY ACCESS</span></span></div>

        {error && <div role="alert" className="error-banner"><span>{error}</span><button className="icon-button" aria-label="Dismiss error" onClick={() => setError('')}><X size={16}/></button></div>}

        {!data && <section className="connect-card"><LockKeyhole size={22}/><div><h2>Connect your local workspace</h2><p>Enter the access token from <code>.leancode/access-token</code> or your backend environment.</p><form onSubmit={e => { e.preventDefault(); sessionStorage.setItem('leancode-token', tokenInput); setToken(tokenInput); setError('') }}><input aria-label="Local access token" type="password" autoComplete="off" value={tokenInput} onChange={e => setTokenInput(e.target.value)} placeholder="Local access token" required/><button className="primary-button">Connect <ArrowRight size={15}/></button></form></div></section>}

        <div className="metrics-grid">
          <Metric label="SESSION TOKENS" value={count((usage?.input_tokens || 0) + (usage?.output_tokens || 0))} detail={`${count(usage?.input_tokens)} input · ${count(usage?.output_tokens)} output`} icon={<Zap size={17}/>} accent/>
          <Metric label="SESSION COST" value={money(usage?.cost_micro)} detail="Reported usage, including retries" icon={<Wallet size={17}/>}/>
          <Metric label="AVAILABLE BUDGET" value={money(available)} detail={`${money(budget?.reserved_micro)} reserved for requests`} icon={<ShieldCheck size={17}/>}/>
          <Metric label="ACTIVE MODEL" value={usage?.model || 'Not started'} detail={repository?.confidential ? 'Confidential · local models only' : 'Policy-controlled model routing'} icon={<Layers size={17}/>} small/>
        </div>

        {view === 'workspace' ? <>
          <div className="work-grid"><div className="work-main">
            <section className="panel task-panel"><div className="panel-heading"><h2><Command size={17}/> What are we building?</h2><span className="subtle-label">NEW TASK</span></div>
              <form onSubmit={submit}><label className="sr-only" htmlFor="task">Coding task</label><textarea id="task" value={task} onChange={e => setTask(e.target.value)} placeholder="Describe a bug to fix or a change to make…" required minLength={5} maxLength={12000} disabled={!data || busy}/><div className="task-footer"><div className="repo-select"><GitBranch size={14}/><select aria-label="Repository" value={repo} onChange={e => setRepo(e.target.value)} disabled={!data || inProgress}>{!data?.repositories.length && <option value="">No repository configured</option>}{data?.repositories.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}</select></div><button className="primary-button" disabled={!data || !repo || task.trim().length < 5 || busy || inProgress}>{busy ? <Loader2 className="spin" size={15}/> : <Play size={14}/>} Run agent</button></div></form>
            </section>

            <section className="panel execution-panel"><div className="execution-tabs"><div role="tablist" aria-label="Execution views"><button role="tab" aria-selected={tab === 'activity'} className={tab === 'activity' ? 'active' : ''} onClick={() => setTab('activity')}><Terminal size={15}/> Activity</button><button role="tab" aria-selected={tab === 'changes'} className={tab === 'changes' ? 'active' : ''} onClick={() => setTab('changes')}><FileCode2 size={15}/> Changes {session?.actions.filter(a => a.kind === 'patch').length || ''}</button></div><span className="execution-status"><span className={`status-dot ${session?.status || ''}`}/>{session ? session.status.replaceAll('_', ' ') : 'Ready'}</span></div>
              <div className="activity-body" role="tabpanel" aria-live="polite">
                {tab === 'activity' ? session?.events.length ? <><div className="run-title"><Code2 size={16}/><span>{session.task}</span></div>{session.events.map(event => <EventRow key={event.id} event={event}/>)}<div ref={bottom}/></> : <div className="empty-state"><div className="empty-icon"><Terminal size={25}/></div><h3>A little context. A lot of capability.</h3><p>Give the agent a task. Follow its progress,<br/>review the changes, and verify the result.</p><div className="workflow"><span>Inspect</span><ChevronRight size={12}/><span>Review</span><ChevronRight size={12}/><span>Verify</span></div></div> : session?.actions.some(a => a.kind === 'patch') ? session.actions.filter(a => a.kind === 'patch').map(action => <div className="change" key={action.id}><div className="change-heading"><FileCode2 size={14}/> Proposed patch <span>{action.status}</span></div><Diff text={action.payload.diff || ''}/></div>) : <div className="empty-state"><FileCode2 size={28}/><h3>No changes yet</h3><p>Proposed patches will appear here before execution.</p></div>}
              </div><div className="execution-footer"><span><Radio size={12}/>{reconnecting ? 'Reconnecting…' : live ? 'Live session' : 'Session events persisted locally'}</span><span>Approval before execution <ShieldCheck size={12}/></span></div>
            </section>

            {pending.map(action => <section className="panel approval-panel" key={action.id}><div className="approval-heading"><span className="approval-icon"><ShieldCheck size={19}/></span><div><h2>Your approval is needed</h2><p>{action.payload.reason || `Review this ${action.kind} before it runs.`}</p></div><span className="pill amber">PAUSED</span></div>{action.kind === 'patch' ? <Diff text={action.payload.diff || ''}/> : <pre className="command-preview">{JSON.stringify(action.payload.command)}</pre>}<div className="approval-footer"><span>Approval applies to this exact action only.</span><button className="secondary-button" disabled={busy} onClick={() => decide(action.id, false)}><X size={14}/> Reject</button><button className="primary-button" disabled={busy} onClick={() => decide(action.id, true)}><Check size={15}/> Approve {action.kind}</button></div></section>)}

            {session && ['blocked', 'interrupted', 'failed'].includes(session.status) && <button className="secondary-button resume-button" disabled={busy} onClick={async () => {
              setBusy(true); try { setSession(await request<Session>(`/sessions/${session.id}/resume`, token, { method: 'POST' })); await refresh() } catch (e) { setError((e as Error).message) } finally { setBusy(false) }
            }}>Resume saved session <ArrowRight size={14}/></button>}
          </div>

          <aside className="details-column"><section className="panel policy-panel"><div className="panel-heading"><h2><ShieldCheck size={17}/> Guardrails on</h2><span className="status-dot completed"/></div><div className="guardrail"><LockKeyhole size={17}/><div><h3>Privacy comes first</h3><p>{repository?.confidential ? 'This repository stays with local models.' : 'Repository policy controls every model route.'}</p></div></div><div className="guardrail"><CheckCircle2 size={17}/><div><h3>You approve the action</h3><p>Review patches and commands before anything runs.</p></div></div><div className="guardrail"><Wallet size={17}/><div><h3>A budget with boundaries</h3><p>Request costs are reserved before model calls.</p></div></div><div className="guardrail"><GitBranch size={17}/><div><h3>Built to keep going</h3><p>Allowed failover routes preserve session progress.</p></div></div></section>
            <section className="panel integrations-panel"><div className="panel-heading"><h2>Connections</h2><span className="subtle-label">CONFIGURATION</span></div>{(data?.integrations || [{ name: 'Bifrost', configured: false, detail: 'Connect backend to inspect' }, { name: 'Ollama', configured: false, detail: 'Local model inference' }, { name: 'Tavily', configured: false, detail: 'Public documentation search' }]).map(item => <div className="integration" key={item.name}><span className="integration-logo">{item.name.charAt(0)}</span><div><h3>{item.name}</h3><p>{item.detail}</p></div><span className={`status-dot ${item.configured ? 'completed' : ''}`} title={item.configured ? 'Configured, availability not yet verified' : 'Not configured'}/></div>)}</section>
            <div className="efficiency-note"><ArrowDownRight size={18}/><h3>Efficiency you can verify.</h3><p>Token savings appear in benchmarks after matched runs. No guessed percentages.</p></div>
          </aside></div>
        </> : <section className="panel benchmark-panel"><div className="panel-heading"><h2><Activity size={17}/> Matched task results</h2><span className="subtle-label">ACTUAL RUNS ONLY</span></div>{results.length ? <div className="table-scroll"><table><thead><tr><th>Task</th><th>Variant</th><th>Outcome</th><th>Tokens</th><th>Cost</th></tr></thead><tbody>{results.map((row, index) => <tr key={index}><td>{String(row.task)}</td><td>{String(row.variant)}</td><td>{String(row.outcome)}</td><td>{String(row.tokens ?? 'Unknown')}</td><td>{money(Number(row.cost_micro || 0))}</td></tr>)}</tbody></table></div> : <div className="empty-state"><Activity size={30}/><h3>Let the results do the talking.</h3><p>No benchmark runs recorded. Run the evaluation suite<br/>to compare correctness, token usage, and cost.</p></div>}</section>}
        <footer className="page-footer"><span>LEAN CODE. CLEAR EVIDENCE.</span><span>Built with Bifrost <span className="footer-dot">·</span> Documentation by Tavily</span></footer>
      </div>
    </main>
  </div>
}

function Metric({ label, value, detail, icon, accent = false, small = false }: { label: string; value: string; detail: string; icon: React.ReactNode; accent?: boolean; small?: boolean }) {
  return <section className={`metric ${accent ? 'accent' : ''}`}><div className="metric-label">{label}<span>{icon}</span></div><div className={`metric-value ${small ? 'model-value' : ''}`}>{value}</div><p>{detail}</p></section>
}

function EventRow({ event }: { event: AgentEvent }) {
  const text = String(event.data.message || event.data.reason || event.kind)
  return <div className={`event-row event-${event.kind}`}><span className="event-time">{event.created_at?.slice(11, 19) || '—'}</span><span className="event-icon">{event.kind === 'error' ? <X size={13}/> : event.kind === 'action' ? <ShieldCheck size={13}/> : event.kind === 'model' ? <Layers size={13}/> : <Circle size={8}/>}</span><div><p>{text}</p>{event.data.output != null && <pre>{String(event.data.output)}</pre>}</div></div>
}

function Diff({ text }: { text: string }) {
  return <pre className="diff" aria-label="Patch diff">{text.split('\n').map((line, index) => <span key={index} className={line.startsWith('+') ? 'added' : line.startsWith('-') ? 'removed' : line.startsWith('@@') ? 'hunk' : ''}>{line || ' '}<br/></span>)}</pre>
}
