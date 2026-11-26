<template>
  <div class="page">
    <div class="page-head">
      <span class="page-title">账本结算</span>
      <span class="page-sub">押金场次流水明细 · 店员发薪记录</span>
      <div class="spacer"></div>
      <div v-if="auth.isAdmin" class="pos-seg" role="tablist">
        <button
          type="button"
          class="pos-seg-btn"
          :class="{ active: activeTab === 'records' }"
          @click="onTabChange('records')"
        >
          流水与场次明细
        </button>
        <button
          type="button"
          class="pos-seg-btn"
          :class="{ active: activeTab === 'salary' }"
          @click="onTabChange('salary')"
        >
          发薪记录
        </button>
      </div>
    </div>

    <RecordsView v-if="activeTab === 'records'" embedded />
    <SalaryRecordsView v-else-if="auth.isAdmin" />
  </div>
</template>

<script setup lang="ts">
import { ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import RecordsView from '@/views/RecordsView.vue'
import SalaryRecordsView from '@/views/SalaryRecordsView.vue'

const route = useRoute()
const router = useRouter()
const auth = useAuthStore()

function validTabs(): string[] {
  return auth.isAdmin ? ['records', 'salary'] : ['records']
}

function queryTab(): string {
  const tab = typeof route.query.tab === 'string' ? route.query.tab : ''
  return validTabs().includes(tab) ? tab : 'records'
}

const activeTab = ref(queryTab())

watch(
  () => route.query.tab,
  () => {
    activeTab.value = queryTab()
  },
)

function onTabChange(name: string) {
  if (activeTab.value === name) return
  activeTab.value = name
  router.replace({ query: { ...route.query, tab: name } })
}
</script>
