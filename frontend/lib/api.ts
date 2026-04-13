const API_BASE = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000'

async function apiFetch<T>(path: string, options: RequestInit = {}, token?: string): Promise<T> {
  const headers: HeadersInit = {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
    ...options.headers,
  }
  const res = await fetch(`${API_BASE}${path}`, { ...options, headers })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: 'Unknown error' }))
    throw new Error(err.detail || `HTTP ${res.status}`)
  }
  return res.json()
}

export const api = {
  createMultipartUpload: (token: string, filename: string) =>
    apiFetch<{ video_id: string; upload_id: string; key: string }>(
      '/api/v1/videos/multipart/create',
      { method: 'POST', body: JSON.stringify({ filename, content_type: 'video/mp4' }) },
      token
    ),

  signMultipartPart: (token: string, key: string, uploadId: string, partNumber: number) =>
    apiFetch<{ url: string }>(
      `/api/v1/videos/multipart/sign-part?key=${encodeURIComponent(key)}&upload_id=${uploadId}&part_number=${partNumber}`,
      {},
      token
    ),

  completeMultipartUpload: (token: string, key: string, uploadId: string, parts: object[]) =>
    apiFetch('/api/v1/videos/multipart/complete', {
      method: 'POST',
      body: JSON.stringify({ key, upload_id: uploadId, parts }),
    }, token),

  confirmUpload: (token: string, videoId: string) =>
    apiFetch(`/api/v1/videos/${videoId}/confirm`, { method: 'POST' }, token),

  listVideos: (token: string) =>
    apiFetch<object[]>('/api/v1/videos', {}, token),

  getVideo: (token: string, videoId: string) =>
    apiFetch<object>(`/api/v1/videos/${videoId}`, {}, token),

  getIdentifyFrame: (token: string, videoId: string) =>
    apiFetch<{ frame_url: string; bboxes: object[] }>(`/api/v1/videos/${videoId}/identify`, {}, token),

  tapIdentify: (token: string, videoId: string, bboxIndex: number) =>
    apiFetch(`/api/v1/videos/${videoId}/identify`, {
      method: 'POST',
      body: JSON.stringify({ bbox_index: bboxIndex }),
    }, token),

  listHighlights: (token: string, videoId: string) =>
    apiFetch<object[]>(`/api/v1/videos/${videoId}/highlights`, {}, token),

  getClipDownloadUrl: (token: string, highlightId: string) =>
    apiFetch<{ download_url: string }>(`/api/v1/highlights/${highlightId}/download`, {}, token),

  listLowlights: (token: string, videoId: string) =>
    apiFetch<object[]>(`/api/v1/videos/${videoId}/lowlights`, {}, token),

  updateHighlightFeedback: (token: string, highlightId: string, feedback: 'liked' | 'disliked' | null) =>
    apiFetch(`/api/v1/highlights/${highlightId}`, {
      method: 'PATCH',
      body: JSON.stringify({ user_feedback: feedback }),
    }, token),

  downloadClipsZip: async (token: string, videoId: string): Promise<Blob> => {
    const res = await fetch(`${API_BASE}/api/v1/videos/${videoId}/clips/download-zip`, {
      headers: { Authorization: `Bearer ${token}` },
    })
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: 'Unknown error' }))
      throw new Error(err.detail || `HTTP ${res.status}`)
    }
    return res.blob()
  },

  confirmIdentity: (token: string, videoId: string, confirmed: boolean) =>
    apiFetch<{ status: string; auto_recognized?: boolean; bboxes?: object[] }>(
      `/api/v1/videos/${videoId}/confirm-identity`,
      { method: 'POST', body: JSON.stringify({ confirmed }) },
      token
    ),

  retryPipeline: (token: string, videoId: string) =>
    apiFetch<{ status: string; video_id: string; message?: string }>(
      `/api/v1/videos/${videoId}/retry`,
      { method: 'POST' },
      token
    ),

  generateReels: (token: string, videoId: string) =>
    apiFetch<{ status: string; video_id: string }>(
      `/api/v1/videos/${videoId}/generate-reels`,
      { method: 'POST' },
      token
    ),

  listReels: (token: string, videoId: string) =>
    apiFetch<object[]>(`/api/v1/videos/${videoId}/reels`, {}, token),

  createReel: (token: string, videoId: string, outputType: string, format: string = 'horizontal') =>
    apiFetch<{ id: string; status: string; output_type: string }>(
      '/api/v1/reels',
      { method: 'POST', body: JSON.stringify({ video_id: videoId, output_type: outputType, format }) },
      token
    ),

  getReel: (token: string, reelId: string) =>
    apiFetch<object>(`/api/v1/reels/${reelId}`, {}, token),

  shareReel: (token: string, reelId: string) =>
    apiFetch<{ share_url: string; share_token: string }>(
      `/api/v1/reels/${reelId}/share`,
      { method: 'POST' },
      token
    ),
}
