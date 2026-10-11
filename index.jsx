import { useEffect, useState } from 'react'

const CSS = `
  * { box-sizing: border-box; }
  body { margin: 0; }
  .so {
    --so-accent: #a9eb3d;
    --so-heading: #a9eb3d;
    min-height: 100%;
    padding: clamp(20px, 4vw, 52px);
    background: radial-gradient(circle at 50% 5%, #a9eb3d12, transparent 38%), var(--bg);
    color: var(--text);
    font-family: var(--font);
  }
  :root[data-theme="light"] .so { --so-heading: #557b08; }
  .so-wrap { max-width: 920px; margin: auto; }
  .so-top {
    display: flex; justify-content: space-between; align-items: center; gap: 16px;
    padding-bottom: 20px; border-bottom: 1px solid var(--border);
  }
  .so-logo { font-size: 20px; font-weight: 900; letter-spacing: -.07em; }
  .so-logo span { color: var(--so-heading); }
  .so-badge {
    padding: 9px 11px; border: 1px solid var(--border); border-radius: 100px;
    color: var(--muted); font-size: 11px; text-transform: uppercase; letter-spacing: .15em;
  }
  .so-hero { max-width: 690px; margin: clamp(64px, 9vw, 110px) auto 40px; text-align: center; }
  .so-kicker { color: var(--so-heading); font-size: 12px; font-weight: 800; letter-spacing: .16em; text-transform: uppercase; }
  .so-kicker::before {
    content: ''; display: inline-block; width: 7px; height: 7px; margin-right: 9px;
    border-radius: 50%; background: currentColor; box-shadow: 0 0 15px currentColor; vertical-align: middle;
  }
  .so h1 { margin: 18px auto 22px; font-size: clamp(54px, 8vw, 94px); line-height: .96; letter-spacing: -.075em; }
  .so h1 em { color: var(--so-heading); font-style: normal; }
  .so-intro { max-width: 550px; margin: 0 auto; color: var(--muted); font-size: clamp(15px, 2vw, 17px); line-height: 1.55; }
  .so-card, .so-section, .so-empty, .so-job, .so-note { max-width: 740px; margin-left: auto; margin-right: auto; }
  .so-card {
    padding: clamp(18px, 3vw, 30px); border: 1px solid var(--border); border-radius: 24px;
    background: var(--surface); box-shadow: 0 22px 80px #0000000b;
  }
  .so-label { display: block; margin-bottom: 12px; color: var(--muted); font-size: 12px; font-weight: 800; letter-spacing: .11em; text-transform: uppercase; }
  .so textarea {
    width: 100%; min-height: 118px; padding: 17px; resize: vertical; outline: none;
    border: 1px solid var(--border); border-radius: 14px; background: var(--bg); color: var(--text);
    font: 15px/1.5 var(--font);
  }
  .so textarea:focus { border-color: var(--so-accent); box-shadow: 0 0 0 3px #a9eb3d33; }
  .so textarea::placeholder { color: var(--muted); }
  .so-actions { display: flex; align-items: center; justify-content: space-between; gap: 14px; margin-top: 16px; }
  .so-hint { color: var(--muted); font-size: 12px; line-height: 1.45; }
  .so button {
    min-height: 46px; padding: 0 22px; border: 0; border-radius: 12px;
    background: var(--so-accent); color: #192009; cursor: pointer;
    font: 800 14px var(--font); transition: transform .15s, filter .15s;
  }
  .so button:hover { filter: brightness(1.05); transform: translateY(-1px); }
  .so button:disabled { opacity: .55; cursor: wait; transform: none; }
  .so button:focus-visible { outline: 3px solid var(--text); outline-offset: 3px; }
  .so-error { margin: 14px 0 0; padding: 13px 16px; border-radius: 12px; background: #de584e16; color: #de584e; font-size: 13px; }
  .so-section { display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-top: 68px; margin-bottom: 15px; }
  .so h2 { margin: 0; font-size: 19px; letter-spacing: -.04em; }
  .so-count { color: var(--muted); font-size: 12px; }
  .so-bulk-status { max-width: 740px; margin: 0 auto 15px; color: var(--muted); font-size: 12px; line-height: 1.5; }
  .so-bulk-status[role="alert"] { color: #de584e; }
  .so-empty { padding: 38px 22px; border: 1px dashed var(--border); border-radius: 18px; color: var(--muted); text-align: center; }
  .so-job { margin-bottom: 12px; overflow: hidden; border: 1px solid var(--border); border-radius: 18px; background: var(--surface); }
  .so-job-head { display: flex; justify-content: space-between; align-items: center; gap: 14px; padding: 17px 20px; }
  .so-job-title { font-size: 13px; font-weight: 750; overflow-wrap: anywhere; }
  .so-status { color: var(--muted); font-size: 12px; white-space: nowrap; }
  .so-list { border-top: 1px solid var(--border); }
  .so-track { display: grid; grid-template-columns: minmax(0, 1fr) auto; align-items: center; gap: 8px 16px; padding: 14px 20px; border-top: 1px solid var(--border); }
  .so-track > div:first-child { min-width: 0; }
  .so-track:first-child { border-top: 0; }
  .so-track strong { display: block; overflow: hidden; font-size: 13px; white-space: nowrap; text-overflow: ellipsis; }
  .so-track small { display: block; margin-top: 4px; color: var(--muted); }
  .so-track button { min-height: 44px; padding: 0 16px; font-size: 12px; }
  .so-progress { grid-column: 1/-1; height: 3px; overflow: hidden; border-radius: 3px; background: var(--surface-2); }
  .so-progress span { display: block; height: 100%; background: var(--so-accent); transition: width .2s; }
  .so-note { margin-top: 22px; color: var(--muted); font-size: 12px; line-height: 1.5; text-align: center; }
  .so-note strong { color: var(--text); }
  .so-save-error { grid-column: 1/-1; color: #de584e; font-size: 12px; }
  @media (max-width: 700px) {
    .so-hero { margin: 70px auto 36px; }
    .so h1 { font-size: clamp(52px, 14vw, 72px); }
    .so-actions { flex-direction: column; align-items: stretch; }
    .so-actions button { width: 100%; }
    .so-hint { order: 2; text-align: center; }
    .so-section { margin-top: 54px; }
    .so-job-head { flex-direction: column; align-items: flex-start; gap: 6px; }
    .so-track { grid-template-columns: 1fr; }
    .so-track button { width: 100%; }
  }
  @media (prefers-reduced-motion: reduce) { .so button, .so-progress span { transition: none; } }
`

