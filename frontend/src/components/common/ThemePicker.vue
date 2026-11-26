<template>
  <el-dropdown
    trigger="click"
    :placement="placement"
    @command="onSelect"
  >
    <slot :current="current">
      <button type="button" class="theme-pill" :title="`当前主题：${current.label}`">
        <span
          class="swatch"
          :style="{
            background: `linear-gradient(135deg, ${current.swatchBg} 50%, ${current.swatchAccent} 50%)`,
          }"
        ></span>
        <span>{{ current.label }}</span>
      </button>
    </slot>

    <template #dropdown>
      <el-dropdown-menu class="theme-menu">
        <el-dropdown-item
          v-for="item in THEMES"
          :key="item.id"
          :command="item.id"
          :class="{ 'is-selected': item.id === app.theme }"
        >
          <div class="theme-opt">
            <span
              class="swatch"
              :style="{
                background: `linear-gradient(135deg, ${item.swatchBg} 50%, ${item.swatchAccent} 50%)`,
              }"
            ></span>
            <div class="theme-opt-text">
              <span class="theme-opt-name">{{ item.label }}</span>
              <span class="theme-opt-desc">{{ item.desc }}</span>
            </div>
            <el-icon v-if="item.id === app.theme" class="theme-check"><Check /></el-icon>
          </div>
        </el-dropdown-item>
      </el-dropdown-menu>
    </template>
  </el-dropdown>
</template>

<script setup lang="ts">
import { Check } from '@element-plus/icons-vue'
import { computed } from 'vue'

import { useAppStore } from '@/stores/app'
import { getThemeMeta, THEMES, type ThemeId } from '@/utils/themes'

withDefaults(
  defineProps<{
    placement?: 'right-end' | 'bottom-end' | 'top-start' | 'bottom-start'
  }>(),
  {
    placement: 'bottom-end',
  },
)

const app = useAppStore()
const current = computed(() => getThemeMeta(app.theme))

function onSelect(id: ThemeId) {
  app.setTheme(id)
}
</script>

<style scoped>
.theme-pill {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  height: 32px;
  padding: 0 11px;
  border-radius: 8px;
  border: 1px solid var(--app-border);
  background: var(--app-bg-panel);
  color: var(--app-text-muted);
  font: inherit;
  font-size: 12.5px;
  cursor: pointer;
  transition: border-color 0.14s ease, color 0.14s ease;
}

.theme-pill:hover {
  border-color: var(--app-border-strong);
  color: var(--app-text-main);
}

.swatch {
  width: 14px;
  height: 14px;
  border-radius: 50%;
  border: 1px solid var(--app-border-strong);
  flex: none;
  box-shadow: inset 0 0 0 1px rgba(255, 255, 255, 0.12);
}

.theme-opt {
  display: flex;
  align-items: center;
  gap: 9px;
  min-width: 158px;
  padding: 2px 0;
}

.theme-opt-text {
  display: flex;
  flex-direction: column;
  line-height: 1.25;
  flex: 1;
}

.theme-opt-name {
  font-size: 13px;
  font-weight: 550;
  color: var(--app-text-main);
}

.theme-opt-desc {
  font-size: 11px;
  color: var(--app-text-muted);
}

.theme-check {
  color: var(--app-primary);
  font-size: 14px;
}
</style>
