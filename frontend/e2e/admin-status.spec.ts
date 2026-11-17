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
  const history = days(90, 'operational')
  history[60] = { ...history[60], status: 'outage', uptime: 93.99, note: 'Estimated from tunnel log: tunnel restart', estimated: true }
  await page.route('**/api/status', (route) =>
    route.fulfill({
      json: {
        status: 'operational',
        generated_at: new Date().toISOString(),
        days: 90,
        components: [
          { id: 'website', name: 'Website', group: 'Service', status: 'operational', uptime: 99.93, latency_ms: 5, days: history },
        ],
      },
    }),
  )
}

test.describe('Status page', () => {
  test('shows the website, its uptime and a day tooltip', async ({ page }) => {
    await mockStatus(page)
    await page.goto('/status')
    await expect(page.getByText('All systems operational')).toBeVisible()
    await expect(page.getByRole('heading', { name: /Website/ })).toBeVisible()
    await expect(page.getByText('99.93% uptime')).toBeVisible()
    await expect(page.getByText(/Downloads by platform/)).toHaveCount(0)

    const websiteDays = page.getByRole('list', { name: /Website/ }).getByRole('listitem')
    await expect(websiteDays).toHaveCount(90)
    await websiteDays.nth(60).hover()
    await expect(page.getByText('~93.99% uptime (estimated)')).toBeVisible()
    await expect(page.getByText('Estimated from tunnel log: tunnel restart')).toBeVisible()
  })

  test('home footer links to the status page', async ({ page }) => {
    await page.goto('/')
    await expect(page.locator('footer a', { hasText: /^status$/ })).toHaveAttribute('href', '/status')
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
    await page.route('**/api/admin/insights**', (route) => {
      if (!signedIn) return route.fulfill({ status: 401, json: {} })
      const hour = 3600 * 1000
      const start = Date.now() - 24 * hour
      return route.fulfill({
        json: {
          range: '7d', bucket_seconds: 3600, total: 3,
          buckets: Array.from({ length: 24 }, (_, i) => ({
            start: new Date(start + i * hour).toISOString(),
            end: new Date(start + (i + 1) * hour).toISOString(),
            completed: i === 23 ? 2 : 0, failed: i === 23 ? 1 : 0, cancelled: 0, other: 0,
          })),
          platforms: [{ platform: 'youtube', count: 2 }, { platform: 'tiktok', count: 1 }],
        },
      })
    })
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
    await expect(page.getByRole('heading', { name: 'Downloads', exact: true })).toBeVisible()
    await expect(page.getByRole('link', { name: 'A video' })).toBeVisible()
    await expect(page.getByRole('table').first().getByRole('cell', { name: '203.0.113.5' })).toBeVisible()
    await expect(page.getByText('CPU, last 24 h')).toBeVisible()
    await expect(page.getByRole('img', { name: 'Downloads by platform' })).toBeVisible()
    await expect(page.getByRole('list', { name: 'Platforms' })).toContainText('YouTube')
    await expect(page.getByRole('navigation', { name: 'Pages' })).toContainText('1–1 of 1')

    // Clicking a platform filters the list
    const jobsRequest = page.waitForRequest((r) => r.url().includes('/api/admin/jobs') && r.url().includes('platform=tiktok'))
    await page.getByRole('list', { name: 'Platforms' }).getByRole('button', { name: /TikTok/ }).click()
    await jobsRequest
  })
})
