'use client'

import { useEffect, useRef, useState } from 'react'
import { createClient } from '@/lib/supabase'

const STATUS_LABELS: Record<string, string> = {
  uploading: 'Uploading...',
  identifying: 'Waiting for player identification',
  processing: 'Analyzing your game...',
  analyzed: 'Ready!',
  failed: 'Processing failed',
  timed_out: 'Timed out — please re-upload',
}

interface Props {
  videoId: string
  initialStatus: string
  onAnalyzed: () => void
}

export function ProcessingStatus({ videoId, initialStatus, onAnalyzed }: Props) {
  const [status, setStatus] = useState(initialStatus)
  const onAnalyzedRef = useRef(onAnalyzed)
  onAnalyzedRef.current = onAnalyzed

  useEffect(() => {
    const supabase = createClient()
    const channel = supabase
      .channel(`video-${videoId}`)
      .on(
        'postgres_changes',
        { event: 'UPDATE', schema: 'public', table: 'videos', filter: `id=eq.${videoId}` },
        (payload) => {
          const newStatus = (payload.new as { status: string }).status
          setStatus((prev) => {
            if (newStatus === 'analyzed' && prev !== 'analyzed') {
              onAnalyzedRef.current()
            }
            return newStatus
          })
        }
      )
      .subscribe()

    return () => { supabase.removeChannel(channel) }
  }, [videoId])

  const isProcessing = ['uploading', 'processing'].includes(status)

  return (
    <div className="flex items-center gap-3 p-4 bg-gray-50 rounded-lg">
      {isProcessing && (
        <div className="w-4 h-4 border-2 border-blue-500 border-t-transparent rounded-full animate-spin" />
      )}
      <span className={`text-sm ${status === 'failed' ? 'text-red-600' : 'text-gray-700'}`}>
        {STATUS_LABELS[status] || status}
      </span>
    </div>
  )
}
