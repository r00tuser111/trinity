<!--
  Step `email` (ent#581) — absorbs FinishSetupCard section 1 (#2381).

  FALLBACK ONLY. A marketplace operator binds their email while claiming the
  instance at /setup (ent#580), so the registry predicate is false and this
  step never appears — the "no duplicate asks" AC is that predicate, not a
  promise in this file. It survives for the ADMIN_PASSWORD-provisioned install,
  where nobody was ever asked. The field is here rather than a link to
  Settings, because leaving the Dashboard would leave the sequence.
-->
<template>
  <div data-testid="first-run-step-email">
    <FirstRunStepHeader
      :kicker="uiText(&quot;Sign-in&quot;)"
      :title="ctx.hasEmail ? uiText(&quot;Sign-in email is set&quot;) : uiText(&quot;Add a sign-in email&quot;)"
      :lead="lead"
      :badge="ctx.hasEmail ? 'Done' : 'Optional'"
      schematic="email"
    />

    <form v-if="!ctx.hasEmail" class="mt-5 max-w-md space-y-2" novalidate @submit.prevent="save">
      <BaseInput
        v-model="email"
        type="email"
        :label="uiText(&quot;Email&quot;)"
        placeholder="you@company.com"
        autocomplete="email"
        :error="fieldError"
        :disabled="saving"
        :help="uiText(&quot;No verification email is sent.&quot;)"
        data-testid="first-run-email-input"
      />
      <BaseButton
        type="submit"
        variant="secondary"
        size="sm"
        :loading="saving"
        loading-label="Saving…"
        :disabled="!email.trim()"
        data-testid="first-run-email-save"
      >
        {{ uiText("Save email") }}
      </BaseButton>
    </form>
    <InlineError v-if="saveError" class="mt-3" :message="saveError" @dismiss="saveError = ''" />
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useAuthStore } from '../../../stores/auth'
import BaseButton from '../../base/BaseButton.vue'
import BaseInput from '../../base/BaseInput.vue'
import InlineError from '../../InlineError.vue'
import FirstRunStepHeader from '../FirstRunStepHeader.vue'

const props = defineProps({ ctx: { type: Object, default: () => ({}) } })
const emit = defineEmits(['complete', 'skip'])

const auth = useAuthStore()

// Mirrors the backend _EMAIL_RE shape check, as /setup does.
const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s.]+$/

const lead = computed(() =>
  props.ctx.hasEmail
    ? uiText('You can sign in with {email} and your password. Change it in Settings → General.', { email: props.ctx.userEmail })
    : uiText('You sign in with the username admin today. Bind an email and you can sign in with that and your password instead.')
)

const email = ref('')
const saving = ref(false)
const fieldError = ref('')
const saveError = ref('')

async function save() {
  const value = email.value.trim()
  if (!EMAIL_RE.test(value)) {
    fieldError.value = uiText("Enter a full email address — for example you@company.com")
    return
  }
  fieldError.value = ''
  saveError.value = ''
  saving.value = true
  try {
    await auth.setOwnEmail(value)
    email.value = ''
    emit('complete')
  } catch (e) {
    const detail = e?.response?.data?.detail
    saveError.value = typeof detail === 'string' ? detail : uiText("Could not save the email. Try again.")
  } finally {
    saving.value = false
  }
}

import { t as uiText } from '@/i18n'
</script>
