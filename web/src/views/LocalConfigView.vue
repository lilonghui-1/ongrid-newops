<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Refresh, Setting } from '@element-plus/icons-vue'
import { Codemirror } from 'vue-codemirror'
import { yaml } from '@codemirror/lang-yaml'
import type { Extension } from '@codemirror/state'
import request from '@/api/request'

interface LocalConfigFile {
  name: string
  path: string
  label: string
  description: string
  format: string
  exists: boolean
  size: number
  modified_at: string | null
}

interface ConfigContent {
  name: string
  content: string
  size: number
}

const configFiles = ref<LocalConfigFile[]>([])
const selectedFileName = ref('')
const content = ref('')
const originalContent = ref('')
const loading = ref(false)
const editorLoading = ref(false)
const saving = ref(false)
const reloading = ref(false)

const extensions = computed<Extension[]>(() => [yaml()])

const hasUnsavedChanges = computed(
  () => content.value !== originalContent.value,
)

const selectedFile = computed(() =>
  configFiles.value.find((f) => f.name === selectedFileName.value),
)

const activeConfigs = computed(() =>
  configFiles.value.filter((f) => f.exists),
)

async function loadConfigList() {
  loading.value = true
  try {
    const res = await request.get<LocalConfigFile[]>('/local-configs/files')
    configFiles.value = Array.isArray(res.data) ? res.data : []
    if (configFiles.value.length && !selectedFileName.value) {
      const first = configFiles.value.find((f) => f.exists)
      if (first) await loadFileContent(first.name)
    }
  } catch {
    // 错误提示由拦截器处理
  } finally {
    loading.value = false
  }
}

/** 加载指定配置文件内容（不检查未保存状态，供标签页切换使用） */
async function loadFileContent(name: string) {
  selectedFileName.value = name
  editorLoading.value = true
  try {
    const res = await request.get<ConfigContent>(
      `/local-configs/files/${encodeURIComponent(name)}`,
    )
    const data = res.data
    content.value = typeof data.content === 'string' ? data.content : ''
    originalContent.value = content.value
  } catch {
    // 错误提示由拦截器处理
  } finally {
    editorLoading.value = false
  }
}

/** 标签页切换前的未保存校验：返回 false 则阻止切换 */
async function beforeSwitchTab(targetName: string | number): Promise<boolean> {
  if (String(targetName) === selectedFileName.value) return true
  if (!hasUnsavedChanges.value) return true
  try {
    await ElMessageBox.confirm(
      '当前文件有未保存的修改，切换后将丢失，是否继续？',
      '提示',
      { type: 'warning', confirmButtonText: '继续', cancelButtonText: '取消' },
    )
    return true
  } catch {
    return false
  }
}

/** 标签页成功切换后加载目标文件内容 */
async function onTabChange(name: string | number) {
  await loadFileContent(String(name))
}

async function refreshFile() {
  if (selectedFileName.value) {
    await loadFileContent(selectedFileName.value)
    ElMessage.success('已重新加载文件内容')
  } else {
    await loadConfigList()
  }
}

