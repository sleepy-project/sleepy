<script setup lang="ts">
import { useAuthStore } from '@/stores/auth'
const auth = useAuthStore()
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <RouterLink class="brand" to="/"><span class="brand-mark">S</span><span>Sleepy</span></RouterLink>
      <nav>
        <RouterLink to="/">状态</RouterLink>
        <template v-if="auth.authenticated">
          <RouterLink to="/admin">管理</RouterLink><RouterLink to="/tokens">令牌</RouterLink><RouterLink to="/metrics">统计</RouterLink>
          <button class="link-button" @click="auth.logout()">退出</button>
        </template>
        <RouterLink v-else to="/login">登录</RouterLink>
      </nav>
    </header>
    <main><RouterView /></main>
    <footer>Sleepy v7 alpha · 状态以服务器快照为准</footer>
  </div>
</template>
