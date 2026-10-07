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
    <router-view @refresh="loadBoard" />
  </div>
</template>
<script setup>
import { ref, onMounted, provide } from 'vue'
import { api } from './api'
const counts = ref({})
const board = ref({ available: [], active: [], overdue: [], business_date: '' })
// Shared loan-history snapshot so the settings save can update it in the
// same breath as the board, using the server's saved result.
const loans = ref({ active: [], overdue: [], returned: [], business_date: '' })
async function loadBoard() {
  board.value = await api('/board')
  counts.value = board.value.counts || {}
}
async function loadLoans() {
  loans.value = await api('/loans')
}
// Apply a board snapshot returned by a mutating call (e.g. lend): strip and
// panes come from the same response, classified under the current day.
function applyBoard(payload) {
  board.value = payload
  counts.value = payload.counts || {}
}
// Apply the result of a settings save: strip, panes and loan history all
// follow the same saved business_date from one server response.
function applySettingsResult(result) {
  board.value = result.board
  counts.value = result.board.counts || {}
  loans.value = result.loans
}
provide('board', board)
provide('loans', loans)
provide('reloadBoard', loadBoard)
provide('reloadLoans', loadLoans)
provide('applyBoard', applyBoard)
provide('applySettingsResult', applySettingsResult)
onMounted(loadBoard)
</script>
