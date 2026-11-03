<template>
  <div class="page-container">
    <div class="page-header">
      <h1 class="page-title">定时任务管理</h1>
      <p class="page-subtitle">管理数据采集定时任务，查看采集记录与执行状态</p>
    </div>

    <PageTabs :model-value="activeTab" route-base="/schedule" :tabs="scheduleTabs" />

    <!-- 加载状态 -->
    <StateBlock v-if="loading" type="loading" text="数据加载中..." />

    <!-- 错误提示 -->
    <StateBlock v-if="error" type="error" :text="error" retry-text="重试" @retry="fetchData" />

    <!-- 采集统计卡片 -->
    <div class="overview-grid">
      <div class="overview-card card" v-for="s in statsCards" :key="s.label">
        <div class="overview-icon" :style="{ background: s.bg, color: s.color }">{{ s.icon }}</div>
        <div class="overview-info">
          <div class="overview-value" :style="{ color: s.color }">{{ s.value }}</div>
          <div class="overview-label">{{ s.label }}</div>
        </div>
      </div>
    </div>

    <!-- 定时任务控制 -->
    <div v-show="activeTab === 'tasks'" class="card">
      <div class="card-header">
        <h2 class="card-title">定时任务列表</h2>
        <div class="card-actions">
          <button class="refresh-btn" @click="fetchData" :disabled="loading">
            <span v-if="loading" class="btn-spinner"></span>
            刷新
          </button>
        </div>
      </div>
      <div class="task-grid">
        <div class="task-card" v-for="task in taskList" :key="task.id" :class="{ enabled: task.enabled }">
          <div class="task-header">
            <div class="task-icon" :style="{ background: task.iconBg, color: task.iconColor }">
              {{ task.icon }}
            </div>
            <div class="task-info">
              <h3 class="task-name">{{ task.name }}</h3>
              <p class="task-desc">{{ task.description }}</p>
            </div>
            <span class="task-status" :class="task.enabled ? 'running' : 'stopped'">
              {{ task.enabled ? '运行中' : '已停止' }}
            </span>
            <span v-if="task.inProgress" class="task-status executing">执行中</span>
          </div>

          <div class="task-meta">
            <div class="meta-item">
              <span class="meta-label">间隔</span>
              <span class="meta-value">{{ task.interval ? task.interval + ' 分钟' : '-' }}</span>
            </div>
            <div class="meta-item">
              <span class="meta-label">下次执行</span>
              <span class="meta-value">{{ formatTime(task.next_run) }}</span>
            </div>
          </div>

          <div class="task-actions">
            <button
              v-if="!task.enabled"
              class="btn btn-primary btn-sm"
              @click="enableTask(task)"
              :disabled="task.operating"
            >启用</button>
            <button
              v-else
              class="btn btn-warning btn-sm"
              @click="disableTask(task)"
              :disabled="task.operating"
            >停止</button>
            <button
              class="btn btn-sm"
              @click="runNow(task)"
              :disabled="task.operating"
            >{{ task.operating ? '执行中...' : '立即执行' }}</button>
            <button
              v-if="task.enabled"
              class="btn btn-sm"
              @click="openIntervalDialog(task)"
            >设置间隔</button>
          </div>
        </div>
      </div>
    </div>

    <!-- 系统运行日志 -->
    <div v-show="activeTab === 'runtime'" class="card">
      <div class="card-header">
        <h2 class="card-title">系统运行日志</h2>
        <div class="card-actions">
          <button class="refresh-btn" @click="fetchRuntimeLogs" :disabled="runtimeLogLoading">
            <span v-if="runtimeLogLoading" class="btn-spinner"></span>
            刷新
          </button>
          <button class="btn btn-sm btn-primary" @click="downloadRuntimeLog()" :disabled="runtimeLogDownloading">
            {{ runtimeLogDownloading ? '下载中...' : '下载当前日志' }}
          </button>
        </div>
      </div>
      <p class="runtime-log-hint">记录系统启动后的运行输出，默认展示最近 300 行。完整日志请下载。</p>
      <div class="runtime-log-meta" v-if="runtimeLogCurrent">
        <span>当前文件：<b>{{ runtimeLogCurrent }}</b></span>
        <span v-if="runtimeLogFiles.length">共 {{ runtimeLogFiles.length }} 个日志文件</span>
      </div>
      <div class="runtime-log-viewer">
        <pre v-if="runtimeLogContent">{{ runtimeLogContent }}</pre>
        <div v-else class="empty-row">暂无运行日志，请确认后端已启动</div>
      </div>
    </div>

    <!-- 采集日志 -->
    <div v-show="activeTab === 'logs'" class="card">
      <div class="card-header">
        <h2 class="card-title">采集记录</h2>
        <div class="card-actions">
          <button class="refresh-btn" @click="fetchLogs">刷新日志</button>
        </div>
      </div>

      <!-- 筛选器 -->
      <div class="filters">
        <div class="filter-item">
          <label>采集类别</label>
          <select v-model="filters.crawl_category" @change="onFilterChange">
            <option :value="null">全部</option>
            <option value="match">赛事采集</option>
            <option value="player">球员统计</option>
            <option value="squad">阵容采集</option>
            <option value="train">采集+训练</option>
            <option value="environment">气象环境</option>
            <option value="quality">质量告警</option>
            <option value="injury">伤病</option>
            <option value="odds">胜平负/让球</option>
            <option value="p0">P0补齐</option>
            <option value="standings">积分榜</option>
            <option value="scorers">射手榜</option>
            <option value="team">球队</option>
            <option value="match_player">逐场统计</option>
          </select>
        </div>
        <div class="filter-item">
          <label>采集类型</label>
          <select v-model="filters.crawl_type" @change="onFilterChange">
            <option :value="null">全部</option>
            <option value="scheduled">定时采集</option>
            <option value="manual">手动采集</option>
            <option value="initial">初始采集</option>
          </select>
        </div>
        <div class="filter-item">
          <label>状态</label>
          <select v-model="filters.status" @change="onFilterChange">
            <option :value="null">全部</option>
            <option value="success">成功</option>
            <option value="failed">失败</option>
          </select>
        </div>
        <div class="filter-item">
          <label>时间范围</label>
          <select v-model.number="filters.hours" @change="onFilterChange">
            <option :value="1">近1小时</option>
            <option :value="24">近24小时</option>
            <option :value="72">近3天</option>
            <option :value="168">近7天</option>
            <option :value="720">近30天</option>
            <option :value="2160">近90天</option>
            <option :value="4320">近180天</option>
            <option :value="8760">近一年</option>
            <option :value="0">全部</option>
          </select>
        </div>
        <button class="btn btn-sm" @click="resetFilters">重置</button>
      </div>

      <!-- 日志表格 -->
      <div class="table-wrapper">
        <table class="data-table">
          <thead>
            <tr>
              <th>采集时间</th>
              <th>类别</th>
              <th>类型</th>
              <th>新增</th>
              <th>更新</th>
              <th>耗时</th>
              <th>状态</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="log in logs" :key="log.id">
              <td>{{ formatDateTime(log.started_at) }}</td>
              <td>
                <span class="tag" :class="crawlCategoryTagClass(log.crawl_category)">
                  {{ crawlCategoryText(log.crawl_category) }}
                </span>
              </td>
              <td>
                <span class="tag" :class="crawlTypeTagClass(log.crawl_type)">
                  {{ crawlTypeText(log.crawl_type) }}
                </span>
              </td>
              <td>{{ log.saved_count }}</td>
              <td>{{ log.updated_count }}</td>
              <td>{{ log.duration_ms ? log.duration_ms + 'ms' : '-' }}</td>
              <td>
                <span class="tag" :class="log.status === 'success' ? 'tag-low' : 'tag-high'">
                  {{ log.status === 'success' ? '成功' : '失败' }}
                </span>
              </td>
              <td>
                <button class="link-btn" @click="viewLogDetail(log)">详情</button>
                <button class="link-btn link-danger" @click="deleteLog(log)">删除</button>
              </td>
            </tr>
            <tr v-if="logs.length === 0">
              <td colspan="8" class="empty-row">暂无采集记录</td>
            </tr>
          </tbody>
        </table>
      </div>

      <!-- 分页 -->
      <Pagination
        v-if="logsTotal > 0"
        :page="filters.page"
        :page-size="filters.page_size"
        :total="logsTotal"
        @change="changePage"
      />
    </div>

    <!-- 间隔设置弹窗 -->
    <BaseModal v-model="intervalDialogVisible" title="设置采集间隔" width="420px">
      <p class="modal-tip">当前任务：<b>{{ currentTask?.name }}</b></p>
      <div class="form-group">
        <label>采集间隔（分钟）</label>
        <input type="number" v-model.number="intervalValue" min="5" max="10080" />
        <span class="form-hint">最小5分钟，最大10080分钟（7天）；重点联赛训练建议 720（12小时）</span>
      </div>
      <template #footer>
        <button class="btn" @click="intervalDialogVisible = false">取消</button>
        <button class="btn btn-primary" @click="confirmInterval">确定</button>
      </template>
    </BaseModal>

    <!-- 日志详情弹窗 -->
    <BaseModal v-model="logDetailVisible" :title="`采集日志详情 #${logDetail?.id ?? ''}`" width="720px">
      <div class="detail-grid">
        <div class="detail-item">
          <span class="detail-label">采集类别</span>
          <span class="detail-value">{{ crawlCategoryText(logDetail.crawl_category) }}</span>
        </div>
        <div class="detail-item">
          <span class="detail-label">采集类型</span>
          <span class="detail-value">{{ crawlTypeText(logDetail.crawl_type) }}</span>
        </div>
        <div class="detail-item">
          <span class="detail-label">联赛</span>
          <span class="detail-value">{{ logDetail.league_name || logDetail.league_id || '-' }}</span>
        </div>
        <div class="detail-item">
          <span class="detail-label">状态</span>
          <span class="detail-value">
            <span class="tag" :class="logDetail.status === 'success' ? 'tag-low' : 'tag-high'">
              {{ logDetail.status === 'success' ? '成功' : '失败' }}
            </span>
          </span>
        </div>
        <div class="detail-item">
          <span class="detail-label">开始时间</span>
          <span class="detail-value">{{ formatDateTime(logDetail.started_at) }}</span>
        </div>
        <div class="detail-item">
          <span class="detail-label">结束时间</span>
          <span class="detail-value">{{ formatDateTime(logDetail.finished_at) }}</span>
        </div>
        <div class="detail-item">
          <span class="detail-label">耗时</span>
          <span class="detail-value">{{ logDetail.duration_ms ? logDetail.duration_ms + ' ms' : '-' }}</span>
        </div>
        <div class="detail-item">
          <span class="detail-label">发现数据</span>
          <span class="detail-value">{{ logDetail.found_count }} 条</span>
        </div>
        <div class="detail-item">
          <span class="detail-label">新增数据</span>
          <span class="detail-value">{{ logDetail.saved_count }} 条</span>
        </div>
        <div class="detail-item">
          <span class="detail-label">更新数据</span>
          <span class="detail-value">{{ logDetail.updated_count }} 条</span>
        </div>
      </div>
      <div v-if="logDetail.error_message" class="error-message">
        <div class="error-title">错误信息</div>
        <pre>{{ logDetail.error_message }}</pre>
      </div>
      <div v-if="logDetail.crawled_data" class="crawled-data">
        <div class="data-title">采集原始数据</div>
        <pre>{{ formatCrawledData(logDetail.crawled_data) }}</pre>
      </div>
      <template #footer>
        <button class="btn" @click="logDetail = null">关闭</button>
      </template>
    </BaseModal>

    <!-- 立即执行提示弹窗 -->
    <BaseModal
      v-model="runNowDialogVisible"
      :title="runNowStatus === 'running' ? '正在执行...' : (runNowStatus === 'success' ? '执行成功' : '执行失败')"
      :closable="runNowStatus !== 'running'"
      width="420px"
    >
      <div v-if="runNowStatus === 'running'" class="run-now-loading">
        <div class="run-now-spinner"></div>
        <p>正在执行 {{ runNowTaskName }}，请稍候...</p>
        <p class="run-now-hint">任务在后台执行，您可以关闭此弹窗继续操作</p>
      </div>
      <div v-else-if="runNowStatus === 'success'" class="run-now-success">
        <div class="run-now-icon">✅</div>
        <p>{{ runNowTaskName }} 已成功启动！</p>
        <p class="run-now-hint">任务正在后台执行，可在采集日志中查看结果</p>
      </div>
      <div v-else class="run-now-failed">
        <div class="run-now-icon">❌</div>
        <p>{{ runNowTaskName }} 执行失败</p>
        <p class="run-now-error">{{ runNowErrorMessage }}</p>
      </div>
      <template #footer>
        <button v-if="runNowStatus !== 'running'" class="btn btn-primary" @click="runNowDialogVisible = false">确定</button>
      </template>
    </BaseModal>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, reactive, watch } from 'vue'