async function confirmSave() {
  if (!selectedFileName.value) {
    ElMessage.warning('请先选择配置文件')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确定要保存「${selectedFileName.value}」吗？\n\n保存后系统将自动备份原文件，并立即生效。`,
      '保存确认',
      { type: 'info', confirmButtonText: '确定保存', cancelButtonText: '取消' },
    )
  } catch {
    return
  }

  saving.value = true
  try {
    await request.put(
      `/local-configs/files/${encodeURIComponent(selectedFileName.value)}`,
      { content: content.value },
    )
    originalContent.value = content.value
    ElMessage.success('配置文件已保存')

    // 保存成功后自动触发热重载
    await triggerReload()
  } catch {
    // 错误提示由拦截器处理
  } finally {
    saving.value = false
  }
}

async function triggerReload() {
  reloading.value = true
  try {
    const res = await request.post('/local-configs/reload')
    const data = res.data as { message?: string; details?: Record<string, unknown> }
    const detailInfo = data.details
      ? Object.entries(data.details)
          .map(([k, v]) => `${k}: ${Array.isArray(v) ? v.join(', ') : v}`)
          .join('；')
      : ''
    ElMessage.success(`配置已生效 ${detailInfo ? `(${detailInfo})` : ''}`)
  } catch {
    ElMessage.warning('配置已保存，但热重载失败，建议重启应用')
  } finally {
    reloading.value = false
  }
}

function fmtTime(t?: string | null): string {
  if (!t) return '-'
  const d = new Date(t)
  return isNaN(d.getTime()) ? t : d.toLocaleString('zh-CN')
}

function fmtSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}

onMounted(loadConfigList)
</script>

<template>
  <div class="local-config-view">
    <!-- 顶部工具栏 -->
    <el-card shadow="never" class="toolbar-card">
      <div class="toolbar-head">
        <div class="head-left">
          <span class="card-title">本地配置管理</span>
          <el-tag v-if="selectedFile" size="small" type="info">
            {{ selectedFile.name }}
          </el-tag>
          <el-tag v-if="hasUnsavedChanges" size="small" type="warning">
            未保存
          </el-tag>
        </div>
        <div class="head-right">
          <el-tag v-if="selectedFile" size="small" type="info">
            大小: {{ fmtSize(selectedFile.size) }}
          </el-tag>
          <el-tag v-if="selectedFile" size="small" type="info">
            修改时间: {{ fmtTime(selectedFile.modified_at) }}
          </el-tag>
          <el-button :icon="Refresh" size="small" @click="refreshFile">
            刷新
          </el-button>
          <el-button
            type="primary"
            size="small"
            :loading="saving"
            :disabled="!hasUnsavedChanges"
            @click="confirmSave"
          >
            保存
          </el-button>
          <el-button
            type="warning"
            size="small"
            :icon="Setting"
            :loading="reloading"
            @click="triggerReload"
          >
            重载配置
          </el-button>
        </div>
      </div>
    </el-card>

    <!-- 配置切换标签页 + 编辑器 -->
    <el-card shadow="never" class="editor-card" v-loading="loading">
      <el-empty
        v-if="!activeConfigs.length"
        description="暂无配置文件"
        :image-size="80"
      />
      <el-tabs
        v-else
        v-model="selectedFileName"
        type="border-card"
        :before-leave="beforeSwitchTab"
        @tab-change="onTabChange"
      >
        <el-tab-pane
          v-for="f in activeConfigs"
          :key="f.name"
          :name="f.name"
          :label="f.label"
        >
          <template #label>
            <div class="tab-label">
              <span class="tab-title">{{ f.label }}</span>
              <span class="tab-desc">{{ f.description }}</span>
            </div>
          </template>
          <div
            class="editor-wrap"
            v-if="selectedFileName === f.name"
            v-loading="editorLoading"
          >
            <Codemirror
              v-model="content"
              :extensions="extensions"
              :disabled="!selectedFileName"
              :style="{ height: 'calc(100vh - 280px)', minHeight: '360px' }"
              :indent-with-tab="true"
              :tab-size="2"
            />
          </div>
        </el-tab-pane>
      </el-tabs>
    </el-card>
  </div>
</template>

<style scoped lang="scss">
.local-config-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.card-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
  white-space: nowrap;
}

.toolbar-card {
  .toolbar-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 8px;

    .head-left {
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .head-right {
      display: flex;
      align-items: center;
      gap: 8px;
      flex-wrap: wrap;
    }
  }
}

.editor-card {
  :deep(.el-tabs__content) {
    padding: 12px;
  }

  .tab-label {
    display: flex;
    flex-direction: column;
    align-items: flex-start;
    line-height: 1.3;

    .tab-title {
      font-size: 14px;
      font-weight: 500;
    }

    .tab-desc {
      font-size: 11px;
      color: #909399;
    }
  }

  .editor-wrap {
    min-height: 360px;
  }
}
</style>