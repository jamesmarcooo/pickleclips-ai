'use client'

export const dynamic = 'force-dynamic'

import { useEffect, useState } from 'react'
import { useRouter, useParams } from 'next/navigation'
import Link from 'next/link'
import { createClient } from '@/lib/supabase'
import { api } from '@/lib/api'
import { ProcessingStatus } from '@/components/ProcessingStatus'
import { ClipCard } from '@/components/ClipCard'
import { FeedbackButtons } from '@/components/FeedbackButtons'

type Tab = 'highlights' | 'lowlights'

export default function VideoPage() {
  const params = useParams()
  const videoId = params.id as string
  const router = useRouter()

  const [token, setToken] = useState<string | null>(null)
  const [video, setVideo] = useState<{ status: string; duration_seconds?: number | null } | null>(null)
  const [highlights, setHighlights] = useState<object[]>([])
  const [lowlights, setLowlights] = useState<object[]>([])
  const [activeTab, setActiveTab] = useState<Tab>('highlights')
  const [downloadingZip, setDownloadingZip] = useState(false)
  const [retrying, setRetrying] = useState(false)
  const [actionError, setActionError] = useState<string | null>(null)

  useEffect(() => {
    const supabase = createClient()
    supabase.auth.getSession().then(async ({ data }) => {
      const t = localStorage.getItem('dev_token') ?? data.session?.access_token
      if (!t) return router.push('/login')
      setToken(t)
      const v = await api.getVideo(t, videoId)
      setVideo(v as { status: string; duration_seconds?: number | null })
      if ((v as { status: string }).status === 'analyzed') {
        await loadClips(t)
      }
      if ((v as { status: string }).status === 'identifying') {
        router.push(`/videos/${videoId}/identify`)
      }
    })
  }, [videoId, router])

  async function loadClips(t: string) {
    const [h, l] = await Promise.all([
      api.listHighlights(t, videoId),
      api.listLowlights(t, videoId),
    ])
    setHighlights(h)
    setLowlights(l)
    setVideo((v) => v ? { ...v, status: 'analyzed' } : v)
  }

  async function onAnalyzed() {
    if (token) await loadClips(token)
  }

  async function handleDownloadZip() {
    if (!token) return
    setActionError(null)
    setDownloadingZip(true)
    try {
      const blob = await api.downloadClipsZip(token, videoId)
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `clips_${videoId.slice(0, 8)}.zip`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      window.URL.revokeObjectURL(url)
    } catch (e: unknown) {
      setActionError(e instanceof Error ? e.message : 'Download failed')
    } finally {
      setDownloadingZip(false)
    }
  }

  async function handleRetry() {
    if (!token) return
    setRetrying(true)
    try {
      const result = await api.retryPipeline(token, videoId)
      if (result.status === 'identifying') {
        router.push(`/videos/${videoId}/identify`)
      } else {
        setVideo((v) => v ? { ...v, status: 'processing' } : v)
      }
    } finally {
      setRetrying(false)
    }
  }

  if (!video || !token) return <div className="p-8 text-gray-400">Loading…</div>

  const tabs: { id: Tab; label: string; count: number }[] = [
    { id: 'highlights', label: 'Highlights', count: highlights.length },
    { id: 'lowlights', label: 'Points of Improvement', count: lowlights.length },
  ]

  return (
    <div className="max-w-4xl mx-auto p-8">
      <div className="flex items-center justify-between mb-6">
        <div className="flex items-center gap-4">
          <Link href="/videos" className="text-gray-400 hover:text-white text-sm">← Back</Link>
          <h1 className="text-2xl font-bold">Your Game</h1>
        </div>
        {video.status === 'analyzed' && (
          <Link
            href={`/videos/${videoId}/reels`}
            className="px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded transition-colors"
          >
            View Reels
          </Link>
        )}
      </div>

      <ProcessingStatus
        videoId={videoId}
        initialStatus={video.status}
        durationSeconds={video.duration_seconds}
        onAnalyzed={onAnalyzed}
      />

      {(video.status === 'failed' || video.status === 'processing') && (
        <div className="mt-3 flex items-center gap-3">
          {video.status === 'failed' && (
            <p className="text-sm text-red-400">Processing failed.</p>
          )}
          <button
            onClick={handleRetry}
            disabled={retrying}
            className="text-sm px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white rounded disabled:opacity-50"
          >
            {retrying ? 'Retrying…' : 'Retry'}
          </button>
        </div>
      )}

      {video.status === 'analyzed' && (
        <>
          {/* Tab bar */}
          <div className="flex border-b border-gray-700 mb-6 mt-6">
            {tabs.map((tab) => (
              <button
                key={tab.id}
                onClick={() => setActiveTab(tab.id)}
                className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
                  activeTab === tab.id
                    ? 'border-blue-500 text-white'
                    : 'border-transparent text-gray-400 hover:text-gray-200'
                }`}
              >
                {tab.label}
                {tab.count > 0 && (
                  <span className="ml-2 bg-gray-700 text-gray-300 text-xs px-1.5 py-0.5 rounded-full">
                    {tab.count}
                  </span>
                )}
              </button>
            ))}
          </div>

          {/* Highlights tab */}
          {activeTab === 'highlights' && (
            highlights.length > 0 ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {highlights.map((h) => {
                  const hi = h as { id: string; highlight_score: number; start_time_ms: number; end_time_ms: number; shot_type: string | null; rally_length: number; user_feedback: 'liked' | 'disliked' | null }
                  return (
                    <div key={hi.id} className="flex flex-col gap-2">
                      <ClipCard highlight={hi} token={token} />
                      <FeedbackButtons
                        highlightId={hi.id}
                        initialFeedback={hi.user_feedback}
                        token={token}
                      />
                    </div>
                  )
                })}
              </div>
            ) : (
              <p className="text-gray-500">No highlights detected in this game.</p>
            )
          )}

          {/* Points of Improvement tab */}
          {activeTab === 'lowlights' && (
            lowlights.length > 0 ? (
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                {lowlights.map((l) => {
                  const li = l as { id: string; highlight_score: number; start_time_ms: number; end_time_ms: number; shot_type: string | null; rally_length: number; user_feedback: 'liked' | 'disliked' | null }
                  return (
                    <div key={li.id} className="flex flex-col gap-2">
                      <ClipCard highlight={li} token={token} />
                      <FeedbackButtons
                        highlightId={li.id}
                        initialFeedback={li.user_feedback}
                        token={token}
                      />
                    </div>
                  )
                })}
              </div>
            ) : (
              <p className="text-gray-500">No errors or weak shots detected.</p>
            )
          )}


          <div className="mt-6 space-y-3">
            <div className="flex gap-3">
              {highlights.length > 0 && (
                <button
                  onClick={handleDownloadZip}
                  disabled={downloadingZip}
                  className="px-4 py-2 bg-green-600 text-white rounded disabled:opacity-50"
                >
                  {downloadingZip ? 'Preparing ZIP…' : 'Download ZIP'}
                </button>
              )}
            </div>
            {actionError && (
              <p className="text-sm text-red-400">{actionError}</p>
            )}
          </div>
        </>
      )}
    </div>
  )
}
