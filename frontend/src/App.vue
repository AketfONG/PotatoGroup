<script setup lang="ts">
// Naive UI + 中文 locale + 主题令牌(浅色/深色)
import {
  NConfigProvider,
  NDialogProvider,
  NGlobalStyle,
  NMessageProvider,
  zhCN,
  dateZhCN,
} from 'naive-ui'

import { useThemeStore } from '@/stores/theme'

const themeStore = useThemeStore()
</script>

<template>
  <n-config-provider
    :theme="themeStore.naiveTheme"
    :theme-overrides="themeStore.themeOverrides"
    :locale="zhCN"
    :date-locale="dateZhCN"
    style="height: 100%"
  >
    <n-message-provider>
      <n-dialog-provider>
        <router-view />
      </n-dialog-provider>
    </n-message-provider>
    <n-global-style />
  </n-config-provider>
</template>

<style>
html,
body {
  overflow-x: clip;
}

html,
body,
#app {
  height: 100%;
  margin: 0;
  padding: 0;
  background: var(--bg, #f6f8fb);
  background-image: var(--bg-decor);
  background-attachment: fixed;
  color: var(--text, #0f172a);
  font-family: system-ui, 'PingFang SC', 'Noto Sans SC', sans-serif;
}

/* 主题切换瞬间关掉颜色过渡,避免 CSS 变量先变、Naive 后变的错层感 */
html.theme-switching,
html.theme-switching * {
  transition: none !important;
}

a {
  color: var(--accent);
}

/* 用户菜单中的危险项(NDropdown 渲染在 body 下,需全局样式) */
.n-dropdown-option.danger-item .n-dropdown-option-body__label {
  color: var(--danger);
}

a:focus-visible,
button:focus-visible,
[tabindex]:focus-visible,
.nav-link:focus-visible,
.conv-item:focus-visible,
.bubble:focus-visible {
  outline: none;
  box-shadow: var(--focus-ring);
}

@media (prefers-reduced-motion: reduce) {
  *,
  *::before,
  *::after {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
</style>
