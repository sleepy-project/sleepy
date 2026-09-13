<script setup lang="ts">
import { ref } from 'vue'; import { useRoute, useRouter } from 'vue-router'; import Notice from '@/components/Notice.vue'; import { useAuthStore } from '@/stores/auth'
const auth = useAuthStore(); const router = useRouter(); const route = useRoute(); const password = ref(''); const error = ref('')
async function submit() { error.value = ''; try { await auth.login(password.value); await router.push(String(route.query.redirect || '/admin')) } catch (reason) { error.value = reason instanceof Error ? reason.message : '登录失败' } }
</script>
<template><section class="auth-card"><span class="eyebrow">管理端</span><h1>欢迎回来</h1><p>登录后可管理状态、设备、令牌和统计。</p><Notice :message="error" type="error"/><form @submit.prevent="submit"><label>管理密码<input v-model="password" type="password" autocomplete="current-password" required autofocus /></label><button class="primary" :disabled="auth.loading">{{ auth.loading ? '登录中…' : '登录' }}</button></form></section></template>
