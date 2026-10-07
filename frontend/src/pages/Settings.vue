<template>
  <div style="padding:16px;max-width:480px">
    <h1>设置</h1>
    <label class="muted">看板名</label>
    <input v-model="form.board_name" placeholder="看板名" />
    <label class="muted">业务日（YYYY-MM-DD，逾期以此日现算）</label>
    <input v-model="form.business_date" placeholder="YYYY-MM-DD" />
    <button @click="save">保存设置</button>
    <span v-if="error" class="save-error">业务日非法，已回到改前：{{ error }}</span>
    <span v-else-if="saved" class="save-ok">已保存，顶细条 / 分栏 / 借还记录已按 {{ saved }} 重算</span>
    <h3>全部设置</h3>
    <pre>{{ JSON.stringify(form, null, 2) }}</pre>
  </div>
</template>
<script setup>
import { reactive, ref, inject, onMounted } from 'vue'
import { api } from '../api'
const applySettingsResult = inject('applySettingsResult')
const form = reactive({ board_name: '', business_date: '' })
const error = ref('')
const saved = ref('')
// Last value confirmed by the server. An invalid edit reverts to this,
// matching the backend rollback so form and strip never diverge.
let lastSaved = { board_name: '', business_date: '' }
onMounted(async () => {
  const s = await api('/settings')
  Object.assign(form, s)
  lastSaved = { ...s }
})
async function save() {
  error.value = ''
  saved.value = ''
  try {
    const result = await api('/settings', {
      method: 'PUT',
      body: JSON.stringify({
        values: { board_name: form.board_name, business_date: form.business_date },
      }),
    })
    lastSaved = { ...result.settings }
    Object.assign(form, result.settings)
    // One saved result drives the stat strip, board panes and loan history.
    applySettingsResult(result)
    saved.value = result.settings.business_date
  } catch (e) {
    // Invalid business_date: both the setting and the strip stay pre-edit.
    Object.assign(form, lastSaved)
    error.value = e.message
  }
}
</script>