import { useRoute } from 'vue-router'
import { scheduleApi } from '@/api'
import PageTabs from '@/components/common/PageTabs.vue'
import Pagination from '@/components/common/Pagination.vue'
import StateBlock from '@/components/common/StateBlock.vue'
import BaseModal from '@/components/common/BaseModal.vue'

const route = useRoute()
const SCHEDULE_TABS = new Set(['tasks', 'logs', 'runtime'])
const activeTab = computed(() => {
  const t = route.params.tab
  return SCHEDULE_TABS.has(t) ? t : 'tasks'
})
const loadedScheduleTabs = ref(new Set())
const scheduleTabs = [
  { key: 'tasks', label: '任务控制' },
  { key: 'logs', label: '采集记录' },
  { key: 'runtime', label: '运行日志' },
]

const loading = ref(false)
const error = ref(null)
const operating = ref(false)

const runNowDialogVisible = ref(false)
const runNowStatus = ref('running')
const runNowTaskName = ref('')
const runNowErrorMessage = ref('')

const schedulerStatus = ref({ scheduler_running: false, tasks: {} })
const logStats = ref({ total: 0, success: 0, failed: 0, success_rate: 0, by_category: [] })
const logs = ref([])
const logsTotal = ref(0)

const filters = reactive({
  crawl_category: null,
  crawl_type: null,
  status: null,
  hours: 24,
  page: 1,
  page_size: 15
})

