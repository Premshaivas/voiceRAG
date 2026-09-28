import { useEffect, useRef, useState } from 'react'
import { authenticatedFetch } from './authSession'

type Doc = {id:string,title:string,status:string}
type Word = {text:string,start?:number,end?:number,speaker?:string}
export function TranscriptPanel({documents}:{documents:Doc[]}) {
  const [documentId, setDocumentId] = useState('')
  const [query, setQuery] = useState('')
  const [text, setText] = useState('')
  const [words, setWords] = useState<Word[]>([])
  const [matches, setMatches] = useState<{excerpt:string}[]>([])
  const [active, setActive] = useState(-1)
  const [message, setMessage] = useState('')
  const audio = useRef<HTMLAudioElement | null>(null)
  async function load() { if (!documentId) return; const response = await authenticatedFetch(`/api/documents/${documentId}/transcript`); if (!response.ok) return setMessage('Transcript is not ready'); const data = await response.json(); setText(data.text); setWords(data.words ?? []); setMessage('') }
  async function search() { if (!documentId || !query.trim()) return; const response = await authenticatedFetch(`/api/documents/${documentId}/transcript/search?q=${encodeURIComponent(query)}`); if (response.ok) setMatches((await response.json()).matches); }
  async function playAt(ms:number) { if (!documentId) return; if (!audio.current) { const response = await authenticatedFetch(`/api/documents/${documentId}/audio`); if (!response.ok) return setMessage('Audio is unavailable'); audio.current = new Audio(URL.createObjectURL(await response.blob())); audio.current.ontimeupdate = () => { const now = (audio.current?.currentTime ?? 0) * 1000; setActive(words.findIndex(word => word.start !== undefined && word.end !== undefined && now >= word.start && now <= word.end)) } } audio.current.currentTime = ms / 1000; await audio.current.play() }
  useEffect(() => () => { audio.current?.pause() }, [])
  return <section className="panel transcript-panel"><div className="panel-heading"><div><p className="eyebrow">06 / TRANSCRIPT</p><h2>Read and search</h2></div></div><div className="transcript-toolbar"><select value={documentId} onChange={e=>{setDocumentId(e.target.value);setText('');setWords([]);setMatches([])}}><option value="">Select a recording</option>{documents.filter(doc=>doc.status==='completed').map(doc=><option key={doc.id} value={doc.id}>{doc.title}</option>)}</select><button onClick={load} disabled={!documentId}>Load</button></div><div className="transcript-search"><input value={query} onChange={e=>setQuery(e.target.value)} placeholder="Search transcript"/><button onClick={search} disabled={!documentId || !query.trim()}>Find</button></div>{message && <p className="error">{message}</p>}{matches.length > 0 && <div className="transcript-matches">{matches.map((match,index)=><p key={index}>{match.excerpt}</p>)}</div>}{words.length > 0 ? <div className="transcript-text word-transcript">{words.map((word,index)=><button className={`word ${index===active?'word-active':''}`} key={`${index}-${word.start}`} title={word.speaker ? `Speaker ${word.speaker}` : undefined} onClick={()=>void playAt(Number(word.start ?? 0))}>{word.speaker && (index===0 || words[index-1]?.speaker!==word.speaker) ? <b className="speaker-label">Speaker {word.speaker}: </b> : null}{word.text} </button>)}</div> : text && <pre className="transcript-text">{text}</pre>}</section>
}
