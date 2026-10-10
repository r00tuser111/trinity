// @vitest-environment jsdom
/**
 * LLM-PROVIDER-001 — the Settings card, mounted.
 *
 * Pins the honest-state chain (loading → failed → form), that a named
 * validation error blocks the save round-trip, and that the pending banner
 * offers the restart instead of doing it silently.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('@/api', () => {
  const inst = { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() }
  return { default: inst }
})

import api from '@/api'
import ModelProviderPanel from '@/components/settings/ModelProviderPanel.vue'

const STATUS = {
  mode: 'custom', active: true, base_url: 'https://api.deepseek.com/anthropic',
  api_key_configured: true, api_key_masked: 'sk-a…wxyz',
  models: [{ id: 'deepseek-chat', label: 'DeepSeek Chat', context_window: 128000 }],
  default_model: 'deepseek-chat', fast_model: 'deepseek-chat',
}

function route({ status = STATUS, pending = { agents: [], count: 0 } } = {}) {
  api.get.mockImplementation((url) => {
    if (url === '/api/settings/model-provider') {
      return status instanceof Error ? Promise.reject(status) : Promise.resolve({ data: status })
    }
    if (url === '/api/settings/model-provider/pending') return Promise.resolve({ data: pending })
    return Promise.resolve({ data: { provider: 'anthropic', models: null } })
  })
}

async function mountPanel() {
  const wrapper = mount(ModelProviderPanel, { attachTo: document.body })
  await flushPromises()
  return wrapper
}

describe('ModelProviderPanel', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
    document.body.innerHTML = ''
  })

  it('a failed read renders LoadFailed, not an empty form', async () => {
    route({ status: Object.assign(new Error('offline'), { response: { status: 500 } }) })
    const wrapper = await mountPanel()
    expect(wrapper.find('[data-testid="load-failed"]').exists()).toBe(true)
    expect(wrapper.find('form').exists()).toBe(false)
  })

  it('opens pre-filled with the saved provider and the masked key', async () => {
    route()
    const wrapper = await mountPanel()
    const inputs = wrapper.findAll('input')
    expect(inputs.some((i) => i.element.value === STATUS.base_url)).toBe(true)
    expect(wrapper.text()).toContain('sk-a…wxyz')
    expect(wrapper.find('input[type="password"]').element.value).toBe('')
  })

  it('a named validation error blocks the save request', async () => {
    route()
    const wrapper = await mountPanel()
    const url = wrapper.findAll('input').find((i) => i.element.value === STATUS.base_url)
    await url.setValue('ftp://api.deepseek.com')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(api.put).not.toHaveBeenCalled()
    expect(wrapper.text()).toMatch(/http\(s\)/)
  })

  it('saves the edited provider without resending the stored key', async () => {
    route()
    api.put.mockResolvedValueOnce({ data: STATUS })
    const wrapper = await mountPanel()
    const url = wrapper.findAll('input').find((i) => i.element.value === STATUS.base_url)
    await url.setValue('https://api.deepseek.com/anthropic/')
    await wrapper.find('form').trigger('submit')
    await flushPromises()
    expect(api.put).toHaveBeenCalledTimes(1)
    const [path, body] = api.put.mock.calls[0]
    expect(path).toBe('/api/settings/model-provider')
    expect(body).not.toHaveProperty('api_key')
    expect(body.models.map((m) => m.id)).toEqual(['deepseek-chat'])
  })

  it('the pending banner offers the restart and only runs it on request', async () => {
    route({ pending: { agents: ['a1', 'a2'], count: 2 } })
    api.post.mockResolvedValueOnce({
      data: { restarted: ['a1', 'a2'], not_ready: [], skipped: [], count: 2 },
    })
    const wrapper = await mountPanel()
    const banner = wrapper.find('[data-testid="model-provider-pending"]')
    expect(banner.exists()).toBe(true)
    expect(api.post).not.toHaveBeenCalled()
    await banner.find('button').trigger('click')
    await flushPromises()
    expect(api.post).toHaveBeenCalledWith('/api/settings/model-provider/apply')
    expect(wrapper.find('[data-testid="model-provider-pending"]').exists()).toBe(false)
    expect(wrapper.text()).toContain('Restarted 2 agent(s)')
  })

  it('keeps the pending banner when a restart does not come up ready', async () => {
    route({ pending: { agents: ['a1'], count: 1 } })
    api.post.mockResolvedValueOnce({
      data: { restarted: [], not_ready: ['a1'], skipped: [], count: 0 },
    })
    const wrapper = await mountPanel()
    await wrapper.find('[data-testid="model-provider-pending"] button').trigger('click')
    await flushPromises()
    expect(wrapper.find('[data-testid="model-provider-pending"]').exists()).toBe(true)
    expect(wrapper.text()).toContain('did not finish')
  })
})
