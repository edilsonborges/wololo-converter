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

  test('should display all quality options after entering a valid URL', async ({ page }) => {
    await page.locator('textarea').fill('https://www.youtube.com/watch?v=dQw4w9WgXcQ')

    await expect(page.locator('button', { hasText: '360p' })).toBeVisible()
    await expect(page.locator('button', { hasText: '480p' })).toBeVisible()
    await expect(page.locator('button', { hasText: '720p' })).toBeVisible()
    await expect(page.locator('button', { hasText: '1080p' })).toBeVisible()
    await expect(page.locator('button', { hasText: 'MP3' })).toBeVisible()
  })

  test('should have 480p selected by default', async ({ page }) => {
    await page.locator('textarea').fill('https://www.youtube.com/watch?v=dQw4w9WgXcQ')

    const defaultButton = page.locator('button', { hasText: '480p' })
    await expect(defaultButton).toHaveClass(/border-accent/)
  })

  test('should allow switching quality', async ({ page }) => {
    await page.locator('textarea').fill('https://www.youtube.com/watch?v=dQw4w9WgXcQ')

    const mp3Button = page.locator('button', { hasText: 'MP3' })
    await mp3Button.click()
    await expect(mp3Button).toHaveClass(/border-accent/)

    // 480p should no longer be selected
    const defaultButton = page.locator('button', { hasText: '480p' })
    await expect(defaultButton).not.toHaveClass(/border-accent/)
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

  test('should open release notes from the footer version', async ({ page }) => {
    const version = page.locator('footer button', { hasText: /^v\d+\.\d+\.\d+$/ })
    const label = (await version.textContent())!.trim()
    await version.click()

    const dialog = page.getByRole('dialog', { name: 'Release notes' })
    await expect(dialog).toBeVisible()
    await expect(dialog.getByRole('heading', { name: label })).toBeVisible()
    await expect(dialog.getByText('Current', { exact: true })).toBeVisible()
    await expect(dialog.getByRole('heading', { name: 'v0.1.0' })).toBeAttached()

    await page.keyboard.press('Escape')
    await expect(dialog).toBeHidden()
  })

  test('should resolve a music page link into MP3 queue items', async ({ page }) => {
    await page.route('**/api/resolve', (route) =>
      route.fulfill({
        json: {
          album: 'Album',
          tracks: [
            { title: 'Song', artist: 'Artist', duration: 120, video_url: null, source_url: 'https://artlist.io/royalty-free-music/song/song/2' },
          ],
        },
      }),
    )

    await page.locator('textarea').fill('https://artlist.io/royalty-free-music/album/album/1')
    await expect(page.getByText(/unsupported/)).toHaveCount(0)
    await expect(page.getByText('360p', { exact: true })).toHaveCount(0)
    await page.locator('button', { hasText: /Add 1 URL/ }).click()

    await expect(page.getByText('Artist - Song')).toBeVisible()
    await expect(page.getByText('No matching video found on YouTube')).toBeVisible()
    await expect(page.getByTitle('Retry')).toBeVisible()
  })
})
