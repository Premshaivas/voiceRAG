import { getAccessToken } from './authSession'

type VoiceCallbacks = { onEvent?: (event: any) => void; onState?: (state: string) => void; onError?: (message: string) => void }

function encodePcm16(samples: Float32Array, inputRate: number, outputRate = 24000) {
  const ratio = inputRate / outputRate
  const length = Math.round(samples.length / ratio)
  const pcm = new Int16Array(length)
  for (let i = 0; i < length; i++) {
    const source = Math.min(samples.length - 1, Math.floor(i * ratio))
    const value = Math.max(-1, Math.min(1, samples[source]))
    pcm[i] = value < 0 ? value * 0x8000 : value * 0x7fff
  }
  const bytes = new Uint8Array(pcm.buffer)
  let binary = ''
  for (const byte of bytes) binary += String.fromCharCode(byte)
  return btoa(binary)
}

function decodePcm16(value: string) {
  const binary = atob(value)
  const bytes = Uint8Array.from(binary, char => char.charCodeAt(0))
  return new Int16Array(bytes.buffer)
}

export class VoiceAgentClient {
  private socket: WebSocket | null = null
  private stream: MediaStream | null = null
  private context: AudioContext | null = null
  private processor: ScriptProcessorNode | null = null
  private nextPlayback = 0
  private manualStop = false
  private reconnectAttempts = 0
  private reconnectTimer: number | null = null
  constructor(private callbacks: VoiceCallbacks = {}) {}

  async start() {
    if (this.socket) return
    this.manualStop = false
    this.callbacks.onState?.('requesting microphone')
    this.stream = await navigator.mediaDevices.getUserMedia({audio: {echoCancellation:true, noiseSuppression:true, channelCount:1}})
    this.context = new AudioContext()
    const protocol = location.protocol === 'https:' ? 'wss' : 'ws'
    const host = import.meta.env.VITE_API_BASE_URL ? new URL(import.meta.env.VITE_API_BASE_URL).host : location.host
    const token = getAccessToken()
    const query = token ? `?access_token=${encodeURIComponent(token)}` : ''
    this.socket = new WebSocket(`${protocol}://${host}/api/voice-agent${query}`)
    this.socket.onopen = () => { this.reconnectAttempts = 0; this.callbacks.onState?.('connected') }
    this.socket.onclose = () => {
      this.cleanupAudio()
      this.socket = null
      if (!this.manualStop && this.reconnectAttempts < 2) {
        this.reconnectAttempts += 1
        this.callbacks.onState?.(`reconnecting ${this.reconnectAttempts}/2`)
        this.reconnectTimer = window.setTimeout(() => { this.reconnectTimer = null; void this.start().catch(error => this.callbacks.onError?.(error instanceof Error ? error.message : 'Voice reconnect failed')) }, this.reconnectAttempts * 1000)
      } else if (!this.manualStop) this.callbacks.onState?.('ended')
    }
    this.socket.onerror = () => this.callbacks.onError?.('Voice connection failed')
    this.socket.onmessage = event => this.handle(JSON.parse(event.data))
    await new Promise<void>((resolve, reject) => { const timer = window.setTimeout(() => reject(new Error('Voice connection timed out')), 10000); const socket = this.socket!; const opened = () => { clearTimeout(timer); socket.removeEventListener('open', opened); resolve() }; socket.addEventListener('open', opened); socket.addEventListener('error', () => { clearTimeout(timer); reject(new Error('Voice connection failed')) }, {once:true}) })
    const source = this.context.createMediaStreamSource(this.stream)
    this.processor = this.context.createScriptProcessor(4096, 1, 1)
    this.processor.onaudioprocess = event => { if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(JSON.stringify({type:'input.audio', audio:encodePcm16(event.inputBuffer.getChannelData(0), this.context!.sampleRate)})) }
    source.connect(this.processor); this.processor.connect(this.context.destination)
    this.callbacks.onState?.('listening')
  }

  stop() {
    this.manualStop = true
    if (this.reconnectTimer !== null) { window.clearTimeout(this.reconnectTimer); this.reconnectTimer = null }
    if (this.socket?.readyState === WebSocket.OPEN) this.socket.send(JSON.stringify({type:'session.end'}))
    this.socket?.close(); this.socket = null; this.cleanupAudio(); this.callbacks.onState?.('idle')
  }

  private handle(event: any) {
    this.callbacks.onEvent?.(event)
    if (event.type === 'session.ready') this.callbacks.onState?.('listening')
    if (event.type === 'session.error') this.callbacks.onError?.(event.message || 'Voice session error')
    if (event.type === 'reply.audio') this.play(decodePcm16(event.data))
    if (event.type === 'input.speech.started') this.callbacks.onState?.('you are speaking')
    if (event.type === 'reply.started') this.callbacks.onState?.('agent is thinking')
    if (event.type === 'reply.done') this.callbacks.onState?.('listening')
  }

  private play(samples: Int16Array) {
    if (!this.context) return
    const buffer = this.context.createBuffer(1, samples.length, 24000)
    const channel = buffer.getChannelData(0)
    for (let i = 0; i < samples.length; i++) channel[i] = samples[i] / 32768
    const source = this.context.createBufferSource(); source.buffer = buffer; source.connect(this.context.destination)
    const now = this.context.currentTime
    this.nextPlayback = Math.max(this.nextPlayback, now)
    source.start(this.nextPlayback); this.nextPlayback += buffer.duration
  }

  private cleanupAudio() { this.processor?.disconnect(); this.processor = null; this.stream?.getTracks().forEach(track => track.stop()); this.stream = null; void this.context?.close(); this.context = null; this.nextPlayback = 0 }
}
