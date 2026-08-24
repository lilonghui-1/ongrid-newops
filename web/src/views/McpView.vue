<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, Connection } from '@element-plus/icons-vue'
import request from '@/api/request'

interface McpParam {
  name: string
  type: string
  required: boolean
}

interface McpTool {
  name: string
  description: string
  parameters: McpParam[]
}

interface McpListResponse {
  servers: string[]
  total: number
  tools: McpTool[]
}

const loading = ref(false)
const servers = ref<string[]>([])
const tools = ref<McpTool[]>([])
const total = ref(0)

// 调用对话框
const showCall = ref(false)
const callLoading = ref(false)
const callTool = ref<McpTool | null>(null)
const callArgs = ref('{}')
const callResult = ref<Record<string, unknown> | null>(null)

async function loadMcp() {
  loading.value = true
  try {
    const res = await request.get<McpListResponse>('/mcp/')
    const data = res.data
    servers.value = Array.isArray(data.servers) ? data.servers : []
    tools.value = Array.isArray(data.tools) ? data.tools : []
    total.value = data.total ?? 0
  } catch {
    // 错误提示由拦截器处理
  } finally {
    loading.value = false
  }
}

function openCall(tool: McpTool) {
  callTool.value = tool
  callArgs.value = '{}'
  callResult.value = null
  showCall.value = true
}

async function confirmCall() {
  if (!callTool.value) return
  callLoading.value = true
  try {
    let args: Record<string, unknown> = {}
    try {
      args = JSON.parse(callArgs.value || '{}')
    } catch {
      ElMessage.warning('参数 JSON 格式不正确')
      return
    }
    const res = await request.post('/mcp/call', {
      tool: callTool.value.name,
      args,
    })
    callResult.value = res.data
    ElMessage.success('MCP 工具调用完成')
  } catch {
    // 错误提示由拦截器处理
  } finally {
    callLoading.value = false
  }
}

function paramText(params: McpParam[]): string {
  if (!params?.length) return '-'
  return params
    .map((p) => `${p.name}${p.required ? '*' : '?'}:${p.type}`)
    .join(', ')
}

onMounted(() => {
  loadMcp()
})
</script>

<template>
  <div class="mcp-view">
    <!-- 工具栏 -->
    <el-card shadow="never" class="toolbar-card">
      <div class="toolbar">
        <div class="toolbar-left">
          <span class="page-title">MCP 工具</span>
          <el-tag v-for="s in servers" :key="s" size="small" type="success" effect="plain">
            {{ s }}
          </el-tag>
        </div>
        <div class="toolbar-right">
          <el-button :icon="Refresh" size="small" @click="loadMcp">刷新</el-button>
        </div>
      </div>
    </el-card>

    <!-- MCP 工具列表 -->
    <el-card shadow="never" v-loading="loading">
      <el-table :data="tools as McpTool[]" stripe style="width: 100%" empty-text="未注册 MCP 工具（请检查 config/mcp.yaml）">
        <el-table-column prop="name" label="工具名" min-width="220" show-overflow-tooltip>
          <template #default="{ row }">
            <span style="font-family: monospace; color: #409eff">{{ row.name }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="260" show-overflow-tooltip />
        <el-table-column label="参数" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span style="font-family: monospace; font-size: 12px">{{ paramText(row.parameters) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" align="center" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" link :icon="Connection" @click="openCall(row as McpTool)">
              调用
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 调用对话框 -->
    <el-dialog
      v-model="showCall"
      :title="`调用 MCP 工具: ${callTool?.name || ''}`"
      width="560px"
      :close-on-click-modal="false"
    >
      <el-form label-width="90px" label-position="right">
        <el-form-item label="工具描述">
          <div class="tool-desc">{{ callTool?.description }}</div>
        </el-form-item>
        <el-form-item label="参数 JSON">
          <el-input
            v-model="callArgs"
            type="textarea"
            :rows="4"
            placeholder='如 {"expr": "up", "range": "1h"}'
          />
        </el-form-item>
      </el-form>
      <div v-if="callResult" class="call-result">
        <pre>{{ JSON.stringify(callResult, null, 2) }}</pre>
      </div>
      <template #footer>
        <el-button @click="showCall = false">关闭</el-button>
        <el-button type="primary" :loading="callLoading" @click="confirmCall">调用</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped lang="scss">
.mcp-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.toolbar-card {
  .toolbar {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 12px;

    .toolbar-left {
      display: flex;
      align-items: center;
      gap: 12px;

      .page-title {
        font-size: 16px;
        font-weight: 600;
        color: #303133;
      }
    }
  }
}

.tool-desc {
  color: #606266;
  font-size: 13px;
}

.call-result {
  margin-top: 8px;
  background: #f5f7fa;
  border-radius: 6px;
  padding: 12px;
  max-height: 240px;
  overflow: auto;

  pre {
    margin: 0;
    font-size: 12px;
    color: #303133;
    white-space: pre-wrap;
    word-break: break-all;
  }
}
</style>