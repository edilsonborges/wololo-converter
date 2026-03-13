import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { FormatSelector } from '../components/FormatSelector'

describe('FormatSelector', () => {
  it('should render all quality options', () => {
    const onChange = vi.fn()
    render(<FormatSelector selectedFormat="480p" onFormatChange={onChange} />)

    expect(screen.getByText('360p')).toBeInTheDocument()
    expect(screen.getByText('480p')).toBeInTheDocument()
    expect(screen.getByText('720p')).toBeInTheDocument()
    expect(screen.getByText('1080p')).toBeInTheDocument()
    expect(screen.getByText('MP3')).toBeInTheDocument()
  })

  it('should call onFormatChange when clicking a quality', () => {
    const onChange = vi.fn()
    render(<FormatSelector selectedFormat="480p" onFormatChange={onChange} />)

    fireEvent.click(screen.getByText('720p'))
    expect(onChange).toHaveBeenCalledWith('720p')
  })

  it('should call onFormatChange for MP3', () => {
    const onChange = vi.fn()
    render(<FormatSelector selectedFormat="480p" onFormatChange={onChange} />)

    fireEvent.click(screen.getByText('MP3'))
    expect(onChange).toHaveBeenCalledWith('mp3')
  })

  it('should disable buttons when disabled prop is true', () => {
    const onChange = vi.fn()
    render(<FormatSelector selectedFormat="480p" onFormatChange={onChange} disabled />)

    const buttons = screen.getAllByRole('button')
    buttons.forEach(button => {
      expect(button).toBeDisabled()
    })
  })

  it('should highlight the selected quality', () => {
    const onChange = vi.fn()
    render(<FormatSelector selectedFormat="720p" onFormatChange={onChange} />)

    const button = screen.getByText('720p').closest('button')
    expect(button?.className).toContain('border-accent')
  })
})
