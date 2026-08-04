<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Document, Refresh, Tickets } from '@element-plus/icons-vue'
import { Codemirror } from 'vue-codemirror'
import { yaml } from '@codemirror/lang-yaml'
import { json } from '@codemirror/lang-json'
import type { Extension } from '@codemirror/state'
import request from '@/api/request'

interface ServerItem {
  host: string
  hostname?: string
  [key: string]: unknown
}

interface ConfigFile {
  path: string
  name?: string
  [key: string]: unknown
}

interface HistoryItem {
  id: number | string
  file_path?: string
  content?: string
  updated_at?: string
  operator?: string
  message?: string
  [key: string]: unknown
}

interface DiffRow {
  type: 'same' | 'add' | 'del'
  oldNo: number | null
  newNo: number | null
  oldLine: string
  newLine: string
}

const servers = ref<ServerItem[]>([])
const selectedHost = ref('')
const configFiles = ref<ConfigFile[]>([])
const selectedFile = ref('')
const content = ref('')
const originalContent = ref('')
const loading = ref(false)
const editorLoading = ref(false)

const historyVisible = ref(false)
const historyLoading = ref(false)
const historyList = ref<HistoryItem[]>([])

const diffVisible = ref(false)
const diffRows = ref<DiffRow[]>([])

/** 根据文件扩展名选择 CodeMirror 语法扩展 */
const extensions = computed<Extension[]>(() => {
  const ext = selectedFile.value.split('.').pop()?.toLowerCase() || ''
  if (ext === 'yaml' || ext === 'yml') return [yaml()]
  if (ext === 'json') return [json()]
  // properties / conf / ini 等使用纯文本
  return []
})

const languageLabel = computed(() => {
  const ext = selectedFile.value.split('.').pop()?.toLowerCase() || ''
  if (ext === 'yaml' || ext === 'yml') return 'YAML'
  if (ext === 'json') return 'JSON'
  if (ext === 'properties' || ext === 'conf' || ext === 'ini') return 'Properties'
  return 'Text'
})

const hasUnsavedChanges = computed(
  () => content.value !== originalContent.value,
)

async function loadServers() {
  try {
    const res = await request.get<ServerItem[] | { items?: ServerItem[] }>('/servers')
    const raw = res.data
    servers.value = Array.isArray(raw)
      ? raw
      : (raw as { items?: ServerItem[] }).items || []
    if (servers.value.length && !selectedHost.value) {
      selectedHost.value = servers.value[0].host
    }
  } catch {
    // 错误提示由拦截器处理
  }
}

function normalizeFiles(data: unknown): ConfigFile[] {
  if (Array.isArray(data)) {
    return data.map((item) =>
      typeof item === 'string' ? { path: item, name: item } : (item as ConfigFile),
    )
  }
  if (data && typeof data === 'object') {
    const d = data as { files?: unknown; items?: unknown }
    if (Array.isArray(d.files)) return normalizeFiles(d.files)
    if (Array.isArray(d.items)) return normalizeFiles(d.items)
  }
  return []
}

async function loadConfigList() {
  if (!selectedHost.value) {
    configFiles.value = []
    return
  }
  loading.value = true
  try {
    const res = await request.get(
      `/configs/${encodeURIComponent(selectedHost.value)}/list`,
    )
    configFiles.value = normalizeFiles(res.data)
    if (configFiles.value.length && !selectedFile.value) {
      await selectFile(configFiles.value[0])
    }
  } catch {
    // 错误提示由拦截器处理
  } finally {
    loading.value = false
  }
}

async function onHostChange() {
  selectedFile.value = ''
  content.value = ''
  originalContent.value = ''
  await loadConfigList()
}

async function selectFile(file: ConfigFile) {
  if (!file?.path) return
  // 切换前若有未保存修改，提示
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
  selectedFile.value = file.path
  editorLoading.value = true
  try {
    const res = await request.get(
      `/configs/${encodeURIComponent(selectedHost.value)}/read`,
      { params: { file_path: file.path } },
    )
    const data = res.data
    const text =
      typeof data === 'string'
        ? data
        : typeof data?.content === 'string'
          ? data.content
          : ''
    content.value = text
    originalContent.value = text
  } catch {
    // 错误提示由拦截器处理
  } finally {
    editorLoading.value = false
  }
}

