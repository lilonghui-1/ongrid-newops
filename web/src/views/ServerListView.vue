<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import { Refresh, Search, View } from '@element-plus/icons-vue'
import request from '@/api/request'

const router = useRouter()

interface ServerItem {
  id?: number | string
  name?: string
  host: string
  port?: number
  os_type?: string
  tags?: string[]
  online?: boolean
  databases?: string[]
  [key: string]: unknown
}

const loading = ref(false)
const servers = ref<ServerItem[]>([])
const keyword = ref('')

function isOnline(s: { online?: boolean } | Record<string, any>): boolean {
  return s?.online === true
}

const filteredServers = computed(() => {
  const kw = keyword.value.trim().toLowerCase()
  if (!kw) return servers.value
  return servers.value.filter(
    (s) =>
      (s.name || '').toLowerCase().includes(kw) ||
      (s.host || '').toLowerCase().includes(kw),
  )
})

async function loadData() {
  loading.value = true
  try {
    const res = await request.get<ServerItem[] | { items?: ServerItem[] }>('/servers')
    const raw = res.data
    servers.value = Array.isArray(raw)
      ? raw
      : (raw as { items?: ServerItem[] }).items || []
  } catch {
    // 错误提示由拦截器处理
  } finally {
    loading.value = false
  }
}

async function refresh() {
  await loadData()
  ElMessage.success('服务器列表已刷新')
}

function handleRowClick(row: ServerItem) {
  router.push(`/servers/${encodeURIComponent(row.host)}`)
}

function goDetail(host: string) {
  router.push(`/servers/${encodeURIComponent(host)}`)
}

onMounted(loadData)
</script>

<template>
  <div class="server-list-view" v-loading="loading">
    <el-card shadow="never">
      <template #header>
        <div class="toolbar">
          <div class="toolbar-left">
            <span class="title">服务器监控</span>
            <el-tag size="small" type="info">共 {{ servers.length }} 台</el-tag>
          </div>
          <div class="toolbar-right">
            <el-input
              v-model="keyword"
              placeholder="搜索主机名 / IP"
              :prefix-icon="Search"
              clearable
              style="width: 220px"
            />
            <el-button :icon="Refresh" @click="refresh">刷新</el-button>
          </div>
        </div>
      </template>

      <el-table
        :data="filteredServers"
        stripe
        highlight-current-row
        style="width: 100%"
        empty-text="暂无服务器数据"
        @row-click="handleRowClick"
      >
        <el-table-column prop="name" label="主机名" min-width="140">
          <template #default="{ row }">
            <span class="host-cell">
              <span
                class="status-dot"
                :class="isOnline(row) ? 'online' : 'offline'"
              ></span>
              {{ row.name || row.host }}
            </span>
          </template>
        </el-table-column>
        <el-table-column prop="host" label="IP 地址" min-width="140">
          <template #default="{ row }">{{ row.host }}</template>
        </el-table-column>
        <el-table-column prop="os_type" label="系统" min-width="120">
          <template #default="{ row }">{{ row.os_type || '-' }}</template>
        </el-table-column>
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag size="small" :type="isOnline(row) ? 'success' : 'danger'">
              {{ isOnline(row) ? '在线' : '离线' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120" align="center" fixed="right">
          <template #default="{ row }">
            <el-button
              type="primary"
              link
              :icon="View"
              @click.stop="goDetail(row.host)"
            >
              查看详情
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>
  </div>
</template>

<style scoped lang="scss">
.server-list-view {
  display: flex;
  flex-direction: column;
}

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

    .title {
      font-size: 15px;
      font-weight: 600;
      color: #303133;
    }
  }

  .toolbar-right {
    display: flex;
    align-items: center;
    gap: 8px;
  }
}

.host-cell {
  display: flex;
  align-items: center;
  gap: 8px;
  color: #303133;
  font-weight: 500;
}

.status-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
  display: inline-block;

  &.online {
    background: #67c23a;
    box-shadow: 0 0 5px rgba(103, 194, 58, 0.6);
  }

  &.offline {
    background: #f56c6c;
    box-shadow: 0 0 5px rgba(245, 108, 108, 0.6);
  }
}

.usage-cell {
  display: flex;
  align-items: center;
  gap: 8px;

  :deep(.el-progress) {
    flex: 1;
  }

  .usage-text {
    font-size: 12px;
    color: #606266;
    min-width: 48px;
    text-align: right;
  }
}

:deep(.el-table__row) {
  cursor: pointer;
}
</style>
