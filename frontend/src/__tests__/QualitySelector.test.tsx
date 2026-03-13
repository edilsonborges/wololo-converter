import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { QualitySelector } from '../components/QualitySelector'

describe('QualitySelector', () => {
  it('should render all quality options', () => {
    const onChange = vi.fn()
    render(<QualitySelector selectedQuality="480p" onQualityChange={onChange} />)

    expect(screen.getByText('360p')).toBeInTheDocument()
    expect(screen.getByText('480p')).toBeInTheDocument()
    expect(screen.getByText('720p')).toBeInTheDocument()
    expect(screen.getByText('1080p')).toBeInTheDocument()
    expect(screen.getByText('MP3')).toBeInTheDocument()
  })

  it('should call onQualityChange when clicking a quality', () => {
    const onChange = vi.fn()
    render(<QualitySelector selectedQuality="480p" onQualityChange={onChange} />)

    fireEvent.click(screen.getByText('720p'))
    expect(onChange).toHaveBeenCalledWith('720p')
  })

  it('should call onQualityChange for MP3', () => {
    const onChange = vi.fn()
    render(<QualitySelector selectedQuality="480p" onQualityChange={onChange} />)

    fireEvent.click(screen.getByText('MP3'))
    expect(onChange).toHaveBeenCalledWith('mp3')
  })

  it('should disable buttons when disabled prop is true', () => {
    const onChange = vi.fn()
    render(<QualitySelector selectedQuality="480p" onQualityChange={onChange} disabled />)

    const buttons = screen.getAllByRole('button')
    buttons.forEach(button => {
      expect(button).toBeDisabled()
    })
  })

  it('should highlight the selected quality', () => {
    const onChange = vi.fn()
    render(<QualitySelector selectedQuality="720p" onQualityChange={onChange} />)

    const button = screen.getByText('720p').closest('button')
    expect(button?.className).toContain('border-accent')
  })

  it('should disable unavailable qualities based on availableQualities', () => {
    const onChange = vi.fn()
    render(
      <QualitySelector
        selectedQuality="480p"
        onQualityChange={onChange}
        availableQualities={[360, 480]}
      />
    )

    // 360p and 480p should be enabled
    expect(screen.getByText('360p').closest('button')).not.toBeDisabled()
    expect(screen.getByText('480p').closest('button')).not.toBeDisabled()

    // 720p and 1080p should be disabled (no resolution >= 720 or 1080)
    expect(screen.getByText('720p').closest('button')).toBeDisabled()
    expect(screen.getByText('1080p').closest('button')).toBeDisabled()

    // MP3 is always enabled
    expect(screen.getByText('MP3').closest('button')).not.toBeDisabled()
  })

  it('should show tooltip on unavailable quality', () => {
    const onChange = vi.fn()
    render(
      <QualitySelector
        selectedQuality="480p"
        onQualityChange={onChange}
        availableQualities={[360]}
      />
    )

    const button720 = screen.getByText('720p').closest('button')
    expect(button720).toHaveAttribute('title', 'Qualidade não disponível para este vídeo')
  })

  it('should enable all video options when no availableQualities provided', () => {
    const onChange = vi.fn()
    render(<QualitySelector selectedQuality="480p" onQualityChange={onChange} />)

    const buttons = screen.getAllByRole('button')
    buttons.forEach(button => {
      expect(button).not.toBeDisabled()
    })
  })
})
