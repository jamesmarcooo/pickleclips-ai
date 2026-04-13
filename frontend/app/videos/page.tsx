'use client'

export const dynamic = 'force-dynamic'

import { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import Link from 'next/link'
import { createClient } from '@/lib/supabase'
import { api } from '@/lib/api'

export default function VideosPage() {
  const router = useRouter()
  const [videos, setVideos] = useState<object[]>([])

  useEffect(() => {
    const supabase = createClient()
    supabase.auth.getSession().then(async ({ data }) => {
      const t = localStorage.getItem('dev_token') ?? data.session?.access_token
      if (!t) return router.push('/login')
      setVideos(await api.listVideos(t))
    })
  }, [router])

  return (
    <div className="max-w-4xl mx-auto p-8">
      <div className="flex justify-between items-center mb-6">
        <h1 className="text-2xl font-bold">My Games</h1>
        <Link href="/upload" className="px-4 py-2 bg-blue-600 text-white rounded-lg">
          Upload Game
        </Link>
      </div>
      {videos.length === 0 && <p className="text-gray-500">No games uploaded yet.</p>}
      <div className="space-y-3">
        {videos.map((v) => {
          const video = v as { id: string; status: string; uploaded_at: string; original_filename: string | null }
          const label = video.original_filename
            ? video.original_filename.replace(/\.[^/.]+$/, '')
            : `Game — ${new Date(video.uploaded_at).toLocaleDateString()}`

          const STATUS_LABEL: Record<string, string> = {
            uploading: 'Uploading',
            identifying: 'Identifying player',
            confirming: 'Identifying player',
            processing: 'Analyzing',
            analyzed: 'Ready',
            failed: 'Failed',
            timed_out: 'Timed out',
          }
          const STATUS_STYLE: Record<string, string> = {
            analyzed: 'bg-green-100 text-green-700',
            failed: 'bg-red-100 text-red-600',
            timed_out: 'bg-red-100 text-red-600',
          }
          const badgeStyle = STATUS_STYLE[video.status] ?? 'bg-yellow-100 text-yellow-700'
          const badgeLabel = STATUS_LABEL[video.status] ?? video.status

          return (
            <Link key={video.id} href={`/videos/${video.id}`} className="block border rounded-lg p-4 hover:bg-gray-50">
              <div className="flex justify-between items-center">
                <div>
                  <span className="font-medium">{label}</span>
                  <span className="block text-xs text-gray-400 mt-0.5">{new Date(video.uploaded_at).toLocaleDateString()}</span>
                </div>
                <span className={`text-sm px-2 py-1 rounded whitespace-nowrap ${badgeStyle}`}>{badgeLabel}</span>
              </div>
            </Link>
          )
        })}
      </div>
    </div>
  )
}
