'use client'

import { useState } from 'react'
import { api } from '@/lib/api'

interface Props {
  highlightId: string
  initialFeedback: 'liked' | 'disliked' | null
  token: string
}

export function FeedbackButtons({ highlightId, initialFeedback, token }: Props) {
  const [feedback, setFeedback] = useState<'liked' | 'disliked' | null>(initialFeedback)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  async function handleFeedback(value: 'liked' | 'disliked') {
    if (loading) return
    setError(null)  // clear previous error
    const previous = feedback
    const next = previous === value ? null : value
    setFeedback(next)  // optimistic update
    setLoading(true)
    try {
      await api.updateHighlightFeedback(token, highlightId, next)
    } catch {
      setFeedback(previous)
      setError('Could not save. Try again.')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <div className="flex gap-2 items-center">
        <button
          onClick={() => handleFeedback('liked')}
          disabled={loading}
          className={`px-3 py-1 rounded text-sm transition-colors ${
            feedback === 'liked'
              ? 'bg-green-600 text-white'
              : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
          }`}
          aria-label="Mark as liked"
          aria-pressed={feedback === 'liked'}
        >
          👍
        </button>
        <button
          onClick={() => handleFeedback('disliked')}
          disabled={loading}
          className={`px-3 py-1 rounded text-sm transition-colors ${
            feedback === 'disliked'
              ? 'bg-red-600 text-white'
              : 'bg-gray-700 text-gray-300 hover:bg-gray-600'
          }`}
          aria-label="Mark as disliked"
          aria-pressed={feedback === 'disliked'}
        >
          👎
        </button>
      </div>
      {error && <p className="text-xs text-red-500 mt-1">{error}</p>}
    </div>
  )
}
