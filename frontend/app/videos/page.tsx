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
      if (!data.session) return router.push('/login')
      const t = data.session.access_token
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
          const video = v as { id: string; status: string; uploaded_at: string }
          return (
            <Link key={video.id} href={`/videos/${video.id}`} className="block border rounded-lg p-4 hover:bg-gray-50">
              <div className="flex justify-between">
                <span className="font-medium">Game — {new Date(video.uploaded_at).toLocaleDateString()}</span>
                <span className={`text-sm px-2 py-1 rounded ${
                  video.status === 'analyzed' ? 'bg-green-100 text-green-700' :
                  video.status === 'failed' ? 'bg-red-100 text-red-600' :
                  'bg-yellow-100 text-yellow-700'
                }`}>{video.status}</span>
              </div>
            </Link>
          )
        })}
      </div>
    </div>
  )
}
