<template>
  <div style="padding:16px">
    <h1>借还记录 <span class="muted">· 业务日 {{ data.business_date || '—' }}</span></h1>
    <h3>逾期</h3>
    <div v-for="l in data.overdue" :key="'o'+l.id" class="item overdue">{{ l.title }} · {{ l.borrower }} · 应还 {{ l.due_date }}</div>
    <h3>在借</h3>
    <div v-for="l in data.active" :key="'a'+l.id" class="item">{{ l.title }} · {{ l.borrower }} · 应还 {{ l.due_date }}</div>
    <h3>已还</h3>
    <div v-for="l in data.returned" :key="'r'+l.id" class="item">{{ l.title }} · {{ l.borrower }}</div>
  </div>
</template>
<script setup>
import { inject, onMounted } from 'vue'
// Shared snapshot: a settings save updates this exact object, so the
// overdue section here moves with the saved business_date immediately.
const data = inject('loans')
const reloadLoans = inject('reloadLoans')
onMounted(reloadLoans)
</script>
