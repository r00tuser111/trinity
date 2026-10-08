import { t as uiText, msg } from '../../../i18n/index.js'

/**
 * Decidable logic behind the ent#582 credential steps (StepClaude, StepKeys)
 * and the Settings → Integrations key fields that reuse them.
 *
 * Format rules and every line of operator copy live here — `vitest.config.js`
 * runs `environment: 'node'` with no component mount, so a rule left in an SFC
 * is one no test can reach (the ent#392 / #2380 / ent#437 rule). Errors name the
 * problem, the fix and an example (design-system principle 17).
 *
 * Twin: `src/backend/services/platform_keys_service.py` and
 * `routers/subscriptions.py::test_subscription_token` hold the same rules and
 * the same words; the server re-checks because it is the boundary.
 */

export const SETTINGS_PATH = 'Settings → Integrations'

const DOCS_PAGE =
  'https://github.com/abilityai/trinity/blob/main/docs/user-docs/credentials/platform-keys.md'

// ent#581 spec comment 2, verbatim (markdown emphasis dropped — plain text).
export const OAT_IN_API_KEY_TAB = msg(
  'That key was rejected. API keys start with sk-ant-api — this one starts with sk-ant-oat, which is a subscription token. Paste it on the Subscription token tab instead.'
)

// ---------------------------------------------------------------------------
// Claude — the one required credential
// ---------------------------------------------------------------------------

export const CLAUDE_TABS = [
  { id: 'subscription', get "label"() { return uiText("Subscription token") } },
  { id: 'api_key', get "label"() { return uiText("API key") } },
]

export const CLAUDE_TAB_COPY = {
  subscription: {
    get "label"() { return uiText("Subscription token") },
    placeholder: 'sk-ant-oat01-…',
    get "help"() { return uiText("Uses your Claude Pro or Max plan. On a computer with Claude Code signed in to that plan, run 'claude setup-token' and paste the token it prints. No terminal? Use the API key tab.") },
    providerUrl: 'https://code.claude.com/docs/en/authentication#generate-a-long-lived-token',
    get "providerLabel"() { return uiText("How to get a token") },
  },
  api_key: {
    get "label"() { return uiText("Anthropic API key") },
    placeholder: 'sk-ant-api03-…',
    get "help"() { return uiText("Pay-as-you-go through the Anthropic Console. Create a key in your browser — no terminal needed.") },
    providerUrl: 'https://console.anthropic.com/settings/keys',
    get "providerLabel"() { return uiText("Create a key") },
  },
}

export const CLAUDE_DOCS_URL = `${DOCS_PAGE}#claude`

/** Client-side format check for the Claude step; '' when it passes (or is empty). */
export function claudeCredentialError(tab, raw) {
  const v = (raw || '').trim()
  if (!v) return ''
  if (tab === 'api_key') {
    if (v.startsWith('sk-ant-oat')) return uiText(OAT_IN_API_KEY_TAB)
    if (!v.startsWith('sk-ant-')) {
      return (
        uiText("That doesn't look like an Anthropic API key. API keys start with sk-ant-api (for example sk-ant-api03-…). Create one at console.anthropic.com → API Keys.")
      )
    }
    return ''
  }
  if (v.startsWith('sk-ant-api')) {
    return (
      uiText("That's an API key, not a subscription token. Subscription tokens start with sk-ant-oat01- and come from 'claude setup-token'. Paste it on the API key tab instead.")
    )
  }
  if (!v.startsWith('sk-ant-oat01-')) {
    return (
      uiText("That doesn't look like a subscription token. Tokens start with sk-ant-oat01- — run 'claude setup-token' on a computer signed in to your Claude plan and paste what it prints.")
    )
  }
  return ''
}

/** The tab a pasted value clearly belongs on instead, or null — powers "Move it there". */
export function claudeTabFor(tab, raw) {
  const v = (raw || '').trim()
  if (tab === 'api_key' && v.startsWith('sk-ant-oat')) return 'subscription'
  if (tab === 'subscription' && v.startsWith('sk-ant-api')) return 'api_key'
  return null
}

/**
 * The name a first-run subscription is registered under. An upsert key: a
 * second token pasted here REPLACES the first for every agent using it, so the
 * copy below says "replace", never "add".
 */
export const FIRST_RUN_SUBSCRIPTION_NAME = 'primary'

/** Shown when the instance already had a Claude credential before this step. */
export const CLAUDE_ALREADY_CONNECTED = msg(
  'This instance already has a Claude credential, so agents can run. Continue, or paste a new one below: a token is saved as the "primary" subscription and an API key as the platform key, replacing whatever is saved there now for every agent that uses it.'
)

/**
 * The line after a validated save. `connectedAgents` is the save response's
 * `connected_agents` (subscription POST / anthropic-key PUT): how many agents
 * that had no Claude credential now use this one. Anything but a count — an
 * older backend, a malformed body — gets wording that claims neither outcome.
 */
export function claudeSavedText(connectedAgents) {
  const later = uiText('Manage it later in {path}.', { path: uiText(SETTINGS_PATH) })
  if (!Number.isInteger(connectedAgents) || connectedAgents < 0) return uiText('Saved. {later}', { later })
  if (connectedAgents === 0) return uiText("Saved. New agents will use it. {arg1}", { arg1: (later) })
  return connectedAgents === 1
    ? uiText('Connected 1 agent that had no Claude credential — running ones restart in the background, which takes about a minute. {later}', { later })
    : uiText('Connected {count} agents that had no Claude credential — running ones restart in the background, which takes about a minute. {later}', { count: connectedAgents, later })
}