const totalPages = computed(() => Math.max(1, Math.ceil(logsTotal.value / filters.page_size)))

const statsCards = computed(() => [
  { label: '调度器状态', value: schedulerStatus.value.scheduler_running ? '运行中' : '已停止', icon: '⚙️', color: schedulerStatus.value.scheduler_running ? 'var(--color-green)' : 'var(--color-red)', bg: schedulerStatus.value.scheduler_running ? 'rgba(var(--color-green-rgb), 0.12)' : 'rgba(var(--color-red-rgb), 0.12)' },
  { label: '活跃任务数', value: Object.keys(schedulerStatus.value.tasks || {}).length, icon: '📋', color: 'var(--color-blue)', bg: 'rgba(var(--color-blue-rgb), 0.12)' },
  {
    label: logStats.value.hours
      ? `近${logStats.value.hours}h采集次数`
      : '全部采集次数',
    value: logStats.value.total || 0,
    icon: '🔄',
    color: 'var(--color-gold)',
    bg: 'rgba(var(--color-gold-rgb), 0.12)',
  },
  { label: '采集成功率', value: (logStats.value.success_rate || 0) + '%', icon: '✅', color: logStats.value.success_rate >= 90 ? 'var(--color-green)' : 'var(--color-orange)', bg: 'rgba(var(--color-green-rgb), 0.12)' }
])

