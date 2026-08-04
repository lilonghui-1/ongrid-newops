<script setup lang="ts">
import {
  computed,
  nextTick,
  onBeforeUnmount,
  onMounted,
  ref,
  watch,
} from 'vue'
import { ElMessage } from 'element-plus'
import { Download, Search } from '@element-plus/icons-vue'
import request from '@/api/request'
import { useAuthStore } from '@/stores/auth'

const auth = useAuthStore()

interface ServerItem {
  host: string
  hostname?: string
  ip?: string
  [key: string]: unknown
}

interface LogLine {
  text: string
  level: 'error' | 'warn' | 'info'
}

const servers = ref<ServerItem[]>([])
const selectedHost = ref('')
const filePath = ref('/var/log/messages')
const mode = ref<'tail' | 'head' | 'grep'>('tail')
const lines = ref(200)
const keyword = ref('')
const realtime = ref(false)

const logLines = ref<LogLine[]>([])
const loading = ref(false)
const logBodyRef = ref<HTMLElement>()

let ws: WebSocket | null = null

function classify(line: string): LogLine['level'] {
  const up = line.toUpperCase()
  if (/\b(ERROR|ERR|FATAL|CRITICAL|EXCEPTION)\b/.test(up)) return 'error'
  if (/\b(WARN|WARNING)\b/.test(up)) return 'warn'
  return 'info'
}

const lineCount = computed(() => logLines.value.length)

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

async function query() {
  if (!selectedHost.value) {
    ElMessage.warning('请先选择服务器')
    return
  }
  if (!filePath.value.trim()) {
    ElMessage.warning('请输入日志文件路径')
    return
  }
  // 关闭实时模式后再查询历史
  if (realtime.value) realtime.value = false
  loading.value = true
  logLines.value = []
  try {
    const res = await request.post('/logs/search', {
      server_host: selectedHost.value,
      log_file: filePath.value.trim(),
      mode: mode.value,
      lines: lines.value,
      keyword: keyword.value.trim() || undefined,
    })
    const data = res.data
    const rawLines: string[] = Array.isArray(data?.logs)
      ? data.logs
      : typeof data === 'string'
        ? data.split('\n')
        : []
    logLines.value = rawLines
      .filter((l) => l !== undefined && l !== null)
      .map((l) => ({ text: String(l), level: classify(String(l)) }))
    ElMessage.success(`已加载 ${logLines.value.length} 行`)
    scrollToBottom()
  } catch {
    // 错误提示由拦截器处理
  } finally {
    loading.value = false
  }
}

function buildWsUrl(): string {
  // 通过页面当前地址构造，开发环境由 Vite /ws 代理转发到后端
  const proto = window.location.protocol === 'https:' ? 'wss' : 'ws'
  const wsHost = window.location.host
  const params = new URLSearchParams({
    file_path: filePath.value.trim(),
    token: auth.token || '',
  })
  return `${proto}://${wsHost}/ws/logs/${encodeURIComponent(selectedHost.value)}?${params.toString()}`
}

function startRealtime() {
  if (!selectedHost.value) {
    ElMessage.warning('请先选择服务器')
    realtime.value = false
    return
  }
  if (!filePath.value.trim()) {
    ElMessage.warning('请输入日志文件路径')
    realtime.value = false
    return
  }
  logLines.value = []
  try {
    ws = new WebSocket(buildWsUrl())
  } catch (e) {
    ElMessage.error('WebSocket 连接失败')
    realtime.value = false
    return
  }
  ws.onopen = () => ElMessage.success('实时日志已连接')
  ws.onmessage = (ev) => {
    const text = typeof ev.data === 'string' ? ev.data : ''
    // 后端可能一次推送多行
    text.split('\n').forEach((line) => {
      if (line === '') return
      logLines.value.push({ text: line, level: classify(line) })
    })
    if (logLines.value.length > 5000) {
      logLines.value = logLines.value.slice(-5000)
    }
    scrollToBottom()
  }
  ws.onerror = () => ElMessage.error('WebSocket 连接异常')
  ws.onclose = () => {
    realtime.value = false
  }
}

function stopRealtime() {
  if (ws) {
    ws.onclose = null
    ws.close()
    ws = null
  }
  realtime.value = false
}

watch(realtime, (val) => {
  if (val) startRealtime()
  else stopRealtime()
})

function scrollToBottom() {
  nextTick(() => {
    if (logBodyRef.value) {
      logBodyRef.value.scrollTop = logBodyRef.value.scrollHeight
    }
  })
}

