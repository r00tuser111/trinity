import { t as uiText } from '../i18n/index.js'
import { MODEL_CATALOG } from '../constants/modelCatalog.js'
import presets from '../constants/modelProviderPresets.json'

/**
 * Custom model provider (LLM-PROVIDER-001) — the pure half of the Settings
 * card and the model pickers. `vitest` runs in `node` (no component mounting),
 * so everything a test needs to pin lives here, not in the .vue files.
 *
 * The backend is the authority (`services/llm_provider.py`); these checks only
 * pre-validate what is knowable client-side so the common mistakes are named
 * before a round-trip (principle 17).
 */

// Mirrors `_MODEL_ID_RE` in services/llm_provider.py.
export const MODEL_ID_RE = /^[A-Za-z0-9][A-Za-z0-9._:/@[\]-]{0,127}$/
export const MAX_MODELS = 50
export const DEFAULT_CONTEXT_WINDOW = 128000

// Anthropic-compatible endpoints only (phase 1). A preset is a starting
// proposal (principle 3) — every field stays editable. Kept as data: the
// labels are product names, not copy to translate.
export const PROVIDER_PRESETS = presets

export function emptyModelRow() {
  return { id: '', label: '', context_window: '' }
}

/** Editable form state from `GET /api/settings/model-provider`. */
export function formFromStatus(status) {
  const models = (status?.models || []).map((m) => ({
    id: m.id || '',
    label: m.label && m.label !== m.id ? m.label : '',
    context_window: m.context_window ? String(m.context_window) : '',
  }))
  return {
    mode: status?.mode === 'custom' ? 'custom' : 'anthropic',
    base_url: status?.base_url || '',
    api_key: '',
    models: models.length ? models : [emptyModelRow()],
    default_model: status?.default_model || '',
    fast_model: status?.fast_model || '',
  }
}

export function applyPreset(form, preset) {
  return {
    ...form,
    mode: 'custom',
    base_url: preset.base_url,
    models: preset.models.map((m) => ({ ...m, context_window: String(m.context_window) })),
    default_model: preset.default_model,
    fast_model: preset.fast_model,
  }
}

function filledRows(form) {
  return (form.models || []).filter((m) => (m.id || '').trim() || (m.label || '').trim())
}

export function listedModelIds(form) {
  return filledRows(form).map((m) => (m.id || '').trim()).filter(Boolean)
}

/**
 * Named, fixable problems keyed by field; `{}` when the form may be sent.
 * `apiKeyConfigured` — a blank key keeps the stored one.
 */
export function validateProviderForm(form, { apiKeyConfigured = false } = {}) {
  const errors = {}
  if (form.mode !== 'custom') return errors

  const url = (form.base_url || '').trim()
  if (!url) {
    errors.base_url = uiText('Enter the provider\'s Anthropic-compatible base URL, e.g. https://api.deepseek.com/anthropic.')
  } else {
    let parsed = null
    try { parsed = new URL(url) } catch { parsed = null }
    if (!parsed || !['http:', 'https:'].includes(parsed.protocol)) {
      errors.base_url = uiText('Use an http(s) URL, e.g. https://api.deepseek.com/anthropic.')
    } else if (parsed.username || parsed.password) {
      errors.base_url = uiText('Remove the credentials from the URL — put the key in the API key field.')
    } else if (parsed.search || parsed.hash) {
      errors.base_url = uiText('Remove the query string or fragment from the URL.')
    }
  }

  if (!(form.api_key || '').trim() && !apiKeyConfigured) {
    errors.api_key = uiText('Enter the provider\'s API key.')
  }

  const rows = filledRows(form)
  const seen = new Set()
  for (const row of rows) {
    const id = (row.id || '').trim()
    if (!id) {
      errors.models = uiText('Every model row needs an id, e.g. deepseek-chat.')
      break
    }
    if (!MODEL_ID_RE.test(id)) {
      errors.models = uiText('"{arg1}" is not a valid model id — use letters, digits and . _ - : / @ only.', { arg1: id })
      break
    }
    if (seen.has(id)) {
      errors.models = uiText('"{arg1}" is listed twice.', { arg1: id })
      break
    }
    seen.add(id)
    const cw = String(row.context_window ?? '').trim()
    if (cw && !/^\d+$/.test(cw)) {
      errors.models = uiText('The context window for "{arg1}" must be a whole number of tokens, e.g. 128000.', { arg1: id })
      break
    }
  }
  if (!errors.models && rows.length === 0) {
    errors.models = uiText('Add at least one model the provider serves, e.g. deepseek-chat.')
  }
  if (!errors.models && rows.length > MAX_MODELS) {
    errors.models = uiText('At most {arg1} models.', { arg1: MAX_MODELS })
  }

  if (!errors.models) {
    for (const key of ['default_model', 'fast_model']) {
      const value = (form[key] || '').trim()
      if (value && !seen.has(value)) {
        errors[key] = uiText('Pick one of the listed models.')
      }
    }
  }
  return errors
}

/** Body for `PUT /api/settings/model-provider`. */
export function buildProviderPayload(form) {
  if (form.mode !== 'custom') return { mode: 'anthropic' }
  const models = filledRows(form).map((m) => {
    const cw = String(m.context_window ?? '').trim()
    return {
      id: (m.id || '').trim(),
      label: (m.label || '').trim() || null,
      context_window: cw ? Number(cw) : null,
    }
  })
  const body = {
    mode: 'custom',
    base_url: (form.base_url || '').trim(),
    models,
    default_model: (form.default_model || '').trim() || null,
    fast_model: (form.fast_model || '').trim() || null,
  }
  const key = (form.api_key || '').trim()
  if (key) body.api_key = key
  return body
}

/** Body for `POST /api/settings/model-provider/test` — a blank key reuses the stored one. */
export function buildTestPayload(form) {
  const ids = listedModelIds(form)
  const body = {
    base_url: (form.base_url || '').trim(),
    model: (form.default_model || '').trim() || ids[0] || '',
  }
  const key = (form.api_key || '').trim()
  if (key) body.api_key = key
  return body
}

/** True when the provider-controlled catalog is in force. */
export function isProviderCatalog(catalog) {
  return catalog?.provider === 'custom' && Array.isArray(catalog.models)
}

/** ModelSelector presets: the provider's models, or the Claude catalog. */
export function presetModelsFor(catalog) {
  if (isProviderCatalog(catalog)) {
    return catalog.models.map((m) => ({ value: m.id, label: m.label || m.id, note: '' }))
  }
  return MODEL_CATALOG.map((m) => ({ value: m.id, label: m.label, note: m.note }))
}

/** Admin fleet-default dropdown options (Haiku excluded for Claude, #1080). */
export function adminDefaultModelsFor(catalog) {
  if (isProviderCatalog(catalog)) {
    return catalog.models.map((m) => ({
      id: m.id,
      label: m.label || m.id,
      note: '',
      recommended: m.id === catalog.default_model,
    }))
  }
  return MODEL_CATALOG.filter((m) => m.adminDefaultSelectable)
}
