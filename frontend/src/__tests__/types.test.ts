import { describe, it, expect } from 'vitest'
import { FORMAT_OPTIONS, PLATFORMS } from '../types'

describe('FORMAT_OPTIONS', () => {
  it('should have 7 format options', () => {
    expect(FORMAT_OPTIONS).toHaveLength(7)
  })

  it('should include video MP4', () => {
    const mp4 = FORMAT_OPTIONS.find(o => o.value === 'video')
    expect(mp4).toBeDefined()
    expect(mp4!.label).toContain('MP4')
  })

  it('should include video WebM', () => {
    const webm = FORMAT_OPTIONS.find(o => o.value === 'video_webm')
    expect(webm).toBeDefined()
    expect(webm!.label).toContain('WebM')
  })

  it('should include audio MP3', () => {
    const mp3 = FORMAT_OPTIONS.find(o => o.value === 'audio_mp3')
    expect(mp3).toBeDefined()
    expect(mp3!.label).toContain('MP3')
  })

  it('should include audio M4A', () => {
    const m4a = FORMAT_OPTIONS.find(o => o.value === 'audio_m4a')
    expect(m4a).toBeDefined()
  })

  it('should include audio WAV', () => {
    const wav = FORMAT_OPTIONS.find(o => o.value === 'audio_wav')
    expect(wav).toBeDefined()
  })

  it('should include audio FLAC', () => {
    const flac = FORMAT_OPTIONS.find(o => o.value === 'audio_flac')
    expect(flac).toBeDefined()
  })

  it('should include audio OGG', () => {
    const ogg = FORMAT_OPTIONS.find(o => o.value === 'audio_ogg')
    expect(ogg).toBeDefined()
  })

  it('each option should have label, description, and icon', () => {
    for (const option of FORMAT_OPTIONS) {
      expect(option.label).toBeTruthy()
      expect(option.description).toBeTruthy()
      expect(option.icon).toBeTruthy()
    }
  })
})

describe('PLATFORMS', () => {
  it('should include youtube', () => {
    expect(PLATFORMS.youtube).toBeDefined()
    expect(PLATFORMS.youtube.name).toBe('YouTube')
  })

  it('should include instagram', () => {
    expect(PLATFORMS.instagram).toBeDefined()
  })

  it('should include twitter', () => {
    expect(PLATFORMS.twitter).toBeDefined()
    expect(PLATFORMS.twitter.name).toBe('Twitter/X')
  })

  it('should not include facebook (temporarily disabled)', () => {
    expect(PLATFORMS.facebook).toBeUndefined()
  })
})