const CATEGORY_META = {
  match: { icon: '⚽', iconBg: 'rgba(var(--color-blue-rgb), 0.12)', iconColor: 'var(--color-blue)' },
  match_player: { icon: '📊', iconBg: 'rgba(var(--color-orange-rgb), 0.12)', iconColor: 'var(--color-orange)' },
  player: { icon: '🏃', iconBg: 'rgba(var(--color-green-rgb), 0.12)', iconColor: 'var(--color-green)' },
  squad: { icon: '📋', iconBg: 'rgba(var(--color-green-rgb), 0.12)', iconColor: 'var(--color-green)' },
  league: { icon: '🏆', iconBg: 'rgba(255, 180, 50, 0.12)', iconColor: 'var(--color-orange)' },
  team: { icon: '👕', iconBg: 'rgba(0, 180, 255, 0.12)', iconColor: 'var(--color-blue)' },
  media: { icon: '🖼️', iconBg: 'rgba(var(--color-blue-rgb), 0.12)', iconColor: 'var(--color-blue)' },
  train: { icon: '🧠', iconBg: 'rgba(0, 255, 200, 0.12)', iconColor: 'var(--color-green)' },
  standings: { icon: '📈', iconBg: 'rgba(var(--color-blue-rgb), 0.12)', iconColor: 'var(--color-blue)' },
  scorers: { icon: '🎯', iconBg: 'rgba(var(--color-red-rgb), 0.12)', iconColor: 'var(--color-red)' },
  environment: { icon: '🌤️', iconBg: 'rgba(var(--color-gold-rgb), 0.12)', iconColor: 'var(--color-gold)' },
  quality: { icon: '⚑', iconBg: 'rgba(var(--color-red-rgb), 0.12)', iconColor: 'var(--color-red)' },
  injury: { icon: '🩹', iconBg: 'rgba(var(--color-orange-rgb), 0.12)', iconColor: 'var(--color-orange)' },
  odds: { icon: '📋', iconBg: 'rgba(var(--color-gold-rgb), 0.12)', iconColor: 'var(--color-gold)' },
  p0: { icon: '🚀', iconBg: 'rgba(var(--color-blue-rgb), 0.12)', iconColor: 'var(--color-blue)' },
}

const taskList = computed(() => {
  const tasks = schedulerStatus.value.tasks || {}
  const result = []
  for (const [id, info] of Object.entries(tasks)) {
    const meta = CATEGORY_META[info.category] || { icon: '📡', iconBg: 'rgba(139, 92, 246, 0.12)', iconColor: 'var(--color-purple)' }
    result.push({
      id,
      name: info.name || id,
      description: info.description || '',
      icon: meta.icon,
      iconBg: meta.iconBg,
      iconColor: meta.iconColor,
      enabled: info.is_enabled || false,
      inProgress: !!info.in_progress,
      interval: info.interval,
      next_run: info.next_run,
      category: info.category,
      registered: info.registered !== false,
    })
  }
  return result.sort((a, b) => a.name.localeCompare(b.name, 'zh-CN'))
})

// 间隔设置弹窗
const intervalDialogVisible = ref(false)
const currentTask = ref(null)
const intervalValue = ref(60)

// 日志详情
const logDetail = ref(null)
const logDetailVisible = computed({
  get: () => !!logDetail.value,
  set: (v) => { if (!v) logDetail.value = null },
})

// 系统运行日志
const runtimeLogLoading = ref(false)
const runtimeLogDownloading = ref(false)
const runtimeLogCurrent = ref('')
const runtimeLogFiles = ref([])
const runtimeLogContent = ref('')

