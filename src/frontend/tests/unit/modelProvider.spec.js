/**
 * LLM-PROVIDER-001 — the custom model provider's frontend half.
 *
 * Pins: the client-side pre-validation names the common mistakes, the request
 * bodies never carry a blank key (a blank key keeps the stored one), the pickers
 * swap to the provider's list only when the catalog says a provider is active,
 * and the store refreshes the shared catalog after every change.
 */
import { describe, it, expect, beforeEach, vi } from 'vitest'
import { setActivePinia, createPinia } from 'pinia'

vi.mock('@/api', () => {
  const inst = { get: vi.fn(), post: vi.fn(), put: vi.fn(), delete: vi.fn() }
  return { default: inst }
})

import api from '@/api'
import { useModelProviderStore } from '@/stores/modelProvider'
import { MODEL_CATALOG } from '@/constants/modelCatalog'
import {
  PROVIDER_PRESETS,
  formFromStatus,
  applyPreset,
  validateProviderForm,
  buildProviderPayload,
  buildTestPayload,
  presetModelsFor,
  adminDefaultModelsFor,
  isProviderCatalog,
} from '@/utils/modelProvider'

const deepseek = () => applyPreset(formFromStatus(null), PROVIDER_PRESETS[0])

const PROVIDER_CATALOG = {
  provider: 'custom',
  models: [
    { id: 'deepseek-chat', label: 'DeepSeek Chat', context_window: 128000 },
    { id: 'deepseek-reasoner', label: 'DeepSeek Reasoner', context_window: 128000 },
  ],
  default_model: 'deepseek-reasoner',
  fast_model: 'deepseek-chat',
}

describe('validateProviderForm', () => {
  it('accepts the DeepSeek preset once a key is entered', () => {
    const form = { ...deepseek(), api_key: 'sk-test' }
    expect(validateProviderForm(form)).toEqual({})
  })

  it('does not validate anything in Anthropic mode', () => {
    expect(validateProviderForm(formFromStatus(null))).toEqual({})
  })

  it('a stored key makes the key field optional', () => {
    expect(validateProviderForm(deepseek()).api_key).toBeTruthy()
    expect(validateProviderForm(deepseek(), { apiKeyConfigured: true })).toEqual({})
  })

  it.each([
    ['', /base URL/],
    ['ftp://api.example.com', /http\(s\)/],
    ['not a url', /http\(s\)/],
    ['https://user:pw@api.example.com', /credentials/],
    ['https://api.example.com/anthropic?x=1', /query/],
  ])('names the base-URL problem for %j', (url, pattern) => {
    const errors = validateProviderForm({ ...deepseek(), base_url: url, api_key: 'k' })
    expect(errors.base_url).toMatch(pattern)
  })

  it.each([
    [[{ id: '', label: 'Named only', context_window: '' }], /needs an id/],
    [[{ id: '--model', label: '', context_window: '' }], /not a valid model id/],
    [[{ id: 'a', label: '', context_window: '' }, { id: 'a', label: '', context_window: '' }], /listed twice/],
    [[{ id: 'a', label: '', context_window: '12k' }], /whole number/],
    [[{ id: '', label: '', context_window: '' }], /at least one model/],
  ])('names the model-list problem', (models, pattern) => {
    const errors = validateProviderForm({ ...deepseek(), models, default_model: '', fast_model: '', api_key: 'k' })
    expect(errors.models).toMatch(pattern)
  })

  it('the default and fast models must be listed', () => {
    const errors = validateProviderForm({ ...deepseek(), default_model: 'claude-sonnet-4-6', api_key: 'k' })
    expect(errors.default_model).toBeTruthy()
  })
})

