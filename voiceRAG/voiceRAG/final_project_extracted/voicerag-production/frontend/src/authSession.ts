const API = import.meta.env.VITE_API_BASE_URL ?? ''
let accessToken: string | null = null
let csrfToken: string | null = null
let refreshInFlight: Promise<boolean> | null = null

export function hasSession() { return Boolean(accessToken) }
export function getAccessToken() { return accessToken }
export function clearSession() { accessToken = null; csrfToken = null }

export async function login(email: string, password: string, register = false) {
  const response = await fetch(`${API}/api/auth/${register ? 'register' : 'login'}`, { method: 'POST', headers: {'Content-Type':'application/json'}, credentials: 'include', body: JSON.stringify({email, password}) })
  if (!response.ok) throw new Error((await response.json()).detail ?? 'Authentication failed')
  const data = await response.json(); accessToken = data.access_token; csrfToken = data.csrf_token
}

async function refresh(): Promise<boolean> {
  if (!refreshInFlight) refreshInFlight = fetch(`${API}/api/auth/refresh`, { method:'POST', credentials:'include', headers: csrfToken ? {'X-CSRF-Token': csrfToken} : {} }).then(async response => {
    if (!response.ok) { clearSession(); return false }
    const data = await response.json(); accessToken = data.access_token; csrfToken = data.csrf_token; return true
  }).finally(() => { refreshInFlight = null })
  return refreshInFlight
}

export async function authenticatedFetch(path: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers)
  if (accessToken) headers.set('Authorization', `Bearer ${accessToken}`)
  let response = await fetch(`${API}${path}`, {...init, headers, credentials:'include'})
  if (response.status === 401 && await refresh()) {
    const retryHeaders = new Headers(init.headers)
    if (accessToken) retryHeaders.set('Authorization', `Bearer ${accessToken}`)
    response = await fetch(`${API}${path}`, {...init, headers: retryHeaders, credentials:'include'})
  }
  return response
}

export async function logout() {
  if (csrfToken) await fetch(`${API}/api/auth/logout`, {method:'POST', credentials:'include', headers:{'X-CSRF-Token':csrfToken}})
  clearSession()
}
