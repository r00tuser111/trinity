<template>
  <div>
    <h3 class="text-lg font-medium text-gray-900 dark:text-white mb-2">{{ uiText("Trinity access key") }}</h3>
    <p class="text-sm text-gray-500 dark:text-gray-400 mb-4">
      {{ uiText("The agent-scoped key this agent uses to call Trinity's own MCP tools. It is what makes the") }}
      <span class="font-medium">{{ uiText("Permissions") }}</span> {{ uiText("matrix apply — a container configured with somebody's personal key acts as that person instead, and the matrix is silently bypassed.") }}
    </p>

    <div v-if="loading" class="text-sm text-gray-400">{{ uiText("Loading…") }}</div>

    <div v-else class="space-y-4">
      <!-- Health -->
      <div
        class="rounded-md border p-3"
        :class="toneClass"
      >
        <div class="flex items-center gap-2">
          <span class="inline-block w-2.5 h-2.5 rounded-full" :class="dotClass"></span>
          <span class="text-sm font-medium">{{ healthLabel }}</span>
        </div>
        <p v-if="status.health_detail" class="mt-1 text-xs opacity-90">
          {{ status.health_detail }}
        </p>
      </div>

      <!-- Key metadata (never the secret — only the hash is stored) -->
      <dl v-if="status.exists && status.key_prefix" class="grid grid-cols-2 gap-x-4 gap-y-2 text-sm">
        <dt class="text-gray-500 dark:text-gray-400">{{ uiText("Key") }}</dt>
        <dd class="text-gray-900 dark:text-gray-100">
          <code class="font-mono text-xs">{{ status.key_prefix }}…</code>
        </dd>
        <dt class="text-gray-500 dark:text-gray-400">{{ uiText("Scope") }}</dt>
        <dd class="text-gray-900 dark:text-gray-100">{{ status.scope || '—' }}</dd>
        <dt class="text-gray-500 dark:text-gray-400">{{ uiText("Created") }}</dt>
        <dd class="text-gray-900 dark:text-gray-100">{{ fmt(status.created_at) }}</dd>
        <dt class="text-gray-500 dark:text-gray-400">{{ uiText("Last MCP call") }}</dt>
        <dd class="text-gray-900 dark:text-gray-100">
          {{ status.last_used_at ? fmt(status.last_used_at) : uiText("never") }}
          <span v-if="status.usage_count" class="text-gray-500 dark:text-gray-400">
            ({{ status.usage_count }} {{ uiText("calls)") }}
          </span>
        </dd>
      </dl>

      <!-- What the CONTAINER actually presents (#1854 detect) -->
      <div
        v-if="verify && verify.verdict && verify.verdict !== 'unavailable'"
        class="rounded-md border p-3"
        :class="verifyToneClass"
      >
        <div class="flex items-start justify-between gap-2">
          <div class="min-w-0">
            <p class="text-sm font-medium">{{ verifyLabel }}</p>
            <p v-if="verify.message" class="mt-1 text-xs opacity-90">{{ verify.message }}</p>
          </div>
          <button
            type="button"
            @click="runVerify"
            :disabled="verifying"
            class="shrink-0 px-2 py-1 text-xs font-medium rounded-md text-gray-700 dark:text-gray-200 bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 disabled:opacity-50"
          >{{ verifying ? uiText("Checking…") : uiText("Re-check") }}</button>
        </div>
      </div>
      <div v-else class="flex items-center gap-2">
        <button
          type="button"
          @click="runVerify"
          :disabled="verifying"
          class="px-3 py-1.5 text-sm font-medium rounded-md text-gray-700 dark:text-gray-200 bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600 disabled:opacity-50"
        >{{ verifying ? uiText("Checking…") : uiText("Check what the container is using") }}</button>
        <span v-if="verify && verify.verdict === 'unavailable'" class="text-xs text-gray-500 dark:text-gray-400">
          {{ verify.message }}
        </span>
      </div>

      <!-- Rotate -->
      <div v-if="status.rotatable" class="pt-3 border-t border-gray-200 dark:border-gray-700">
        <button
          type="button"
          @click="regenerate"
          :disabled="busy"
          class="px-3 py-1.5 text-sm font-medium rounded-md text-white bg-action-primary-600 hover:bg-action-primary-700 disabled:opacity-50"
        >{{ busy ? uiText("Working…") : (status.exists ? uiText("Regenerate key") : uiText("Issue a key")) }}</button>
        <p class="mt-2 text-xs text-gray-500 dark:text-gray-400">
          {{ uiText("Issues a fresh key and invalidates the old one. A") }} <strong>{{ uiText("running") }}</strong>
          {{ uiText("agent is restarted to pick it up — in-flight work is interrupted. A") }}
          <strong>{{ uiText("stopped") }}</strong> {{ uiText("agent stays stopped and picks the key up the next time you start it. The key itself is never shown: only its hash is stored, and nothing outside the container needs it.") }}
        </p>
        <p class="mt-1 text-xs text-gray-500 dark:text-gray-400">
          {{ uiText("Restarting the agent also re-applies the correct key on its own, so a restart is usually enough to repair a mismatch.") }}
        </p>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../api'

const props = defineProps({
  agentName: { type: String, required: true },
  // Positional (message, type) — same contract as the other settings panels.
  notify: { type: Function, default: null },
})

function notifyUser(message, type = 'success') {
  if (props.notify) props.notify(message, type)
}

const loading = ref(false)
const busy = ref(false)
const verifying = ref(false)
const status = ref({ exists: false, health: 'missing', rotatable: true })
const verify = ref(null)

const HEALTH_LABELS = {
  missing: msg('No platform key'),
  env_absent: msg('Key not present in the container'),
  env_mismatch: msg('Container key not recognized'),
  never_used: msg('Never used for an MCP call'),
  stale: msg('Key unused while the agent kept working'),
  active: msg('In active use'),
  exempt: msg('Managed by the platform'),
}

// Deliberately discriminating rather than quiet: a bare `never_used` on an agent
// that legitimately does not collaborate must NOT read as an accusation, but the
// motivating incident (`stale`, or a container presenting somebody else's key)
// must not render green either.
const WARN_STATES = new Set(['missing', 'env_absent', 'env_mismatch', 'stale'])

const healthLabel = computed(() => HEALTH_LABELS[status.value.health] ? uiText(HEALTH_LABELS[status.value.health]) : status.value.health)

const isWarning = computed(() => {
  if (WARN_STATES.has(status.value.health)) return true
  // `never_used` escalates only when the container check corroborates it.
  const v = verify.value && verify.value.verdict
  return status.value.health === 'never_used' && v && v !== 'ok' && v !== 'unavailable'
})

const toneClass = computed(() => isWarning.value
  ? 'bg-amber-50 dark:bg-amber-900/30 border-amber-300 dark:border-amber-700 text-amber-900 dark:text-amber-200'
  : 'bg-gray-50 dark:bg-gray-900/40 border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300')

const dotClass = computed(() => {
  if (isWarning.value) return 'bg-amber-500'
  return status.value.health === 'active' ? 'bg-status-success-500' : 'bg-gray-400 dark:bg-gray-600'
})

const VERIFY_LABELS = {
  ok: msg('The container uses this agent’s own key'),
  foreign_user_key: msg('The container authenticates as a person, not as this agent'),
  // #2323 — a bounded read-only ops key belongs to a monitoring integration;
  // it is not a person's key and must not be described as one.
  foreign_ops_key: msg('The container authenticates with a read-only ops key, not as this agent'),
  foreign_agent_key: msg('The container uses another agent’s key'),
  unknown_key: msg('The container’s key is not known to Trinity'),
  not_configured: msg('The container has no Trinity MCP entry'),
  shadow_entry: msg('A second Trinity entry exists under a different name'),
}

const verifyLabel = computed(() => {
  const v = verify.value && verify.value.verdict
  return VERIFY_LABELS[v] ? uiText(VERIFY_LABELS[v]) : v
})

const verifyToneClass = computed(() => {
  const v = verify.value && verify.value.verdict
  return v === 'ok'
    ? 'bg-gray-50 dark:bg-gray-900/40 border-gray-200 dark:border-gray-700 text-gray-700 dark:text-gray-300'
    : 'bg-amber-50 dark:bg-amber-900/30 border-amber-300 dark:border-amber-700 text-amber-900 dark:text-amber-200'
})

function fmt(value) {
  if (!value) return '—'
  try {
    return new Date(value).toLocaleString()
  } catch {
    return String(value)
  }
}

async function load() {
  loading.value = true
  try {
    const { data } = await api.get(`/api/agents/${props.agentName}/mcp-key`)
    status.value = data || status.value
  } catch (e) {
    notifyUser(uiText('Failed to load the agent access key status.'), 'error')
  } finally {
    loading.value = false
  }
}

async function runVerify() {
  verifying.value = true
  try {
    const { data } = await api.post(`/api/agents/${props.agentName}/mcp-key/verify`)
    verify.value = data
  } catch (e) {
    // A stopped agent already degrades to `unavailable` server-side, so a real
    // error here is worth surfacing — but never as a blocking failure.
    verify.value = { verdict: 'unavailable', get "message"() { return uiText("Could not read the container configuration.") } }
  } finally {
    verifying.value = false
  }
}

async function regenerate() {
  const warning = status.value.exists
    ? uiText('Regenerate this agent’s Trinity access key?\n\nThe current key stops working immediately. If the agent is running it will be replaced with a new container to pick the key up, which interrupts any work in flight. If that replacement fails the agent is left stopped and you will need to start it again.')
    : uiText('Issue a Trinity access key for this agent?')
  if (!confirm(warning)) return

  busy.value = true
  try {
    const { data } = await api.post(`/api/agents/${props.agentName}/mcp-key/regenerate`)
    notifyUser(data?.message || uiText('A new access key was issued.'), 'success')
    verify.value = null
    await load()
    await runVerify()
  } catch (e) {
    notifyUser(e?.response?.data?.detail || uiText('Failed to regenerate the access key.'), 'error')
    await load()
  } finally {
    busy.value = false
  }
}

onMounted(async () => {
  await load()
  // One probe per mount. Degrades to `unavailable` when the agent is stopped —
  // the docker exec is why this is a separate route and not part of the GET.
  runVerify()
})

import { t as uiText, msg } from '@/i18n'
</script>
