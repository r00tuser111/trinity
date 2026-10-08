import { test, expect } from '@playwright/test'

async function mockApi(page, setupCompleted = true) {
  await page.routeWebSocket('**/ws**', socket => socket.close())
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname
    const responses = {
      '/api/auth/mode': { email_auth_enabled: true },
      '/api/setup/status': { setup_completed: setupCompleted },
      '/api/enterprise/sso/public-providers': [],
      '/api/users/me': { username: 'test-admin', email: 'user@example.com', role: 'admin' },
      '/api/templates': [],
    }
    return route.fulfill({ json: responses[path] ?? {} })
  })
}

for (const theme of ['light', 'dark']) {
  for (const width of [375, 1280]) {
    test(`login switches and preserves input (${theme}, ${width}px)`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 })
      await page.addInitScript(({ theme }) => {
        localStorage.setItem('trinity-theme', theme)
        // Only seed the first visit: reload must exercise saved language.
        if (!localStorage.getItem('trinity-locale')) localStorage.setItem('trinity-locale', 'en')
      }, { theme })
      await mockApi(page)
      const errors = []
      page.on('pageerror', e => errors.push(e.message))
      await page.goto('/login')
      await page.getByLabel('Email Address', { exact: true }).fill('user@example.com')
      if (theme === 'dark') await expect(page.locator('html')).toHaveClass(/dark/)
      else await expect(page.locator('html')).not.toHaveClass(/dark/)
      const selector = page.getByTestId('language-select')
      await expect(selector).toBeVisible()
      await selector.selectOption('zh-CN')
      await expect(page.getByText('登录以管理您的智能体')).toBeVisible()
      await expect(page.getByRole('button', { name: '发送验证码', exact: true })).toBeVisible()
      await expect(page.getByLabel('电子邮箱', { exact: true })).toHaveValue('user@example.com')
      await expect(page.locator('html')).toHaveAttribute('lang', 'zh-CN')
      await expect(page).toHaveTitle('Trinity — 登录')
      const box = await selector.boundingBox()
      expect(box.x).toBeGreaterThan(width / 2)
      expect(box.x + box.width).toBeLessThanOrEqual(width)
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true)
      await page.reload()
      await expect(selector).toHaveValue('zh-CN')
      await expect(page.getByText('登录以管理您的智能体')).toBeVisible()
      await selector.selectOption('en')
      await expect(page.getByText('Sign in to manage your agents')).toBeVisible()
      await expect(page).toHaveTitle('Trinity — Login')
      expect(errors).toEqual([])
    })
  }
}

test('setup detects Chinese and switches password guidance live', async ({ page }) => {
  await mockApi(page, false)
  await page.addInitScript(() => Object.defineProperty(navigator, 'languages', { value: ['zh-CN'] }))
  await page.goto('/setup')
  await expect(page.getByText('创建管理员账户', { exact: true })).toBeVisible()
  await page.locator('#password').fill('ExampleOnly1!')
  await expect(page.getByText('至少 12 个字符')).toBeVisible()
  await page.getByTestId('language-select').selectOption('en')
  await expect(page.getByText('At least 12 characters')).toBeVisible()
})

test('console navigation switches at the top right without leaving the route', async ({ page }) => {
  await mockApi(page)
  await page.addInitScript(() => {
    const payload = btoa(JSON.stringify({ sub: 'test-admin', mode: 'admin', exp: 4102444800 }))
    localStorage.setItem('token', `test.${payload}.fixture`)
    localStorage.setItem('auth0_user', JSON.stringify({ username: 'test-admin', role: 'admin' }))
    localStorage.setItem('trinity-locale', 'en')
  })
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.goto('/library?tab=templates')
  const nav = page.locator('nav').first()
  const selector = nav.getByTestId('language-select')
  await selector.selectOption('zh-CN')
  await expect(nav.getByRole('link', { name: '仪表盘', exact: true })).toBeVisible()
  await expect(nav.getByRole('link', { name: '资源库', exact: true })).toBeVisible()
  await expect(nav.getByRole('link', { name: '设置', exact: true })).toBeVisible()
  await expect(page).toHaveURL(/\/library\?tab=templates$/)
  expect(errors).toEqual([])
  // The actual tabs re-render; internal ids and URL state stay unchanged.
  await expect(page.getByRole('button', { name: '智能体模板', exact: true })).toBeVisible()
  for (const width of [375, 768, 1280]) {
    await page.setViewportSize({ width, height: 900 })
    const box = await selector.boundingBox()
    expect(box.x + box.width).toBeLessThanOrEqual(width)
    expect(box.x).toBeGreaterThanOrEqual(0)
  }
})
