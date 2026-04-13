'use client'

export const dynamic = 'force-dynamic'

import { useEffect, useState } from 'react'
import { useRouter, useParams } from 'next/navigation'
import { createClient } from '@/lib/supabase'
import { api } from '@/lib/api'
import { ReelCard } from '@/components/ReelCard'

const ON_DEMAND_TYPES = [
  { id: 'best_shots', label: 'Best Shots Reel' },
  { id: 'scored_point_rally', label: 'Scored Point Rally' },
  { id: 'full_rally_replay', label: 'Full Rally Replay' },
]

export default function ReelsPage() {
  const params = useParams()
  const videoId = params.id as string
  const router = useRouter()

  const [token, setToken] = useState<string | null>(null)
  const [reels, setReels] = useState<object[]>([])
  const [generating, setGenerating] = useState<string | null>(null)

  useEffect(() => {
    const supabase = createClient()
    supabase.auth.getSession().then(async ({ data }) => {
      const t = localStorage.getItem('dev_token') ?? data.session?.access_token
      if (!t) return router.push('/login')
      setToken(t)
      const r = await api.listReels(t, videoId)
      setReels(r)
    })
  }, [videoId, router])

  async function handleGenerate(outputType: string) {
    if (!token || generating) return
    setGenerating(outputType)
    try {
      const newReel = await api.createReel(token, videoId, outputType, 'horizontal')
      setReels((prev) => [newReel, ...prev])
    } finally {
      setGenerating(null)
    }
  }

  if (!token) return <div className="p-8 text-gray-400">Loading…</div>

  const existingTypes = new Set(
    (reels as { output_type: string }[]).map((r) => r.output_type)
  )

  return (
    <div className="max-w-4xl mx-auto p-8">
      <div className="flex items-center gap-4 mb-8">
        <button
          onClick={() => router.back()}
          className="text-gray-400 hover:text-white text-sm"
        >
          ← Back
        </button>
        <h1 className="text-2xl font-bold">Reels</h1>
      </div>

      {/* Auto-generated reels */}
      {reels.length > 0 && (
        <section className="mb-8">
          <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">
            Your Reels
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            {(reels as { id: string; output_type: string; format: string; status: 'queued' | 'generating' | 'ready' | 'failed'; duration_seconds: number | null; auto_generated: boolean; download_url?: string; share_url?: string }[]).map((reel) => (
              <ReelCard key={reel.id} reel={reel} token={token} />
            ))}
          </div>
        </section>
      )}

      {/* On-demand reel generation */}
      <section>
        <h2 className="text-sm font-semibold text-gray-400 uppercase tracking-wider mb-4">
          Generate On-Demand
        </h2>
        <div className="flex flex-col gap-2">
          {ON_DEMAND_TYPES.filter((t) => !existingTypes.has(t.id)).map((type) => (
            <button
              key={type.id}
              onClick={() => handleGenerate(type.id)}
              disabled={!!generating}
              className="flex items-center justify-between px-4 py-3 bg-gray-800 hover:bg-gray-700 border border-gray-700 rounded-lg text-left transition-colors disabled:opacity-50"
            >
              <span className="text-white text-sm">{type.label}</span>
              {generating === type.id ? (
                <span className="text-yellow-400 text-xs">Queuing…</span>
              ) : (
                <span className="text-blue-400 text-xs">Generate →</span>
              )}
            </button>
          ))}
          {ON_DEMAND_TYPES.every((t) => existingTypes.has(t.id)) && (
            <p className="text-gray-500 text-sm">All reel types generated.</p>
          )}
        </div>
      </section>
    </div>
  )
}
