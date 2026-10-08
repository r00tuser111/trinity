<!--
  Model provider (LLM-PROVIDER-001).

  Where Claude-runtime agents and the platform's own AI features send model
  calls: Anthropic (the default) or one custom Anthropic-compatible endpoint
  such as DeepSeek. A subscription bound to an agent still wins over this.

  Saving changes the configuration only. Running agents keep the provider they
  were started with until they restart — the pending banner says how many, and
  offers the restart rather than doing it behind the operator's back.
-->
<template>
  <BaseCard flush data-testid="model-provider-panel">
    <div class="px-6 py-4 border-b border-gray-200 dark:border-gray-750 flex items-start justify-between gap-4">
      <div>
        <h2 class="text-lg font-medium text-gray-900 dark:text-gray-100">{{ uiText('Model provider') }}</h2>
        <p class="mt-1 text-sm text-gray-500 dark:text-gray-400">
          {{ uiText('Where Claude Code agents and platform AI features send model calls. A custom provider must speak the Anthropic Messages API.') }}
        </p>
      </div>
      <BaseBadge v-if="store.status" :variant="store.status.active ? 'info' : 'neutral'" dot>
        {{ store.status.active ? uiText('Custom provider') : uiText('Anthropic') }}
      </BaseBadge>
    </div>

    <div class="px-6 py-4">
      <SkeletonLoader v-if="view.state === 'loading'" variant="rows" :count="4" height="2.25rem" />
      <LoadFailed
        v-else-if="view.state === 'failed'"
        dense
        :title="uiText('Couldn\'t load the model provider')"
        :detail="apiErrorMessage(store.loadError)"
        :retrying="retrying"
        @retry="retry"
      />

      <form v-else class="space-y-4" @submit.prevent="save">
        <BaseSelect
          v-model="form.mode"
          :label="uiText('Provider')"
          :help="form.mode === 'custom'
            ? uiText('Agents without a subscription use the provider below.')
            : uiText('Agents use the Anthropic API key or a Claude subscription.')"
          :disabled="busy"
        >
          <option value="anthropic">{{ uiText('Anthropic (default)') }}</option>
          <option value="custom">{{ uiText('Custom provider (Anthropic-compatible)') }}</option>
        </BaseSelect>

        <template v-if="form.mode === 'custom'">
          <div class="flex flex-wrap items-center gap-2">
            <span class="text-sm text-gray-600 dark:text-gray-300">{{ uiText('Start from a preset:') }}</span>
            <BaseButton
              v-for="preset in PROVIDER_PRESETS"
              :key="preset.id"
              variant="secondary"
              size="sm"
              :disabled="busy"
              @click="usePreset(preset)"
            >{{ preset.label }}</BaseButton>
          </div>

          <BaseInput
            v-model="form.base_url"
            :label="uiText('Base URL')"
            :help="uiText('The Anthropic-compatible endpoint, without /v1/messages. Plain http is accepted only for private-network hosts.')"
            :error="errors.base_url"
            :disabled="busy"
            placeholder="https://api.deepseek.com/anthropic"
            autocomplete="off"
            spellcheck="false"
          />

          <BaseInput
            v-model="form.api_key"
            type="password"
            :label="uiText('API key')"
            :help="store.status?.api_key_configured
              ? uiText('Stored key {arg1} — leave blank to keep it.', { arg1: store.status.api_key_masked })
              : uiText('Sent to the provider only. Stored encrypted and never shown again.')"
            :error="errors.api_key"
            :disabled="busy"
            autocomplete="new-password"
          />

          <div>
            <div class="flex items-center justify-between">
              <span class="block text-sm font-medium text-gray-700 dark:text-gray-300">{{ uiText('Models') }}</span>
              <span class="text-xs tabular-nums text-gray-500 dark:text-gray-400">
                {{ uiText('{arg1} of {arg2}', { arg1: form.models.length, arg2: MAX_MODELS }) }}
              </span>
            </div>
            <div class="mt-1 max-h-72 overflow-y-auto rounded-md border border-gray-200 dark:border-gray-750">
              <div class="sticky top-0 grid grid-cols-[minmax(0,2fr)_minmax(0,2fr)_7rem_2rem] gap-2 px-3 py-1.5 bg-gray-100 dark:bg-gray-750 text-[11px] font-mono uppercase tracking-wide text-gray-500 dark:text-gray-400">
                <span>{{ uiText('Model id') }}</span>
                <span>{{ uiText('Display name') }}</span>
                <span class="text-right">{{ uiText('Context') }}</span>
                <span class="sr-only">{{ uiText('Remove') }}</span>
              </div>
              <div
                v-for="(row, index) in form.models"
                :key="index"
                class="grid grid-cols-[minmax(0,2fr)_minmax(0,2fr)_7rem_2rem] gap-2 items-center px-3 py-1.5 border-t border-gray-200 dark:border-gray-750"
              >
                <BaseInput v-model="row.id" :aria-label="uiText('Model id')" placeholder="deepseek-chat" :disabled="busy" spellcheck="false" />
                <BaseInput v-model="row.label" :aria-label="uiText('Display name')" :placeholder="row.id || uiText('Optional')" :disabled="busy" />
                <BaseInput v-model="row.context_window" :aria-label="uiText('Context window (tokens)')" :placeholder="String(DEFAULT_CONTEXT_WINDOW)" inputmode="numeric" class="tabular-nums" :disabled="busy" />
                <BaseButton
                  variant="ghost"
                  size="sm"
                  :aria-label="uiText('Remove model')"
                  :disabled="busy || form.models.length === 1"
                  @click="removeRow(index)"
                >×</BaseButton>
              </div>
            </div>
            <p v-if="errors.models" class="mt-1 text-sm text-status-danger-600 dark:text-status-danger-300" role="alert">{{ errors.models }}</p>
            <p v-else class="mt-1 text-xs text-gray-500 dark:text-gray-400">
              {{ uiText('Ids exactly as the provider names them. The context window defaults to 128000 tokens.') }}
            </p>
            <BaseButton
              class="mt-2"
              variant="secondary"
              size="sm"
              :disabled="busy || form.models.length >= MAX_MODELS"
              @click="addRow"
            >{{ uiText('Add model') }}</BaseButton>
          </div>

          <div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <BaseSelect
              v-model="form.default_model"
              :label="uiText('Default model')"
              :help="uiText('Used for chats and schedules that do not pick a model.')"
              :error="errors.default_model"
              :disabled="busy"
            >
              <option value="">{{ uiText('First listed model') }}</option>
              <option v-for="id in modelIds" :key="id" :value="id">{{ id }}</option>
            </BaseSelect>
            <BaseSelect
              v-model="form.fast_model"
              :label="uiText('Fast model')"
              :help="uiText('Used for background work: titles, summaries, compatibility checks.')"
              :error="errors.fast_model"
              :disabled="busy"
            >
              <option value="">{{ uiText('Same as default') }}</option>
              <option v-for="id in modelIds" :key="id" :value="id">{{ id }}</option>
            </BaseSelect>
          </div>

          <p class="text-xs text-gray-500 dark:text-gray-400">
            {{ uiText('Cost figures are computed from Claude prices, so they are approximate for other providers. Image input, extended context and some tools depend on what the provider supports.') }}
          </p>
        </template>

        <div class="flex flex-wrap items-center gap-3 pt-2">
          <BaseButton
            type="submit"
            :loading="saving"
            :loading-label="uiText('Saving…')"
            :disabled="busy || !dirty"
          >{{ uiText('Save') }}</BaseButton>
          <BaseButton
            v-if="form.mode === 'custom'"
            variant="secondary"
            :loading="testing"
            :loading-label="uiText('Testing…')"
            :disabled="busy"
            @click="testConnection"
          >{{ uiText('Test connection') }}</BaseButton>
          <BaseButton
            v-if="hasStoredConfig"
            variant="ghost"
            :disabled="busy"
            @click="confirmForget = true"
          >{{ uiText('Forget provider') }}</BaseButton>
          <span v-if="savedNote" class="text-sm text-status-success-600 dark:text-status-success-400" role="status">{{ savedNote }}</span>
          <span v-if="testResult?.valid" class="text-sm text-status-success-600 dark:text-status-success-400" role="status">
            {{ uiText('Connected — {arg1} answered.', { arg1: testResult.model }) }}
          </span>
        </div>

        <InlineError :message="testError" @dismiss="testError = ''" />
        <InlineError :message="saveError" @dismiss="saveError = ''" />

        <div
          v-if="store.pending?.count"
          class="rounded-md border border-status-warning-200 dark:border-status-warning-500/30 bg-status-warning-50 dark:bg-status-warning-500/10 p-3 flex flex-wrap items-center justify-between gap-3"
          role="status"
          data-testid="model-provider-pending"
        >
          <p class="text-sm text-status-warning-800 dark:text-status-warning-300">
            {{ uiText('{arg1} running agent(s) still use the previous provider and switch on their next restart. Restarting now ends their open chat sessions; agents mid-task are skipped.', { arg1: store.pending.count }) }}
          </p>
          <BaseButton
            variant="secondary"
            size="sm"
            :loading="applying"
            :loading-label="uiText('Restarting…')"
            :disabled="busy"
            @click="applyNow"
          >{{ uiText('Restart now') }}</BaseButton>
        </div>
        <InlineError :message="applyError" @dismiss="applyError = ''" />
      </form>
    </div>

    <ConfirmDialog
      v-model:visible="confirmForget"
      :title="uiText('Forget the model provider?')"
      :message="uiText('The base URL, models and stored key are deleted and agents go back to Anthropic on their next restart.')"
      :confirm-text="uiText('Forget provider')"
      @confirm="forget"
    />
  </BaseCard>
