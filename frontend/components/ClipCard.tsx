'use client'

import { useState } from 'react'
import { api } from '@/lib/api'

interface Props {
  highlight: {
    id: string
    highlight_score: number
    start_time_ms: number
    end_time_ms: number
    shot_type: string | null
    rally_length: number
  }
  token: string
}

export function ClipCard({ highlight, token }: Props) {
  const [downloading, setDownloading] = useState(false)

  const duration = ((highlight.end_time_ms - highlight.start_time_ms) / 1000).toFixed(1)
  const startSec = (highlight.start_time_ms / 1000).toFixed(1)

  async function handleDownload() {
    setDownloading(true)
    try {
      const { download_url } = await api.getClipDownloadUrl(token, highlight.id)
      const a = document.createElement('a')
      a.href = download_url
      a.download = `clip-${highlight.id.slice(0, 8)}.mp4`
      a.click()
    } finally {
      setDownloading(false)
    }
  }

  return (
    <div className="border rounded-lg p-4 bg-white shadow-sm">
      <div className="flex justify-between items-start mb-2">
        <div>
          <span className="text-sm font-medium text-gray-900">
            {highlight.shot_type ?? 'Rally'} @ {startSec}s
          </span>
          <p className="text-xs text-gray-500">{duration}s · {highlight.rally_length} shots</p>
        </div>
        <span className="text-xs bg-green-100 text-green-700 px-2 py-1 rounded">
          Score: {(highlight.highlight_score * 100).toFixed(0)}
        </span>
      </div>
      <button
        onClick={handleDownload}
        disabled={downloading}
        className="w-full mt-2 px-4 py-2 bg-blue-600 text-white text-sm rounded disabled:opacity-50"
      >
        {downloading ? 'Getting link...' : 'Download Clip'}
      </button>
    </div>
  )
}
