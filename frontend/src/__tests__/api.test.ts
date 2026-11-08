import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { api, ApiError } from '../api'

describe('api', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  describe('health', () => {
    it('should call /api/health', async () => {
      const mockResponse = {
        status: 'healthy',
        version: '1.0.0',
        yt_dlp_version: '2025.1.15',
        active_downloads: 0,
        temp_dir_size_mb: 0,
      }

      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve(mockResponse),
      })

      const result = await api.health()
      expect(result.status).toBe('healthy')
      expect(fetch).toHaveBeenCalledWith('/api/health')
    })

    it('should throw ApiError on failure', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: false,
        status: 500,
        json: () => Promise.resolve({ error: 'Server error' }),
      })

      await expect(api.health()).rejects.toThrow(ApiError)
    })
  })

  describe('validateUrl', () => {
    it('should send POST request with url', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ valid: true, platform: 'youtube' }),
      })

      const result = await api.validateUrl('https://youtube.com/watch?v=test')
      expect(result.valid).toBe(true)
      expect(fetch).toHaveBeenCalledWith('/api/validate', expect.objectContaining({
        method: 'POST',
      }))
    })
  })

  describe('startDownload', () => {
    it('should send POST request with url and format', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({
        ok: true,
        json: () => Promise.resolve({ job_id: 'test-123', message: 'Started', status: 'queued' }),
      })

      const result = await api.startDownload({
        url: 'https://youtube.com/watch?v=test',
        quality: 'mp3',
      })
      expect(result.job_id).toBe('test-123')

      const callBody = JSON.parse((fetch as any).mock.calls[0][1].body)
      expect(callBody.quality).toBe('mp3')
    })
  })

  describe('cancelJob', () => {
    it('should send DELETE request', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({ ok: true })

      await api.cancelJob('test-123')
      expect(fetch).toHaveBeenCalledWith('/api/jobs/test-123', { method: 'DELETE' })
    })

    it('should throw on failure', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({ ok: false, status: 404 })

      await expect(api.cancelJob('nonexistent')).rejects.toThrow(ApiError)
    })
  })

  describe('getDownloadUrl', () => {
    it('should return correct URL', () => {
      expect(api.getDownloadUrl('test-123')).toBe('/api/jobs/test-123/download')
    })
  })

  describe('subscribeToProgress', () => {
    it('should create EventSource and return cleanup function', () => {
      const mockClose = vi.fn()
      const mockAddEventListener = vi.fn()

      class MockEventSource {
        addEventListener = mockAddEventListener
        close = mockClose
        constructor(public url: string) {}
      }

      globalThis.EventSource = MockEventSource as any

      const cleanup = api.subscribeToProgress('test-123', {
        onProgress: vi.fn(),
        onComplete: vi.fn(),
        onError: vi.fn(),
      })

      expect(mockAddEventListener).toHaveBeenCalledTimes(3)

      cleanup()
      expect(mockClose).toHaveBeenCalled()
    })
  })

  describe('subscribeToProgress fallback when the live connection drops', () => {
    type Listener = (event: { data: string }) => void

    let listeners: Record<string, Listener>
    let closeSpy: ReturnType<typeof vi.fn>

    beforeEach(() => {
      listeners = {}
      closeSpy = vi.fn()
      class MockEventSource {
        close = closeSpy
        constructor(public url: string) {}
        addEventListener(name: string, fn: Listener) {
          listeners[name] = fn
        }
      }
      globalThis.EventSource = MockEventSource as any
    })

    afterEach(() => {
      vi.useRealTimers()
      vi.restoreAllMocks()
    })

    const job = (status: string, extra = {}) => ({
      ok: true,
      status: 200,
      json: async () => ({ id: 'j1', url: 'u', status, progress: status === 'completed' ? 100 : 40, ...extra }),
    })

    it('polls the job after the stream drops and completes when the server finishes', async () => {
      const fetchMock = vi.fn()
        .mockResolvedValueOnce(job('converting', { current_stage: 'Extracting audio...' }))
        .mockResolvedValueOnce(job('completed', { title: 'Live replay' }))
      globalThis.fetch = fetchMock as any
      const onProgress = vi.fn()
      const onComplete = vi.fn()
      const onError = vi.fn()

      api.subscribeToProgress('j1', { onProgress, onComplete, onError }, { pollIntervalMs: 5 })
      listeners.error({ data: '' })

      await vi.waitFor(() => expect(onComplete).toHaveBeenCalledOnce())
      expect(fetchMock).toHaveBeenCalledWith('/api/jobs/j1')
      expect(onProgress).toHaveBeenCalledWith(expect.objectContaining({ status: 'converting', progress: 40 }))
      expect(onComplete).toHaveBeenCalledWith(
        expect.objectContaining({ status: 'completed', download_ready: true, title: 'Live replay' }),
      )
      expect(onError).not.toHaveBeenCalled()
    })

    it('keeps polling through temporary network errors', async () => {
      const fetchMock = vi.fn()
        .mockRejectedValueOnce(new Error('offline'))
        .mockRejectedValueOnce(new Error('offline'))
        .mockResolvedValueOnce(job('completed'))
      globalThis.fetch = fetchMock as any
      const onComplete = vi.fn()
      const onError = vi.fn()

      api.subscribeToProgress('j1', { onProgress: vi.fn(), onComplete, onError }, { pollIntervalMs: 5 })
      listeners.error({ data: '' })

      await vi.waitFor(() => expect(onComplete).toHaveBeenCalledOnce())
      expect(onError).not.toHaveBeenCalled()
    })

    it('gives up after too many consecutive failures', async () => {
      globalThis.fetch = vi.fn().mockRejectedValue(new Error('offline')) as any
      const onError = vi.fn()

      api.subscribeToProgress('j1', { onProgress: vi.fn(), onComplete: vi.fn(), onError }, { pollIntervalMs: 1, maxPollFailures: 3 })
      listeners.error({ data: '' })

      await vi.waitFor(() => expect(onError).toHaveBeenCalledWith(new Error('Connection lost')))
    })

    it('reports a job the server no longer knows', async () => {
      globalThis.fetch = vi.fn().mockResolvedValue({ ok: false, status: 404 }) as any
      const onError = vi.fn()

      api.subscribeToProgress('j1', { onProgress: vi.fn(), onComplete: vi.fn(), onError }, { pollIntervalMs: 1 })
      listeners.error({ data: '' })

      await vi.waitFor(() => expect(onError).toHaveBeenCalledWith(new Error('Job not found')))
    })

    it('stops polling after cleanup', async () => {
      const fetchMock = vi.fn().mockResolvedValue(job('downloading'))
      globalThis.fetch = fetchMock as any

      const cleanup = api.subscribeToProgress('j1', { onProgress: vi.fn(), onComplete: vi.fn(), onError: vi.fn() }, { pollIntervalMs: 5 })
      listeners.error({ data: '' })
      await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled())
      cleanup()
      const calls = fetchMock.mock.calls.length
      await new Promise((r) => setTimeout(r, 30))
      expect(fetchMock.mock.calls.length).toBeLessThanOrEqual(calls + 1)
    })

    it('a complete event over SSE still finishes without polling', () => {
      const fetchMock = vi.fn()
      globalThis.fetch = fetchMock as any
      const onComplete = vi.fn()

      api.subscribeToProgress('j1', { onProgress: vi.fn(), onComplete, onError: vi.fn() })
      listeners.complete({ data: JSON.stringify({ job_id: 'j1', status: 'completed', progress: 100, download_ready: true }) })

      expect(onComplete).toHaveBeenCalledOnce()
      expect(fetchMock).not.toHaveBeenCalled()
      expect(closeSpy).toHaveBeenCalled()
    })
  })
})
