<script setup lang="ts">
// Naive UI 按需引入 + 中文 locale
import { NConfigProvider, NGlobalStyle, NMessageProvider, zhCN, dateZhCN } from 'naive-ui'
</script>

<template>
  <n-config-provider :theme="null" :locale="zhCN" :date-locale="dateZhCN" style="height: 100%">
    <n-message-provider>
      <router-view />
    </n-message-provider>
    <n-global-style />
  </n-config-provider>
</template>

<style>
html,
body,
#app {
  height: 100%;
  margin: 0;
  padding: 0;
}
</style>