export default function App({ appId, token }) {
  const [input, setInput] = useState('')
  const [jobs, setJobs] = useState([])
  const [readyCount, setReadyCount] = useState(0)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [saving, setSaving] = useState(null)
  const [saveErrors, setSaveErrors] = useState({})
  const [allBusy, setAllBusy] = useState(false)
  const [allStatus, setAllStatus] = useState('')
  const [allError, setAllError] = useState(false)
  const auth = { Authorization: `Bearer ${token}` }
  async function request(path, options = {}) {
    const res = await fetch(`/api/apps/${appId}/service/${path}`, { ...options, headers: { ...auth, ...(options.headers || {}) } })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(data.detail || `Error ${res.status}`)
    return data
  }
  async function refresh() {
    try { const data = await request('jobs'); setJobs(data.jobs); setReadyCount(data.ready_count || 0) } catch (e) { setError(e.message) }
  }
  useEffect(() => { refresh(); const timer = setInterval(refresh, 3000); return () => clearInterval(timer) }, [appId, token])
  async function submit(e) {
    e.preventDefault(); setBusy(true); setError('')
    try {
      await request('jobs', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ links: input }) })
      setInput(''); await refresh()
      const res = await fetch(`/api/apps/${appId}/run-job`, { method: 'POST', headers: auth })
      if (!res.ok) throw new Error('The download was queued, but the background job did not start.')
    } catch (e) { setError(e.message) } finally { setBusy(false) }
  }
  async function save(item) {
    setSaving(item.id)
    setSaveErrors(current => ({ ...current, [item.id]: null }))
    try {
      if (!window.mobius?.fileExport?.save) throw new Error('The latest Möbius file export is unavailable. Refresh Möbius and try again.')
      await window.mobius.fileExport.save(item.file, item.name || `${item.artist} - ${item.title}.mp3`)
    } catch (e) {
      setSaveErrors(current => ({ ...current, [item.id]: e.message || 'Could not save the file.' }))
    } finally { setSaving(null) }
  }
  async function saveAll() {
    setAllBusy(true); setAllError(false); setAllStatus('Preparing your MP3s…')
    let batchId = null
    let offset = 0
    let saved = 0
    try {
      if (!window.mobius?.fileExport?.save) throw new Error('The latest Möbius file export is unavailable. Refresh Möbius and try again.')
      while (true) {
        const part = await request('archive', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(batchId ? { batch_id: batchId, offset } : {}) })
        batchId = part.batch_id
        setAllStatus(`Confirm the save for ${part.name} (${Math.min(saved + part.count, part.total)} of ${part.total} ready MP3s)…`)
        let confirmed = false
        try {
          confirmed = await window.mobius.fileExport.save(part.file, part.name)
        } finally {
          await request(`archive/${batchId}/${offset}`, { method: 'DELETE' }).catch(() => {})
        }
        if (!confirmed) {
          setAllStatus(saved ? `Stopped after saving ${saved} MP3${saved === 1 ? '' : 's'}.` : 'Download cancelled. Your MP3s are still here.')
          break
        }
        saved += part.count
        if (part.next_offset === null) {
          setAllStatus(`Saved ${saved} ready MP3${saved === 1 ? '' : 's'} in ${offset ? 'ZIP archives' : 'one ZIP archive'}.`)
          break
        }
        offset = part.next_offset
        setAllStatus(`Preparing the next ZIP (${saved} of ${part.total} saved)…`)
      }
    } catch (e) {
      setAllError(true)
      setAllStatus(`${e.message || 'Could not download all MP3s.'}${saved ? ` ${saved} MP3${saved === 1 ? '' : 's'} already saved.` : ''}`)
    } finally {
      if (batchId) await request(`archive/${batchId}`, { method: 'DELETE' }).catch(() => {})
      setAllBusy(false)
    }
  }
  return <div className="so"><style>{CSS}</style><div className="so-wrap">
    <header className="so-top"><div className="so-logo">SONG<span>IO</span></div><div className="so-badge">Möbius edition · beta</div></header>
    <section className="so-hero"><div><div className="so-kicker">Your music, your way</div><h1>Links in.<br/><em>MP3s out.</em></h1></div><p className="so-intro">Drop a Spotify or YouTube track, album, or playlist link. SONGIO finds the audio and prepares a tagged MP3 with artwork.</p></section>
    <form className="so-card" onSubmit={submit}><label className="so-label" htmlFor="so-links">Paste your links</label><textarea id="so-links" value={input} onChange={e => setInput(e.target.value)} placeholder="https://open.spotify.com/track/…&#10;https://www.youtube.com/watch?v=…" required/><div className="so-actions"><span className="so-hint">Add several links at once · downloads run in the background</span><button type="submit" disabled={busy}>{busy ? 'Adding…' : 'Create MP3 →'}</button></div>{error && <p className="so-error" role="alert">{error}</p>}</form>
    <div className="so-section"><h2>Your processing jobs</h2><span className="so-count">{jobs.length ? `${jobs.length} ${jobs.length === 1 ? 'job' : 'jobs'}` : 'No jobs yet'}</span></div>
    {allStatus && <p className="so-bulk-status" role={allError ? 'alert' : 'status'}>{allStatus}</p>}
    {!jobs.length && <div className="so-empty">Your downloaded tracks will appear here.</div>}
    {jobs.map(job => <article className="so-job" key={job.id}><div className="so-job-head"><div className="so-job-title">{job.urls.join(' · ')}</div><div className="so-status">{job.status === 'working' ? job.message : job.status === 'queued' ? 'Queued' : job.status === 'done' ? 'Complete' : 'Error'}</div></div>{(job.items.length > 0 || job.errors.length > 0) && <div className="so-list">{job.items.map(item => <div className="so-track" key={item.id}><div><strong>{item.artist} — {item.title}</strong><small>{item.status === 'done' ? 'MP3 prepared for this session' : item.message || item.status}</small></div>{!item.file && <span className="so-status">{item.progress || 0}%</span>}{!item.file && <div className="so-progress"><span style={{width:`${item.progress || 0}%`}}/></div>}</div>)}{job.errors.map((message, i) => <div className="so-track" key={i}><small>{message}</small></div>)}</div>}</article>)}
    <p className="so-note"><strong>Good to know</strong> · Spotify supplies track details; SONGIO looks for audio on YouTube. Some links may require sign-in or may be unavailable. This Store version prepares results for review; file export is available only in the local full version.</p>
  </div></div>
}
