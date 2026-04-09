'use client'

import { useState } from 'react'
import { api } from '@/lib/api'

interface Reel {
  id: string
  output_type: string
  format: string
  status: 'queued' | 'generating' | 'ready' | 'failed'
  duration_seconds: number | null
  auto_generated: boolean
  download_url?: string
  share_url?: string
}

interface Props {
  reel: Reel
  token: string
}

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

const STATUS_STYLES: Record<string, string> = {
  queued: 'bg-gray-600 text-gray-200',
  generating: 'bg-yellow-600 text-yellow-100 animate-pulse',
  ready: 'bg-green-700 text-green-100',
  failed: 'bg-red-700 text-red-100',
}

export function ReelCard({ reel, token }: Props) {
  const [shareUrl, setShareUrl] = useState<string | null>(reel.share_url ?? null)
  const [sharing, setSharing] = useState(false)
  const [copied, setCopied] = useState(false)

  async function handleShare() {
    if (shareUrl) {
      await navigator.clipboard.writeText(shareUrl)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
      return
    }
    setSharing(true)
    try {
      const result = await api.shareReel(token, reel.id)
      setShareUrl(result.share_url)
      await navigator.clipboard.writeText(result.share_url)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } finally {
      setSharing(false)
    }
  }

  const label = OUTPUT_TYPE_LABELS[reel.output_type] ?? reel.output_type
  const duration = reel.duration_seconds ? `${Math.round(reel.duration_seconds)}s` : null

  return (
    <div className="bg-gray-800 border border-gray-700 rounded-lg p-4 flex flex-col gap-3">
      <div className="flex items-start justify-between gap-2">
        <div>
          <h3 className="font-semibold text-white text-sm">{label}</h3>
          <p className="text-gray-400 text-xs mt-1 capitalize">
            {reel.format}{duration ? ` · ${duration}` : ''}
            {reel.auto_generated ? ' · Auto-generated' : ''}
          </p>
        </div>
        <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${STATUS_STYLES[reel.status]}`}>
          {reel.status}
        </span>
      </div>

      {reel.status === 'ready' && (
        <div className="flex gap-2">
          {reel.download_url && (
            <a
              href={reel.download_url}
              download
              className="flex-1 text-center px-3 py-1.5 bg-blue-600 hover:bg-blue-500 text-white text-sm rounded transition-colors"
            >
              Download
            </a>
          )}
          <button
            onClick={handleShare}
            disabled={sharing}
            className="flex-1 px-3 py-1.5 bg-gray-700 hover:bg-gray-600 text-white text-sm rounded transition-colors"
          >
            {copied ? 'Copied!' : sharing ? 'Getting link…' : shareUrl ? 'Copy link' : 'Share'}
          </button>
        </div>
      )}

      {reel.status === 'generating' && (
        <p className="text-yellow-400 text-xs">Assembling reel…</p>
      )}

      {reel.status === 'failed' && (
        <p className="text-red-400 text-xs">Reel generation failed.</p>
      )}
    </div>
  )
}