function formatTime(dateStr) {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  if (isNaN(d.getTime())) return '-'
  return `${d.getMonth() + 1}-${d.getDate()} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function formatDateTime(dateStr) {
  if (!dateStr) return '-'
  const d = new Date(dateStr)
  if (isNaN(d.getTime())) return String(dateStr)
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
}

function crawlCategoryText(c) {
  return {
    match: '赛事', player: '球员', squad: '阵容', train: '训练', match_player: '逐场',
    league: '联赛', team: '球队', media: '媒体',
    standings: '积分榜', scorers: '射手榜', environment: '气象', quality: '质量', injury: '伤病', odds: '胜平负/让球', p0: 'P0补齐',
  }[c] || c || '-'
}

function crawlCategoryTagClass(c) {
  return { match: 'tag-info', train: 'tag-low', player: 'tag-mid' }[c] || 'tag-mid'
}

function crawlTypeText(t) {
  return { scheduled: '定时', manual: '手动', initial: '初始' }[t] || t
}

function crawlTypeTagClass(t) {
  return { scheduled: 'tag-info', manual: 'tag-low', initial: 'tag-mid' }[t] || 'tag-mid'
}

function formatCrawledData(data) {
  try {
    const obj = typeof data === 'string' ? JSON.parse(data) : data
    return JSON.stringify(obj, null, 2)
  } catch (e) {
    return String(data)
  }
}

async function loadScheduleTab(tab) {
  if (!loadedScheduleTabs.value.has(tab)) {
    loadedScheduleTabs.value.add(tab)
    if (tab === 'logs') await fetchLogs()
    else if (tab === 'runtime') await fetchRuntimeLogs()
  }
}

watch(activeTab, (tab) => loadScheduleTab(tab), { immediate: true })

async function fetchData() {
  loading.value = true
  error.value = null
  try {
    await Promise.all([fetchStatus(), fetchLogStats()])
    loadedScheduleTabs.value.delete(activeTab.value)
    await loadScheduleTab(activeTab.value)
  } catch (e) {
    error.value = e?.message || '数据加载失败'
  } finally {
    loading.value = false
  }
}

async function fetchStatus() {
  const res = await scheduleApi.getStatus()
  schedulerStatus.value = res
}

async function fetchLogStats() {
  const res = await scheduleApi.getLogStats(filters.hours)
  logStats.value = res
}

async function fetchLogs() {
  const res = await scheduleApi.getLogs({ ...filters })
  logs.value = res.logs || []
  logsTotal.value = res.total || 0
}

function onFilterChange() {
  filters.page = 1
  fetchLogs()
  fetchLogStats()
}

function resetFilters() {
  filters.crawl_category = null
  filters.crawl_type = null
  filters.status = null
  filters.hours = 24
  filters.page = 1
  fetchLogs()
}

function changePage(p) {
  if (p < 1 || p > totalPages.value) return
  filters.page = p
  fetchLogs()
}

async function enableTask(task) {
  task.operating = true
  try {
    if (task.id === 'match_crawl') {
      await scheduleApi.enableMatch(60)
    } else if (task.id === 'player_stats_crawl') {
      await scheduleApi.enablePlayerStats(360)
    } else if (task.id === 'match_player_stats_crawl') {
      await scheduleApi.enableMatchPlayerStats(360)
    } else if (task.id === 'league_crawl') {
      await scheduleApi.enableLeague(1440)
    } else if (task.id === 'team_crawl') {
      await scheduleApi.enableTeam(1440)
    } else if (task.id === 'squad_crawl') {
      await scheduleApi.enableSquad(1440)
    } else if (task.id === 'image_crawl') {
      await scheduleApi.enableImage(720)
    } else if (task.id === 'priority_train') {
      await scheduleApi.enablePriorityTrain(720)
    } else if (task.id === 'standings_crawl') {
      await scheduleApi.enableStandingsSchedule(360)
    } else if (task.id === 'scorers_crawl') {
      await scheduleApi.enableScorersSchedule(360)
    } else if (task.id === 'environment_crawl') {
      await scheduleApi.enableEnvironmentSchedule(360)
    } else if (task.id === 'quality_alert_check') {
      await scheduleApi.enableQualityAlertsSchedule(360)
    } else if (task.id === 'live500_crawl') {
      await scheduleApi.enableLive500(30)
    } else if (task.id === 'jingcai_odds_crawl') {
      await scheduleApi.enableJingcaiOdds(30)
    } else if (task.id === 'jingcai_bf_crawl') {
      await scheduleApi.enableJingcaiBf(30)
    } else if (task.id === 'jingcai_bf_history_crawl') {
      await scheduleApi.enableJingcaiBfHistory(360)
    } else if (task.id === 'jingcai_score_crawl') {
      await scheduleApi.enableJingcaiScores(60)
    } else if (task.id === 'live_jingcai_crawl') {
      await scheduleApi.enableLiveJingcai(30)
    } else if (task.id === 'injury_crawl') {
      await scheduleApi.enableInjuryCrawl(120)
    }
    await fetchStatus()
  } catch (e) {
    error.value = e?.message || '启用任务失败'
  } finally {
    task.operating = false
  }
}

async function disableTask(task) {
  task.operating = true
  try {
    if (task.id === 'match_crawl') {
      await scheduleApi.disableMatch()
    } else if (task.id === 'player_stats_crawl') {
      await scheduleApi.disablePlayerStats()
    } else if (task.id === 'match_player_stats_crawl') {
      await scheduleApi.disableMatchPlayerStats()
    } else if (task.id === 'league_crawl') {
      await scheduleApi.disableLeague()
    } else if (task.id === 'team_crawl') {
      await scheduleApi.disableTeam()
    } else if (task.id === 'squad_crawl') {
      await scheduleApi.disableSquad()
    } else if (task.id === 'image_crawl') {
      await scheduleApi.disableImage()
    } else if (task.id === 'priority_train') {
      await scheduleApi.disablePriorityTrain()
    } else if (task.id === 'standings_crawl') {
      await scheduleApi.disableStandingsSchedule()
    } else if (task.id === 'scorers_crawl') {
      await scheduleApi.disableScorersSchedule()
    } else if (task.id === 'environment_crawl') {
      await scheduleApi.disableEnvironmentSchedule()
    } else if (task.id === 'quality_alert_check') {
      await scheduleApi.disableQualityAlertsSchedule()
    } else if (task.id === 'live500_crawl') {
      await scheduleApi.disableLive500()
    } else if (task.id === 'jingcai_odds_crawl') {
      await scheduleApi.disableJingcaiOdds()
    } else if (task.id === 'jingcai_bf_crawl') {
      await scheduleApi.disableJingcaiBf()
    } else if (task.id === 'jingcai_bf_history_crawl') {
      await scheduleApi.disableJingcaiBfHistory()
    } else if (task.id === 'jingcai_score_crawl') {
      await scheduleApi.disableJingcaiScores()
    } else if (task.id === 'live_jingcai_crawl') {
      await scheduleApi.disableLiveJingcai()
    } else if (task.id === 'injury_crawl') {
      await scheduleApi.disableInjuryCrawl()
    }
    await fetchStatus()
  } catch (e) {
    error.value = e?.message || '停止任务失败'
  } finally {
    task.operating = false
  }
}

async function runNow(task) {
  task.operating = true
  runNowTaskName.value = task.name
  runNowStatus.value = 'running'
  runNowDialogVisible.value = true
  runNowErrorMessage.value = ''
  try {
    if (task.id === 'match_crawl') {
      await scheduleApi.runMatchNow()
    } else if (task.id === 'player_stats_crawl') {
      await scheduleApi.runPlayerStatsNow()
    } else if (task.id === 'match_player_stats_crawl') {
      await scheduleApi.runMatchPlayerStatsNow()
    } else if (task.id === 'league_crawl') {
      await scheduleApi.runLeagueNow()
    } else if (task.id === 'team_crawl') {
      await scheduleApi.runTeamNow()
    } else if (task.id === 'squad_crawl') {
      await scheduleApi.runSquadNow()
    } else if (task.id === 'image_crawl') {
      await scheduleApi.runImageNow()
    } else if (task.id === 'priority_train') {
      await scheduleApi.runPriorityTrainNow()
    } else if (task.id === 'standings_crawl') {
      await scheduleApi.runStandingsScheduleNow()
    } else if (task.id === 'scorers_crawl') {
      await scheduleApi.runScorersScheduleNow()
    } else if (task.id === 'environment_crawl') {
      await scheduleApi.runEnvironmentScheduleNow()
    } else if (task.id === 'quality_alert_check') {
      await scheduleApi.runQualityAlertsScheduleNow()
    } else if (task.id === 'live500_crawl') {
      await scheduleApi.runLive500Now()
    } else if (task.id === 'jingcai_odds_crawl') {
      await scheduleApi.runJingcaiOddsNow()
    } else if (task.id === 'jingcai_bf_crawl') {
      await scheduleApi.runJingcaiBfNow()
    } else if (task.id === 'jingcai_bf_history_crawl') {
      await scheduleApi.runJingcaiBfHistoryNow()
    } else if (task.id === 'jingcai_score_crawl') {
      await scheduleApi.runJingcaiScoresNow()
    } else if (task.id === 'live_jingcai_crawl') {
      await scheduleApi.runLiveJingcaiNow()
    } else if (task.id === 'injury_crawl') {
      await scheduleApi.runInjuryCrawlNow()
    }
    runNowStatus.value = 'success'
    await fetchLogStats()
    await fetchLogs()
  } catch (e) {
    runNowStatus.value = 'failed'
    runNowErrorMessage.value = e?.message || '立即执行失败'
    error.value = e?.message || '立即执行失败'
  } finally {
    task.operating = false
  }
}

function openIntervalDialog(task) {
  currentTask.value = task
  intervalValue.value = task.interval || 60
  intervalDialogVisible.value = true
}

async function confirmInterval() {
  if (!currentTask.value) return
  if (intervalValue.value < 5 || intervalValue.value > 10080) {
    error.value = '间隔时间必须在 5-10080 分钟之间'
    return
  }
  try {
    if (currentTask.value.id === 'match_crawl') {
      await scheduleApi.enableMatch(intervalValue.value)
    } else if (currentTask.value.id === 'player_stats_crawl') {
      await scheduleApi.enablePlayerStats(intervalValue.value)
    } else if (currentTask.value.id === 'match_player_stats_crawl') {
      await scheduleApi.enableMatchPlayerStats(intervalValue.value)
    } else if (currentTask.value.id === 'league_crawl') {
      await scheduleApi.enableLeague(intervalValue.value)
    } else if (currentTask.value.id === 'team_crawl') {
      await scheduleApi.enableTeam(intervalValue.value)
    } else if (currentTask.value.id === 'squad_crawl') {
      await scheduleApi.enableSquad(intervalValue.value)
    } else if (currentTask.value.id === 'image_crawl') {
      await scheduleApi.enableImage(intervalValue.value)
    } else if (currentTask.value.id === 'priority_train') {
      await scheduleApi.enablePriorityTrain(intervalValue.value)
    } else if (currentTask.value.id === 'standings_crawl') {
      await scheduleApi.enableStandingsSchedule(intervalValue.value)
    } else if (currentTask.value.id === 'scorers_crawl') {
      await scheduleApi.enableScorersSchedule(intervalValue.value)
    } else if (currentTask.value.id === 'environment_crawl') {
      await scheduleApi.enableEnvironmentSchedule(intervalValue.value)
    } else if (currentTask.value.id === 'quality_alert_check') {
      await scheduleApi.enableQualityAlertsSchedule(intervalValue.value)
    } else if (currentTask.value.id === 'live500_crawl') {
      await scheduleApi.enableLive500(intervalValue.value)
    } else if (currentTask.value.id === 'jingcai_odds_crawl') {
      await scheduleApi.enableJingcaiOdds(intervalValue.value)
    } else if (currentTask.value.id === 'jingcai_bf_crawl') {
      await scheduleApi.enableJingcaiBf(intervalValue.value)
    } else if (currentTask.value.id === 'jingcai_bf_history_crawl') {
      await scheduleApi.enableJingcaiBfHistory(intervalValue.value)
    } else if (currentTask.value.id === 'jingcai_score_crawl') {
      await scheduleApi.enableJingcaiScores(intervalValue.value)
    } else if (currentTask.value.id === 'live_jingcai_crawl') {
      await scheduleApi.enableLiveJingcai(intervalValue.value)
    } else if (currentTask.value.id === 'injury_crawl') {
      await scheduleApi.enableInjuryCrawl(intervalValue.value)
    }
    intervalDialogVisible.value = false
    await fetchStatus()
  } catch (e) {
    error.value = e?.message || '设置间隔失败'
  }
}

async function viewLogDetail(log) {
  try {
    const detail = await scheduleApi.getLogById(log.id)
    logDetail.value = detail
  } catch (e) {
    error.value = e?.message || '获取详情失败'
  }
}

async function deleteLog(log) {
  if (!confirm(`确认删除日志 #${log.id} 吗？`)) return
  try {
    await scheduleApi.deleteLog(log.id)
    await fetchLogs()
    await fetchLogStats()
  } catch (e) {
    error.value = e?.message || '删除失败'
  }
}

