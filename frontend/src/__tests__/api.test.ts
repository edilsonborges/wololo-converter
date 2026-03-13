import { describe, it, expect, vi, beforeEach } from 'vitest'
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
})
