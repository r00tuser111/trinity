<template>
  <div>
    <h3 class="text-lg font-medium text-gray-900 dark:text-white mb-2">{{ uiText("WhatsApp (Twilio)") }}</h3>
    <p class="text-sm text-gray-500 dark:text-gray-400 mb-4">
      {{ uiText("Connect a Twilio WhatsApp sender so users can message this agent on WhatsApp. Each agent brings its own Twilio account; direct messages only (Twilio does not support WhatsApp groups).") }}
    </p>

    <!-- Loading -->
    <div v-if="loading" class="flex items-center gap-2 text-sm text-gray-500 dark:text-gray-400">
      <svg class="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
      </svg>
      {{ uiText("Loading...") }}
    </div>

    <!-- Access Denied -->
    <div v-else-if="accessDenied" class="text-sm text-gray-500 dark:text-gray-400">
      {{ uiText("Only the agent owner can manage WhatsApp settings.") }}
    </div>

    <!-- Connected State -->
    <div v-else-if="binding.configured" class="space-y-3">
      <div class="p-4 bg-gray-50 dark:bg-gray-900/50 rounded-lg border border-gray-200 dark:border-gray-700">
        <div class="flex items-center justify-between">
          <div class="flex items-center gap-3">
            <span class="inline-block w-2.5 h-2.5 rounded-full bg-status-success-500"></span>
            <div>
              <p class="text-sm font-medium text-gray-900 dark:text-white">
                {{ binding.from_number }}
                <span
                  v-if="binding.is_sandbox"
                  class="ml-2 px-1.5 py-0.5 text-xs rounded bg-status-warning-100 dark:bg-status-warning-900/50 text-status-warning-800 dark:text-status-warning-200"
                >{{ uiText("Sandbox") }}</span>
              </p>
              <p class="text-xs text-gray-500 dark:text-gray-400">
                {{ uiText("AccountSid:") }} {{ truncatedSid }}
                <span v-if="binding.display_name"> · {{ binding.display_name }}</span>
              </p>
            </div>
          </div>
          <div class="flex items-center gap-2">
            <button
              @click="verifyCredentials"
              :disabled="verifying"
              class="text-sm text-action-primary-600 dark:text-action-primary-400 hover:text-action-primary-800 dark:hover:text-action-primary-300 disabled:opacity-50"
            >
              {{ verifying ? uiText("Verifying...") : uiText("Verify") }}
            </button>
            <button
              @click="disconnectBinding"
              :disabled="disconnecting"
              class="text-sm text-status-danger-600 dark:text-status-danger-400 hover:text-status-danger-800 dark:hover:text-status-danger-300 disabled:opacity-50"
            >
              {{ disconnecting ? uiText("Removing...") : uiText("Disconnect") }}
            </button>
          </div>
        </div>
      </div>

      <!-- Webhook URL Display -->
      <div v-if="binding.webhook_url" class="p-3 rounded-lg bg-action-primary-50 dark:bg-action-primary-900/20 border border-action-primary-100 dark:border-action-primary-800/40">
        <p class="text-xs font-medium text-action-primary-900 dark:text-action-primary-200 mb-1">
          {{ uiText("Webhook URL — paste into Twilio Console") }}
        </p>
        <div class="flex items-center gap-2">
          <code class="flex-1 text-xs text-action-primary-900 dark:text-action-primary-100 font-mono break-all select-all">
            {{ binding.webhook_url }}
          </code>
          <button
            @click="copyWebhook"
            class="text-xs text-action-primary-700 dark:text-action-primary-300 hover:text-action-primary-900 dark:hover:text-action-primary-100"
          >
            {{ copied ? uiText("Copied!") : uiText("Copy") }}
          </button>
        </div>
        <p class="mt-2 text-xs text-action-primary-700 dark:text-action-primary-300">
          {{ uiText("In Twilio Console → Messaging →") }} {{ binding.is_sandbox ? uiText("Sandbox settings") : uiText("your sender") }} →
          <strong>{{ uiText("When a message comes in") }}</strong>{{ uiText(", set method to") }} <strong>HTTP POST</strong> {{ uiText("and paste this URL.") }}
        </p>
      </div>

      <!-- Ops prerequisite notice -->
      <div class="p-3 rounded-lg text-xs bg-state-autonomous-50 dark:bg-state-autonomous-900/30 text-state-autonomous-800 dark:text-state-autonomous-200">
        <strong>{{ uiText("Deployment prerequisite:") }}</strong> {{ uiText("Cloudflare Tunnel ingress must route") }}
        <code class="font-mono">/api/whatsapp/webhook/*</code> {{ uiText("to the") }} <strong>{{ uiText("backend") }}</strong> {{ uiText("service (") }}<code class="font-mono">http://backend:8000</code>{{ uiText("). See") }} <em>docs/requirements/PUBLIC_EXTERNAL_ACCESS_SETUP.md</em>.
      </div>

      <!-- Webhook URL warning (no public_chat_url) -->
      <div
        v-if="binding.warning"
        class="p-3 rounded-lg text-sm bg-status-warning-50 dark:bg-status-warning-900/30 text-status-warning-700 dark:text-status-warning-300"
      >
        {{ binding.warning }}
      </div>

      <!-- Sandbox instructions -->
      <div v-if="binding.is_sandbox" class="p-3 rounded-lg text-xs bg-gray-50 dark:bg-gray-900/50 border border-gray-200 dark:border-gray-700">
        <p class="font-medium text-gray-700 dark:text-gray-300 mb-1">{{ uiText("Sandbox testing") }}</p>
        <p class="text-gray-600 dark:text-gray-400">
          {{ uiText("Users must opt in by sending") }} <code class="font-mono">join &lt;your-sandbox-keyword&gt;</code> {{ uiText("from their phone to") }} <code class="font-mono">{{ binding.from_number }}</code>{{ uiText(". Check your Twilio Console → Messaging → Try WhatsApp for the keyword.") }}
        </p>
      </div>

      <!-- Voice replies (epic #24 / trinity-enterprise#56) — shared agent-level TTS control -->
      <VoiceChannelToggle :agent-name="agentName" channel="whatsapp" class="mt-2" />
    </div>

    <!-- Disconnected State — Credentials Form -->
    <div v-else>
      <form @submit.prevent="connectBinding" class="space-y-3 max-w-lg">
        <div>
          <label for="wa-account-sid" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            {{ uiText("Twilio Account SID") }}
          </label>
          <input
            id="wa-account-sid"
            v-model="form.accountSid"
            type="text"
            :placeholder="uiText(&quot;ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx&quot;)"
            :disabled="connecting"
            class="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-action-primary-500 disabled:bg-gray-100 dark:disabled:bg-gray-900 font-mono text-xs"
          />
        </div>
        <div>
          <label for="wa-auth-token" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            {{ uiText("Auth Token") }}
          </label>
          <input
            id="wa-auth-token"
            v-model="form.authToken"
            type="password"
            :placeholder="uiText(&quot;Paste your Twilio Auth Token&quot;)"
            :disabled="connecting"
            class="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-action-primary-500 disabled:bg-gray-100 dark:disabled:bg-gray-900"
          />
          <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
            {{ uiText("From Twilio Console — stored encrypted.") }}
          </p>
        </div>
        <div>
          <label for="wa-from" class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
            {{ uiText("WhatsApp From Number") }}
          </label>
          <input
            id="wa-from"
            v-model="form.fromNumber"
            type="text"
            :placeholder="uiText(&quot;whatsapp:+14155238886&quot;)"
            :disabled="connecting"
            class="w-full px-4 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-400 dark:placeholder-gray-500 focus:outline-none focus:ring-2 focus:ring-action-primary-500 disabled:bg-gray-100 dark:disabled:bg-gray-900 font-mono text-xs"
          />
          <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
            {{ uiText("Must start with") }} <code class="font-mono">whatsapp:+</code>{{ uiText(". Use") }}
            <code class="font-mono">whatsapp:+14155238886</code> {{ uiText("for Twilio Sandbox.") }}
          </p>
        </div>
        <button
          type="submit"
          :disabled="connecting || !canSubmit"
          class="inline-flex items-center px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-action-primary-600 hover:bg-action-primary-700 disabled:opacity-50 disabled:cursor-not-allowed"
        >
          <svg v-if="connecting" class="animate-spin -ml-1 mr-2 h-4 w-4" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          {{ connecting ? uiText("Validating...") : uiText("Connect") }}
        </button>
      </form>
    </div>

    <!-- Messages -->
    <div
      v-if="message"
      :class="[
        'mt-3 p-3 rounded-lg text-sm',
        message.type === 'success'
          ? 'bg-status-success-50 dark:bg-status-success-900/30 text-status-success-700 dark:text-status-success-300'
          : 'bg-status-danger-50 dark:bg-status-danger-900/30 text-status-danger-700 dark:text-status-danger-300'
      ]"
    >
      {{ message.text }}
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import api from '../api'
import VoiceChannelToggle from './VoiceChannelToggle.vue'

const props = defineProps({
  agentName: {
    type: String,
    required: true
  }
})

const loading = ref(true)
const connecting = ref(false)
const disconnecting = ref(false)
const verifying = ref(false)
const accessDenied = ref(false)
const copied = ref(false)
const binding = ref({ configured: false })
const message = ref(null)
const form = ref({ accountSid: '', authToken: '', fromNumber: '' })

const canSubmit = computed(() =>
  form.value.accountSid.trim() &&
  form.value.authToken.trim() &&
  form.value.fromNumber.trim()
)

const truncatedSid = computed(() => {
  const sid = binding.value?.account_sid || ''
  if (sid.length <= 12) return sid
  return `${sid.slice(0, 8)}...${sid.slice(-4)}`
})

async function loadBinding() {
  loading.value = true
  message.value = null
  accessDenied.value = false
  try {
    const response = await api.get(`/api/agents/${props.agentName}/whatsapp`)
    binding.value = response.data
  } catch (e) {
    if (e.response?.status === 403) {
      accessDenied.value = true
    }
    binding.value = { configured: false }
  } finally {
    loading.value = false
  }
}

async function connectBinding() {
  connecting.value = true
  message.value = null
  try {
    const response = await api.put(`/api/agents/${props.agentName}/whatsapp`, {
      account_sid: form.value.accountSid.trim(),
      auth_token: form.value.authToken.trim(),
      from_number: form.value.fromNumber.trim()
    })
    form.value = { accountSid: '', authToken: '', fromNumber: '' }
    binding.value = response.data
    message.value = { type: 'success', get "text"() { return uiText("WhatsApp binding configured") } }
    setTimeout(() => { message.value = null }, 3000)
  } catch (e) {
    const detail = e.response?.data?.detail || uiText('Failed to configure binding')
    message.value = { type: 'error', text: detail }
  } finally {
    connecting.value = false
  }
}

async function disconnectBinding() {
  disconnecting.value = true
  message.value = null
  try {
    await api.delete(`/api/agents/${props.agentName}/whatsapp`)
    binding.value = { configured: false }
    message.value = { type: 'success', get "text"() { return uiText("WhatsApp binding removed") } }
    setTimeout(() => { message.value = null }, 3000)
  } catch (e) {
    const detail = e.response?.data?.detail || uiText('Failed to remove binding')
    message.value = { type: 'error', text: detail }
  } finally {
    disconnecting.value = false
  }
}

async function verifyCredentials() {
  verifying.value = true
  message.value = null
  try {
    const response = await api.post(`/api/agents/${props.agentName}/whatsapp/test`, {})
    if (response.data.ok) {
      message.value = { type: 'success', text: response.data.message }
    } else {
      message.value = { type: 'error', text: response.data.message || uiText("Verification failed") }
    }
    setTimeout(() => { message.value = null }, 3000)
  } catch (e) {
    const detail = e.response?.data?.detail || uiText('Failed to verify credentials')
    message.value = { type: 'error', text: detail }
  } finally {
    verifying.value = false
  }
}

async function copyWebhook() {
  try {
    await navigator.clipboard.writeText(binding.value.webhook_url || '')
    copied.value = true
    setTimeout(() => { copied.value = false }, 1500)
  } catch (e) {
    message.value = { type: 'error', get "text"() { return uiText("Clipboard copy failed — select and copy manually") } }
  }
}

watch(() => props.agentName, () => loadBinding())
onMounted(() => loadBinding())

import { t as uiText } from '@/i18n'
</script>