// ---------------------------------------------------------------------------
// The optional keys
// ---------------------------------------------------------------------------

export const KEY_PROVIDERS = {
  github: {
    id: 'github',
    get "title"() { return uiText("GitHub access token") },
    get "label"() { return uiText("Personal access token") },
    placeholder: 'ghp_… or github_pat_…',
    get "enables"() { return uiText('Lets agents clone private repositories and push their work to GitHub.') },
    get "skipConsequence"() { return uiText('Without it, agents use public templates only and cannot push to GitHub.') },
    providerUrl: 'https://github.com/settings/tokens/new?scopes=repo&description=Trinity',
    get "providerLabel"() { return uiText('Create a token') },
    docsUrl: `${DOCS_PAGE}#github-access-token`,
  },
  resend: {
    id: 'resend',
    get "title"() { return uiText("Email provider (Resend)") },
    get "label"() { return uiText("Resend API key") },
    get "placeholder"() { return uiText("re_…") },
    get "enables"() { return uiText('Sends the one-time codes for email sign-in — for you and for anyone you share an agent with.') },
    get "skipConsequence"() { return uiText('Without it, nobody can sign in with an email code: only the admin password works, and codes are written to the server log instead of sent.') },
    providerUrl: 'https://resend.com/api-keys',
    get "providerLabel"() { return uiText('Create a key') },
    docsUrl: `${DOCS_PAGE}#email-provider-resend`,
  },
  gemini: {
    id: 'gemini',
    title: 'Gemini',
    get "label"() { return uiText("Gemini API key") },
    get "placeholder"() { return uiText("AIza…") },
    get "enables"() { return uiText('Powers voice conversations with agents and generates agent avatars.') },
    get "skipConsequence"() { return uiText('Without it, voice is off and agents get no generated avatars — the starter fleet shows initials instead of pictures.') },
    providerUrl: 'https://aistudio.google.com/apikey',
    get "providerLabel"() { return uiText('Create a key') },
    docsUrl: `${DOCS_PAGE}#gemini`,
  },
}

export const KEY_ORDER = ['github', 'resend', 'gemini']

/** Where to do it later — every skip names its destination. */
export function laterHint() {
  return uiText("Skip it for now and add it later in {arg1}.", { arg1: (SETTINGS_PATH) })
}

/** Client-side format check for an optional key; '' when it passes (or is empty). */
export function keyFormatError(provider, raw) {
  const v = (raw || '').trim()
  if (!v) return ''
  if (provider === 'github' && !(v.startsWith('ghp_') || v.startsWith('github_pat_'))) {
    return (
      uiText("That doesn't look like a GitHub token. Tokens start with ghp_ or github_pat_ — create one at github.com/settings/tokens with the repo scope.")
    )
  }
  if (provider === 'resend' && !v.startsWith('re_')) {
    return uiText("That doesn't look like a Resend API key. Resend keys start with re_ — create one at resend.com/api-keys.")
  }
  if (provider === 'gemini' && !v.startsWith('AIza')) {
    return (
      uiText("That doesn't look like a Gemini API key. Keys from Google AI Studio start with AIza — create one at aistudio.google.com/apikey.")
    )
  }
  return ''
}

// `Name <addr@domain>` or a bare address — the backend's `from_address_domain`.
const FROM_RE = /^(?:[^<>]*<)?\s*[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+\s*>?$/

/** The Resend sender address; '' when it passes. */
export function fromAddressError(raw) {
  const v = (raw || '').trim()
  if (FROM_RE.test(v)) return ''
  return (
    uiText("Enter the address sign-in codes are sent from, on a domain you have verified in Resend — for example noreply@your-domain.com.")
  )
}

/**
 * A placeholder sender (the compose default `noreply@trinity.example.com`, or any
 * `example.com` address) is never a working proposal — Resend refuses it — so the
 * field opens empty rather than pre-filled with something guaranteed to fail.
 */
export function prefillFromAddress(current) {
  const v = (current || '').trim()
  return /@([^@>\s]+\.)?example\.com>?$/i.test(v) ? '' : v
}

/**
 * Reduce a key-test response to what the field shows.
 * `{valid, error?, warning?, verified_domains?, has_repo_access?}` →
 * `{ok, error, warning, field}`. `field` says which input the error belongs
 * under: Resend answers `verified_domains` only once it ACCEPTED the key, so a
 * failure carrying it is about the sender address, not the key.
 */
export function describeKeyTest(provider, result) {
  if (!result || result.valid !== true) {
    return {
      ok: false,
      error: result?.error || uiText("The key couldn't be checked — try again in a moment."),
      warning: '',
      field: provider === 'resend' && Array.isArray(result?.verified_domains) ? 'from' : 'key',
    }
  }
  let warning = result.warning || ''
  if (provider === 'github' && result.has_repo_access === false) {
    warning = uiText("This token can't reach your repositories — give it the repo scope (classic) or Contents access (fine-grained) so agents can clone and push.")
  }
  return { ok: true, error: '', warning, field: '' }
}

/** One line for a configured key: where it resolves from, masked. */
export function configuredLine(status) {
  if (!status?.configured) return ''
  const masked = status.masked
  if (status.source === 'settings') {
    return masked
      ? uiText('Configured ({masked}) — saved in Settings.', { masked })
      : uiText('Configured — saved in Settings.')
  }
  return masked
    ? uiText('Configured ({masked}) — from the server environment.', { masked })
    : uiText('Configured — from the server environment.')
}
