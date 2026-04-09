'use client'

export const dynamic = 'force-dynamic'

import { useEffect, useState } from 'react'
import { useRouter, useParams } from 'next/navigation'
import { createClient } from '@/lib/supabase'
import { api } from '@/lib/api'

const OUTPUT_TYPE_LABELS: Record<string, string> = {
  highlight_montage: 'Highlight Montage',
  my_best_plays: 'My Best Plays',
  game_recap: 'Game Recap',
  points_of_improvement: 'Points of Improvement',
  best_shots: 'Best Shots',
  scored_point_rally: 'Scored Point Rally',
  full_rally_replay: 'Full Rally Replay',
  single_shot_clip: 'Single Shot Clip',
}

interface ReelDetail {
  id: string
  output_type: string
  format: string
  status: string
  duration_seconds: number | null
  download_url?: string
  share_url?: string
}

export default function ReelPage() {
  const params = useParams()
  const reelId = params.id as string
  const router = useRouter()

  const [token, setToken] = useState<string | null>(null)
  const [reel, setReel] = useState<ReelDetail | null>(null)
  const [shareUrl, setShareUrl] = useState<string | null>(null)
  const [copied, setCopied] = useState(false)
  const [sharing, setSharing] = useState(false)

  useEffect(() => {
    const supabase = createClient()
    supabase.auth.getSession().then(async ({ data }) => {
      if (!data.session) return router.push('/login')
      const t = data.session.access_token
      setToken(t)
      const r = await api.getReel(t, reelId)
      const rd = r as ReelDetail
      setReel(rd)
      if (rd.share_url) setShareUrl(rd.share_url)
    })
  }, [reelId, router])

  async function handleShare() {
    if (!token || !reel) return
    if (shareUrl) {
      await navigator.clipboard.writeText(shareUrl)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
      return
    }
    setSharing(true)
    try {
      const result = await api.shareReel(token, reelId)
      setShareUrl(result.share_url)
      await navigator.clipboard.writeText(result.share_url)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } finally {
      setSharing(false)
    }
  }

  if (!reel || !token) return <div className="p-8 text-gray-400">Loading…</div>

  const label = OUTPUT_TYPE_LABELS[reel.output_type] ?? reel.output_type
  const isVertical = reel.format === 'vertical'

  return (
    <div className="max-w-2xl mx-auto p-8">
      <button
        onClick={() => router.back()}
        className="text-gray-400 hover:text-white text-sm mb-6 block"
      >
        ← Back
      </button>

      <h1 className="text-2xl font-bold mb-1">{label}</h1>
      <p className="text-gray-400 text-sm mb-6 capitalize">
        {reel.format}
        {reel.duration_seconds ? ` · ${Math.round(reel.duration_seconds)}s` : ''}
      </p>

      {/* Video player (only when ready) */}
      {reel.status === 'ready' && reel.download_url && (
        <div className={`mb-6 bg-black rounded-lg overflow-hidden ${isVertical ? 'max-w-xs mx-auto' : ''}`}>
          <video
            src={reel.download_url}
            controls
            autoPlay={false}
            className="w-full"
          />
        </div>
      )}

      {reel.status === 'generating' && (
        <div className="mb-6 bg-gray-800 rounded-lg p-8 text-center">
          <p className="text-yellow-400 animate-pulse">Assembling your reel…</p>
          <p className="text-gray-500 text-sm mt-2">Usually takes 1–2 minutes.</p>
        </div>
      )}

      {reel.status === 'queued' && (
        <div className="mb-6 bg-gray-800 rounded-lg p-8 text-center">
          <p className="text-gray-400">Reel is queued and will start shortly.</p>
        </div>
      )}

      {reel.status === 'failed' && (
        <div className="mb-6 bg-red-900/40 border border-red-700 rounded-lg p-6 text-center">
          <p className="text-red-400">Reel generation failed. Try regenerating.</p>
        </div>
      )}

      {/* Action buttons */}
      {reel.status === 'ready' && (
        <div className="flex gap-3">
          {reel.download_url && (
            <a
              href={reel.download_url}
              download
              className="flex-1 text-center px-4 py-2 bg-blue-600 hover:bg-blue-500 text-white rounded transition-colors"
            >
              Download
            </a>
          )}
          <button
            onClick={handleShare}
            disabled={sharing}
            className="flex-1 px-4 py-2 bg-gray-700 hover:bg-gray-600 text-white rounded transition-colors"
          >
            {copied ? 'Link copied!' : sharing ? 'Getting link…' : shareUrl ? 'Copy share link' : 'Share'}
          </button>
        </div>
      )}
    </div>
  )
}
