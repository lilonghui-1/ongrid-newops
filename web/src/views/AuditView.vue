<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, Search } from '@element-plus/icons-vue'
import request from '@/api/request'

interface AuditItem {
  id?: number | string
  timestamp?: string
  created_at?: string
  time?: string
  user?: string
  user_id?: string | number
  username?: string
  action?: string
  object?: string
  target?: string
  method?: string
  status_code?: number
  status?: number
  ip?: string
  details?: string
  detail?: string
  [key: string]: unknown
}

const loading = ref(false)
const tableData = ref<AuditItem[]>([])
const total = ref(0)
const drawerVisible = ref(false)
const currentRow = ref<AuditItem | null>(null)

const actionOptions = [
  { label: '全部', value: '' },
  { label: '登录', value: 'login' },
  { label: '登出', value: 'logout' },
  { label: '创建', value: 'create' },
  { label: '更新', value: 'update' },
  { label: '删除', value: 'delete' },
  { label: '重启', value: 'restart' },
  { label: '关机', value: 'shutdown' },
  { label: '配置保存', value: 'config_save' },
  { label: '配置回滚', value: 'config_rollback' },
]

const query = reactive({
  user_id: '',
  action: '',
  timeRange: [] as [Date, Date] | [],
  page: 1,
  page_size: 20,
})

function fmtTime(t?: string): string {
  if (!t) return '-'
  const d = new Date(t)
  return isNaN(d.getTime()) ? t : d.toLocaleString('zh-CN')
}

function getVal(row: AuditItem, ...keys: string[]): string {
  for (const k of keys) {
    if (row[k] != null && row[k] !== '') return String(row[k])
  }
  return '-'
}

function statusTagType(code: number | undefined): 'success' | 'warning' | 'danger' {
  if (code == null) return 'warning'
  if (code >= 200 && code < 300) return 'success'
  if (code >= 400 && code < 500) return 'warning'
  return 'danger'
}

async function loadData() {
  loading.value = true
  try {
    const params: Record<string, unknown> = {
      page: query.page,
      page_size: query.page_size,
    }
    if (query.user_id.trim()) params.user_id = query.user_id.trim()
    if (query.action) params.action = query.action
    if (Array.isArray(query.timeRange) && query.timeRange.length === 2) {
      params.start_time = new Date(query.timeRange[0]).toISOString()
      params.end_time = new Date(query.timeRange[1]).toISOString()
    }
    const res = await request.get('/audit', { params })
    const data = res.data
    const items: AuditItem[] = Array.isArray(data)
      ? data
      : (data as { items?: AuditItem[] })?.items ||
        (data as { records?: AuditItem[] })?.records ||
        (data as { data?: AuditItem[] })?.data ||
        []
    tableData.value = items
    total.value =
      (data as { total?: number })?.total ??
      (data as { count?: number })?.count ??
      items.length
  } catch {
    // 错误提示由拦截器处理
  } finally {
    loading.value = false
  }
}

async function handleSearch() {
  query.page = 1
  await loadData()
  ElMessage.success('查询完成')
}

async function handleReset() {
  query.user_id = ''
  query.action = ''
  query.timeRange = []
  query.page = 1
  await loadData()
}

function handlePageChange(p: number) {
  query.page = p
  loadData()
}

function handleSizeChange(s: number) {
  query.page_size = s
  query.page = 1
  loadData()
}

function openDetail(row: AuditItem) {
  currentRow.value = row
  drawerVisible.value = true
}

onMounted(loadData)
</script>

