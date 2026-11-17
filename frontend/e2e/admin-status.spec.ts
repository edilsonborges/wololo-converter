import { test, expect, type Page } from '@playwright/test'

function days(count: number, status: string, extra: Record<string, unknown> = {}) {
  const today = new Date()
  return Array.from({ length: count }, (_, i) => {
    const date = new Date(today)
    date.setDate(today.getDate() - (count - 1 - i))
    return { date: date.toISOString().slice(0, 10), status, uptime: status === 'no_data' ? null : 100, ...extra }
  })
}

async function mockStatus(page: Page) {
  await page.route('**/api/status', (route) =>
    route.fulfill({
      json: {
        status: 'degraded',
        generated_at: new Date().toISOString(),
        days: 90,
        components: [
          { id: 'website', name: 'Website', group: 'Service', status: 'operational', uptime: 99.98, latency_ms: 5, days: days(90, 'operational') },
          { id: 'api', name: 'API', group: 'Service', status: 'operational', uptime: 100, latency_ms: 2, days: days(90, 'operational') },
          {
            id: 'tiktok', name: 'TikTok', group: 'Downloads', status: 'degraded', uptime: 60, latency_ms: null,
            days: days(90, 'degraded', { completed: 3, failed: 2 }),
          },
        ],
      },
    }),
  )
}

test.describe('Status page', () => {
  test('shows components, uptime and a day tooltip', async ({ page }) => {
    await mockStatus(page)
    await page.goto('/status')
    await expect(page.getByText('Some systems are degraded')).toBeVisible()
    await expect(page.getByRole('heading', { name: /Website/ })).toBeVisible()
    await expect(page.getByText('99.98% uptime')).toBeVisible()
    await expect(page.getByText('60.00% success')).toBeVisible()

    const tiktokDays = page.getByRole('list', { name: /TikTok/ }).getByRole('listitem')
    await expect(tiktokDays).toHaveCount(90)
    await tiktokDays.last().hover()
    await expect(page.getByText('3 of 5 downloads succeeded')).toBeVisible()
  })

  test('home footer links to the status page', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('footer a', { hasText: '_status' })).toHaveAttribute('href', '/status')
  })
})

test.describe('Admin', () => {
  test('redirects to login, rejects a wrong password and opens the dashboard', async ({ page }) => {
    let signedIn = false
    await page.route('**/api/admin/me', (route) =>
      signedIn ? route.fulfill({ json: { ok: true } }) : route.fulfill({ status: 401, json: { detail: 'Not signed in' } }),
    )
    await page.route('**/api/admin/login', async (route) => {
      const { password } = route.request().postDataJSON()
      if (password === 'right') {
        signedIn = true
        return route.fulfill({ json: { ok: true } })
      }
      return route.fulfill({ status: 401, json: { detail: 'Wrong password' } })
    })
    const period = { total: 2, completed: 1, failed: 1, cancelled: 0, interrupted: 0, success_rate: 50, bytes: 2048, unique_ips: 1 }
    await page.route('**/api/admin/summary', (route) =>
      signedIn
        ? route.fulfill({ json: { last_24h: period, last_7d: period, last_30d: period, platforms_7d: [{ platform: 'youtube', count: 2 }], top_ips_7d: [{ ip: '203.0.113.5', count: 2, last_seen: new Date().toISOString() }] } })
        : route.fulfill({ status: 401, json: {} }),
    )
    await page.route('**/api/admin/system**', (route) =>
      signedIn
        ? route.fulfill({
            json: {
              now: {
                cpu_percent: 12, cpu_count: 4, load_average: [0.5, 0.4, 0.3], memory_percent: 40,
                memory_used_bytes: 4e9, memory_total_bytes: 8e9, disk_percent: 50, disk_used_bytes: 5e10,
                disk_total_bytes: 1e11, temp_dir_bytes: 1e6, process_memory_bytes: 1e8,
                process_started_at: new Date().toISOString(), active_downloads: 1, queued_downloads: 0,
                max_concurrent_downloads: 3,
              },
              samples: [
                { at: new Date(Date.now() - 60000).toISOString(), cpu: 10, memory: 40, disk: 50, active: 0, queued: 0 },
                { at: new Date().toISOString(), cpu: 12, memory: 41, disk: 50, active: 1, queued: 0 },
              ],
            },
          })
        : route.fulfill({ status: 401, json: {} }),
    )
    await page.route('**/api/admin/jobs**', (route) =>
      signedIn
        ? route.fulfill({
            json: {
              total: 1,
              items: [{
                id: 'j1', created_at: new Date().toISOString(), started_at: null, completed_at: null,
                elapsed_seconds: 7, status: 'completed', platform: 'youtube', quality: '720p',
                url: 'https://youtu.be/x', title: 'A video', filename: 'A video.mp4', file_size: 2048,
                duration: 60, error_message: null, client_ip: '203.0.113.5', client_name: null,
                source: 'link', user_agent: 'Agent/1.0',
              }],
            },
          })
        : route.fulfill({ status: 401, json: {} }),
    )

    await page.goto('/admin')
    await page.waitForURL('**/login')
    await page.getByLabel('Password').fill('wrong')
    await page.getByRole('button', { name: 'Sign in' }).click()
    await expect(page.getByRole('alert')).toHaveText('Wrong password.')

    await page.getByLabel('Password').fill('right')
    await page.getByRole('button', { name: 'Sign in' }).click()
    await page.waitForURL('**/admin')
    await expect(page.getByRole('heading', { name: 'Download history' })).toBeVisible()
    await expect(page.getByRole('link', { name: 'A video' })).toBeVisible()
    await expect(page.getByRole('table').last().getByRole('cell', { name: '203.0.113.5' })).toBeVisible()
    await expect(page.getByText('CPU, last 24 h')).toBeVisible()
  })
})