</template>

<script setup>
import { t as uiText } from '@/i18n'
import { ref, computed, onMounted } from 'vue'
import BaseCard from '../base/BaseCard.vue'
import BaseBadge from '../base/BaseBadge.vue'
import BaseButton from '../base/BaseButton.vue'
import BaseInput from '../base/BaseInput.vue'
import BaseSelect from '../base/BaseSelect.vue'
import SkeletonLoader from '../SkeletonLoader.vue'
import LoadFailed from '../LoadFailed.vue'
import InlineError from '../InlineError.vue'
import ConfirmDialog from '../ConfirmDialog.vue'
import { useModelProviderStore } from '../../stores/modelProvider'
import { viewState } from '../../utils/loadingState'
import { apiErrorMessage } from '../../utils/apiError'
import {
  PROVIDER_PRESETS,
  MAX_MODELS,
  DEFAULT_CONTEXT_WINDOW,
  emptyModelRow,
  formFromStatus,
  applyPreset,
  listedModelIds,
  validateProviderForm,
  buildProviderPayload,
  buildTestPayload,
} from '../../utils/modelProvider'

const store = useModelProviderStore()

const form = ref(formFromStatus(null))
const baseline = ref(JSON.stringify(form.value))
const errors = ref({})
const saving = ref(false)
const testing = ref(false)
const applying = ref(false)
const retrying = ref(false)
const saveError = ref('')
const testError = ref('')
const applyError = ref('')
const testResult = ref(null)
const savedNote = ref('')
const confirmForget = ref(false)

