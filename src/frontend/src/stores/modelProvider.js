import { defineStore } from 'pinia'
import api from '../api'

// LLM-PROVIDER-001 — the platform's model provider.
//   catalog:  `GET /api/settings/model-catalog` (any user) — what every model
//             picker offers. `models: null` means the Claude catalog applies.
//   status:   `GET /api/settings/model-provider` (admin) — the editable config,
//             key masked.
// A failed catalog read keeps whatever was shown and the pickers fall back to
// the Claude catalog; the backend still validates every model it is sent.
export const useModelProviderStore = defineStore('modelProvider', {
  state: () => ({
    catalog: null,
    catalogLoaded: false,
    catalogError: null,
    status: null,
    hasLoaded: false,
    loadError: null,
    pending: null,     // { agents: [...], count } — running agents on the old provider
  }),

  actions: {
    async fetchCatalog({ force = false } = {}) {
      if (this.catalogLoaded && !force) return this.catalog
      try {
        const { data } = await api.get('/api/settings/model-catalog')
        this.catalog = data || null
        this.catalogLoaded = true
        this.catalogError = null
      } catch (e) {
        this.catalogError = e
      }
      return this.catalog
    },

    async fetchStatus() {
      try {
        const { data } = await api.get('/api/settings/model-provider')
        this.status = data || null
        this.hasLoaded = true
        this.loadError = null
      } catch (e) {
        this.loadError = e
      }
      return this.status
    },

    async fetchPending() {
      try {
        const { data } = await api.get('/api/settings/model-provider/pending')
        this.pending = data || { agents: [], count: 0 }
      } catch {
        // Advisory only: the apply verb reports its own failure.
      }
      return this.pending
    },

    /** Live check; resolves to `{valid, error?, model?}` — never stores. */
    async test(body) {
      const { data } = await api.post('/api/settings/model-provider/test', body)
      return data
    },

    async save(body) {
      const { data } = await api.put('/api/settings/model-provider', body)
      this.status = data
      this.hasLoaded = true
      await Promise.all([this.fetchCatalog({ force: true }), this.fetchPending()])
      return data
    },

    async remove() {
      const { data } = await api.delete('/api/settings/model-provider')
      this.status = data
      await Promise.all([this.fetchCatalog({ force: true }), this.fetchPending()])
      return data
    },

    async apply() {
      const { data } = await api.post('/api/settings/model-provider/apply')
      const leftover = (data?.not_ready?.length || 0) + (data?.skipped?.length || 0)
      if (leftover) await this.fetchPending()
      else this.pending = { agents: [], count: 0 }
      return data
    },
  },
})
