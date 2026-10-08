import { t as uiText } from '../i18n/index.js'

import { ref, nextTick } from 'vue'

/**
 * Composable for terminal fullscreen and keyboard handling
 * Manages terminal state and events
 */
export function useAgentTerminal(showNotification) {
  const isTerminalFullscreen = ref(false)
  const terminalRef = ref(null)

  const toggleTerminalFullscreen = () => {
    isTerminalFullscreen.value = !isTerminalFullscreen.value
    nextTick(() => {
      if (terminalRef.value?.fit) {
        terminalRef.value.fit()
      }
    })
  }

  const handleTerminalKeydown = (event) => {
    if (event.key === 'Escape' && isTerminalFullscreen.value) {
      toggleTerminalFullscreen()
    }
  }

  const onTerminalConnected = () => {
    showNotification(uiText("Terminal connected"), 'success')
  }

  const onTerminalDisconnected = () => {
    showNotification(uiText("Terminal disconnected"), 'info')
  }

  const onTerminalError = (errorMsg) => {
    showNotification(uiText("Terminal error: {arg1}", { arg1: (errorMsg) }), 'error')
  }

  return {
    isTerminalFullscreen,
    terminalRef,
    toggleTerminalFullscreen,
    handleTerminalKeydown,
    onTerminalConnected,
    onTerminalDisconnected,
    onTerminalError
  }
}
