import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { FormatSelector } from '../components/FormatSelector'

describe('FormatSelector', () => {
  it('should render all format options', () => {
    const onChange = vi.fn()
    render(<FormatSelector selectedFormat="video" onFormatChange={onChange} />)

    expect(screen.getByText('MP4 Video')).toBeInTheDocument()
    expect(screen.getByText('WebM Video')).toBeInTheDocument()
    expect(screen.getByText('MP3')).toBeInTheDocument()
    expect(screen.getByText('M4A')).toBeInTheDocument()
    expect(screen.getByText('WAV')).toBeInTheDocument()
    expect(screen.getByText('FLAC')).toBeInTheDocument()
    expect(screen.getByText('OGG')).toBeInTheDocument()
  })

  it('should call onFormatChange when clicking a format', () => {
    const onChange = vi.fn()
    render(<FormatSelector selectedFormat="video" onFormatChange={onChange} />)

    fireEvent.click(screen.getByText('MP3'))
    expect(onChange).toHaveBeenCalledWith('audio_mp3')
  })

  it('should call onFormatChange for WAV', () => {
    const onChange = vi.fn()
    render(<FormatSelector selectedFormat="video" onFormatChange={onChange} />)

    fireEvent.click(screen.getByText('WAV'))
    expect(onChange).toHaveBeenCalledWith('audio_wav')
  })

  it('should disable buttons when disabled prop is true', () => {
    const onChange = vi.fn()
    render(<FormatSelector selectedFormat="video" onFormatChange={onChange} disabled />)

    const buttons = screen.getAllByRole('button')
    buttons.forEach(button => {
      expect(button).toBeDisabled()
    })
  })

  it('should highlight the selected format', () => {
    const onChange = vi.fn()
    render(<FormatSelector selectedFormat="audio_mp3" onFormatChange={onChange} />)

    // The selected button should have the accent border class
    const mp3Button = screen.getByText('MP3').closest('button')
    expect(mp3Button?.className).toContain('border-accent')
  })
})
