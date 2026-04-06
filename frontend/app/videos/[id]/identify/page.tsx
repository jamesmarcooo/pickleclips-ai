'use client'

export const dynamic = 'force-dynamic'

import { useEffect, useState } from 'react'
import { useRouter, useParams } from 'next/navigation'
import { createClient } from '@/lib/supabase'
import { api } from '@/lib/api'
import { PlayerIdentify } from '@/components/PlayerIdentify'

export default function IdentifyPage() {
  const params = useParams()
  const videoId = params.id as string
  const router = useRouter()
  const [token, setToken] = useState<string | null>(null)
  const [frameData, setFrameData] = useState<{ frame_url: string; bboxes: object[] } | null>(null)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    const supabase = createClient()
    supabase.auth.getSession().then(async ({ data }) => {
      if (!data.session) return router.push('/login')
      const t = data.session.access_token
      setToken(t)
      try {
        const result = await api.getIdentifyFrame(t, videoId)
        setFrameData(result)
      } catch (e: unknown) {
        setError(e instanceof Error ? e.message : 'Failed to load frame')
      }
    })
  }, [videoId, router])

  async function handleSelect(index: number) {
    if (!token) return
    setSubmitting(true)
    try {
      await api.tapIdentify(token, videoId, index)
      router.push(`/videos/${videoId}`)
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to submit')
      setSubmitting(false)
    }
  }

  if (error) return <div className="p-8 text-red-600">{error}</div>
  if (!frameData) return <div className="p-8">Loading frame...</div>

  return (
    <div className="max-w-4xl mx-auto p-8">
      <h1 className="text-2xl font-bold mb-6">Identify Yourself</h1>
      <PlayerIdentify
        frameUrl={frameData.frame_url}
        bboxes={frameData.bboxes as { x: number; y: number; w: number; h: number }[]}
        onSelect={handleSelect}
        isSubmitting={submitting}
      />
    </div>
  )
}
