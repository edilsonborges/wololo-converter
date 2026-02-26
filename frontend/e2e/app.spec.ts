import { test, expect } from '@playwright/test'

test.describe('Wololo Converter App', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/')
  })

  test('should display the header', async ({ page }) => {
    await expect(page.locator('h1')).toContainText('Wololo Converter')
  })

  test('should display supported platforms', async ({ page }) => {
    await expect(page.getByText('YouTube', { exact: true })).toBeVisible()
    await expect(page.getByText('Instagram', { exact: true })).toBeVisible()
    await expect(page.getByText('Twitter/X', { exact: true })).toBeVisible()
  })

  test('should show empty queue message', async ({ page }) => {
    await expect(page.getByText('Your download queue is empty')).toBeVisible()
  })

  test('should display URL input textarea', async ({ page }) => {
    const textarea = page.locator('textarea')
    await expect(textarea).toBeVisible()
    await expect(textarea).toHaveAttribute('placeholder', /Paste one or more URLs/)
  })

  test('should display all format options', async ({ page }) => {
    await expect(page.getByText('MP4 Video')).toBeVisible()
    await expect(page.getByText('WebM Video')).toBeVisible()
    await expect(page.getByText('MP3')).toBeVisible()
    await expect(page.getByText('M4A')).toBeVisible()
    await expect(page.getByText('WAV')).toBeVisible()
    await expect(page.getByText('FLAC')).toBeVisible()
    await expect(page.getByText('OGG')).toBeVisible()
  })

  test('should have MP4 Video selected by default', async ({ page }) => {
    const mp4Button = page.locator('button', { hasText: 'MP4 Video' })
    await expect(mp4Button).toHaveClass(/border-accent/)
  })

  test('should allow switching format', async ({ page }) => {
    const mp3Button = page.locator('button', { hasText: 'MP3' })
    await mp3Button.click()
    await expect(mp3Button).toHaveClass(/border-accent/)

    // MP4 should no longer be selected
    const mp4Button = page.locator('button', { hasText: 'MP4 Video' })
    await expect(mp4Button).not.toHaveClass(/border-accent/)
  })

  test('should detect valid YouTube URL', async ({ page }) => {
    const textarea = page.locator('textarea')
    await textarea.fill('https://www.youtube.com/watch?v=dQw4w9WgXcQ')

    await expect(page.getByText('1 valid')).toBeVisible()
  })

  test('should detect multiple URLs', async ({ page }) => {
    const textarea = page.locator('textarea')
    await textarea.fill(
      'https://www.youtube.com/watch?v=dQw4w9WgXcQ\nhttps://www.instagram.com/reel/ABC123/'
    )

    await expect(page.getByText('2 valid')).toBeVisible()
  })

  test('should mark unsupported URLs', async ({ page }) => {
    const textarea = page.locator('textarea')
    await textarea.fill('https://example.com/video')

    await expect(page.getByText('1 unsupported')).toBeVisible()
  })

  test('should enable add button when valid URLs exist', async ({ page }) => {
    const addButton = page.locator('button', { hasText: 'Add to Queue' })
    await expect(addButton).toBeDisabled()

    const textarea = page.locator('textarea')
    await textarea.fill('https://www.youtube.com/watch?v=dQw4w9WgXcQ')

    await expect(page.locator('button', { hasText: /Add 1 URL/ })).toBeEnabled()
  })

  test('should show footer with disclaimer', async ({ page }) => {
    await expect(page.getByText(/Personal use only/)).toBeVisible()
  })
})
