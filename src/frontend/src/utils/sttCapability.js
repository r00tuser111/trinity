import { t as uiText, msg } from '../i18n/index.js'

// #2695 — what the Voice settings panel says about speech-to-text.
//
// `key_configured` is presence; `stt_capability` is what the provider answered
// when asked. ElevenLabs permissions are per endpoint, so a key that speaks may
// still not transcribe — and before this the panel said "configured" while every
// Workspace voice message failed. Pure, so the wording rule is testable without
// mounting the panel (vitest runs `environment: 'node'`).

export const STT_TONE = Object.freeze({ ok: 'ok', bad: 'bad', unverified: 'unverified', none: 'none' })

/**
 * @param {{ key_configured?: boolean, stt_capability?: string, stt_detail?: string|null }} state
 * @returns {{ tone: string, label: string, hint: string }}
 */
export function describeSttCapability(state) {
  if (!state || !state.key_configured || state.stt_capability === 'unconfigured') {
    return { tone: STT_TONE.none, label: '', hint: '' }
  }
  switch (state.stt_capability) {
    case 'capable':
      return {
        tone: STT_TONE.ok,
        get "label"() { return uiText("can transcribe") },
        get "hint"() { return uiText("Workspace voice input (dictation) is available.") },
      }
    case 'refused':
      return {
        tone: STT_TONE.bad,
        label: state.stt_detail ? uiText("cannot transcribe — {arg1}", { arg1: (state.stt_detail) }) : uiText("cannot transcribe"),
        hint: uiText("This key is not permitted to call speech-to-text, so Workspace server-side dictation is disabled (the browser's own dictation engine, where it has one, still works). Grant the Speech to Text permission on the key at ElevenLabs, then save it again."),
      }
    default:
      return {
        tone: STT_TONE.unverified,
        get "label"() { return uiText("transcription not verified") },
        hint: uiText("ElevenLabs could not be reached to check the key; the Workspace mic stays available until the check completes."),
      }
  }
}

const FAILURE_CATEGORY_TEXT = Object.freeze({
  permission: msg('the key is missing the speech-to-text permission'),
  auth: msg('the key was rejected'),
  quota: msg('out of credits, or the plan does not allow speech-to-text'),
  rate_limit: msg('the provider rate-limited the request'),
  audio: msg('the recording was rejected by the provider'),
  provider: msg('the provider failed'),
  unknown: msg('the provider answered with an unrecognised error'),
})

/**
 * #2696 — the last live `/stt` failure, in operator words. `null` when there is
 * none to report. The client got a category sentence at the time; this is the
 * half with the provider's status word, which only the admin panel carries.
 * @param {{ category?: string, provider_status?: number, detail?: string|null, at?: number|null }|null|undefined} failure
 * @returns {{ text: string, at: number|null }|null}
 */
export function describeSttLastFailure(failure) {
  if (!failure || !failure.category) return null
  const why = FAILURE_CATEGORY_TEXT[failure.category] || FAILURE_CATEGORY_TEXT.unknown
  const status = failure.provider_status ? `HTTP ${failure.provider_status}` : ''
  const word = failure.detail ? `${failure.detail}` : ''
  const provider = [status, word].filter(Boolean).join(' ')
  return {
    get "text"() { return uiText("Last voice-input failure: {arg1}{arg2}.", { arg1: uiText(why), arg2: (provider ? ` (${provider})` : '') }) },
    at: typeof failure.at === 'number' ? failure.at : null,
  }
}