describe('request bodies', () => {
  it('Anthropic mode sends only the mode', () => {
    expect(buildProviderPayload({ ...deepseek(), mode: 'anthropic', api_key: 'k' })).toEqual({ mode: 'anthropic' })
  })

  it('a blank key is omitted so the stored one is kept', () => {
    const body = buildProviderPayload({ ...deepseek(), api_key: '   ' })
    expect(body).not.toHaveProperty('api_key')
    expect(buildTestPayload(deepseek())).not.toHaveProperty('api_key')
  })

  it('trims, drops empty rows and converts context windows', () => {
    const form = {
      ...deepseek(),
      base_url: ' https://api.deepseek.com/anthropic ',
      api_key: ' sk-test ',
      models: [
        { id: ' deepseek-chat ', label: '', context_window: '64000' },
        { id: '', label: '', context_window: '' },
      ],
      default_model: '',
      fast_model: '',
    }
    expect(buildProviderPayload(form)).toEqual({
      mode: 'custom',
      base_url: 'https://api.deepseek.com/anthropic',
      api_key: 'sk-test',
      models: [{ id: 'deepseek-chat', label: null, context_window: 64000 }],
      default_model: null,
      fast_model: null,
    })
  })

  it('the test call uses the default model, else the first listed one', () => {
    expect(buildTestPayload(deepseek()).model).toBe('deepseek-chat')
    expect(buildTestPayload({ ...deepseek(), default_model: '' }).model).toBe('deepseek-chat')
    expect(buildTestPayload({ ...deepseek(), default_model: 'deepseek-reasoner' }).model).toBe('deepseek-reasoner')
  })

  it('round-trips the saved status into the form without the key', () => {
    const form = formFromStatus({
      mode: 'custom', base_url: 'https://api.deepseek.com/anthropic', api_key_configured: true,
      models: [{ id: 'deepseek-chat', label: 'deepseek-chat', context_window: 128000 }],
      default_model: 'deepseek-chat', fast_model: 'deepseek-chat',
    })
    expect(form.api_key).toBe('')
    expect(form.models).toEqual([{ id: 'deepseek-chat', label: '', context_window: '128000' }])
  })
})

describe('picker lists', () => {
  it('fall back to the Claude catalog when no provider is active', () => {
    for (const catalog of [null, { provider: 'anthropic', models: null }]) {
      expect(isProviderCatalog(catalog)).toBe(false)
      expect(presetModelsFor(catalog).map((m) => m.value)).toEqual(MODEL_CATALOG.map((m) => m.id))
      expect(adminDefaultModelsFor(catalog).every((m) => m.adminDefaultSelectable)).toBe(true)
    }
  })

  it('switch to the provider list when one is active', () => {
    expect(presetModelsFor(PROVIDER_CATALOG)).toEqual([
      { value: 'deepseek-chat', label: 'DeepSeek Chat', note: '' },
      { value: 'deepseek-reasoner', label: 'DeepSeek Reasoner', note: '' },
    ])
    const admin = adminDefaultModelsFor(PROVIDER_CATALOG)
    expect(admin.find((m) => m.recommended).id).toBe('deepseek-reasoner')
  })
})

describe('useModelProviderStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia())
    vi.clearAllMocks()
  })

  it('reads the catalog once and keeps it on a failed refresh', async () => {
    api.get.mockResolvedValueOnce({ data: PROVIDER_CATALOG })
    const store = useModelProviderStore()
    await store.fetchCatalog()
    await store.fetchCatalog()
    expect(api.get).toHaveBeenCalledTimes(1)

    api.get.mockRejectedValueOnce(new Error('offline'))
    await store.fetchCatalog({ force: true })
    expect(store.catalog).toEqual(PROVIDER_CATALOG)
    expect(store.catalogError).toBeTruthy()
  })

  it('a failed status read is "failed", never an empty config', async () => {
    api.get.mockRejectedValueOnce(new Error('offline'))
    const store = useModelProviderStore()
    await store.fetchStatus()
    expect(store.hasLoaded).toBe(false)
    expect(store.loadError).toBeTruthy()
  })

  it('saving refreshes the shared catalog and the pending count', async () => {
    api.put.mockResolvedValueOnce({ data: { mode: 'custom', active: true } })
    api.get.mockImplementation((url) => Promise.resolve({
      data: url.endsWith('/pending') ? { agents: ['a1'], count: 1 } : PROVIDER_CATALOG,
    }))
    const store = useModelProviderStore()
    await store.save({ mode: 'custom' })
    expect(api.put).toHaveBeenCalledWith('/api/settings/model-provider', { mode: 'custom' })
    expect(store.catalog).toEqual(PROVIDER_CATALOG)
    expect(store.pending.count).toBe(1)
  })

  it('apply clears the pending banner', async () => {
    api.post.mockResolvedValueOnce({ data: { restarting: ['a1'], count: 1 } })
    const store = useModelProviderStore()
    store.pending = { agents: ['a1'], count: 1 }
    const result = await store.apply()
    expect(result.count).toBe(1)
    expect(store.pending.count).toBe(0)
  })
})