function downloadFile(content: string, filename: string) {
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

async function exportTxt() {
  if (!logLines.value.length) {
    ElMessage.warning('当前没有可导出的日志')
    return
  }
  const content = logLines.value.map((l) => l.text).join('\n')
  downloadFile(content, `log-${selectedHost.value || 'export'}-${Date.now()}.txt`)
}

async function exportCsv() {
  if (!logLines.value.length) {
    ElMessage.warning('当前没有可导出的日志')
    return
  }
  try {
    // 优先由后端导出
    const res = await request.post(
      '/logs/export',
      {
        server_host: selectedHost.value,
        log_file: filePath.value.trim(),
        mode: mode.value,
        lines: lines.value,
        keyword: keyword.value.trim() || undefined,
        format: 'csv',
      },
      { responseType: 'blob' },
    )
    const blob = new Blob([res.data as BlobPart], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `log-${selectedHost.value || 'export'}-${Date.now()}.csv`
    a.click()
    URL.revokeObjectURL(url)
  } catch {
    // 后端不支持则前端导出当前日志
    const header = '行号,级别,内容\n'
    const rows = logLines.value
      .map((l, i) => `${i + 1},${l.level},"${l.text.replace(/"/g, '""')}"`)
      .join('\n')
    downloadFile(header + rows, `log-${selectedHost.value || 'export'}-${Date.now()}.csv`)
  }
}

function clearLogs() {
  logLines.value = []
}

onMounted(() => {
  loadServers()
})

onBeforeUnmount(() => {
  stopRealtime()
})
</script>

<template>
  <div class="log-query-view">
    <el-card shadow="never" class="filter-card">
      <el-form :inline="true" class="filter-form">
        <el-form-item label="服务器">
          <el-select
            v-model="selectedHost"
            placeholder="选择服务器"
            filterable
            style="width: 200px"
          >
            <el-option
              v-for="s in servers"
              :key="s.host"
              :label="s.hostname || s.host"
              :value="s.host"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="文件路径">
          <el-input
            v-model="filePath"
            placeholder="/var/log/messages"
            clearable
            style="width: 240px"
          />
        </el-form-item>
        <el-form-item label="模式">
          <el-select v-model="mode" style="width: 110px">
            <el-option label="tail（尾部）" value="tail" />
            <el-option label="head（头部）" value="head" />
            <el-option label="grep（过滤）" value="grep" />
          </el-select>
        </el-form-item>
        <el-form-item label="行数">
          <el-input-number v-model="lines" :min="10" :max="10000" :step="100" style="width: 130px" />
        </el-form-item>
        <el-form-item label="关键词">
          <el-input
            v-model="keyword"
            placeholder="grep 模式下生效"
            clearable
            style="width: 180px"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" :loading="loading" @click="query">
            查询
          </el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never" class="log-card">
      <template #header>
        <div class="log-toolbar">
          <div class="toolbar-left">
            <span class="card-title">日志输出</span>
            <el-tag size="small" type="info">共 {{ lineCount }} 行</el-tag>
            <el-tag v-if="realtime" size="small" type="success">实时中</el-tag>
          </div>
          <div class="toolbar-right">
            <el-button :icon="Download" size="small" @click="exportTxt">导出 TXT</el-button>
            <el-button :icon="Download" size="small" @click="exportCsv">导出 CSV</el-button>
            <el-button size="small" @click="clearLogs">清空</el-button>
            <span class="realtime-switch">
              实时模式
              <el-switch v-model="realtime" />
            </span>
          </div>
        </div>
      </template>
      <div ref="logBodyRef" class="log-body" v-loading="loading">
        <div v-if="!logLines.length && !loading" class="empty-tip">
          请选择服务器并查询日志，或开启实时模式
        </div>
        <pre
          v-for="(line, idx) in logLines"
          :key="idx"
          class="log-line"
          :class="line.level"
        >{{ line.text }}</pre>
      </div>
    </el-card>
  </div>
</template>

<style scoped lang="scss">
.log-query-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.filter-form {
  display: flex;
  flex-wrap: wrap;
  gap: 0;
}

.card-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

.log-card {
  :deep(.el-card__body) {
    padding: 0;
  }
}

.log-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 8px;

  .toolbar-left {
    display: flex;
    align-items: center;
    gap: 10px;
  }

  .toolbar-right {
    display: flex;
    align-items: center;
    gap: 8px;

    .realtime-switch {
      display: flex;
      align-items: center;
      gap: 6px;
      font-size: 13px;
      color: #606266;
      margin-left: 8px;
    }
  }
}

.log-body {
  background: #1e1e1e;
  color: #d4d4d4;
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace;
  font-size: 13px;
  line-height: 1.6;
  padding: 12px 16px;
  height: calc(100vh - 320px);
  min-height: 320px;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-all;

  .empty-tip {
    color: #6a6a6a;
    text-align: center;
    padding: 60px 0;
  }

  .log-line {
    margin: 0;
    white-space: pre-wrap;
    word-break: break-all;

    &.error {
      color: #f56c6c;
    }

    &.warn {
      color: #e6a23c;
    }

    &.info {
      color: #d4d4d4;
    }
  }
}
</style>
