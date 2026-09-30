import { useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { authenticatedFetch, hasSession, login, logout } from './authSession'
import { uploadMultipart } from './uploadMultipart'
import { VoiceAgentClient } from './voiceAgent'
import { EvaluationPanel } from './EvaluationPanel'
import { TranscriptPanel } from './TranscriptPanel'
import { AdminPanel } from './AdminPanel'
import { VideoIntelligencePanel } from './VideoIntelligencePanel'
import './styles.css'

type DocumentRow = {id:string, title:string, filename:string, status:string, transcript_id?:string}
type Answer = {answer:string, answer_mode?:string, grounded:boolean, citations:string[], citation_coverage?:number, confidence?:number, sources:{citation:string,text:string,metadata:Record<string, unknown>}[]}

type VoiceEvent = {type:string, text?:string, message?:string, status?:string}

function App() {
  const [signedIn, setSignedIn] = useState(hasSession())
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [registerMode, setRegisterMode] = useState(false)
  const [documents, setDocuments] = useState<DocumentRow[]>([])
  const [file, setFile] = useState<File | null>(null)
  const [title, setTitle] = useState('')
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState<Answer | null>(null)
  const [progress, setProgress] = useState(0)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const [voiceState, setVoiceState] = useState('idle')
  const [voiceConversationId, setVoiceConversationId] = useState<string | null>(null)
  const [voiceEvents, setVoiceEvents] = useState<VoiceEvent[]>(() => { try { return JSON.parse(localStorage.getItem('voicerag.voiceHistory') ?? '[]') } catch { return [] } })
  const voiceRef = useRef<VoiceAgentClient | null>(null)
  const audioRef = useRef<HTMLAudioElement | null>(null)

  async function loadDocuments() { const response = await authenticatedFetch('/api/documents'); if (response.ok) setDocuments(await response.json()) }
  useEffect(() => { if (signedIn) loadDocuments() }, [signedIn])
  useEffect(() => () => { voiceRef.current?.stop() }, [])

  async function submitAuth(event: React.FormEvent) { event.preventDefault(); setBusy(true); setMessage(''); try { await login(email, password, registerMode); setSignedIn(true); setPassword('') } catch (error) { setMessage(error instanceof Error ? error.message : 'Authentication failed') } finally { setBusy(false) } }
  async function submitUpload(event: React.FormEvent) { event.preventDefault(); if (!file) return; setBusy(true); setMessage(''); setProgress(0); try { await uploadMultipart(file, title || undefined, setProgress); setMessage('Upload queued for validation and transcription.'); setFile(null); setTitle(''); await loadDocuments() } catch (error) { setMessage(error instanceof Error ? error.message : 'Upload failed') } finally { setBusy(false) } }
  async function askQuestion(event: React.FormEvent) { event.preventDefault(); if (!question.trim()) return; setBusy(true); setMessage(''); try { const docId = documents.find(d => d.status === 'completed')?.id; const payload: Record<string, unknown> = { question }; if (docId) payload.document_id = docId; const response = await authenticatedFetch('/api/answers', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)}); if (!response.ok) throw new Error((await response.json()).detail ?? 'Answer failed'); setAnswer(await response.json()) } catch (error) { setMessage(error instanceof Error ? error.message : 'Answer failed') } finally { setBusy(false) } }

  async function playCitation(source: Answer['sources'][number]) {
    const documentId = String(source.metadata.document_id ?? '')
    if (!documentId) return
    try {
      const response = await authenticatedFetch(`/api/documents/${documentId}/audio`)
      if (!response.ok) throw new Error('Audio is unavailable')
      const url = URL.createObjectURL(await response.blob())
      audioRef.current?.pause()
      const audio = new Audio(url)
      audioRef.current = audio
      audio.currentTime = Math.max(0, Number(source.metadata.start_ms ?? 0) / 1000)
      audio.addEventListener('ended', () => URL.revokeObjectURL(url), {once:true})
      await audio.play()
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Could not play citation') }
  }

  async function toggleVoice() {
    if (voiceRef.current) { voiceRef.current.stop(); voiceRef.current = null; setVoiceState('idle'); return }
    let conversationId = voiceConversationId
    if (!conversationId) { const response = await authenticatedFetch('/api/voice-conversations', {method:'POST'}); if (response.ok) { conversationId = (await response.json()).id; setVoiceConversationId(conversationId) } }
    const client = new VoiceAgentClient({onState: setVoiceState, onError: setMessage, onEvent: event => { if (event.type === 'transcript.user' || event.type === 'transcript.agent' || event.type === 'session.error') { setVoiceEvents(current => { const next = [...current.slice(-19), event]; localStorage.setItem('voicerag.voiceHistory', JSON.stringify(next)); return next }); const text = event.text ?? event.message; if (conversationId && text) void authenticatedFetch(`/api/voice-conversations/${conversationId}/messages`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({role:event.type === 'transcript.user' ? 'user' : 'agent', text})}) } }})
    voiceRef.current = client
    try { await client.start() } catch (error) { voiceRef.current = null; setVoiceState('idle'); setMessage(error instanceof Error ? error.message : 'Could not start microphone') }
  }

  if (!signedIn) return <main className="auth-shell"><section className="auth-card"><p className="eyebrow">VOICERAG / KNOWLEDGE WORKSPACE</p><h1>Turn recorded lectures into answers you can verify.</h1><p className="muted">Upload audio directly to storage, let the processing pipeline transcribe it, then ask grounded questions with source citations.</p><form onSubmit={submitAuth} className="stack"><label>Email<input type="email" value={email} onChange={e=>setEmail(e.target.value)} required /></label><label>Password<input type="password" minLength={8} value={password} onChange={e=>setPassword(e.target.value)} required /></label><button disabled={busy}>{busy ? 'Working…' : registerMode ? 'Create account' : 'Sign in'}</button></form><button className="link-button" onClick={()=>setRegisterMode(!registerMode)}>{registerMode ? 'Already have an account? Sign in' : 'Create an account'}</button>{message && <p className="error">{message}</p>}</section></main>

  return <main className="app-shell"><header className="topbar"><div><p className="eyebrow">VOICERAG / WORKSPACE</p><h1>Lecture intelligence</h1></div><button className="quiet-button" onClick={async()=>{voiceRef.current?.stop(); await logout();setSignedIn(false)}}>Sign out</button></header><div className="grid"><VideoIntelligencePanel documents={documents} onRefreshDocs={loadDocuments} /><section className="panel upload-panel"><div className="panel-heading"><div><p className="eyebrow">01 / INGEST</p><h2>Add a recording</h2></div><span className="pill">S3 multipart</span></div><p className="muted">Large files upload directly to storage. Validation, malware scanning, transcription, and indexing run in the background.</p><form onSubmit={submitUpload} className="stack"><label>Title <span className="optional">optional</span><input value={title} onChange={e=>setTitle(e.target.value)} placeholder="Operating systems — week 4" /></label><label className="file-drop">{file ? <><strong>{file.name}</strong><span>{(file.size/1024/1024).toFixed(1)} MB</span></> : <><strong>Choose an audio file</strong><span>MP3, WAV, M4A, FLAC, OGG, or WebM</span></>}<input type="file" accept="audio/*,video/mp4,video/webm" onChange={e=>setFile(e.target.files?.[0] ?? null)} required /></label>{progress > 0 && <div className="progress"><span style={{width:`${progress}%`}} /></div>}<button disabled={busy || !file}>{busy ? progress ? `Uploading ${progress}%` : 'Processing…' : 'Upload recording'}</button></form></section><section className="panel"><div className="panel-heading"><div><p className="eyebrow">02 / LIBRARY</p><h2>Your recordings</h2></div><button className="icon-button" onClick={loadDocuments}>↻</button></div><div className="document-list">{documents.length === 0 ? <p className="empty">No recordings yet.</p> : documents.map(doc=><div className="document-row" key={doc.id}><div><strong>{doc.title}</strong><span>{doc.filename}</span></div><span className={`status status-${doc.status}`}>{doc.status}</span></div>)}</div></section><section className="panel answer-panel"><div className="panel-heading"><div><p className="eyebrow">03 / ASK</p><h2>Question the archive</h2></div><span className="pill">Grounded answers</span></div><form onSubmit={askQuestion} className="question-form"><textarea value={question} onChange={e=>setQuestion(e.target.value)} placeholder="What are the three main ideas from the lecture?" rows={3} /><button disabled={busy || !question.trim()}>Ask the archive</button></form>{answer && <article className={`answer ${answer.grounded ? 'grounded' : ''}`}><div className="answer-label">{answer.answer_mode === 'transcript_excerpt' ? 'TRANSCRIPT EXCERPT · LLM GATEWAY ACCESS REQUIRED' : answer.grounded ? 'GROUNDED RESPONSE' : 'NO VERIFIED SOURCE'}</div>{answer.grounded && <div className="answer-metrics"><span>Confidence {Math.round((answer.confidence ?? 0) * 100)}%</span><span>Citation coverage {Math.round((answer.citation_coverage ?? 0) * 100)}%</span></div>}<p>{answer.answer}</p>{answer.sources.length > 0 && <div className="sources"><h3>Sources</h3>{answer.sources.map(source=><details key={source.citation}><summary>{source.citation} · {String(source.metadata.title ?? 'Transcript')}</summary><button className="citation-button" onClick={()=>void playCitation(source)}>Play from {Math.round(Number(source.metadata.start_ms ?? 0) / 1000)}s</button><p>{source.text}</p></details>)}</div>}</article>}</section><section className="panel voice-panel"><div className="panel-heading"><div><p className="eyebrow">04 / LIVE VOICE</p><h2>Talk to your lectures</h2></div><span className={`pill voice-pill ${voiceState !== 'idle' ? 'voice-live' : ''}`}>{voiceState}</span></div><p className="muted">Use your microphone to ask questions naturally. The voice agent searches your owned transcripts before it answers.</p><button className={voiceState !== 'idle' ? 'stop-button' : ''} onClick={toggleVoice}>{voiceState !== 'idle' ? 'End voice session' : 'Start voice session'}</button>{voiceEvents.length > 0 && <div className="voice-transcript">{voiceEvents.map((event, index)=><p key={`${event.type}-${index}`}><span>{event.type === 'transcript.user' ? 'You' : 'Agent'}</span>{event.text ?? event.message}</p>)}</div>}</section><EvaluationPanel /><TranscriptPanel documents={documents} /><AdminPanel /></div>{message && <div className="toast">{message}</div>}</main>
}

createRoot(document.getElementById('root')!).render(<App />)
