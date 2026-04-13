'use client'

export const dynamic = 'force-dynamic'

import Link from 'next/link'
import { useRouter } from 'next/navigation'
import { useEffect, useState } from 'react'
import { createClient } from '@/lib/supabase'
import { UploadZone } from '@/components/UploadZone'

export default function UploadPage() {
  const [token, setToken] = useState<string | null>(null)
  const router = useRouter()
  const supabase = createClient()

  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => {
    supabase.auth.getSession().then(({ data }) => {
      const t = localStorage.getItem('dev_token') ?? data.session?.access_token
      if (!t) {
        router.push('/login')
      } else {
        setToken(t)
      }
    })
  }, [])

  if (!token) return <div className="p-8 text-center">Loading...</div>

  return (
    <div className="max-w-2xl mx-auto p-8">
      <div className="flex items-center gap-4 mb-6">
        <Link href="/videos" className="text-gray-400 hover:text-white text-sm">← Back</Link>
        <h1 className="text-2xl font-bold">Upload Game</h1>
      </div>
      <UploadZone
        token={token}
        onUploadComplete={(videoId) => router.push(`/videos/${videoId}`)}
      />
    </div>
  )
}