<template>
  <div class="audit-view">
    <el-card shadow="never" class="filter-card">
      <el-form :inline="true" class="filter-form">
        <el-form-item label="用户">
          <el-input
            v-model="query.user_id"
            placeholder="用户名 / ID"
            clearable
            style="width: 180px"
          />
        </el-form-item>
        <el-form-item label="操作类型">
          <el-select
            v-model="query.action"
            placeholder="全部"
            clearable
            style="width: 150px"
          >
            <el-option
              v-for="opt in actionOptions"
              :key="opt.value"
              :label="opt.label"
              :value="opt.value"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="时间范围">
          <el-date-picker
            v-model="query.timeRange"
            type="datetimerange"
            range-separator="至"
            start-placeholder="开始时间"
            end-placeholder="结束时间"
            value-format="x"
            style="width: 360px"
          />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :icon="Search" @click="handleSearch">
            查询
          </el-button>
          <el-button :icon="Refresh" @click="handleReset">重置</el-button>
        </el-form-item>
      </el-form>
    </el-card>

    <el-card shadow="never">
      <template #header>
        <div class="card-head">
          <span class="card-title">审计日志</span>
          <el-tag size="small" type="info">共 {{ total }} 条</el-tag>
        </div>
      </template>
      <el-table
        :data="tableData"
        v-loading="loading"
        stripe
        style="width: 100%"
        empty-text="暂无审计记录"
        @row-click="openDetail"
      >
        <el-table-column label="时间" width="180">
          <template #default="{ row }">
            {{ fmtTime(row.timestamp || row.created_at || row.time) }}
          </template>
        </el-table-column>
        <el-table-column label="用户" min-width="120">
          <template #default="{ row }">
            {{ getVal(row, 'username', 'user', 'user_id') }}
          </template>
        </el-table-column>
        <el-table-column label="操作" min-width="120">
          <template #default="{ row }">
            {{ getVal(row, 'action') }}
          </template>
        </el-table-column>
        <el-table-column label="对象" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            {{ getVal(row, 'object', 'target') }}
          </template>
        </el-table-column>
        <el-table-column label="方法" width="100">
          <template #default="{ row }">
            {{ getVal(row, 'method') }}
          </template>
        </el-table-column>
        <el-table-column label="状态码" width="100" align="center">
          <template #default="{ row }">
            <el-tag
              size="small"
              :type="statusTagType(row.status_code ?? (row.status as number))"
            >
              {{ row.status_code ?? row.status ?? '-' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="IP" min-width="140">
          <template #default="{ row }">
            {{ getVal(row, 'ip_address', 'ip') }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="90" align="center" fixed="right">
          <template #default="{ row }">
            <el-button type="primary" link size="small" @click.stop="openDetail(row)">
              详情
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-bar">
        <el-pagination
          v-model:current-page="query.page"
          v-model:page-size="query.page_size"
          :page-sizes="[10, 20, 50, 100]"
          :total="total"
          layout="total, sizes, prev, pager, next, jumper"
          background
          @current-change="handlePageChange"
          @size-change="handleSizeChange"
        />
      </div>
    </el-card>

    <!-- 详情抽屉 -->
    <el-drawer
      v-model="drawerVisible"
      title="审计记录详情"
      size="40%"
      direction="rtl"
    >
      <template v-if="currentRow">
        <el-descriptions :column="1" border>
          <el-descriptions-item label="记录ID">
            {{ currentRow.id ?? '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="时间">
            {{ fmtTime(currentRow.timestamp || currentRow.created_at || currentRow.time) }}
          </el-descriptions-item>
          <el-descriptions-item label="用户">
            {{ getVal(currentRow, 'username', 'user', 'user_id') }}
          </el-descriptions-item>
          <el-descriptions-item label="操作">
            {{ getVal(currentRow, 'action') }}
          </el-descriptions-item>
          <el-descriptions-item label="对象">
            {{ getVal(currentRow, 'object', 'target') }}
          </el-descriptions-item>
          <el-descriptions-item label="方法">
            {{ getVal(currentRow, 'method') }}
          </el-descriptions-item>
          <el-descriptions-item label="状态码">
            {{ currentRow.status_code ?? currentRow.status ?? '-' }}
          </el-descriptions-item>
          <el-descriptions-item label="IP">
            {{ getVal(currentRow, 'ip_address', 'ip') }}
          </el-descriptions-item>
          <el-descriptions-item label="详情">
            <pre class="detail-pre">{{ currentRow.details || currentRow.detail || JSON.stringify(currentRow, null, 2) }}</pre>
          </el-descriptions-item>
        </el-descriptions>
      </template>
    </el-drawer>
  </div>
</template>

<style scoped lang="scss">
.audit-view {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.filter-form {
  display: flex;
  flex-wrap: wrap;
  gap: 0;
}

.card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.card-title {
  font-size: 15px;
  font-weight: 600;
  color: #303133;
}

:deep(.el-table__row) {
  cursor: pointer;
}

.pagination-bar {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.detail-pre {
  background: #f5f7fa;
  padding: 12px;
  border-radius: 6px;
  font-family: 'SFMono-Regular', Consolas, Menlo, monospace;
  font-size: 12px;
  color: #606266;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}
</style>
