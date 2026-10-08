import { readonly, ref } from 'vue'

// Source English is the message key and fallback. Translate only explicit UI
// copy: never walk the DOM or transform user content, API values or identifiers.
export const LOCALE_STORAGE_KEY = 'trinity-locale'
export const LANGUAGES = Object.freeze([
  { value: 'en', label: 'English' },
  { value: 'zh-CN', label: '简体中文' },
])
// Catalogs are separate chunks so English sessions never download them.
const loaders = { 'zh-CN': () => import('./zh-CN.json') }
const catalogs = {}
const currentLocale = ref('en')
export const locale = readonly(currentLocale)
let requestedLocale = 'en'

export async function loadMessages(value) {
  if (!catalogs[value] && loaders[value]) catalogs[value] = (await loaders[value]()).default
}

// The switch happens only once the catalog is present, so a view is never
// half-translated; the latest request wins if catalogs arrive out of order.
function applyLocale(value) {
  requestedLocale = value
  const show = () => {
    if (requestedLocale !== value) return
    currentLocale.value = value
    if (typeof document !== 'undefined') document.documentElement.lang = value
  }
  if (catalogs[value] || !loaders[value]) return show()
  return loadMessages(value).then(show, () => { /* Catalog unavailable: stay in the current language. */ })
}

export function setLocale(value) {
  if (!LANGUAGES.some(language => language.value === value)) return false
  applyLocale(value)
  try { localStorage.setItem(LOCALE_STORAGE_KEY, value) } catch { /* Private/blocked storage: keep this session usable. */ }
  return true
}

export function initializeLocale(languages = globalThis.navigator?.languages || []) {
  let saved
  try { saved = localStorage.getItem(LOCALE_STORAGE_KEY) } catch { /* Browser preference still works. */ }
  if (LANGUAGES.some(language => language.value === saved)) return Promise.resolve(applyLocale(saved))
  // Traditional Chinese is not advertised as supported. Prefer the browser's
  // primary language, falling back to English for other languages.
  const preferred = languages[0] || globalThis.navigator?.language || 'en'
  return Promise.resolve(applyLocale(/^zh(?:$|-(?:CN|SG|Hans)(?:-|$))/i.test(preferred) ? 'zh-CN' : 'en'))
}

// Marks source copy that is stored as a value (exported constants, lookup
// tables) and passed through `t()` where it renders. Returns it unchanged.
export const msg = message => message

export function t(message, params = {}) {
  const catalog = catalogs[currentLocale.value]
  const translated = catalog && Object.hasOwn(catalog, message) ? catalog[message] : message
  if (typeof translated !== 'string') return translated ?? ''
  return translated.replace(/\{(\w+)\}/g, (match, key) =>
    Object.hasOwn(params, key) ? String(params[key]) : match)
}
