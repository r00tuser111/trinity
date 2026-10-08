// @vitest-environment jsdom
import { beforeAll, beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { nextTick } from 'vue'
import { readFileSync } from 'fs'
import { URL as NodeURL, fileURLToPath } from 'url'
import { initializeLocale, loadMessages, locale, setLocale, t, LOCALE_STORAGE_KEY } from '../../src/i18n'
import LanguageSelect from '../../src/components/LanguageSelect.vue'
import zhCN from '../../src/i18n/zh-CN.json'
import { formatRelativeTime } from '../../src/utils/timestamps'

// Node >= 25 ships its own (unconfigured) localStorage global, which shadows jsdom's.
Object.defineProperty(globalThis, 'localStorage', { value: globalThis.jsdom.window.localStorage, configurable: true })
const StoragePrototype = Object.getPrototypeOf(localStorage)

describe('catalog loading', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.resetModules()
  })

  it('keeps translations out of the initial bundle', () => {
    const source = readFileSync(fileURLToPath(new NodeURL('../../src/i18n/index.js', import.meta.url)), 'utf8')
    expect(source).not.toMatch(/^import .*\.json/m)
  })

  it('switches only once the catalog has arrived, never into a half-translated view', async () => {
    const i18n = await import('../../src/i18n')
    expect(i18n.setLocale('zh-CN')).toBe(true)
    expect(i18n.locale.value).toBe('en')
    expect(i18n.t('Dashboard')).toBe('Dashboard')
    await vi.waitFor(() => expect(i18n.locale.value).toBe('zh-CN'))
    expect(i18n.t('Dashboard')).toBe('仪表盘')
    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('zh-CN')
  })

  it('a later choice wins over a catalog that is still loading', async () => {
    const i18n = await import('../../src/i18n')
    i18n.setLocale('zh-CN')
    i18n.setLocale('en')
    await i18n.loadMessages('zh-CN')
    await nextTick()
    expect(i18n.locale.value).toBe('en')
    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('en')
  })

  it('initialization resolves once the saved language can render', async () => {
    localStorage.setItem(LOCALE_STORAGE_KEY, 'zh-CN')
    const i18n = await import('../../src/i18n')
    await i18n.initializeLocale(['en-US'])
    expect(i18n.locale.value).toBe('zh-CN')
    expect(i18n.t('Dashboard')).toBe('仪表盘')
  })
})

beforeAll(() => loadMessages('zh-CN'))

beforeEach(() => {
  localStorage.clear()
  setLocale('en')
})

describe('interface language', () => {
  it('prefers a saved language over browser preferences', () => {
    localStorage.setItem(LOCALE_STORAGE_KEY, 'en')
    initializeLocale(['zh-CN'])
    expect(locale.value).toBe('en')
    localStorage.setItem(LOCALE_STORAGE_KEY, 'zh-CN')
    initializeLocale(['en-US'])
    expect(locale.value).toBe('zh-CN')
    expect(document.documentElement.lang).toBe('zh-CN')
  })

  it.each(['zh-CN', 'zh-SG', 'zh-Hans', 'zh-Hans-CN', 'zh'])('detects Simplified Chinese: %s', (language) => {
    localStorage.removeItem(LOCALE_STORAGE_KEY)
    initializeLocale([language])
    expect(locale.value).toBe('zh-CN')
  })

  it('falls back to English for unsupported preferences and ignores corrupt storage', () => {
    localStorage.setItem(LOCALE_STORAGE_KEY, 'invalid')
    initializeLocale(['fr-FR'])
    expect(locale.value).toBe('en')
    initializeLocale(['zh-TW'])
    expect(locale.value).toBe('en')
    expect(setLocale('invalid')).toBe(false)
    expect(locale.value).toBe('en')
  })

  it('survives blocked browser storage', () => {
    const get = vi.spyOn(StoragePrototype, 'getItem').mockImplementation(() => { throw new Error('blocked') })
    const set = vi.spyOn(StoragePrototype, 'setItem').mockImplementation(() => { throw new Error('blocked') })
    initializeLocale(['zh-CN'])
    expect(locale.value).toBe('zh-CN')
    expect(() => setLocale('en')).not.toThrow()
    get.mockRestore()
    set.mockRestore()
  })

  it('falls back to source copy and interpolates values literally', () => {
    setLocale('zh-CN')
    expect(t('Dashboard')).toBe('仪表盘')
    expect(t('Untranslated message {name}', { name: '$& <admin>' })).toBe('Untranslated message $& <admin>')
    expect(t('Untranslated {missing}')).toBe('Untranslated {missing}')
  })

  it('keeps every interpolation parameter in the translated catalog', () => {
    const parameters = message => [...message.matchAll(/\{(\w+)\}/g)].map(match => match[1]).sort()
    for (const [source, translation] of Object.entries(zhCN)) {
      expect(translation.trim(), source).not.toBe('')
      expect(parameters(translation), source).toEqual(parameters(source))
    }
  })

  it('localizes relative time and interpolates without translating agent names', () => {
    setLocale('zh-CN')
    const fiveMinutesAgo = new Date(Date.now() - 5 * 60 * 1000).toISOString()
    expect(formatRelativeTime(fiveMinutesAgo)).toBe('5 分钟前')
    expect(t('Message {agent}…  ·  / for playbooks', { agent: 'Dashboard' }))
      .toBe('发送消息给 Dashboard…  ·  输入 / 使用操作手册')
  })

  it('switches mounted copy without remounting or discarding input, and persists the selection', async () => {
    const wrapper = mount({
      components: { LanguageSelect },
      setup: () => ({ t }),
      template: '<div><LanguageSelect /><h1>{{ t("Dashboard") }}</h1><input aria-label="draft" /></div>',
    })
    const draft = wrapper.get('input').element
    await wrapper.get('input').setValue('my unsent draft')
    await wrapper.get('select').setValue('zh-CN')
    await nextTick()
    expect(wrapper.get('h1').text()).toBe('仪表盘')
    expect(wrapper.get('select').attributes('aria-label')).toBe('语言')
    expect(localStorage.getItem(LOCALE_STORAGE_KEY)).toBe('zh-CN')
    expect(wrapper.get('input').element).toBe(draft)
    expect(draft.value).toBe('my unsent draft')
    await wrapper.get('select').setValue('en')
    expect(wrapper.get('h1').text()).toBe('Dashboard')
    expect(document.documentElement.lang).toBe('en')
    wrapper.unmount()
  })
})
