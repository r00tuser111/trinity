<template>
  <!--
    Fleet-health panel, embedded as the "Health" tab of Operations.vue (#1109).
    Extracted from the former views/Monitoring.vue: no <NavBar/> and no
    min-h-screen/<main> page wrapper — the Operations container owns those.
    Admin-gated at the tab level by the parent; the per-action buttons here
    stay gated on `isAdmin` (read from authStore.role, not a duplicate
    /api/users/me fetch).
  -->
  <div class="max-w-7xl mx-auto">
    <!-- Toolbar: service status + auto-refresh + admin fleet check -->
    <div class="flex flex-wrap items-center justify-end gap-3 mb-6">
      <span
        class="inline-flex items-center px-3 py-1 rounded-full text-sm font-medium"
        :class="monitoringStore.enabled ? 'bg-status-success-100 dark:bg-status-success-900/30 text-status-success-700 dark:text-status-success-300' : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400'"
      >
        <span class="w-2 h-2 rounded-full mr-2" :class="monitoringStore.enabled ? 'bg-status-success-500' : 'bg-gray-400'"></span>
        {{ monitoringStore.enabled ? t('Monitoring Active') : t('Monitoring Disabled') }}
      </span>

      <!--
        Admin-only enable/disable of the SERVER-SIDE monitoring loop (#1409).
        Distinct from the client-side auto-refresh toggle below (clock icon):
        this persists via POST /api/monitoring/{enable,disable} and survives a
        backend restart (#1121). Non-admins never see it (Health tab is
        admin-gated; keep parity).
      -->
      <button
        v-if="isAdmin"
        @click="toggleMonitoring"
        :disabled="togglingMonitoring"
        class="px-3 py-1.5 text-sm rounded-lg disabled:opacity-50 transition-colors"
        :class="monitoringStore.enabled
          ? 'bg-gray-100 dark:bg-gray-700 text-gray-700 dark:text-gray-200 hover:bg-gray-200 dark:hover:bg-gray-600'
          : 'bg-status-success-600 hover:bg-status-success-700 text-white'"
        :title="monitoringStore.enabled
          ? t('Stop the fleet-health monitoring loop (persists across restarts)')
          : t('Start the fleet-health monitoring loop (persists across restarts)')"
      >
        {{ togglingMonitoring ? t('Working…') : (monitoringStore.enabled ? t('Disable monitoring') : t('Enable monitoring')) }}
      </button>

      <span v-if="autoRefreshEnabled" class="text-xs text-gray-500 dark:text-gray-400">
        {{ t('Auto-refresh:') }} {{ refreshCountdown }}s
      </span>

      <button
        @click="toggleAutoRefresh"
        :class="autoRefreshEnabled ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-700 dark:text-blue-300' : 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400'"
        class="px-3 py-1.5 text-sm rounded-lg hover:bg-opacity-80 transition-colors"
        :title="autoRefreshEnabled ? t('Disable auto-refresh') : t('Enable auto-refresh')"
      >
        <ClockIcon class="w-4 h-4" />
      </button>

      <button
        @click="refreshAll"
        :disabled="monitoringStore.loading"
        class="p-2 text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200 hover:bg-gray-200 dark:hover:bg-gray-700 rounded-lg"
        :title="t('Refresh')"
      >
        <ArrowPathIcon class="w-5 h-5" :class="{ 'animate-spin': monitoringStore.loading }" />
      </button>

      <button
        v-if="isAdmin"
        @click="triggerFleetCheck"
        :disabled="triggeringCheck"
        class="px-3 py-1.5 text-sm bg-blue-600 hover:bg-blue-700 text-white rounded-lg disabled:opacity-50"
      >
        {{ triggeringCheck ? t('Checking...') : t('Check All') }}
      </button>
    </div>

    <!-- Monitoring enable/disable error (#1409) -->
    <div
      v-if="monitoringError"
      class="mb-4 px-4 py-2 rounded-lg bg-status-danger-50 dark:bg-status-danger-900/20 text-status-danger-700 dark:text-status-danger-300 text-sm flex items-center justify-between"
    >
      <span>{{ monitoringError }}</span>
      <button @click="monitoringError = ''" class="ml-3 text-status-danger-500 hover:text-status-danger-700" :title="t('Dismiss')">
        <XCircleIcon class="w-4 h-4" />
      </button>
    </div>

    <!-- Summary Cards -->
    <div class="grid grid-cols-2 md:grid-cols-5 gap-4 mb-6">
      <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-4">
        <div class="text-3xl font-bold text-gray-900 dark:text-white">{{ monitoringStore.summary.total_agents }}</div>
        <div class="text-xs text-gray-500 dark:text-gray-400">{{ t('Total Agents') }}</div>
      </div>
      <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-4 border-l-4 border-status-success-500">
        <div class="text-3xl font-bold text-status-success-600 dark:text-status-success-400">{{ monitoringStore.summary.healthy }}</div>
        <div class="text-xs text-gray-500 dark:text-gray-400">{{ t('Healthy') }}</div>
      </div>
      <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-4 border-l-4 border-status-warning-500">
        <div class="text-3xl font-bold text-status-warning-600 dark:text-status-warning-400">{{ monitoringStore.summary.degraded }}</div>
        <div class="text-xs text-gray-500 dark:text-gray-400">{{ t('Degraded') }}</div>
      </div>
      <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-4 border-l-4 border-status-danger-500">
        <div class="text-3xl font-bold text-status-danger-600 dark:text-status-danger-400">{{ monitoringStore.summary.unhealthy }}</div>
        <div class="text-xs text-gray-500 dark:text-gray-400">{{ t('Unhealthy') }}</div>
      </div>
      <div class="bg-white dark:bg-gray-800 rounded-lg shadow p-4 border-l-4 border-status-danger-700">
        <div class="text-3xl font-bold text-status-danger-700 dark:text-status-danger-500">{{ monitoringStore.summary.critical }}</div>
        <div class="text-xs text-gray-500 dark:text-gray-400">{{ t('Critical') }}</div>
      </div>
    </div>

    <!-- Active Alerts -->
    <div v-if="monitoringStore.hasActiveAlerts" class="bg-status-danger-50 dark:bg-status-danger-900/20 rounded-lg shadow mb-6 p-4">
      <div class="flex items-center justify-between mb-3">
        <h2 class="text-lg font-medium text-status-danger-800 dark:text-status-danger-200 flex items-center">
          <BellAlertIcon class="w-5 h-5 mr-2" />
          {{ t('Active Alerts (') }}{{ monitoringStore.alerts.length }})
        </h2>
      </div>
      <div class="space-y-2">
        <div
          v-for="alert in monitoringStore.alerts.slice(0, 5)"
          :key="alert.id"
          class="bg-white dark:bg-gray-800 rounded p-3 flex items-center justify-between"
        >
          <div class="flex items-center gap-3">
            <ExclamationTriangleIcon
              class="w-5 h-5"
              :class="alert.priority === 'urgent' ? 'text-status-danger-600' : 'text-status-warning-600'"
            />
            <div>
              <span class="font-medium text-gray-900 dark:text-white" :title="agentNameTooltip(agentsStore.agentRefForSlug(alert.agent_name))">{{ alert.agent_name }}</span>
              <span class="text-gray-500 dark:text-gray-400 ml-2">{{ alert.title }}</span>
            </div>
          </div>
          <span class="text-xs text-gray-400">{{ formatRelativeTime(alert.created_at) }}</span>
        </div>
      </div>
    </div>

    <!-- Agent Health Grid -->
    <div class="bg-white dark:bg-gray-800 rounded-lg shadow">
      <div class="px-6 py-4 border-b border-gray-200 dark:border-gray-700 flex items-center justify-between">
        <h2 class="text-lg font-medium text-gray-900 dark:text-white">{{ t('Agent Health Status') }}</h2>

        <!-- Status filter -->
        <div class="flex items-center gap-2">
          <select
            v-model="statusFilter"
            class="text-sm border border-gray-300 dark:border-gray-600 rounded-lg px-3 py-2 bg-white dark:bg-gray-700 text-gray-700 dark:text-gray-200"
          >
            <option value="">{{ t('All Statuses') }}</option>
            <option value="healthy">{{ t('Healthy') }}</option>
            <option value="degraded">{{ t('Degraded') }}</option>
            <option value="unhealthy">{{ t('Unhealthy') }}</option>
            <option value="critical">{{ t('Critical') }}</option>
            <option value="unknown">{{ t('Unknown') }}</option>
          </select>
        </div>
      </div>

      <div class="divide-y divide-gray-200 dark:divide-gray-700">
        <div
          v-for="agent in filteredAgents"
          :key="agent.name"
          class="px-6 py-4 hover:bg-gray-50 dark:hover:bg-gray-700/50 cursor-pointer transition-colors"
          @click="viewAgentDetail(agent.name)"
        >
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-4">
              <!-- Status indicator -->
              <div
                class="w-10 h-10 rounded-full flex items-center justify-center"
                :class="getStatusBgClass(agent.status)"
              >
                <component
                  :is="getStatusIcon(agent.status)"
                  class="w-5 h-5"
                  :class="getStatusTextClass(agent.status)"
                />
              </div>

              <div>
                <div class="flex items-center gap-2">
                  <span class="font-medium text-gray-900 dark:text-white" :title="agentNameTooltip(agentsStore.agentRefForSlug(agent.name))">{{ agent.name }}</span>
                  <span
                    class="px-2 py-0.5 text-xs font-medium rounded capitalize"
                    :class="getStatusBadgeClass(agent.status)"
                  >
                    {{ agent.status }}
                  </span>
                </div>
                <div class="text-sm text-gray-500 dark:text-gray-400 mt-1">
                  <span v-if="agent.docker_status">{{ t('Container:') }} {{ agent.docker_status }}</span>
                  <span v-if="agent.network_reachable !== undefined" class="ml-3">
                    {{ t('Network:') }} {{ agent.network_reachable ? t('Reachable') : t('Unreachable') }}
                  </span>
                </div>
              </div>
            </div>

            <div class="flex items-center gap-4">
              <!-- Issues list -->
              <div v-if="agent.issues && agent.issues.length > 0" class="text-right">
                <div class="text-sm text-status-danger-600 dark:text-status-danger-400">
                  {{ agent.issues.length }} {{ t('issue') }}{{ agent.issues.length > 1 ? 's' : '' }}
                </div>
                <div class="text-xs text-gray-500 dark:text-gray-400 max-w-xs truncate">
                  {{ agent.issues[0] }}
                </div>
              </div>

              <!-- Last check time -->
              <div class="text-right">
                <div class="text-xs text-gray-400">{{ t('Last check') }}</div>
                <div class="text-sm text-gray-600 dark:text-gray-300">
                  {{ agent.last_check_at ? formatRelativeTime(agent.last_check_at) : t('Never') }}
                </div>
              </div>

              <!-- Action button -->
              <button
                v-if="isAdmin"
                @click.stop="triggerAgentCheck(agent.name)"
                :disabled="checkingAgent === agent.name"
                class="p-2 text-gray-400 hover:text-blue-600 dark:hover:text-blue-400 hover:bg-blue-50 dark:hover:bg-blue-900/20 rounded-lg"
                :title="t('Trigger health check')"
              >
                <ArrowPathIcon class="w-4 h-4" :class="{ 'animate-spin': checkingAgent === agent.name }" />
              </button>

              <ChevronRightIcon class="w-5 h-5 text-gray-400" />
            </div>
          </div>
        </div>

        <div v-if="filteredAgents.length === 0" class="px-6 py-12 text-center text-gray-500 dark:text-gray-400">
          <HeartIcon class="w-12 h-12 mx-auto mb-4 text-gray-300 dark:text-gray-600" />
          <p class="text-lg font-medium">{{ t('No agents found') }}</p>
          <p class="text-sm mt-1">
            {{ statusFilter ? t('No agents match the selected filter') : t('No agents are being monitored') }}
          </p>
        </div>
      </div>
    </div>

    <!-- Last updated -->
    <div v-if="monitoringStore.lastCheck" class="mt-4 text-center text-xs text-gray-400">
      {{ t('Last updated:') }} {{ formatTime(monitoringStore.lastCheck) }}
    </div>
  </div>
</template>

<script setup>
import { t as uiText } from '@/i18n'

import { t } from '@/i18n'
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { useMonitoringStore } from '../stores/monitoring'
import { useAuthStore } from '../stores/auth'
import { useAgentsStore } from '../stores/agents'
import { agentNameTooltip } from '../utils/agentName'
import {
  ArrowPathIcon,
  BellAlertIcon,
  ExclamationTriangleIcon,
  CheckCircleIcon,
  XCircleIcon,
  QuestionMarkCircleIcon,
  ChevronRightIcon,
  ClockIcon,
  HeartIcon,
} from '@heroicons/vue/24/outline'

const router = useRouter()
const monitoringStore = useMonitoringStore()
const authStore = useAuthStore()
const agentsStore = useAgentsStore()

// Admin status drives the per-action buttons (Check All, per-agent check)
// and gates the fleet-wide alerts fetch. Read from the auth store getter
// (#1109) rather than a duplicate /api/users/me round-trip.
const isAdmin = computed(() => authStore.role === 'admin')

// State
const statusFilter = ref('')
const triggeringCheck = ref(false)
const checkingAgent = ref(null)
// #1409: server-side monitoring-loop enable/disable (admin-only)
const togglingMonitoring = ref(false)
const monitoringError = ref('')
const autoRefreshEnabled = ref(true)
const refreshCountdown = ref(30)
let refreshInterval = null
let countdownInterval = null

// Computed
const filteredAgents = computed(() => {
  if (!statusFilter.value) {
    return monitoringStore.agents
  }
  return monitoringStore.agents.filter(a => a.status === statusFilter.value)
})

// Lifecycle — onMounted/onUnmounted fire on tab enter/leave because the
// parent toggles this panel with v-if (not v-show), so the interval is
// torn down cleanly when the Health tab is left.
onMounted(async () => {
  await refreshAll()
  startAutoRefresh()
})

onUnmounted(() => {
  stopAutoRefresh()
})

// Methods
async function refreshAll() {
  await Promise.all([
    monitoringStore.fetchStatus(),
    isAdmin.value ? monitoringStore.fetchAlerts() : Promise.resolve()
  ])
  refreshCountdown.value = 30
}

function startAutoRefresh() {
  if (refreshInterval) return

  refreshInterval = setInterval(() => {
    if (autoRefreshEnabled.value) {
      refreshAll()
    }
  }, 30000)

  countdownInterval = setInterval(() => {
    if (autoRefreshEnabled.value && refreshCountdown.value > 0) {
      refreshCountdown.value--
    }
  }, 1000)
}

function stopAutoRefresh() {
  if (refreshInterval) {
    clearInterval(refreshInterval)
    refreshInterval = null
  }
  if (countdownInterval) {
    clearInterval(countdownInterval)
    countdownInterval = null
  }
}

function toggleAutoRefresh() {
  autoRefreshEnabled.value = !autoRefreshEnabled.value
  if (autoRefreshEnabled.value) {
    refreshCountdown.value = 30
  }
}

async function toggleMonitoring() {
  // Start/stop the persisted server-side monitoring loop (#1409 / #1121).
  monitoringError.value = ''
  const turningOn = !monitoringStore.enabled
  togglingMonitoring.value = true
  try {
    if (turningOn) {
      await monitoringStore.enableMonitoring()
    } else {
      await monitoringStore.disableMonitoring()
    }
    // Reflect the new loop state in the summary/health data.
    await refreshAll()
  } catch (err) {
    monitoringError.value = turningOn
      ? uiText("Failed to enable monitoring. Check your permissions and try again.")
      : uiText("Failed to disable monitoring. Please try again.")
  } finally {
    togglingMonitoring.value = false
  }
}

async function triggerFleetCheck() {
  triggeringCheck.value = true
  try {
    await monitoringStore.triggerFleetCheck()
    // Wait a moment then refresh
    setTimeout(() => refreshAll(), 2000)
  } catch (err) {
    console.error('Failed to trigger fleet check:', err)
  } finally {
    triggeringCheck.value = false
  }
}

async function triggerAgentCheck(agentName) {
  checkingAgent.value = agentName
  try {
    await monitoringStore.triggerCheck(agentName)
  } catch (err) {
    console.error('Failed to trigger agent check:', err)
  } finally {
    checkingAgent.value = null
  }
}

function viewAgentDetail(agentName) {
  router.push(`/agents/${agentName}`)
}

function getStatusIcon(status) {
  switch (status) {
    case 'healthy': return CheckCircleIcon
    case 'degraded': return ExclamationTriangleIcon
    case 'unhealthy': return XCircleIcon
    case 'critical': return XCircleIcon
    default: return QuestionMarkCircleIcon
  }
}

function getStatusBgClass(status) {
  switch (status) {
    case 'healthy': return 'bg-status-success-100 dark:bg-status-success-900/30'
    case 'degraded': return 'bg-status-warning-100 dark:bg-status-warning-900/30'
    case 'unhealthy': return 'bg-status-danger-100 dark:bg-status-danger-900/30'
    case 'critical': return 'bg-status-danger-200 dark:bg-status-danger-900/50'
    default: return 'bg-gray-100 dark:bg-gray-700'
  }
}

function getStatusTextClass(status) {
  switch (status) {
    case 'healthy': return 'text-status-success-600 dark:text-status-success-400'
    case 'degraded': return 'text-status-warning-600 dark:text-status-warning-400'
    case 'unhealthy': return 'text-status-danger-600 dark:text-status-danger-400'
    case 'critical': return 'text-status-danger-700 dark:text-status-danger-500'
    default: return 'text-gray-500 dark:text-gray-400'
  }
}

function getStatusBadgeClass(status) {
  switch (status) {
    case 'healthy': return 'bg-status-success-100 dark:bg-status-success-900/30 text-status-success-700 dark:text-status-success-300'
    case 'degraded': return 'bg-status-warning-100 dark:bg-status-warning-900/30 text-status-warning-700 dark:text-status-warning-300'
    case 'unhealthy': return 'bg-status-danger-100 dark:bg-status-danger-900/30 text-status-danger-700 dark:text-status-danger-300'
    case 'critical': return 'bg-status-danger-200 dark:bg-status-danger-900/50 text-status-danger-800 dark:text-status-danger-200'
    default: return 'bg-gray-100 dark:bg-gray-700 text-gray-600 dark:text-gray-400'
  }
}

function formatRelativeTime(dateStr) {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  const now = new Date()
  const diffMs = now - date
  const diffSecs = Math.floor(diffMs / 1000)
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMs / 3600000)
  const diffDays = Math.floor(diffMs / 86400000)

  if (diffSecs < 60) return uiText("just now")
  if (diffMins < 60) return uiText("{arg1}m ago", { arg1: (diffMins) })
  if (diffHours < 24) return uiText("{arg1}h ago", { arg1: (diffHours) })
  return uiText("{arg1}d ago", { arg1: (diffDays) })
}

function formatTime(dateStr) {
  if (!dateStr) return ''
  const date = new Date(dateStr)
  return date.toLocaleString()
}
</script>