/** 行级 LCS diff */
function computeDiff(oldStr: string, newStr: string): DiffRow[] {
  const oldLines = oldStr.split('\n')
  const newLines = newStr.split('\n')
  const m = oldLines.length
  const n = newLines.length
  const dp: number[][] = Array.from({ length: m + 1 }, () =>
    new Array(n + 1).fill(0),
  )
  for (let i = m - 1; i >= 0; i--) {
    for (let j = n - 1; j >= 0; j--) {
      dp[i][j] =
        oldLines[i] === newLines[j]
          ? dp[i + 1][j + 1] + 1
          : Math.max(dp[i + 1][j], dp[i][j + 1])
    }
  }
  const rows: DiffRow[] = []
  let i = 0
  let j = 0
  while (i < m && j < n) {
    if (oldLines[i] === newLines[j]) {
      rows.push({
        type: 'same',
        oldNo: i + 1,
        newNo: j + 1,
        oldLine: oldLines[i],
        newLine: newLines[j],
      })
      i++
      j++
    } else if (dp[i + 1][j] >= dp[i][j + 1]) {
      rows.push({
        type: 'del',
        oldNo: i + 1,
        newNo: null,
        oldLine: oldLines[i],
        newLine: '',
      })
      i++
    } else {
      rows.push({
        type: 'add',
        oldNo: null,
        newNo: j + 1,
        oldLine: '',
        newLine: newLines[j],
      })
      j++
    }
  }
  while (i < m) {
    rows.push({
      type: 'del',
      oldNo: i + 1,
      newNo: null,
      oldLine: oldLines[i],
      newLine: '',
    })
    i++
  }
  while (j < n) {
    rows.push({
      type: 'add',
      oldNo: null,
      newNo: j + 1,
      oldLine: '',
      newLine: newLines[j],
    })
    j++
  }
  return rows
}

async function openSaveDiff() {
  if (!selectedFile.value) {
    ElMessage.warning('请先选择配置文件')
    return
  }
  if (!hasUnsavedChanges.value) {
    ElMessage.info('内容未发生变化')
    return
  }
  diffRows.value = computeDiff(originalContent.value, content.value)
  diffVisible.value = true
}

async function confirmSave() {
  try {
    await request.post(
      `/configs/${encodeURIComponent(selectedHost.value)}/save`,
      { file_path: selectedFile.value, content: content.value },
    )
    originalContent.value = content.value
    diffVisible.value = false
    ElMessage.success('配置已保存')
  } catch {
    // 错误提示由拦截器处理
  }
}

async function openHistory() {
  if (!selectedFile.value) {
    ElMessage.warning('请先选择配置文件')
    return
  }
  historyVisible.value = true
  historyLoading.value = true
  try {
    const res = await request.get(
      `/configs/${encodeURIComponent(selectedHost.value)}/history`,
      { params: { file_path: selectedFile.value } },
    )
    const data = res.data
    historyList.value = Array.isArray(data)
      ? data
      : (data as { items?: HistoryItem[] })?.items || []
  } catch {
    // 错误提示由拦截器处理
  } finally {
    historyLoading.value = false
  }
}

function fmtTime(t?: string): string {
  if (!t) return '-'
  const d = new Date(t)
  return isNaN(d.getTime()) ? t : d.toLocaleString('zh-CN')
}

async function rollback(row: HistoryItem | Record<string, any>) {
  try {
    await ElMessageBox.confirm(
      `确定要将文件回滚到 ${fmtTime(row.updated_at)} 的版本吗？当前未保存的修改将被覆盖。`,
      '回滚确认',
      { type: 'warning', confirmButtonText: '确定回滚', cancelButtonText: '取消' },
    )
    await request.post(
      `/configs/${encodeURIComponent(selectedHost.value)}/rollback/${row.id}`,
      { file_path: selectedFile.value },
    )
    ElMessage.success('已回滚到所选版本')
    historyVisible.value = false
    await selectFile({ path: selectedFile.value })
  } catch (e) {
    if (e !== 'cancel') {
      // 接口错误由拦截器处理
    }
  }
}

async function refreshFile() {
  if (selectedFile.value) {
    await selectFile({ path: selectedFile.value })
    ElMessage.success('已重新加载文件内容')
  } else {
    await loadConfigList()
  }
}

onMounted(async () => {
  await loadServers()
  await loadConfigList()
})
</script>

