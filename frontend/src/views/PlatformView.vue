<template>
  <div class="page">
    <div class="page-head">
      <span class="page-title">平台管理</span>
      <span class="page-sub">商家与门店账号 · 查战绩配额分配</span>
      <div class="spacer"></div>
      <div class="pos-seg" role="tablist">
        <button
          type="button"
          class="pos-seg-btn"
          :class="{ active: tab === 'merchants' }"
          @click="tab = 'merchants'"
        >
          商家与账号
        </button>
        <button
          type="button"
          class="pos-seg-btn"
          :class="{ active: tab === 'zj' }"
          @click="tab = 'zj'"
        >
          查战绩配额
        </button>
      </div>
    </div>

    <MerchantPanel v-if="tab === 'merchants'" />
    <ZhanjiQuotaPanel v-else />
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

import MerchantPanel from '@/views/platform/MerchantPanel.vue'
import ZhanjiQuotaPanel from '@/views/platform/ZhanjiQuotaPanel.vue'

const tab = ref<'merchants' | 'zj'>('merchants')
</script>
