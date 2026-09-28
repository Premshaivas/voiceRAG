import { useState } from 'react'
import { authenticatedFetch } from './authSession'
export function AdminPanel() {
  const [data, setData] = useState<any>(null)
  const [message, setMessage] = useState('')
  async function load() { const response = await authenticatedFetch('/api/admin/usage'); if (response.status===403) return setMessage('Administrator access required'); if (!response.ok) return setMessage('Could not load admin data'); const usage = await response.json(); const users = await (await authenticatedFetch('/api/admin/users')).json(); const audit = await (await authenticatedFetch('/api/admin/audit?limit=10')).json(); setData({usage,users,audit}); setMessage('') }
  return <section className="panel admin-panel"><div className="panel-heading"><div><p className="eyebrow">07 / ADMIN</p><h2>Operations</h2></div><button onClick={load}>Refresh</button></div>{message && <p className="muted">{message}</p>}{data && <><div className="metric-grid"><div className="metric"><span>Users</span><strong>{data.usage.users}</strong></div><div className="metric"><span>Documents</span><strong>{data.usage.documents}</strong></div><div className="metric"><span>Transcripts</span><strong>{data.usage.transcripts}</strong></div></div><h3>Recent audit events</h3>{data.audit.map((item:any)=><p className="audit-row" key={item.id}><strong>{item.action}</strong> · {item.resource_type} · {item.created_at}</p>)}</>}</section>
}
