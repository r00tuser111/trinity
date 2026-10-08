<script setup>
/**
 * Enterprise landing page (#847 Phase 0.5).
 *
 * Cards layout for the planned enterprise features. Each card shows
 * its status (Available / Coming soon) and links to its sub-route
 * when the feature is entitled. Hidden entirely from OSS-only builds
 * by the route guard's `requiresEntitlement: 'enterprise'` umbrella
 * check (true iff any enterprise feature is registered).
 *
 * Adding a new enterprise feature: add a card here, add the route,
 * add the private backend module's `register_module(id)` call. The
 * card's `isEntitled` check decides whether the link is live or
 * shows "Coming soon".
 */
import { computed, onMounted } from 'vue'
import { useEnterpriseStore } from '../../stores/enterprise'
import NavBar from '@/components/NavBar.vue'

const store = useEnterpriseStore()

onMounted(() => {
  store.loadFeatureFlags()
})

// Feature catalogue. `entitlement` matches the feature_id the private
// backend registers via `entitlement_service.register_module(...)`.
// `available` cards link to their sub-route; non-available cards
// display "Coming soon" with the planned scope.
const features = [
  {
    id: 'user_management',
    get "title"() { return uiText("User Management") },
    icon: '👤',
    get "description"() { return uiText("Invite users, deactivate accounts, and review per-user activity — in Settings → User Management.") },
    route: '/settings',
    entitlement: 'user_management',
    soon: false,
  },
  {
    id: 'sso',
    get "title"() { return uiText("Single Sign-On") },
    icon: '🔐',
    get "description"() { return uiText("SAML 2.0 + OIDC. Okta, Azure AD, Google Workspace.") },
    route: '/enterprise/sso',
    entitlement: 'sso',
    soon: true,
  },
  {
    id: 'scim',
    get "title"() { return uiText("SCIM Provisioning") },
    icon: '👥',
    get "description"() { return uiText("Automated user lifecycle from your corporate directory.") },
    route: '/enterprise/scim',
    entitlement: 'scim',
    soon: true,
  },
  {
    id: 'siem',
    get "title"() { return uiText("SIEM Log Export") },
    icon: '📡',
    get "description"() { return uiText("Real-time audit log push to Splunk, Datadog, or Elastic.") },
    route: '/enterprise/siem',
    entitlement: 'siem',
    soon: true,
  },
  {
    id: 'license',
    get "title"() { return uiText("License Management") },
    icon: '📜',
    get "description"() { return uiText("View entitlements, seat usage, expiry. Renew flow.") },
    route: '/enterprise/license',
    entitlement: 'license',
    soon: true,
  },
  {
    id: 'audit',
    get "title"() { return uiText("Audit Log") },
    icon: '🔍',
    get "description"() { return uiText("Searchable platform audit trail with hash-chain verify.") },
    route: '/enterprise/audit',
    entitlement: 'audit',
    soon: false,
  },
]

const cards = computed(() =>
  features.map((f) => ({
    ...f,
    entitled: store.isEntitled(f.entitlement),
    available: !f.soon && store.isEntitled(f.entitlement),
  }))
)

const totalEntitled = computed(
  () => cards.value.filter((c) => c.entitled).length
)

import { t as uiText } from '@/i18n'
</script>

<template>
  <!-- Trinity has no global chrome: App.vue renders only <router-view>, so each
       authenticated view mounts NavBar itself (Dashboard/Settings/Operations/
       Templates do). Without it this page had no way back to the platform but
       the browser's back button (#1636). -->
  <div class="min-h-screen bg-gray-100 dark:bg-gray-900">
    <NavBar />

    <div class="enterprise-landing p-6 max-w-6xl mx-auto">
      <header class="mb-8">
        <div class="flex items-center gap-3 mb-2">
          <h1 class="text-3xl font-semibold text-gray-900 dark:text-white">{{ uiText("Enterprise") }}</h1>
          <span class="px-2 py-0.5 text-xs font-bold rounded bg-purple-100 text-purple-700 dark:bg-purple-900 dark:text-purple-200">
            PRO
          </span>
        </div>
        <p class="text-sm text-gray-500 dark:text-gray-400">
          {{ uiText("Compliance-gating features for Trinity Enterprise. See") }}
          <a href="https://github.com/abilityai/trinity/issues/847" class="underline" target="_blank">#847</a>
          {{ uiText("for the architecture spike.") }}
        </p>
        <p class="text-xs text-gray-400 mt-2">
          {{ totalEntitled }} {{ uiText("of") }} {{ cards.length }} {{ uiText("features entitled for this instance.") }}
        </p>
      </header>

      <div class="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
        <component
          :is="card.available ? 'router-link' : 'div'"
          v-for="card in cards"
          :key="card.id"
          :to="card.available ? card.route : undefined"
          class="block rounded-lg border bg-white dark:bg-gray-800 p-5 transition-all"
          :class="card.available
            ? 'border-gray-200 dark:border-gray-700 hover:border-blue-400 hover:shadow-md cursor-pointer'
            : 'border-gray-200 dark:border-gray-700 opacity-70 cursor-not-allowed'"
        >
          <div class="flex items-start justify-between mb-3">
            <span class="text-3xl">{{ card.icon }}</span>
            <span
              class="px-2 py-0.5 text-[10px] font-bold rounded uppercase tracking-wider"
              :class="card.available
                ? 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-200'
                : 'bg-gray-100 text-gray-500 dark:bg-gray-700 dark:text-gray-400'"
            >
              {{ card.available ? uiText("Available") : card.entitled ? uiText("Coming soon") : uiText("Not licensed") }}
            </span>
          </div>
          <h3 class="text-lg font-medium text-gray-900 dark:text-white mb-1">
            {{ card.title }}
          </h3>
          <p class="text-sm text-gray-600 dark:text-gray-400">{{ card.description }}</p>
        </component>
      </div>

      <footer class="mt-10 p-4 rounded bg-gray-50 dark:bg-gray-800 border border-gray-200 dark:border-gray-700 text-sm text-gray-600 dark:text-gray-400">
        <strong class="block text-gray-900 dark:text-white mb-1">{{ uiText("About Trinity Enterprise") }}</strong>
        {{ uiText("Backend modules ship from the private repo") }}
        <code class="text-xs bg-gray-100 dark:bg-gray-700 px-1 rounded">Abilityai/trinity-enterprise</code>{{ uiText(". Frontend is part of the OSS bundle, gated server-side. See") }}
        <code class="text-xs">docs/planning/ENTERPRISE_ARCHITECTURE.md</code> {{ uiText("for the decision record.") }}
      </footer>
    </div>
  </div>
</template>
