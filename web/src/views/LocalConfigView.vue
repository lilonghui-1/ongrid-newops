<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Document, Refresh, Setting } from '@element-plus/icons-vue'
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
      if (first) await selectFile(first.name)
    }
  } catch {
    // 错误提示由拦截器处理
  } finally {
    loading.value = false
  }
}

async function selectFile(name: string) {
  if (hasUnsavedChanges.value) {
    try {
      await ElMessageBox.confirm(
        '当前文件有未保存的修改，切换后将丢失，是否继续？',
        '提示',
        { type: 'warning', confirmButtonText: '继续', cancelButtonText: '取消' },
      )
    } catch {
      return
    }
  }
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

async function refreshFile() {
  if (selectedFileName.value) {
    await selectFile(selectedFileName.value)
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
    <el-row :gutter="16" class="main-row">
      <!-- 左侧面板 -->
      <el-col :xs="24" :sm="24" :md="6" :lg="5">
        <el-card shadow="never" class="side-card" v-loading="loading">
          <template #header>
            <div class="side-head">
              <span class="card-title">本地配置文件</span>
              <el-button
                :icon="Refresh"
                size="small"
                @click="loadConfigList"
              >
                刷新
              </el-button>
            </div>
          </template>
          <el-empty
            v-if="!activeConfigs.length"
            description="暂无配置文件"
            :image-size="60"
          />
          <el-menu
            v-else
            :default-active="selectedFileName"
            class="config-menu"
            @select="(key: string) => selectFile(key)"
          >
            <el-menu-item
              v-for="f in activeConfigs"
              :key="f.name"
              :index="f.name"
            >
              <el-icon><Document /></el-icon>
              <div class="file-info">
                <span class="file-label">{{ f.label }}</span>
                <span class="file-desc">{{ f.description }}</span>
              </div>
            </el-menu-item>
          </el-menu>
        </el-card>
      </el-col>

      <!-- 右侧编辑器 -->
      <el-col :xs="24" :sm="24" :md="18" :lg="19">
        <el-card shadow="never" class="editor-card">
          <template #header>
            <div class="editor-head">
              <div class="head-left">
                <span class="card-title">
                  {{ selectedFile?.label || selectedFileName || '请选择配置文件' }}
                </span>
                <el-tag v-if="selectedFile" size="small" type="info">
                  {{ selectedFile.name }}
                </el-tag>
                <el-tag
                  v-if="hasUnsavedChanges"
                  size="small"
                  type="warning"
                >
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
          </template>
          <div class="editor-wrap" v-loading="editorLoading">
            <Codemirror
              v-if="selectedFileName"
              v-model="content"
              :extensions="extensions"
              :disabled="!selectedFileName"
              :style="{ height: 'calc(100vh - 260px)', minHeight: '360px' }"
              :indent-with-tab="true"
              :tab-size="2"
            />
            <el-empty
              v-else
              description="请从左侧选择一个配置文件"
              :image-size="80"
            />
          </div>
        </el-card>
      </el-col>
    </el-row>
  </div>
</template>

<style scoped lang="scss">
.local-config-view {
  display: flex;
  flex-direction: column;
}

.main-row {
  margin: 0;
}

.card-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.side-card {
  .side-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }

  .config-menu {
    border-right: none;

    .file-info {
      display: flex;
      flex-direction: column;
      margin-left: 8px;
      overflow: hidden;

      .file-label {
        font-size: 14px;
        font-weight: 500;
        color: #303133;
      }

      .file-desc {
        font-size: 11px;
        color: #909399;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
    }
  }

  :deep(.el-card__body) {
    padding: 12px;
  }
}

.editor-card {
  .editor-head {
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

  .editor-wrap {
    min-height: 360px;
  }
}
</style>