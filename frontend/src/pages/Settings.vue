<template>
  <div style="padding:16px;max-width:480px">
    <h1>设置</h1>
    <label class="muted">业务日（YYYY-MM-DD），在借与逾期都按它划分</label>
    <input v-model="businessDate" placeholder="YYYY-MM-DD" />
    <div style="display:flex;gap:8px;align-items:center">
      <button @click="save">保存业务日</button>
      <span class="muted" v-if="msg" :style="err ? 'color:#a33' : ''">{{ msg }}</span>
    </div>
    <hr />
    <pre>{{ s }}</pre>
  </div>
</template>
<script setup>
import { ref, onMounted, inject } from 'vue'
import { api } from '../api'
const s = ref('')
const businessDate = ref('')
const savedDate = ref('')
const msg = ref('')
const err = ref(false)
const applySavedSnapshot = inject('applySavedSnapshot')

async function load() {
  const settings = await api('/settings')
  s.value = JSON.stringify(settings, null, 2)
  businessDate.value = settings.business_date || ''
  savedDate.value = businessDate.value
}
onMounted(load)

async function save() {
  msg.value = ''; err.value = false
  const before = savedDate.value
  try {
    const snap = await api('/settings', {
      method: 'POST', body: JSON.stringify({ business_date: businessDate.value }),
    })
    // 顶细条、分栏、借还记录一次跟保存结果（同一服务端快照）。
    applySavedSnapshot(snap)
    s.value = JSON.stringify(snap.settings, null, 2)
    savedDate.value = snap.settings.business_date
    businessDate.value = savedDate.value
    msg.value = '已保存，看板与记录按业务日 ' + savedDate.value + ' 重新判定'
  } catch (e) {
    // 非法日期：服务端未落库，本地输入也回到改前的业务日。
    businessDate.value = before
    err = true
    msg.value = '业务日非法，已回到改前值（' + before + '）：' + e.message
  }
}
</script>
