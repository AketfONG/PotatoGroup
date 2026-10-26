/** 浅色 / 深色主题:持久化到 localStorage;切换时先写 CSS 变量再换 Naive,减少闪滞。 */

import { defineStore } from 'pinia'
import { computed, nextTick, ref, watch } from 'vue'
import { darkTheme, type GlobalTheme } from 'naive-ui'

import {
  applyCssVars,
  darkThemeOverrides,
  lightThemeOverrides,
  type ThemeMode,
} from '@/theme/tokens'

const STORAGE_KEY = 'potato_theme'
const SWITCH_CLASS = 'theme-switching'

function readStored(): ThemeMode {
  const raw = localStorage.getItem(STORAGE_KEY)
  return raw === 'dark' ? 'dark' : 'light'
}

function flashSwitchLock(): void {
  const root = document.documentElement
  root.classList.add(SWITCH_CLASS)
  window.setTimeout(() => {
    root.classList.remove(SWITCH_CLASS)
  }, 120)
}

export const useThemeStore = defineStore('theme', () => {
  const mode = ref<ThemeMode>(readStored())

  const naiveTheme = computed<GlobalTheme | null>(() =>
    mode.value === 'dark' ? darkTheme : null,
  )
  const themeOverrides = computed(() =>
    mode.value === 'dark' ? darkThemeOverrides : lightThemeOverrides,
  )

  function apply(): void {
    flashSwitchLock()
    applyCssVars(mode.value)
    localStorage.setItem(STORAGE_KEY, mode.value)
  }

  function setMode(next: ThemeMode): void {
    if (next === mode.value) return
    // 先同步 CSS 变量,再改 mode 触发 Naive 重渲染
    flashSwitchLock()
    applyCssVars(next)
    localStorage.setItem(STORAGE_KEY, next)
    mode.value = next
    void nextTick()
  }

  function toggle(): void {
    setMode(mode.value === 'light' ? 'dark' : 'light')
  }

  // 首屏只应用变量,不重复 flash
  applyCssVars(mode.value)
  watch(mode, () => {
    /* setMode 已处理;其它路径改 mode 时兜底 */
    applyCssVars(mode.value)
    localStorage.setItem(STORAGE_KEY, mode.value)
  })

  return { mode, naiveTheme, themeOverrides, setMode, toggle }
})