async function fetchRuntimeLogs() {
  runtimeLogLoading.value = true
  try {
    const res = await scheduleApi.getRuntimeLogs()
    runtimeLogCurrent.value = res.current || ''
    runtimeLogFiles.value = res.logs || []
    if (res.current) {
      try {
        const tail = await scheduleApi.getRuntimeLogTail({
          name: res.current,
          lines: 300,
        })
        runtimeLogContent.value = tail.content || ''
      } catch {
        runtimeLogContent.value = ''
      }
    } else {
      runtimeLogContent.value = ''
    }
  } catch (e) {
    runtimeLogContent.value = ''
    error.value = e?.message || '加载运行日志失败'
  } finally {
    runtimeLogLoading.value = false
  }
}

function triggerBlobDownload(blob, filename) {
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  window.URL.revokeObjectURL(url)
}

async function downloadRuntimeLog(name = null) {
  runtimeLogDownloading.value = true
  try {
    const blob = await scheduleApi.downloadRuntimeLog(name || runtimeLogCurrent.value || null)
    const filename = name || runtimeLogCurrent.value || `app_${new Date().toISOString().slice(0, 10).replace(/-/g, '')}.log`
    triggerBlobDownload(blob, filename)
  } catch (e) {
    error.value = e?.message || '下载运行日志失败'
  } finally {
    runtimeLogDownloading.value = false
  }
}

