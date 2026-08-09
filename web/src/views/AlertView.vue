<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Delete, Download, Refresh, WarningFilled } from '@element-plus/icons-vue'
import request from '@/api/request'

interface EmailLogItem {
  id: number
  subject: string
  to_addrs: string
  attachment: string | null
  status: string
  error_msg: string | null
  created_at: string
}

interface EmailLogListResponse {
  total: number
  items: EmailLogItem[]
}

const loading = ref(false)
const sendLoading = ref(false)
const logs = ref<EmailLogItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(20)
const statusFilter = ref('')

// 发送邮件表单
const showSendDialog = ref(false)
const sendForm = ref({
  subject: '',
  body: '',
  level: 'warning',
  to_addrs: '',
})

const levelOptions = [
  { value: 'info', label: '信息', color: '#409eff' },
  { value: 'warning', label: '警告', color: '#e6a23c' },
  { value: 'error', label: '错误', color: '#f56c6c' },
  { value: 'critical', label: '严重', color: '#b22222' },
]

async function loadLogs() {
  loading.value = true
  try {
    const params: Record<string, unknown> = {
      page: page.value,
      page_size: pageSize.value,
    }
    if (statusFilter.value) {
      params.status_filter = statusFilter.value
    }
    const res = await request.get<EmailLogListResponse>('/alert/email-logs', { params })
    const data = res.data
    logs.value = Array.isArray(data.items) ? data.items : []
    total.value = data.total ?? 0
  } catch {
    // 错误提示由拦截器处理
  } finally {
    loading.value = false
  }
}

function handlePageChange(p: number) {
  page.value = p
  loadLogs()
}

function handleFilterChange(val: string) {
  statusFilter.value = val
  page.value = 1
  loadLogs()
}

function fmtTime(t: string): string {
  const d = new Date(t)
  return isNaN(d.getTime()) ? t : d.toLocaleString('zh-CN')
}

function statusTag(st: string) {
  if (st === 'success') return 'success'
  if (st === 'failed') return 'danger'
  return 'info'
}

function statusLabel(st: string) {
  if (st === 'success') return '发送成功'
  if (st === 'failed') return '发送失败'
  return st
}

function levelTag(level: string) {
  const opt = levelOptions.find((o) => o.value === level)
  return opt?.label ?? level
}

function levelColor(level: string) {
  const opt = levelOptions.find((o) => o.value === level)
  return opt?.color ?? '#909399'
}

async function openSendDialog() {
  sendForm.value = { subject: '', body: '', level: 'warning', to_addrs: '' }
  showSendDialog.value = true
}

async function confirmSend() {
  if (!sendForm.value.subject) {
    ElMessage.warning('请输入邮件主题')
    return
  }
  if (!sendForm.value.body) {
    ElMessage.warning('请输入邮件内容')
    return
  }

  sendLoading.value = true
  try {
    const res = await request.post('/alert/send-email', sendForm.value)
    const data = res.data as { success?: boolean; message?: string }
    if (data.success) {
      ElMessage.success('告警邮件已发送')
      showSendDialog.value = false
      loadLogs()
    } else {
      ElMessage.error(data.message || '发送失败')
    }
  } catch {
    // 错误提示由拦截器处理
  } finally {
    sendLoading.value = false
  }
}

onMounted(loadLogs)
</script>

<template>
  <div class="alert-view">
    <!-- 工具栏 -->
    <el-card shadow="never" class="toolbar-card">
      <div class="toolbar">
        <div class="toolbar-left">
          <span class="page-title">告警邮件管理</span>
          <el-select
            v-model="statusFilter"
            placeholder="筛选状态"
            size="small"
            clearable
            style="width: 140px"
            @change="handleFilterChange"
          >
            <el-option label="全部" value="" />
            <el-option label="发送成功" value="success" />
            <el-option label="发送失败" value="failed" />
          </el-select>
        </div>
        <div class="toolbar-right">
          <el-button :icon="Refresh" size="small" @click="loadLogs">刷新</el-button>
          <el-button type="primary" size="small" @click="openSendDialog">
            发送告警邮件
          </el-button>
        </div>
      </div>
    </el-card>

    <!-- 邮件发送历史列表 -->
    <el-card shadow="never" class="table-card" v-loading="loading">
      <el-table :data="logs" stripe style="width: 100%" empty-text="暂无邮件发送记录">
        <el-table-column prop="id" label="ID" width="60" align="center" />
        <el-table-column prop="subject" label="主题" min-width="200" show-overflow-tooltip />
        <el-table-column label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="statusTag(row.status)" size="small" effect="plain">
              {{ statusLabel(row.status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column prop="to_addrs" label="收件人" min-width="200" show-overflow-tooltip />
        <el-table-column prop="attachment" label="附件" width="100" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.attachment" size="small" type="info">有附件</el-tag>
            <span v-else class="no-attachment">-</span>
          </template>
        </el-table-column>
        <el-table-column prop="error_msg" label="错误信息" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <span v-if="row.error_msg" style="color: #f56c6c">{{ row.error_msg }}</span>
            <span v-else>-</span>
          </template>
        </el-table-column>
        <el-table-column label="发送时间" width="180" align="center">
          <template #default="{ row }">
            {{ fmtTime(row.created_at) }}
          </template>
        </el-table-column>
      </el-table>

      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="page"
          v-model:page-size="pageSize"
          :total="total"
          layout="total, prev, pager, next"
          background
          small
          @current-change="handlePageChange"
        />
      </div>
    </el-card>

    <!-- 发送邮件对话框 -->
    <el-dialog
      v-model="showSendDialog"
      title="发送告警邮件"
      width="650px"
      :close-on-click-modal="false"
    >
      <el-form :model="sendForm" label-width="80px" label-position="top">
        <el-form-item label="邮件主题">
          <el-input
            v-model="sendForm.subject"
            placeholder="请输入邮件主题"
            maxlength="200"
            show-word-limit
          />
        </el-form-item>
        <el-form-item label="告警级别">
          <el-radio-group v-model="sendForm.level">
            <el-radio
              v-for="opt in levelOptions"
              :key="opt.value"
              :value="opt.value"
              :style="{ color: opt.color }"
            >
              {{ opt.label }}
            </el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="收件人（可选）">
          <el-input
            v-model="sendForm.to_addrs"
            placeholder="多个邮箱用逗号分隔，留空则使用默认配置"
          />
        </el-form-item>
        <el-form-item label="邮件内容">
          <el-input
            v-model="sendForm.body"
            type="textarea"
            :rows="8"
            placeholder="请输入邮件内容，支持 HTML 格式"
          />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showSendDialog = false">取消</el-button>
        <el-button type="primary" :loading="sendLoading" @click="confirmSend">
          发送
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped lang="scss">
.alert-view {
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
      gap: 16px;

      .page-title {
        font-size: 16px;
        font-weight: 600;
        color: #303133;
      }
    }

    .toolbar-right {
      display: flex;
      gap: 8px;
    }
  }
}

.table-card {
  .pagination-wrap {
    display: flex;
    justify-content: flex-end;
    margin-top: 16px;
  }
}

.no-attachment {
  color: #c0c4cc;
}
</style>