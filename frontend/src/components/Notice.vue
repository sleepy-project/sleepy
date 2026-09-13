<script setup lang="ts">defineProps<{ message: string; type?: 'error' | 'success' | 'info' }>()</script>
<template><p v-if="message" class="notice" :class="type || 'info'">{{ message }}</p></template>