const view = computed(() => viewState({ hasLoaded: store.hasLoaded, error: store.loadError }))
const busy = computed(() => saving.value || testing.value || applying.value)
const dirty = computed(() => JSON.stringify(form.value) !== baseline.value)
const modelIds = computed(() => listedModelIds(form.value))
const hasStoredConfig = computed(() => !!(store.status?.base_url || store.status?.api_key_configured))

function adopt(status) {
  form.value = formFromStatus(status)
  baseline.value = JSON.stringify(form.value)
  errors.value = {}
}

async function load() {
  const status = await store.fetchStatus()
  if (store.hasLoaded) adopt(status)
  store.fetchPending()
}

async function retry() {
  retrying.value = true
  try { await load() } finally { retrying.value = false }
}

function usePreset(preset) {
  form.value = applyPreset(form.value, preset)
  errors.value = {}
}

function addRow() {
  form.value.models.push(emptyModelRow())
}

function removeRow(index) {
  form.value.models.splice(index, 1)
}

async function save() {
  saveError.value = ''
  savedNote.value = ''
  errors.value = validateProviderForm(form.value, { apiKeyConfigured: !!store.status?.api_key_configured })
  if (Object.keys(errors.value).length) return
  saving.value = true
  try {
    const status = await store.save(buildProviderPayload(form.value))
    adopt(status)
    savedNote.value = uiText('Saved — new agents use it now; running agents on their next restart.')
  } catch (e) {
    saveError.value = apiErrorMessage(e, uiText('Could not save the model provider.'))
  } finally {
    saving.value = false
  }
}

async function testConnection() {
  testError.value = ''
  testResult.value = null
  const fieldErrors = validateProviderForm(form.value, { apiKeyConfigured: !!store.status?.api_key_configured })
  const relevant = ['base_url', 'api_key', 'models'].filter((k) => fieldErrors[k])
  if (relevant.length) {
    errors.value = fieldErrors
    return
  }
  testing.value = true
  try {
    const result = await store.test(buildTestPayload(form.value))
    if (result?.valid) testResult.value = result
    else testError.value = result?.error || uiText('The provider rejected the test call.')
  } catch (e) {
    testError.value = apiErrorMessage(e, uiText('Could not reach the server to run the test.'))
  } finally {
    testing.value = false
  }
}

async function applyNow() {
  applyError.value = ''
  applying.value = true
  try {
    const result = await store.apply()
    savedNote.value = uiText('Restarting {arg1} agent(s) in the background.', { arg1: result?.count ?? 0 })
  } catch (e) {
    applyError.value = apiErrorMessage(e, uiText('Could not restart the agents. Try again, or restart them from the dashboard.'))
  } finally {
    applying.value = false
  }
}

async function forget() {
  saveError.value = ''
  savedNote.value = ''
  saving.value = true
  try {
    const status = await store.remove()
    adopt(status)
    savedNote.value = uiText('Provider forgotten — agents use Anthropic from their next restart.')
  } catch (e) {
    saveError.value = apiErrorMessage(e, uiText('Could not forget the model provider.'))
  } finally {
    saving.value = false
  }
}

onMounted(load)
</script>
