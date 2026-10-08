<template>
  <BaseSelect
    variant="ghost"
    class="shrink-0"
    :model-value="locale"
    :aria-label="t('Language')"
    :title="t('Language')"
    data-testid="language-select"
    @update:model-value="setLocale"
  >
    <option v-for="language in LANGUAGES" :key="language.value" :value="language.value" :lang="language.value">
      {{ language.label }}
    </option>
  </BaseSelect>
</template>

<script setup>
import BaseSelect from './base/BaseSelect.vue'
import { LANGUAGES, locale, setLocale, t } from '@/i18n'
</script>
