'use client'

export const dynamic = 'force-dynamic'

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
      if (!data.session) {
        router.push('/login')
      } else {
        setToken(data.session.access_token)
      }
    })
  }, [])

  if (!token) return <div className="p-8 text-center">Loading...</div>

  return (
    <div className="max-w-2xl mx-auto p-8">
      <h1 className="text-2xl font-bold mb-6">Upload Game</h1>
      <UploadZone
        token={token}
        onUploadComplete={(videoId) => router.push(`/videos/${videoId}/identify`)}
      />
    </div>
  )
}
