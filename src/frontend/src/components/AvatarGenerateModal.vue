<template>
  <div v-if="show" class="fixed inset-0 z-50 flex items-center justify-center bg-black/50" @click.self="$emit('close')">
    <div class="bg-white dark:bg-gray-800 rounded-xl shadow-2xl w-full max-w-md mx-4 p-6">
      <h3 class="text-lg font-bold text-gray-900 dark:text-white mb-4">{{ uiText("Agent Avatar") }}</h3>

      <!-- Reference image + current avatar preview -->
      <div class="flex justify-center items-center gap-4 mb-4">
        <div v-if="hasReference" class="text-center">
          <img
            :src="`/api/agents/${agentName}/avatar/reference?v=${Date.now()}`"
            class="w-16 h-16 rounded-full object-cover border-2 border-gray-300 dark:border-gray-600"
            alt="Reference"
          />
          <span class="text-[10px] text-gray-400 dark:text-gray-500 mt-1 block">{{ uiText("Reference") }}</span>
        </div>
        <div v-if="hasReference" class="text-gray-300 dark:text-gray-600">
          <svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7" />
          </svg>
        </div>
        <div class="text-center">
          <AgentAvatar :name="agentName" :avatar-url="currentAvatarUrl" size="xl" />
          <span v-if="hasReference" class="text-[10px] text-gray-400 dark:text-gray-500 mt-1 block">{{ uiText("Current") }}</span>
        </div>
      </div>

      <!-- Identity prompt input -->
      <label class="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
        {{ uiText("Identity Prompt") }}
      </label>
      <textarea
        v-model="identityPrompt"
        rows="3"
        maxlength="500"
        :placeholder="uiText(&quot;e.g. \&quot;a wise owl with spectacles\&quot; or \&quot;a friendly robot with glowing blue eyes\&quot;&quot;)"
        class="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-white text-sm focus:ring-2 focus:ring-action-primary-500 focus:border-action-primary-500 resize-none"
        :disabled="generating"
      ></textarea>
      <div class="text-xs text-gray-400 dark:text-gray-500 mt-1 text-right">{{ identityPrompt.length }}/500</div>

      <!-- Error message -->
      <p v-if="error" class="text-sm text-status-danger-500 mt-2">{{ error }}</p>

      <!-- Actions -->
      <div class="flex items-center justify-between mt-4">
        <button
          v-if="currentAvatarUrl"
          @click="removeAvatar"
          :disabled="generating || removing"
          class="text-sm text-status-danger-500 hover:text-status-danger-600 disabled:text-gray-400 transition-colors"
        >
          {{ removing ? uiText("Removing...") : uiText("Remove Avatar") }}
        </button>
        <span v-else></span>

        <div class="flex items-center gap-2">
          <button
            @click="$emit('close')"
            :disabled="generating"
            class="px-4 py-2 text-sm text-gray-600 dark:text-gray-300 hover:text-gray-800 dark:hover:text-white transition-colors"
          >
            {{ uiText("Cancel") }}
          </button>
          <button
            @click="generate"
            :disabled="!identityPrompt.trim() || generating"
            class="px-4 py-2 text-sm font-medium text-white bg-action-primary-600 hover:bg-action-primary-700 disabled:bg-action-primary-400 rounded-lg transition-colors flex items-center gap-2"
          >
            <svg v-if="generating" class="animate-spin h-4 w-4" fill="none" viewBox="0 0 24 24">
              <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
              <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
            </svg>
            {{ generating ? uiText("Generating...") : (hasReference ? uiText("New Reference") : uiText("Generate")) }}
          </button>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'
import api from '@/api'
import AgentAvatar from './AgentAvatar.vue'

const props = defineProps({
  show: { type: Boolean, default: false },
  agentName: { type: String, required: true },
  initialPrompt: { type: String, default: '' },
  currentAvatarUrl: { type: String, default: null },
  hasReference: { type: Boolean, default: false }
})

const emit = defineEmits(['close', 'updated'])

const identityPrompt = ref('')
const generating = ref(false)
const removing = ref(false)
const error = ref('')

watch(() => props.show, (val) => {
  if (val) {
    identityPrompt.value = props.initialPrompt || ''
    error.value = ''
  }
})

// #957: Map axios failures to actionable strings. Backend now sends a
// friendly `detail` per kind, but we still need a fallback chain for the
// no-response cases (network, nginx 504 with HTML body) that strip detail.
function describeAvatarError(err, verb = 'generate') {
  if (err?.response?.data?.detail && typeof err.response.data.detail === 'string') {
    return err.response.data.detail
  }
  const status = err?.response?.status
  if (status === 504) return uiText("Avatar {arg1} timed out — please retry.", { arg1: (verb) })
  if (status === 502 || status === 503) {
    return uiText("Image generation service is unavailable right now — please retry in a few minutes.")
  }
  if (!err?.response) {
    return uiText("Network error while trying to {arg1} avatar — check your connection and retry.", { arg1: (verb) })
  }
  return uiText("Failed to {arg1} avatar (HTTP {arg2}).", { arg1: (verb), arg2: (status) })
}

async function generate() {
  if (!identityPrompt.value.trim()) return
  generating.value = true
  error.value = ''

  try {
    await api.post(`/api/agents/${props.agentName}/avatar/generate`, {
      identity_prompt: identityPrompt.value.trim()
    }, { timeout: 180000 })
    emit('updated')
    emit('close')
  } catch (err) {
    error.value = describeAvatarError(err, uiText("generate"))
  } finally {
    generating.value = false
  }
}

async function removeAvatar() {
  removing.value = true
  error.value = ''

  try {
    await api.delete(`/api/agents/${props.agentName}/avatar`)
    emit('updated')
    emit('close')
  } catch (err) {
    error.value = describeAvatarError(err, uiText("remove"))
  } finally {
    removing.value = false
  }
}

import { t as uiText } from '@/i18n'
</script>
