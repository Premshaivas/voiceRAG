import { useState } from 'react'
import { authenticatedFetch } from './authSession'

type Run = {run_id:string,status:string,case_count:number,metrics:Record<string,number>,results?:{case_id:string,answer:string,answer_f1:number,retrieval_recall:number,citation_precision:number,citation_recall:number,latency_ms:number}[]}

export function EvaluationPanel() {
  const [datasetName, setDatasetName] = useState('Lecture QA smoke set')
  const [datasetId, setDatasetId] = useState('')
  const [question, setQuestion] = useState('')
  const [expectedAnswer, setExpectedAnswer] = useState('')
  const [expectedDocuments, setExpectedDocuments] = useState('')
  const [run, setRun] = useState<Run | null>(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')

  async function createDataset() {
    setBusy(true); setMessage('')
    try { const response = await authenticatedFetch('/api/evaluations/datasets', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({name:datasetName})}); if (!response.ok) throw new Error((await response.json()).detail ?? 'Could not create dataset'); const data = await response.json(); setDatasetId(data.id); setMessage(`Dataset ready: ${data.id}`) } catch (error) { setMessage(error instanceof Error ? error.message : 'Dataset creation failed') } finally { setBusy(false) }
  }
  async function addCase(event: React.FormEvent) {
    event.preventDefault(); if (!datasetId) { setMessage('Create a dataset first.'); return }
    setBusy(true); setMessage('')
    try { const response = await authenticatedFetch(`/api/evaluations/datasets/${datasetId}/cases`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({question, expected_answer:expectedAnswer, expected_document_ids:expectedDocuments.split(',').map(value=>value.trim()).filter(Boolean)})}); if (!response.ok) throw new Error((await response.json()).detail ?? 'Could not add case'); setQuestion(''); setExpectedAnswer(''); setMessage('Labeled case added.') } catch (error) { setMessage(error instanceof Error ? error.message : 'Case creation failed') } finally { setBusy(false) }
  }
  async function runDataset() {
    if (!datasetId) { setMessage('Create a dataset first.'); return }
    setBusy(true); setMessage('Running retrieval and grounded-answer evaluation…')
    try { const response = await authenticatedFetch(`/api/evaluations/datasets/${datasetId}/run`, {method:'POST'}); if (!response.ok) throw new Error((await response.json()).detail ?? 'Evaluation failed'); setRun(await response.json()); setMessage('Evaluation completed.') } catch (error) { setMessage(error instanceof Error ? error.message : 'Evaluation failed') } finally { setBusy(false) }
  }
  const metric = (key: string) => run ? `${(run.metrics[key] ?? 0).toFixed(2)}${key === 'latency_ms' ? ' ms' : ''}` : '—'

  return <section className="panel evaluation-panel"><div className="panel-heading"><div><p className="eyebrow">05 / EVALUATE</p><h2>Measure answer quality</h2></div><span className="pill">Labeled RAG</span></div><p className="muted">Create a small gold set from your lectures, run it against the current pipeline, and track retrieval, citation, answer, and latency quality.</p><div className="eval-toolbar"><input value={datasetName} onChange={event=>setDatasetName(event.target.value)} placeholder="Dataset name" /><button onClick={createDataset} disabled={busy || !datasetName.trim()}>{datasetId ? 'Dataset created' : 'Create dataset'}</button></div>{datasetId && <><div className="dataset-id">Dataset ID <code>{datasetId}</code></div><form onSubmit={addCase} className="eval-form"><textarea value={question} onChange={event=>setQuestion(event.target.value)} placeholder="Question" rows={2} required /><textarea value={expectedAnswer} onChange={event=>setExpectedAnswer(event.target.value)} placeholder="Expected answer" rows={2} required /><input value={expectedDocuments} onChange={event=>setExpectedDocuments(event.target.value)} placeholder="Expected document IDs, comma separated" /><button disabled={busy}>Add labeled case</button></form><button className="run-button" onClick={runDataset} disabled={busy}>Run evaluation</button></>}{run && <div className="metric-grid">{[['retrieval_recall','Retrieval recall'],['citation_precision','Citation precision'],['citation_recall','Citation recall'],['answer_f1','Answer F1'],['latency_ms','Mean latency']].map(([key,label])=><div className="metric" key={key}><span>{label}</span><strong>{metric(key)}</strong></div>)}</div>}{run?.results?.map(result=><details className="eval-result" key={result.case_id}><summary>Case {result.case_id.slice(0,8)} · F1 {result.answer_f1.toFixed(2)} · {result.latency_ms.toFixed(0)} ms</summary><p>{result.answer}</p></details>)}{message && <p className="eval-message">{message}</p>}</section>
}
