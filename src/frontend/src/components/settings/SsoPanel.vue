<template>
  <div class="space-y-8">
    <!-- Header -->
    <div>
      <h3 class="text-lg font-semibold text-gray-900 dark:text-gray-100">{{ uiText("Single Sign-On (OIDC)") }}</h3>
      <p class="mt-1 text-sm text-gray-600 dark:text-gray-400">
        {{ uiText("Let users sign in through your identity provider (Okta, Entra ID, Google Workspace). SAML support is coming separately.") }}
      </p>
    </div>

    <p v-if="error" class="text-sm text-red-600 dark:text-red-400">{{ error }}</p>

    <!-- Providers -->
    <section class="space-y-3">
      <h4 class="text-sm font-medium text-gray-800 dark:text-gray-200">{{ uiText("Identity providers") }}</h4>

      <div v-if="!providers.length" class="text-sm text-gray-500 dark:text-gray-400">
        {{ uiText("No providers configured yet.") }}
      </div>

      <div
        v-for="p in providers"
        :key="p.id"
        class="flex items-center justify-between p-3 border border-gray-200 dark:border-gray-700 rounded-lg"
      >
        <div class="min-w-0">
          <p class="font-medium text-gray-900 dark:text-gray-100 truncate">
            {{ p.name }}
            <span v-if="!p.enabled" class="ml-2 text-xs text-gray-400">{{ uiText("(disabled)") }}</span>
          </p>
          <p class="text-xs text-gray-500 dark:text-gray-400 truncate">{{ p.issuer }}</p>
        </div>
        <div class="flex items-center gap-2 shrink-0">
          <button @click="test(p)" class="text-xs px-2 py-1 border border-gray-300 dark:border-gray-600 rounded hover:bg-gray-50 dark:hover:bg-gray-700">{{ uiText("Test") }}</button>
          <button @click="remove(p)" class="text-xs px-2 py-1 border border-red-300 text-red-600 rounded hover:bg-red-50 dark:hover:bg-red-900/30">{{ uiText("Delete") }}</button>
        </div>
      </div>

      <p v-if="testResult" class="text-xs text-green-600 dark:text-green-400">{{ testResult }}</p>
    </section>

    <!-- Add provider -->
    <section class="space-y-3 p-4 border border-gray-200 dark:border-gray-700 rounded-lg">
      <h4 class="text-sm font-medium text-gray-800 dark:text-gray-200">{{ uiText("Add provider") }}</h4>
      <form @submit.prevent="add" class="space-y-3">
        <input v-model="form.name" :placeholder="uiText(&quot;Display name (e.g. Okta)&quot;)" required :class="inputCls" />
        <input v-model="form.issuer" :placeholder="uiText(&quot;Issuer / discovery URL (https://…)&quot;)" required :class="inputCls" />
        <input v-model="form.client_id" :placeholder="uiText(&quot;Client ID&quot;)" required :class="inputCls" />
        <input v-model="form.client_secret" type="password" :placeholder="uiText(&quot;Client secret&quot;)" required :class="inputCls" />
        <input v-model="form.scopes" :placeholder="uiText(&quot;Scopes&quot;)" :class="inputCls" />
        <label class="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
          <input v-model="form.enabled" type="checkbox" /> {{ uiText("Enabled") }}
        </label>
        <button type="submit" :disabled="busy" :class="btnCls">{{ busy ? uiText("Saving…") : uiText("Add provider") }}</button>
      </form>
    </section>

    <!-- Policy -->
    <section class="space-y-3">
      <h4 class="text-sm font-medium text-gray-800 dark:text-gray-200">{{ uiText("Policy") }}</h4>
      <label class="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
        <input v-model="cfg.allow_password_fallback" type="checkbox" @change="saveConfig" />
        {{ uiText("Keep email / admin password login available") }}
      </label>
      <label class="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
        <input v-model="cfg.auto_provision" type="checkbox" @change="saveConfig" />
        {{ uiText("Auto-provision new users from SSO (otherwise the email must be whitelisted)") }}
      </label>
      <label class="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
        {{ uiText("Default role for provisioned users") }}
        <select v-model="cfg.default_role" @change="saveConfig" class="ml-2 text-sm border border-gray-300 dark:border-gray-600 rounded px-2 py-1 bg-white dark:bg-gray-700">
          <option value="user">{{ uiText("user") }}</option>
          <option value="operator">{{ uiText("operator") }}</option>
          <option value="creator">{{ uiText("creator") }}</option>
          <option value="admin">{{ uiText("admin") }}</option>
        </select>
      </label>
      <p class="text-xs text-gray-500 dark:text-gray-400">{{ uiText("Admin break-glass password login always remains available.") }}</p>
    </section>
  </div>
</template>

<script setup>
import { ref, reactive, onMounted } from 'vue'
import axios from 'axios'
import { useAuthStore } from '../../stores/auth'

const authStore = useAuthStore()
const BASE = '/api/enterprise/sso'
const cfgHeaders = () => ({ headers: { Authorization: `Bearer ${authStore.token}` } })

const inputCls = 'block w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 text-sm'
const btnCls = 'w-full py-2 px-4 rounded-lg text-white bg-blue-600 hover:bg-blue-700 disabled:opacity-50 text-sm'

const providers = ref([])
const cfg = reactive({ allow_password_fallback: true, auto_provision: false, default_role: 'user' })
const form = reactive({ name: '', issuer: '', client_id: '', client_secret: '', scopes: 'openid email profile', enabled: true })
const busy = ref(false)
const error = ref('')
const testResult = ref('')

async function loadProviders() {
  const r = await axios.get(`${BASE}/providers`, cfgHeaders())
  providers.value = r.data.providers || []
}

async function loadConfig() {
  const r = await axios.get(`${BASE}/config`, cfgHeaders())
  Object.assign(cfg, r.data)
}

async function add() {
  busy.value = true
  error.value = ''
  try {
    await axios.post(`${BASE}/providers`, { ...form }, cfgHeaders())
    Object.assign(form, { name: '', issuer: '', client_id: '', client_secret: '', scopes: 'openid email profile', enabled: true })
    await loadProviders()
  } catch (e) {
    error.value = e.response?.data?.detail || uiText("Failed to add provider")
  } finally {
    busy.value = false
  }
}

async function remove(p) {
  if (!confirm(uiText("Delete SSO provider \"{arg1}\"?", { arg1: (p.name) }))) return
  error.value = ''
  try {
    await axios.delete(`${BASE}/providers/${p.id}`, cfgHeaders())
    await loadProviders()
  } catch (e) {
    error.value = e.response?.data?.detail || uiText("Failed to delete provider")
  }
}

async function test(p) {
  testResult.value = ''
  error.value = ''
  try {
    const r = await axios.post(`${BASE}/providers/${p.id}/test`, {}, cfgHeaders())
    testResult.value = uiText('{name}: discovery OK ({count} signing keys)', { name: p.name, count: r.data.jwks_keys })
  } catch (e) {
    error.value = e.response?.data?.detail || uiText("Connectivity test failed for {arg1}", { arg1: (p.name) })
  }
}

async function saveConfig() {
  error.value = ''
  try {
    await axios.put(`${BASE}/config`, { ...cfg }, cfgHeaders())
  } catch (e) {
    error.value = e.response?.data?.detail || uiText("Failed to save policy")
  }
}

onMounted(async () => {
  try {
    await Promise.all([loadProviders(), loadConfig()])
  } catch (e) {
    error.value = e.response?.data?.detail || uiText("Failed to load SSO settings")
  }
})

import { t as uiText } from '@/i18n'
</script>
