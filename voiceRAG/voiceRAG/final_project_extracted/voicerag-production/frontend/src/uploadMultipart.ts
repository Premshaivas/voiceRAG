import { authenticatedFetch } from './authSession'

export async function uploadMultipart(file: File, title?: string, onProgress?: (value: number) => void) {
  const initiate = await authenticatedFetch('/api/uploads/initiate', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({filename:file.name, content_type:file.type || 'application/octet-stream', size_bytes:file.size, title})})
  if (!initiate.ok) throw new Error((await initiate.json()).detail ?? 'Could not start upload')
  const session = await initiate.json()
  const parts: {part_number:number, etag:string}[] = []
  for (let start = 1, offset = 0; offset < file.size; start += 10) {
    const count = Math.min(10, session.part_count - start + 1)
    const urlsResponse = await authenticatedFetch(`/api/uploads/${session.upload_id}/parts?start=${start}&count=${count}`)
    if (!urlsResponse.ok) throw new Error('Could not create upload URLs')
    const {parts: urls} = await urlsResponse.json()
    for (const part of urls) {
      const chunk = file.slice(offset, offset + session.part_size_bytes)
      const uploaded = await fetch(part.url, {method:'PUT', headers:{'Content-Type':file.type || 'application/octet-stream'}, body:chunk})
      if (!uploaded.ok) throw new Error(`Storage upload failed for part ${part.part_number}`)
      const etag = uploaded.headers.get('ETag') ?? uploaded.headers.get('etag')
      if (!etag) throw new Error('Storage did not return an ETag')
      parts.push({part_number:part.part_number, etag})
      offset += chunk.size
      onProgress?.(Math.round((offset / file.size) * 100))
    }
  }
  const complete = await authenticatedFetch(`/api/uploads/${session.upload_id}/complete`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({parts})})
  if (!complete.ok) throw new Error((await complete.json()).detail ?? 'Could not complete upload')
  return complete.json()
}
