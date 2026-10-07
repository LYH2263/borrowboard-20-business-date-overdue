<template>
  <div>
    <div class="status-bar">
      <span>业务日 {{ board.business_date || '—' }}</span>
      <span>可借 {{ counts.available || 0 }}</span>
      <span>在借 {{ counts.active || 0 }}</span>
      <span>逾期 {{ counts.overdue || 0 }}</span>
    </div>
    <nav class="topnav">
      <router-link to="/">看板</router-link>
      <router-link to="/list">上架</router-link>
      <router-link to="/loans">借还记录</router-link>
      <router-link to="/owners">物主</router-link>
      <router-link to="/settings">设置</router-link>
    </nav>
    <router-view @refresh="load" />
  </div>
</template>
<script setup>
import { ref, onMounted, provide } from 'vue'
import { api } from './api'
const counts = ref({})
const board = ref({ business_date: '', available: [], active: [], overdue: [] })
const loans = ref({ business_date: '', active: [], overdue: [], returned: [] })
async function load() {
  board.value = await api('/board')
  counts.value = board.value.counts || {}
}
async function loadLoans() {
  loans.value = await api('/loans')
}
// 设置保存成功后，顶细条、分栏、借还记录一次换成保存结果，杜绝各栏各算一套。
function applySavedSnapshot(snap) {
  if (snap.board) {
    board.value = snap.board
    counts.value = snap.board.counts || {}
  }
  if (snap.loans) loans.value = snap.loans
}
provide('board', board)
provide('loans', loans)
provide('reloadBoard', load)
provide('reloadLoans', loadLoans)
provide('applySavedSnapshot', applySavedSnapshot)
onMounted(load)
</script>
