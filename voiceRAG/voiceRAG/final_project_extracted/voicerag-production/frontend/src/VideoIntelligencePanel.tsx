import { useState, useRef, useEffect } from 'react'
import { authenticatedFetch } from './authSession'

type Doc = { id: string; title: string; filename: string; status: string }
type Source = { citation: string; text: string; metadata: Record<string, unknown> }
type QAItem = {
  question: string
  answer: string
  grounded: boolean
  confidence?: number
  citation_coverage?: number
  sources: Source[]
}

export function VideoIntelligencePanel({
  documents,
  onRefreshDocs,
}: {
  documents: Doc[]
  onRefreshDocs: () => Promise<void>
}) {
  const [tab, setTab] = useState<'url' | 'file'>('url')
  const [videoUrl, setVideoUrl] = useState('')
  const [videoFile, setVideoFile] = useState<File | null>(null)
  const [customTitle, setCustomTitle] = useState('')
  const [loading, setLoading] = useState(false)
  const [loadingStep, setLoadingStep] = useState('')
  const [error, setError] = useState('')

  // Active Video state
  const [activeDocId, setActiveDocId] = useState<string>('')
  const [activeTitle, setActiveTitle] = useState<string>('')
  const [summary, setSummary] = useState<string>('')
  const [keyPoints, setKeyPoints] = useState<string[]>([])
  const [fetchingPoints, setFetchingPoints] = useState(false)

  // Q&A state
  const [question, setQuestion] = useState('')
  const [asking, setAsking] = useState(false)
  const [qaHistory, setQaHistory] = useState<QAItem[]>([])
  const audioRef = useRef<HTMLAudioElement | null>(null)

  // Sync if documents change and we don't have an active one
  useEffect(() => {
    if (!activeDocId && documents.length > 0) {
      const firstCompleted = documents.find(d => d.status === 'completed')
      if (firstCompleted) {
        selectDocument(firstCompleted.id, firstCompleted.title)
      }
    }
  }, [documents])

  async function selectDocument(docId: string, title?: string) {
    if (!docId) return
    setActiveDocId(docId)
    const doc = documents.find(d => d.id === docId)
    setActiveTitle(title || doc?.title || 'Selected Video')
    setSummary('')
    setKeyPoints([])
    setError('')
    setFetchingPoints(true)

    try {
      const res = await authenticatedFetch(`/api/documents/${docId}/key-points`, { method: 'POST' })
      if (!res.ok) {
        const data = await res.json().catch(() => ({}))
        throw new Error(data.detail || 'Could not fetch key points')
      }
      const data = await res.json()
      setSummary(data.summary || '')
      setKeyPoints(data.key_points || [])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Error retrieving key points')
    } finally {
      setFetchingPoints(false)
    }
  }

  // Handle URL import
  async function handleImportUrl(e: React.FormEvent) {
    e.preventDefault()
    if (!videoUrl.trim()) return

    setLoading(true)
    setError('')
    setLoadingStep('Downloading video & audio...')
    try {
      setLoadingStep('Transcribing speech & extracting key insights...')
      const res = await authenticatedFetch('/api/video/import', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: videoUrl.trim(), title: customTitle.trim() || undefined }),
      })

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        throw new Error(errData.detail || 'Video import failed')
      }

      const data = await res.json()
      setVideoUrl('')
      setCustomTitle('')
      await onRefreshDocs()

      // Set active video
      setActiveDocId(data.id)
      setActiveTitle(data.title)
      setSummary(data.summary || '')
      setKeyPoints(data.key_points || [])
      setQaHistory([])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to import video')
    } finally {
      setLoading(false)
      setLoadingStep('')
    }
  }

  // Handle File upload
  async function handleUploadFile(e: React.FormEvent) {
    e.preventDefault()
    if (!videoFile) return

    setLoading(true)
    setError('')
    setLoadingStep('Uploading video...')
    try {
      const formData = new FormData()
      formData.append('file', videoFile)
      if (customTitle.trim()) {
        formData.append('title', customTitle.trim())
      }

      setLoadingStep('Transcribing audio & analyzing key points...')
      const res = await authenticatedFetch('/api/video/upload', {
        method: 'POST',
        body: formData,
      })

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        throw new Error(errData.detail || 'Video upload failed')
      }

      const data = await res.json()
      setVideoFile(null)
      setCustomTitle('')
      await onRefreshDocs()

      // Set active video
      setActiveDocId(data.id)
      setActiveTitle(data.title)
      setSummary(data.summary || '')
      setKeyPoints(data.key_points || [])
      setQaHistory([])
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to process video file')
    } finally {
      setLoading(false)
      setLoadingStep('')
    }
  }

  // Handle Asking Question
  async function handleAskQuestion(e?: React.FormEvent, customQ?: string) {
    if (e) e.preventDefault()
    const query = (customQ || question).trim()
    if (!query || !activeDocId) return

    setAsking(true)
    setError('')
    try {
      const res = await authenticatedFetch(`/api/documents/${activeDocId}/ask`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: query, limit: 6 }),
      })

      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        throw new Error(errData.detail || 'Failed to get answer')
      }

      const answerData = await res.json()
      const newItem: QAItem = {
        question: query,
        answer: answerData.answer || 'No answer available',
        grounded: answerData.grounded ?? true,
        confidence: answerData.confidence,
        citation_coverage: answerData.citation_coverage,
        sources: answerData.sources || [],
      }
      setQaHistory(prev => [newItem, ...prev])
      setQuestion('')
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Question answering failed')
    } finally {
      setAsking(false)
    }
  }

  async function playSourceCitation(source: Source) {
    if (!activeDocId) return
    try {
      const res = await authenticatedFetch(`/api/documents/${activeDocId}/audio`)
      if (!res.ok) throw new Error('Audio is unavailable')
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      audioRef.current?.pause()
      const audio = new Audio(url)
      audioRef.current = audio
      audio.currentTime = Math.max(0, Number(source.metadata.start_ms ?? 0) / 1000)
      audio.addEventListener('ended', () => URL.revokeObjectURL(url), { once: true })
      await audio.play()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not play citation audio')
    }
  }

  return (
    <section className="panel video-intel-panel">
      <div className="panel-heading">
        <div>
          <p className="eyebrow">AI VIDEO INTELLIGENCE &amp; ASSISTANT</p>
          <h2>Video Transcribe, Important Points &amp; Instant Q&amp;A</h2>
        </div>
        <span className="pill video-pill">Direct Video AI</span>
      </div>

      <p className="muted">
        Add any video link (YouTube, lecture link) or upload a video file. It is automatically transcribed,
        summarized with important key points, and equipped with an interactive AI so you can ask questions directly
        without needing any external AI.
      </p>

      {/* Ingestion Section */}
      <div className="video-input-card">
        <div className="video-tabs">
          <button
            type="button"
            className={`tab-btn ${tab === 'url' ? 'active' : ''}`}
            onClick={() => setTab('url')}
          >
            🔗 Paste Video Link
          </button>
          <button
            type="button"
            className={`tab-btn ${tab === 'file' ? 'active' : ''}`}
            onClick={() => setTab('file')}
          >
            📁 Upload Video File
          </button>
        </div>

        {tab === 'url' ? (
          <form onSubmit={handleImportUrl} className="stack video-form">
            <div className="form-row">
              <label className="flex-1">
                Video URL (YouTube or direct video link)
                <input
                  type="url"
                  placeholder="https://www.youtube.com/watch?v=... or direct .mp4 link"
                  value={videoUrl}
                  onChange={e => setVideoUrl(e.target.value)}
                  disabled={loading}
                  required
                />
              </label>
              <label>
                Custom Title <span className="optional">optional</span>
                <input
                  type="text"
                  placeholder="e.g. Distributed Systems Lecture 5"
                  value={customTitle}
                  onChange={e => setCustomTitle(e.target.value)}
                  disabled={loading}
                />
              </label>
            </div>
            <button className="primary-action-btn" disabled={loading || !videoUrl.trim()}>
              {loading ? loadingStep || 'Processing video…' : '🚀 Transcribe & Extract Important Points'}
            </button>
          </form>
        ) : (
          <form onSubmit={handleUploadFile} className="stack video-form">
            <div className="form-row">
              <label className="flex-1 file-drop video-drop">
                {videoFile ? (
                  <>
                    <strong>{videoFile.name}</strong>
                    <span>{(videoFile.size / 1024 / 1024).toFixed(1)} MB</span>
                  </>
                ) : (
                  <>
                    <strong>Choose or drop a video file</strong>
                    <span>MP4, WebM, MOV, MKV, AVI, etc.</span>
                  </>
                )}
                <input
                  type="file"
                  accept="video/*,audio/*"
                  onChange={e => setVideoFile(e.target.files?.[0] ?? null)}
                  disabled={loading}
                  required
                />
              </label>
              <label>
                Custom Title <span className="optional">optional</span>
                <input
                  type="text"
                  placeholder="e.g. Machine Learning Lecture"
                  value={customTitle}
                  onChange={e => setCustomTitle(e.target.value)}
                  disabled={loading}
                />
              </label>
            </div>
            <button className="primary-action-btn" disabled={loading || !videoFile}>
              {loading ? loadingStep || 'Processing video…' : '🚀 Upload, Transcribe & Analyze'}
            </button>
          </form>
        )}

        {loading && (
          <div className="loading-banner">
            <div className="spinner"></div>
            <div>
              <strong>Analyzing Video...</strong>
              <p>{loadingStep}</p>
            </div>
          </div>
        )}
      </div>

      {error && <div className="video-error-banner">⚠️ {error}</div>}

      {/* Select Active Video Dropdown */}
      {documents.length > 0 && (
        <div className="video-selector-bar">
          <span>Active Video:</span>
          <select
            value={activeDocId}
            onChange={e => selectDocument(e.target.value)}
            disabled={loading || fetchingPoints}
          >
            <option value="">Select a video from your library</option>
            {documents
              .filter(d => d.status === 'completed')
              .map(d => (
                <option key={d.id} value={d.id}>
                  {d.title} ({d.filename})
                </option>
              ))}
          </select>
          {fetchingPoints && <span className="fetching-indicator">Loading insights...</span>}
        </div>
      )}

      {/* Video Insights Display */}
      {activeDocId && (
        <div className="video-insights-container">
          <div className="video-meta-header">
            <h3>🎬 {activeTitle}</h3>
            <span className="pill status-completed">Ready for Questions</span>
          </div>

          {/* Executive Summary */}
          {summary && (
            <div className="summary-box">
              <h4>📌 Executive Summary</h4>
              <p>{summary}</p>
            </div>
          )}

          {/* Important Points */}
          <div className="key-points-box">
            <h4>💡 Important Points &amp; Key Insights</h4>
            {keyPoints.length === 0 ? (
              <p className="muted">No key points generated yet.</p>
            ) : (
              <div className="key-points-grid">
                {keyPoints.map((point, index) => (
                  <div key={index} className="key-point-card">
                    <span className="point-number">{index + 1}</span>
                    <div className="point-content">
                      <p>{point}</p>
                      <button
                        type="button"
                        className="point-ask-btn"
                        onClick={() => {
                          const prompt = `Explain this in detail: "${point.slice(0, 80)}..."`
                          setQuestion(prompt)
                          handleAskQuestion(undefined, prompt)
                        }}
                      >
                        💬 Ask about this point
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Interactive In-Context Video Q&A */}
          <div className="video-qa-section">
            <div className="qa-header">
              <div>
                <h4>🤖 Ask Questions About This Video</h4>
                <p className="muted">
                  No need to open another AI. Ask any question below and receive verified answers with exact timestamps from this video.
                </p>
              </div>
            </div>

            {/* Quick Prompt Chips */}
            <div className="quick-chips">
              <button
                type="button"
                className="chip-btn"
                onClick={() => {
                  const q = 'What are the main concepts and takeaways explained in this video?'
                  setQuestion(q)
                  handleAskQuestion(undefined, q)
                }}
              >
                ⚡ Main Concepts
              </button>
              <button
                type="button"
                className="chip-btn"
                onClick={() => {
                  const q = 'What is the conclusion or final result of this video?'
                  setQuestion(q)
                  handleAskQuestion(undefined, q)
                }}
              >
                🏁 Final Conclusion
              </button>
              <button
                type="button"
                className="chip-btn"
                onClick={() => {
                  const q = 'Can you give a step-by-step breakdown of the process discussed?'
                  setQuestion(q)
                  handleAskQuestion(undefined, q)
                }}
              >
                📋 Step-by-Step Breakdown
              </button>
            </div>

            <form onSubmit={e => handleAskQuestion(e)} className="question-form">
              <textarea
                value={question}
                onChange={e => setQuestion(e.target.value)}
                placeholder={`Ask anything about "${activeTitle}"... (e.g. What did the speaker say about...?)`}
                rows={2}
                disabled={asking}
              />
              <button className="ask-btn" disabled={asking || !question.trim()}>
                {asking ? 'Thinking…' : 'Ask AI'}
              </button>
            </form>

            {/* Q&A Stream / History */}
            {qaHistory.length > 0 && (
              <div className="qa-history">
                {qaHistory.map((item, idx) => (
                  <article key={idx} className={`answer ${item.grounded ? 'grounded' : ''}`}>
                    <div className="user-q-bubble">
                      <strong>You asked:</strong> {item.question}
                    </div>
                    <div className="answer-label">
                      {item.grounded ? '✅ GROUNDED FROM THIS VIDEO' : '⚠️ NO VERIFIED SOURCE'}
                    </div>
                    {item.grounded && item.confidence !== undefined && (
                      <div className="answer-metrics">
                        <span>Confidence {Math.round(item.confidence * 100)}%</span>
                        {item.citation_coverage !== undefined && (
                          <span>Coverage {Math.round(item.citation_coverage * 100)}%</span>
                        )}
                      </div>
                    )}
                    <p>{item.answer}</p>

                    {item.sources.length > 0 && (
                      <div className="sources">
                        <h3>Verified Sources &amp; Timestamps:</h3>
                        {item.sources.map(src => (
                          <details key={src.citation}>
                            <summary>
                              {src.citation} · Timestamp {Math.round(Number(src.metadata.start_ms ?? 0) / 1000)}s
                            </summary>
                            <button
                              type="button"
                              className="citation-button"
                              onClick={() => void playSourceCitation(src)}
                            >
                              🔊 Play from {Math.round(Number(src.metadata.start_ms ?? 0) / 1000)}s
                            </button>
                            <p>{src.text}</p>
                          </details>
                        ))}
                      </div>
                    )}
                  </article>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
    </section>
  )
}
