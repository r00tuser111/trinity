import { t as uiText } from '../i18n/index.js'

// Canonical Gemini Live voice list (#28) — the single frontend source of truth
// for both the AgentWorkspace per-session picker and the VoIP settings picker.
// Mirrors the backend `GEMINI_VOICE_NAMES` in src/backend/config.py; a backend
// unit test asserts the two lists agree so they can't silently drift.
export const DEFAULT_VOICE_NAME = 'Kore'

export const VOICES = [
  { id: 'Kore', get "label"() { return uiText("Kore — Firm") } },
  { id: 'Zephyr', get "label"() { return uiText("Zephyr — Bright") } },
  { id: 'Puck', get "label"() { return uiText("Puck — Upbeat") } },
  { id: 'Aoede', get "label"() { return uiText("Aoede — Breezy") } },
  { id: 'Charon', get "label"() { return uiText("Charon — Informational") } },
  { id: 'Fenrir', get "label"() { return uiText("Fenrir — Excitable") } },
  { id: 'Gacrux', get "label"() { return uiText("Gacrux — Mature") } },
]

export const VOICE_IDS = VOICES.map((v) => v.id)
