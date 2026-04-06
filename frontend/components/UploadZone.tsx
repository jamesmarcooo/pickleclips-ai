'use client'

import { useEffect, useRef } from 'react'
import Uppy from '@uppy/core'
// @uppy/aws-s3 v5 (Uppy core v5) replaces the legacy @uppy/aws-s3-multipart package.
// Multipart uploads are enabled via shouldUseMultipart: true.
import AwsS3 from '@uppy/aws-s3'
import Dashboard from '@uppy/dashboard'
import '@uppy/core/css/style.min.css'
import '@uppy/dashboard/css/style.min.css'
import { api } from '@/lib/api'

const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

interface Props {
  token: string
  onUploadComplete: (videoId: string) => void
}

export function UploadZone({ token, onUploadComplete }: Props) {
  const containerRef = useRef<HTMLDivElement>(null)
  const videoIdRef = useRef<string | null>(null)
  // Store callback in ref so useEffect doesn't recreate the Uppy instance when the
  // parent re-renders and passes a new inline function reference.
  const onUploadCompleteRef = useRef(onUploadComplete)
  onUploadCompleteRef.current = onUploadComplete

  useEffect(() => {
    if (!containerRef.current) return

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const s3Opts: any = {
      shouldUseMultipart: true,
      async createMultipartUpload(file: { name: string }) {
        const result = await api.createMultipartUpload(token, file.name)
        videoIdRef.current = result.video_id
        return { uploadId: result.upload_id, key: result.key }
      },
      async signPart(
        _file: unknown,
        { uploadId, key, partNumber }: { uploadId: string; key: string; partNumber: number },
      ) {
        const result = await api.signMultipartPart(token, key, uploadId, partNumber)
        return { url: result.url }
      },
      async completeMultipartUpload(
        _file: unknown,
        { uploadId, key, parts }: { uploadId: string; key: string; parts: object[] },
      ) {
        await api.completeMultipartUpload(token, key, uploadId, parts)
        return { location: key }
      },
      async abortMultipartUpload(
        _file: unknown,
        { uploadId, key }: { uploadId: string; key: string },
      ) {
        await fetch(
          `${API_BASE}/api/v1/videos/multipart/abort?key=${encodeURIComponent(key)}&upload_id=${uploadId}`,
          {
            method: 'DELETE',
            headers: { Authorization: `Bearer ${token}` },
          },
        )
      },
      // listParts returns [] — upload resume on page reload is not supported in Phase 1.
      // eslint-disable-next-line @typescript-eslint/no-unused-vars
      async listParts(_file: unknown, _opts: { uploadId: string; key: string }) {
        return []
      },
    }

    const uppy = new Uppy({
      restrictions: {
        maxFileSize: 6 * 1024 * 1024 * 1024, // 6GB
        allowedFileTypes: ['video/mp4', 'video/quicktime', 'video/x-msvideo'],
        maxNumberOfFiles: 1,
      },
    })

    uppy.use(Dashboard, {
      inline: true,
      target: containerRef.current,
      proudlyDisplayPoweredByUppy: false,
      note: 'Upload your pickleball game video (MP4, up to 6GB)',
      height: 400,
    })

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    ;(uppy as any).use(AwsS3, s3Opts)

    uppy.on('complete', async () => {
      const videoId = videoIdRef.current
      if (!videoId) return
      await api.confirmUpload(token, videoId)
      onUploadCompleteRef.current(videoId)
    })

    return () => uppy.destroy()
  // token is the only dependency that should recreate the Uppy instance (auth changed).
  // onUploadComplete is read via ref to avoid recreation on every parent render.
  }, [token]) // eslint-disable-line react-hooks/exhaustive-deps

  return <div ref={containerRef} className="w-full" />
}