onMounted(() => {
  fetchData()
})
</script>

<style scoped>
.page-container {
  height: 100%;
  overflow-y: auto;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.page-header { margin-bottom: 4px; }
.page-title { font-size: 24px; font-weight: 700; color: var(--text-primary); margin-bottom: 6px; }
.page-subtitle { font-size: 13px; color: var(--text-muted); }

.overview-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}
.overview-card { display: flex; align-items: center; gap: 14px; }
.overview-icon {
  width: 48px; height: 48px; border-radius: var(--radius-md);
  display: flex; align-items: center; justify-content: center;
  font-size: 22px; flex-shrink: 0;
}
.overview-info { display: flex; flex-direction: column; }
.overview-value { font-size: 22px; font-weight: 700; line-height: 1.2; }
.overview-label { font-size: 12px; color: var(--text-muted); margin-top: 4px; }

.card-header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 16px;
}
.card-title { font-size: 16px; font-weight: 700; color: var(--text-primary); }
.card-actions { display: flex; align-items: center; gap: 12px; }

.refresh-btn {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 14px; border-radius: var(--radius-sm);
  border: 1px solid var(--border-color); background: transparent;
  color: var(--text-secondary); font-size: 13px; cursor: pointer;
  transition: var(--transition);
}
.refresh-btn:hover:not(:disabled) {
  border-color: var(--color-blue); color: var(--color-blue);
}
.refresh-btn:disabled { opacity: 0.5; cursor: not-allowed; }
.btn-spinner {
  width: 14px; height: 14px;
  border: 2px solid rgba(var(--color-blue-rgb), 0.3);
  border-top-color: var(--color-blue);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

/* 任务卡片 */
.task-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 16px;
}
.task-card {
  padding: 18px;
  background: rgba(26, 38, 65, 0.6);
  border-radius: var(--radius-md);
  border: 1px solid var(--border-color);
  transition: var(--transition);
}
.task-card:hover { border-color: rgba(var(--color-blue-rgb), 0.3); }
.task-card.enabled { border-color: rgba(var(--color-green-rgb), 0.2); }
.task-header { display: flex; align-items: center; gap: 12px; margin-bottom: 14px; }
.task-icon {
  width: 44px; height: 44px; border-radius: var(--radius-sm);
  display: flex; align-items: center; justify-content: center;
  font-size: 20px; flex-shrink: 0;
}
.task-info { flex: 1; }
.task-name { font-size: 15px; font-weight: 700; color: var(--text-primary); margin: 0 0 4px 0; }
.task-desc { font-size: 12px; color: var(--text-muted); margin: 0; line-height: 1.4; }
.task-status {
  font-size: 11px; padding: 3px 10px; border-radius: 4px; font-weight: 600;
}
.task-status.running { background: rgba(var(--color-green-rgb), 0.15); color: var(--color-green); }
.task-status.stopped { background: rgba(var(--color-red-rgb), 0.15); color: var(--color-red); }
.task-status.executing { background: rgba(255, 180, 50, 0.18); color: var(--color-orange); }