<template>
  <div class="config-edit-view">
    <el-row :gutter="16" class="main-row">
      <!-- 左侧面板 -->
      <el-col :xs="24" :sm="24" :md="6" :lg="5">
        <el-card shadow="never" class="side-card" v-loading="loading">
          <template #header>
            <div class="side-head">
              <span class="card-title">配置文件</span>
            </div>
          </template>
          <div class="server-select">
            <el-select
              v-model="selectedHost"
              placeholder="选择服务器"
              filterable
              style="width: 100%"
              @change="onHostChange"
            >
              <el-option
                v-for="s in servers"
                :key="s.host"
                :label="s.hostname || s.host"
                :value="s.host"
              />
            </el-select>
          </div>
          <el-menu
            :default-active="selectedFile"
            class="file-menu"
            @select="(key: string) => selectFile({ path: key })"
          >
            <el-empty
              v-if="!configFiles.length"
              description="暂无配置文件"
              :image-size="60"
            />
            <el-menu-item
              v-for="f in configFiles"
              :key="f.path"
              :index="f.path"
            >
              <el-icon><Document /></el-icon>
              <span>{{ f.name || f.path }}</span>
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
                  {{ selectedFile || '请选择配置文件' }}
                </span>
                <el-tag v-if="selectedFile" size="small" type="info">
                  {{ languageLabel }}
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
                <el-button :icon="Refresh" size="small" @click="refreshFile">
                  刷新
                </el-button>
                <el-button :icon="Tickets" size="small" @click="openHistory">
                  历史记录
                </el-button>
                <el-button
                  type="primary"
                  size="small"
                  :disabled="!hasUnsavedChanges"
                  @click="openSaveDiff"
                >
                  保存
                </el-button>
              </div>
            </div>
          </template>
          <div class="editor-wrap" v-loading="editorLoading">
            <Codemirror
              v-if="selectedFile"
              v-model="content"
              :extensions="extensions"
              :disabled="!selectedFile"
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

    <!-- 保存 diff 弹窗 -->
    <el-dialog
      v-model="diffVisible"
      title="保存差异确认"
      width="80%"
      top="6vh"
    >
      <div class="diff-toolbar">
        <el-tag type="info">左：原始内容</el-tag>
        <el-tag type="success">右：新内容</el-tag>
        <span class="diff-stat">
          共 {{ diffRows.length }} 行变更
        </span>
      </div>
      <div class="diff-container">
        <div class="diff-pane diff-old">
          <div class="diff-pane-head">原始内容</div>
          <div class="diff-body">
            <div
              v-for="(r, idx) in diffRows"
              :key="`o-${idx}`"
              class="diff-line"
              :class="r.type === 'del' ? 'del' : r.type === 'add' ? 'empty' : ''"
            >
              <span class="line-no">{{ r.oldNo ?? '' }}</span>
              <span class="line-text">{{ r.oldLine }}</span>
            </div>
          </div>
        </div>
        <div class="diff-pane diff-new">
          <div class="diff-pane-head">新内容</div>
          <div class="diff-body">
            <div
              v-for="(r, idx) in diffRows"
              :key="`n-${idx}`"
              class="diff-line"
              :class="r.type === 'add' ? 'add' : r.type === 'del' ? 'empty' : ''"
            >
              <span class="line-no">{{ r.newNo ?? '' }}</span>
              <span class="line-text">{{ r.newLine }}</span>
            </div>
          </div>
        </div>
      </div>
      <template #footer>
        <el-button @click="diffVisible = false">取消</el-button>
        <el-button type="primary" @click="confirmSave">确认保存</el-button>
      </template>
    </el-dialog>

    <!-- 历史记录弹窗 -->
    <el-dialog
      v-model="historyVisible"
      title="历史版本"
      width="70%"
      top="8vh"
    >
      <el-table
        :data="historyList"
        v-loading="historyLoading"
        stripe
        empty-text="暂无历史记录"
        max-height="420"
      >
        <el-table-column prop="id" label="版本ID" width="100" />
        <el-table-column label="更新时间" width="180">
          <template #default="{ row }">{{ fmtTime(row.updated_at) }}</template>
        </el-table-column>
        <el-table-column prop="operator" label="操作人" min-width="120">
          <template #default="{ row }">{{ row.operator || '-' }}</template>
        </el-table-column>
        <el-table-column prop="message" label="备注" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">{{ row.message || '-' }}</template>
        </el-table-column>
        <el-table-column label="操作" width="120" align="center" fixed="right">
          <template #default="{ row }">
            <el-button type="warning" link size="small" @click="rollback(row)">
              回滚
            </el-button>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="historyVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped lang="scss">
.config-edit-view {
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

  .server-select {
    margin-bottom: 12px;
  }

  .file-menu {
    border-right: none;
    max-height: calc(100vh - 260px);
    overflow: auto;
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
    }
  }

  .editor-wrap {
    min-height: 360px;
  }
}

.diff-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 12px;

  .diff-stat {
    font-size: 13px;
    color: #909399;
  }
}

.diff-container {
  display: flex;
  gap: 12px;
  height: 56vh;
  overflow: hidden;
}

.diff-pane {
  flex: 1;
  display: flex;
  flex-direction: column;
  border: 1px solid #e4e7ed;
  border-radius: 6px;
  overflow: hidden;

  .diff-pane-head {
    padding: 8px 12px;
    background: #f5f7fa;
    font-size: 13px;
    font-weight: 600;
    color: #606266;
    border-bottom: 1px solid #e4e7ed;
  }

  .diff-body {
    flex: 1;
    overflow: auto;
    font-family: 'SFMono-Regular', Consolas, Menlo, monospace;
    font-size: 12px;
    background: #fafafa;
  }

  .diff-line {
    display: flex;
    white-space: pre;
    line-height: 20px;

    .line-no {
      width: 44px;
      flex-shrink: 0;
      text-align: right;
      padding-right: 8px;
      color: #c0c4cc;
      background: #f0f0f0;
      user-select: none;
    }

    .line-text {
      padding: 0 8px;
      flex: 1;
      overflow-x: auto;
    }

    &.add {
      background: #f0f9eb;

      .line-text {
        color: #67c23a;
      }
    }

    &.del {
      background: #fef0f0;

      .line-text {
        color: #f56c6c;
        text-decoration: line-through;
      }
    }

    &.empty {
      background: #f7f7f7;
    }
  }
}
</style>
