'use client'

export const dynamic = 'force-dynamic'

import { useEffect, useState } from 'react'
import { useRouter, useParams } from 'next/navigation'
import { createClient } from '@/lib/supabase'
import { api } from '@/lib/api'
import { ProcessingStatus } from '@/components/ProcessingStatus'
import { ClipCard } from '@/components/ClipCard'

export default function VideoPage() {
  const params = useParams()
  const videoId = params.id as string
  const router = useRouter()
  const [token, setToken] = useState<string | null>(null)
  const [video, setVideo] = useState<{ status: string } | null>(null)
  const [highlights, setHighlights] = useState<object[]>([])

  useEffect(() => {
    const supabase = createClient()
    supabase.auth.getSession().then(async ({ data }) => {
      if (!data.session) return router.push('/login')
      const t = data.session.access_token
      setToken(t)
      const v = await api.getVideo(t, videoId)
      setVideo(v as { status: string })
      if ((v as { status: string }).status === 'analyzed') {
        const h = await api.listHighlights(t, videoId)
        setHighlights(h)
      }
      if ((v as { status: string }).status === 'identifying') {
        router.push(`/videos/${videoId}/identify`)
      }
    })
  }, [videoId, router])

  async function loadHighlights() {
    if (!token) return
    const h = await api.listHighlights(token, videoId)
    setHighlights(h)
    setVideo((v) => v ? { ...v, status: 'analyzed' } : v)
  }

  if (!video || !token) return <div className="p-8">Loading...</div>

  return (
    <div className="max-w-4xl mx-auto p-8">
      <h1 className="text-2xl font-bold mb-4">Your Highlights</h1>
      <ProcessingStatus
        videoId={videoId}
        initialStatus={video.status}
        onAnalyzed={loadHighlights}
      />
      {highlights.length > 0 && (
        <div className="mt-8 grid grid-cols-1 sm:grid-cols-2 gap-4">
          {highlights.map((h) => (
            <ClipCard key={(h as { id: string }).id} highlight={h as { id: string; highlight_score: number; start_time_ms: number; end_time_ms: number; shot_type: string | null; rally_length: number }} token={token} />
          ))}
        </div>
      )}
      {video.status === 'analyzed' && highlights.length === 0 && (
        <p className="mt-8 text-gray-500">No highlights detected in this game.</p>
      )}
    </div>
  )
}
