'use client'

import { useState } from 'react'

interface BBox {
  x: number
  y: number
  w: number
  h: number
}

interface Props {
  frameUrl: string
  bboxes: BBox[]
  onSelect: (index: number) => void
  isSubmitting: boolean
}

export function PlayerIdentify({ frameUrl, bboxes, onSelect, isSubmitting }: Props) {
  const [selected, setSelected] = useState<number | null>(null)
  const [imgSize, setImgSize] = useState({ w: 0, h: 0, naturalW: 0, naturalH: 0 })

  const scaleX = imgSize.w / (imgSize.naturalW || 1)
  const scaleY = imgSize.h / (imgSize.naturalH || 1)

  return (
    <div>
      <p className="text-gray-600 mb-4">Tap on yourself in the frame below.</p>
      <div className="relative inline-block">
        <img
          src={frameUrl}
          alt="Seed frame"
          className="max-w-full rounded-lg"
          onLoad={(e) => {
            const img = e.currentTarget
            setImgSize({ w: img.width, h: img.height, naturalW: img.naturalWidth, naturalH: img.naturalHeight })
          }}
        />
        {bboxes.map((bbox, i) => (
          <button
            key={i}
            onClick={() => setSelected(i)}
            style={{
              position: 'absolute',
              left: bbox.x * scaleX,
              top: bbox.y * scaleY,
              width: bbox.w * scaleX,
              height: bbox.h * scaleY,
              border: selected === i ? '3px solid #22c55e' : '2px solid #3b82f6',
              background: selected === i ? 'rgba(34,197,94,0.15)' : 'rgba(59,130,246,0.1)',
              borderRadius: 4,
              cursor: 'pointer',
            }}
          />
        ))}
      </div>
      <button
        className="mt-4 px-6 py-2 bg-green-600 text-white rounded-lg disabled:opacity-50"
        disabled={selected === null || isSubmitting}
        onClick={() => selected !== null && onSelect(selected)}
      >
        {isSubmitting ? 'Processing...' : "That's me"}
      </button>
    </div>
  )
}
