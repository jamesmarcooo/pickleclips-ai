'use client'

import { useEffect, useRef, useState } from 'react'
import { createClient } from '@/lib/supabase'

const STEPS = [
  { key: 'uploading', label: 'Upload', activeLabel: 'Uploading…' },
  { key: 'identifying', label: 'Identify player', activeLabel: 'Identify player' },
  { key: 'processing', label: 'Analyze game', activeLabel: 'Analyzing…' },
  { key: 'analyzed', label: 'Ready', activeLabel: 'Ready' },
]

const STEP_INDEX: Record<string, number> = {
  uploading: 0,
  identifying: 1,
  confirming: 1,
  processing: 2,
  analyzed: 3,
}

function formatBytes(bytes: number): string {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

const STATIC_DETAIL: Record<string, string> = {
  uploading: 'Upload in progress…',
  identifying: 'Waiting for player identification',
  confirming: 'Waiting for player confirmation',
  analyzed: 'Analysis complete!',
  failed: 'Processing failed',
  timed_out: 'Timed out — please re-upload',
}

interface Props {
  videoId: string
  initialStatus: string
  durationSeconds?: number | null
  onAnalyzed: () => void
}

function formatElapsed(seconds: number): string {
  if (seconds < 60) return `${seconds}s`
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return s === 0 ? `${m}m` : `${m}m ${s}s`
}

function processingDetail(elapsed: number, durationSeconds?: number | null): string {
  const elapsedStr = formatElapsed(elapsed)

  if (!durationSeconds) {
    return `Analyzing your game… ${elapsed > 0 ? `(${elapsedStr} elapsed)` : ''}`
  }

  // Rough estimate: ~1s of processing per 2s of video on CPU (YOLOv8 @ 2fps)
  const estimateSecs = Math.round(durationSeconds * 0.5)
  const remaining = Math.max(0, estimateSecs - elapsed)

  if (elapsed === 0) {
    return `Analyzing your game… estimated ${formatElapsed(estimateSecs)}`
  }
  if (remaining > 5) {
    return `Analyzing your game… ~${formatElapsed(remaining)} remaining (${elapsedStr} elapsed)`
  }
  return `Wrapping up… (${elapsedStr} elapsed)`
}

export function ProcessingStatus({ videoId, initialStatus, durationSeconds, onAnalyzed }: Props) {
  const [status, setStatus] = useState(initialStatus)
  const [elapsed, setElapsed] = useState(0)
  const [uploadProgress, setUploadProgress] = useState<{ uploaded: number; total: number } | null>(null)
  const processingStartRef = useRef<number | null>(initialStatus === 'processing' ? Date.now() : null)
  const onAnalyzedRef = useRef(onAnalyzed)
  onAnalyzedRef.current = onAnalyzed

  // Poll sessionStorage for upload progress while in 'uploading' state
  useEffect(() => {
    if (status !== 'uploading') return
    const id = setInterval(() => {
      const raw = sessionStorage.getItem(`upload_progress_${videoId}`)
      if (raw) setUploadProgress(JSON.parse(raw))
    }, 500)
    return () => clearInterval(id)
  }, [status, videoId])

  // Elapsed timer — only ticks while in 'processing' state
  useEffect(() => {
    if (status !== 'processing') return
    if (!processingStartRef.current) processingStartRef.current = Date.now()
    const id = setInterval(() => {
      setElapsed(Math.floor((Date.now() - processingStartRef.current!) / 1000))
    }, 1000)
    return () => clearInterval(id)
  }, [status])

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

  if (status === 'failed' || status === 'timed_out') {
    return (
      <div className="p-4 bg-red-50 border border-red-200 rounded-lg">
        <p className="text-sm text-red-600">{STATIC_DETAIL[status]}</p>
      </div>
    )
  }

  const currentStep = STEP_INDEX[status] ?? 0
  const isActive = !['analyzed', 'failed', 'timed_out'].includes(status)
  let detail: string
  if (status === 'processing') {
    detail = processingDetail(elapsed, durationSeconds)
  } else if (status === 'uploading' && uploadProgress) {
    const pct = Math.round((uploadProgress.uploaded / uploadProgress.total) * 100)
    detail = `Uploading… ${formatBytes(uploadProgress.uploaded)} / ${formatBytes(uploadProgress.total)} (${pct}%)`
  } else {
    detail = STATIC_DETAIL[status] || status
  }

  return (
    <div className="p-4 bg-gray-800 border border-gray-700 rounded-lg space-y-4">
      {/* Step indicators */}
      <div className="flex items-center gap-0">
        {STEPS.map((step, i) => {
          const done = currentStep > i
          const active = currentStep === i
          const isLast = i === STEPS.length - 1
          return (
            <div key={step.key} className="flex items-center flex-1 last:flex-none">
              <div className="flex flex-col items-center gap-1">
                <div
                  className={`w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold border-2 transition-colors ${
                    done
                      ? 'bg-blue-500 border-blue-500 text-white'
                      : active
                      ? 'bg-transparent border-blue-400 text-blue-400'
                      : 'bg-transparent border-gray-600 text-gray-600'
                  }`}
                >
                  {done ? '✓' : i + 1}
                </div>
                <span
                  className={`text-xs whitespace-nowrap ${
                    done ? 'text-blue-400' : active ? 'text-white' : 'text-gray-500'
                  }`}
                >
                  {active ? step.activeLabel : step.label}
                </span>
              </div>
              {!isLast && (
                <div
                  className={`flex-1 h-0.5 mb-4 mx-1 transition-colors ${
                    done ? 'bg-blue-500' : 'bg-gray-600'
                  }`}
                />
              )}
            </div>
          )
        })}
      </div>

      {/* Status detail + spinner */}
      <div className="flex items-center gap-2">
        {isActive && (
          <div className="w-3.5 h-3.5 border-2 border-blue-400 border-t-transparent rounded-full animate-spin flex-shrink-0" />
        )}
        <p className="text-sm text-gray-300">{detail}</p>
      </div>
    </div>
  )
}
