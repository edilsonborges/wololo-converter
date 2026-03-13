import { describe, it, expect } from 'vitest'
import { PLATFORMS } from '../types'

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
