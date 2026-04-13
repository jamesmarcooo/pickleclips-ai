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
  const [isConfirming, setIsConfirming] = useState(false)
  const [candidateFrameUrl, setCandidateFrameUrl] = useState<string | null>(null)

  useEffect(() => {
    const supabase = createClient()
    supabase.auth.getSession().then(async ({ data }) => {
      const t = localStorage.getItem('dev_token') ?? data.session?.access_token
      if (!t) return router.push('/login')
      setToken(t)
      try {
        // Try confirming flow first; fall back to identifying
        const videoRes = await fetch(
          `${process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'}/api/v1/videos/${videoId}`,
          { headers: { Authorization: `Bearer ${t}` } }
        )
        const video = await videoRes.json()
        if (['processing', 'analyzed', 'failed', 'timed_out'].includes(video.status)) {
          // Already past identification — go back to the video page
          router.replace(`/videos/${videoId}`)
          return
        } else if (video.status === 'confirming') {
          setIsConfirming(true)
          const result = await api.getIdentifyFrame(t, videoId).catch(() => null)
          if (result) {
            setCandidateFrameUrl(result.frame_url)
            setFrameData(result)
          }
        } else {
          const result = await api.getIdentifyFrame(t, videoId)
          setFrameData(result)
        }
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

  async function handleConfirm(confirmed: boolean) {
    if (!token) return
    setSubmitting(true)
    try {
      const result = await api.confirmIdentity(token, videoId, confirmed)
      if (result.status === 'processing') {
        router.push(`/videos/${videoId}`)
      } else {
        // fell back to manual tap — re-render with 4-box UI
        setIsConfirming(false)
        setSubmitting(false)
      }
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : 'Failed to confirm')
      setSubmitting(false)
    }
  }

  if (error) return <div className="p-8 text-red-600">{error}</div>
  if (!frameData && !isConfirming) return <div className="p-8">Loading frame...</div>

  return (
    <div className="max-w-4xl mx-auto p-8">
      <h1 className="text-2xl font-bold mb-6">Identify Yourself</h1>
      {isConfirming ? (
        <div className="flex flex-col items-center gap-4">
          <p className="text-lg font-medium">We think we found you — is this you?</p>
          {candidateFrameUrl && (
            <img src={candidateFrameUrl} alt="Player candidate" className="w-48 rounded" />
          )}
          <div className="flex gap-3">
            <button
              onClick={() => handleConfirm(true)}
              disabled={submitting}
              className="px-4 py-2 bg-green-600 text-white rounded disabled:opacity-50"
            >
              Yes, that&apos;s me
            </button>
            <button
              onClick={() => handleConfirm(false)}
              disabled={submitting}
              className="px-4 py-2 bg-gray-500 text-white rounded disabled:opacity-50"
            >
              No, show me all players
            </button>
          </div>
        </div>
      ) : (
        frameData && (
          <PlayerIdentify
            frameUrl={frameData.frame_url}
            bboxes={frameData.bboxes as { x: number; y: number; w: number; h: number }[]}
            onSelect={handleSelect}
            isSubmitting={submitting}
          />
        )
      )}
    </div>
  )
}