.task-meta {
  display: flex; gap: 24px;
  padding: 10px 0; margin-bottom: 12px;
  border-top: 1px dashed var(--border-color);
  border-bottom: 1px dashed var(--border-color);
}
.meta-item { display: flex; flex-direction: column; gap: 2px; }
.meta-label { font-size: 11px; color: var(--text-muted); }
.meta-value { font-size: 13px; font-weight: 600; color: var(--text-primary); }

.task-actions { display: flex; gap: 8px; flex-wrap: wrap; }
.btn-warning {
  background: linear-gradient(135deg, #cc6600, #994400);
  border-color: #cc6600; color: #fff;
}
.btn-warning:hover { background: linear-gradient(135deg, #dd7700, #aa5500); color: #fff; }

/* 筛选器 */
.filters {
  display: flex; flex-wrap: wrap; gap: 12px; align-items: flex-end;
  margin-bottom: 16px; padding: 14px;
  background: rgba(26, 38, 65, 0.4); border-radius: var(--radius-sm);
}
.filter-item { display: flex; flex-direction: column; gap: 4px; }
.filter-item label { font-size: 11px; color: var(--text-muted); }
.filter-item select {
  padding: 6px 10px; border-radius: var(--radius-sm);
  border: 1px solid var(--border-color); background: var(--bg-secondary);
  color: var(--text-primary); font-size: 13px; min-width: 120px;
  cursor: pointer;
}
.filter-item select:focus { outline: none; border-color: var(--color-blue); }

/* 表格 */
.table-wrapper { overflow-x: auto; }
.data-table {
  width: 100%; border-collapse: collapse;
  font-size: 13px;
}
.data-table th, .data-table td {
  padding: 10px 12px; text-align: left;
  border-bottom: 1px solid var(--border-color);
}
.data-table th {
  background: var(--bg-secondary); color: var(--text-secondary);
  font-weight: 600; font-size: 12px;
  position: sticky; top: 0; z-index: 1;
}
.data-table tbody tr:hover { background: var(--bg-hover); }
.empty-row { text-align: center; color: var(--text-muted); padding: 24px 0 !important; }

.link-btn {
  background: none; border: none; color: var(--color-blue);
  cursor: pointer; font-size: 12px; padding: 2px 6px;
  margin-right: 4px; transition: var(--transition);
}
.link-btn:hover { text-decoration: underline; }
.link-danger { color: var(--color-red); }

/* 状态提示 */
@keyframes spin { to { transform: rotate(360deg); } }

/* 弹窗内容 */
.modal-tip { font-size: 13px; color: var(--text-secondary); margin: 0 0 16px 0; }
.form-group { display: flex; flex-direction: column; gap: 6px; }
.form-group label { font-size: 13px; color: var(--text-secondary); }
.form-group input {
  padding: 8px 12px; border-radius: var(--radius-sm);
  border: 1px solid var(--border-color); background: var(--bg-secondary);
  color: var(--text-primary); font-size: 14px;
}
.form-group input:focus { outline: none; border-color: var(--color-blue); }
.form-hint { font-size: 11px; color: var(--text-muted); }

.detail-grid {
  display: grid; grid-template-columns: repeat(2, 1fr);
  gap: 12px 24px; margin-bottom: 16px;
}
.detail-item { display: flex; flex-direction: column; gap: 4px; }
.detail-label { font-size: 11px; color: var(--text-muted); }
.detail-value { font-size: 14px; color: var(--text-primary); font-weight: 500; }

.runtime-log-hint {
  font-size: 12px;
  color: var(--text-muted);
  margin: 0 0 12px 0;
}
.runtime-log-hint code {
  font-size: 11px;
  color: var(--text-secondary);
}
.runtime-log-meta {
  display: flex;
  gap: 20px;
  font-size: 12px;
  color: var(--text-secondary);
  margin-bottom: 12px;
}
.runtime-log-viewer {
  background: rgba(10, 16, 28, 0.85);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  max-height: 360px;
  overflow: auto;
}
.runtime-log-viewer pre {
  margin: 0;
  padding: 14px;
  font-family: 'Consolas', monospace;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-secondary);
  white-space: pre-wrap;
  word-break: break-all;
}

.error-message, .crawled-data {
  margin-top: 16px; padding: 12px;
  background: rgba(var(--color-red-rgb), 0.05);
  border: 1px solid rgba(var(--color-red-rgb), 0.2);
  border-radius: var(--radius-sm);
}
.crawled-data {
  background: rgba(var(--color-blue-rgb), 0.05);
  border-color: rgba(var(--color-blue-rgb), 0.2);
}
.error-title, .data-title {
  font-size: 12px; color: var(--text-muted);
  margin-bottom: 8px; font-weight: 600;
}
.error-message pre, .crawled-data pre {
  font-family: 'Consolas', monospace; font-size: 12px;
  color: var(--text-secondary); white-space: pre-wrap;
  word-break: break-all; max-height: 240px; overflow-y: auto;
}

.run-now-loading, .run-now-success, .run-now-failed {
  display: flex; flex-direction: column; align-items: center;
  gap: 12px; padding: 20px 0;
}

.run-now-spinner {
  width: 40px; height: 40px;
  border: 4px solid rgba(var(--color-blue-rgb), 0.2);
  border-top-color: var(--color-blue);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

.run-now-icon {
  font-size: 48px;
}

.run-now-hint {
  font-size: 12px; color: var(--text-muted); margin-top: 4px;
}

.run-now-error {
  font-size: 13px; color: var(--color-red);
  word-break: break-all; text-align: center;
}
</style>
