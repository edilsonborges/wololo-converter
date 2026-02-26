import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { Icon, FormatIcon, PlatformIcon, iconMap } from '../components/Icon'

describe('Icon', () => {
  it('should render a known icon', () => {
    const { container } = render(<Icon name="video" />)
    expect(container.querySelector('svg')).toBeTruthy()
  })

  it('should return null for unknown icon', () => {
    const { container } = render(<Icon name={'unknown' as any} />)
    expect(container.querySelector('svg')).toBeNull()
  })

  it('should apply different sizes', () => {
    const { container: small } = render(<Icon name="video" size="sm" />)
    const { container: large } = render(<Icon name="video" size="xl" />)

    const smallSvg = small.querySelector('svg')
    const largeSvg = large.querySelector('svg')
    expect(smallSvg?.getAttribute('width')).toBe('16')
    expect(largeSvg?.getAttribute('width')).toBe('32')
  })
})

describe('FormatIcon', () => {
  it('should render video icon for video format', () => {
    const { container } = render(<FormatIcon format="video" />)
    expect(container.querySelector('svg')).toBeTruthy()
  })

  it('should render icon for all audio formats', () => {
    const formats = ['audio_mp3', 'audio_m4a', 'audio_wav', 'audio_flac', 'audio_ogg'] as const
    for (const format of formats) {
      const { container } = render(<FormatIcon format={format} />)
      expect(container.querySelector('svg')).toBeTruthy()
    }
  })

  it('should render icon for video_webm', () => {
    const { container } = render(<FormatIcon format="video_webm" />)
    expect(container.querySelector('svg')).toBeTruthy()
  })
})

describe('PlatformIcon', () => {
  it('should render youtube icon', () => {
    const { container } = render(<PlatformIcon platform="youtube" />)
    expect(container.querySelector('svg')).toBeTruthy()
  })

  it('should render fallback for unknown platform', () => {
    const { container } = render(<PlatformIcon platform="unknown" />)
    expect(container.querySelector('svg')).toBeTruthy()
  })
})

describe('iconMap', () => {
  it('should contain all required icons', () => {
    const requiredIcons = ['youtube', 'instagram', 'twitter', 'video', 'music', 'music2', 'download', 'plus', 'x']
    for (const icon of requiredIcons) {
      expect(iconMap).toHaveProperty(icon)
    }
  })
})
