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

  test('should finish a download even when the live progress connection drops', async ({ page }) => {
    let polls = 0
    await page.route('**/api/preview', (route) => route.fulfill({ status: 400, json: { detail: 'skip' } }))
    await page.route('**/api/download', (route) =>
      route.fulfill({ json: { job_id: 'job-1', message: 'Download started', status: 'queued' } }),
    )
    await page.route('**/api/jobs/job-1/progress', (route) => route.abort())
    await page.route('**/api/jobs/job-1', (route) => {
      polls += 1
      const done = polls >= 2
      return route.fulfill({
        json: {
          id: 'job-1', url: 'https://youtu.be/abc', status: done ? 'completed' : 'converting',
          progress: done ? 100 : 80, title: 'Live replay',
        },
      })
    })

    await page.locator('textarea').fill('https://www.youtube.com/live/abcdefghijk')
    await page.locator('button', { hasText: /Add 1 URL/ }).click()

    await expect(page.getByText('Completed', { exact: true }).first()).toBeVisible({ timeout: 15000 })
    await expect(page.getByText('Live replay')).toBeVisible()
    await expect(page.getByText('Connection lost')).toHaveCount(0)
  })

  test('should collapse repeated links into one queue item', async ({ page }) => {
    await page.route('**/api/preview', (route) => route.fulfill({ status: 400, json: { detail: 'skip' } }))
    await page.route('**/api/download', () => new Promise(() => {})) // stays pending

    const links = [
      'https://youtu.be/XIhEPwTMjWk',
      'https://www.youtube.com/watch?v=XIhEPwTMjWk&t=30',
      'https://m.youtube.com/shorts/XIhEPwTMjWk',
    ]
    await page.locator('textarea').fill(links.join('\n'))
    await expect(page.getByText('2 duplicates ignored')).toBeVisible()
    await page.locator('button', { hasText: /Add 1 URL/ }).click()
    await expect(page.getByRole('status')).toHaveText('3 links → 1 added, 2 duplicates')
    await expect(page.getByTestId('queue-item')).toHaveCount(1)

    // The same video again: nothing new, the existing item is pointed out
    await page.locator('textarea').fill('https://youtu.be/XIhEPwTMjWk')
    await page.locator('button', { hasText: /Add 1 URL/ }).click()
    await expect(page.getByRole('status')).toHaveText('Already in the queue')
    await expect(page.getByTestId('queue-item')).toHaveCount(1)
  })

  test('should warn about a video too large for the chosen quality', async ({ page }) => {
    const GB = 1_000_000_000
    await page.route('**/api/preview', (route) =>
      route.fulfill({
        json: {
          title: '4K UHD 10 hours', thumbnail_url: null, duration: 36000,
          available_qualities: [360, 480, 720, 1080],
          sizes: { '1080p': 6.9 * GB, '720p': 2.3 * GB, '480p': 1.7 * GB, '360p': 1.3 * GB, mp3: 1.44 * GB },
          size_limit: 4 * GB,
        },
      }),
    )
    let started: unknown = null
    await page.route('**/api/download', async (route) => {
      started = route.request().postDataJSON()
      await new Promise(() => {})
    })

    await page.locator('textarea').fill('https://youtu.be/XIhEPwTMjWk')
    const button1080 = page.getByRole('button', { name: /1080p/ })
    await expect(button1080).toBeDisabled()
    await expect(button1080).toContainText('~6.9 GB')
    await expect(page.getByRole('button', { name: /720p/ })).toContainText('~2.3 GB')

    await page.getByRole('button', { name: /720p/ }).click()
    await page.locator('button', { hasText: /Add 1 URL/ }).click()
    await expect(page.getByTestId('queue-item')).toContainText('~2.3 GB')
    await expect.poll(() => started).toEqual({ url: 'https://youtu.be/XIhEPwTMjWk', quality: '720p' })
  })

  test('should offer a quality that fits when the server refuses a large video', async ({ page }) => {
    await page.route('**/api/preview', (route) => route.fulfill({ status: 400, json: { detail: 'skip' } }))
    const requests: string[] = []
    await page.route('**/api/download', (route) => {
      const quality = route.request().postDataJSON().quality
      requests.push(quality)
      return route.fulfill({ json: { job_id: `job-${quality}`, message: 'Download started', status: 'queued' } })
    })
    await page.route('**/api/jobs/job-1080p/progress', (route) =>
      route.fulfill({
        headers: { 'Content-Type': 'text/event-stream' },
        body:
          'event: complete\ndata: ' +
          JSON.stringify({
            job_id: 'job-1080p', status: 'failed', progress: 0, download_ready: false,
            error_message: 'This video is too large: ~6.9 GB at 1080p (limit 4 GB). Try 720p (~2.3 GB).',
            estimated_size: 6.9e9, suggested_quality: '720p',
          }) + '\n\n',
      }),
    )
    await page.route('**/api/jobs/job-720p/progress', () => new Promise(() => {}))

    await page.locator('textarea').fill('https://youtu.be/XIhEPwTMjWk')
    await page.getByRole('button', { name: /1080p/ }).click()
    await page.locator('button', { hasText: /Add 1 URL/ }).click()
    await expect(page.getByText(/This video is too large/)).toBeVisible()
    await page.getByRole('button', { name: 'Switch to 720p' }).click()
    await expect.poll(() => requests).toEqual(['1080p', '720p'])
  })
})
