/**
 * 招聘数据采集与可视化系统 · 前端逻辑
 * ============================================================================
 * 功能：
 *   1. 加载统计数据 → 渲染 KPI 卡片 + 6 个 ECharts 图表
 *   2. 加载职位列表 → 渲染可筛选/排序/分页的表格
 *   3. 爬虫控制 → 启动/停止/状态轮询/SSE 实时日志
 *   4. 图表联动 → 点击图表元素筛选表格
 *   5. 数据导出
 */

// ============================================================================
//  Global State
// ============================================================================
const state = {
  page: 1,
  pageSize: 20,
  totalPages: 1,
  sortBy: '',
  sortOrder: 'asc',
  spiderRunning: false,
  logLines: [],
  charts: {},       // ECharts instances
};

// ============================================================================
//  Initialization
// ============================================================================
document.addEventListener('DOMContentLoaded', () => {
  initCharts();
  loadStats();
  loadJobs();
  window.addEventListener('resize', resizeCharts);
});

// ============================================================================
//  ECharts Init & Resize
// ============================================================================
function initCharts() {
  const ids = ['chart-salary', 'chart-city', 'chart-industry', 'chart-education', 'chart-experience', 'chart-time'];
  ids.forEach(id => {
    const dom = document.getElementById(id);
    if (dom && !state.charts[id]) {
      state.charts[id] = echarts.init(dom);
    }
  });
}

function resizeCharts() {
  Object.values(state.charts).forEach(c => c && c.resize());
}

// ---- Common chart option builder ----
function baseOption() {
  return {
    backgroundColor: 'transparent',
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 10, right: 30, top: 20, bottom: 24, containLabel: true },
  };
}

// ============================================================================
//  API: Load Stats → Render KPI + Charts
// ============================================================================
async function loadStats() {
  try {
    const res = await fetch('/api/stats');
    const data = await res.json();
    renderKPIs(data.overview);
    renderSalaryChart(data.salary_stats);
    renderCityChart(data.city_stats);
    renderIndustryChart(data.industry_stats);
    renderEducationChart(data.education_stats);
    renderExperienceChart(data.experience_stats);
    renderTimeChart(data.publish_time_trend);
  } catch (err) {
    console.error('Stats loading failed:', err);
  }
}

// ---- KPI Cards ----
function renderKPIs(ov) {
  if (!ov) return;
  document.getElementById('kpi-jobs').textContent = ov.total_jobs || 0;
  document.getElementById('kpi-companies').textContent = ov.total_companies || 0;
  document.getElementById('kpi-cities').textContent = ov.total_cities || 0;

  const salMin = ov.avg_salary_min || 0;
  const salMax = ov.avg_salary_max || 0;
  if (salMin && salMax) {
    document.getElementById('kpi-salary').textContent = `${salMin}K-${salMax}K`;
  } else {
    document.getElementById('kpi-salary').textContent = '--';
  }

  document.getElementById('kpi-time').textContent = ov.data_time || '--';
}

// ---- Salary Distribution (Bar) ----
function renderSalaryChart(data) {
  if (!data || data.length === 0) return;
  const chart = state.charts['chart-salary'];
  if (!chart) return;
  chart.setOption({
    ...baseOption(),
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: data.map(d => d.name), axisLabel: { color: '#8fa3b8', fontSize: 11 } },
    yAxis: { type: 'value', name: '职位数', axisLabel: { color: '#8fa3b8' }, splitLine: { lineStyle: { color: '#2a3f55', type: 'dashed' } } },
    series: [{
      type: 'bar', data: data.map(d => d.value),
      itemStyle: { color: '#3b82f6', borderRadius: [4, 4, 0, 0] },
      barWidth: '55%',
    }],
  });
  chart.off('click');
  chart.on('click', (params) => {
    // Click salary bar → no direct filter, but could highlight
  });
}

// ---- City Distribution (Horizontal Bar) ----
function renderCityChart(data) {
  if (!data || data.length === 0) return;
  const chart = state.charts['chart-city'];
  if (!chart) return;
  const names = data.map(d => d.name).reverse();
  const vals = data.map(d => d.value).reverse();
  chart.setOption({
    ...baseOption(),
    tooltip: { trigger: 'axis', axisPointer: { type: 'shadow' } },
    grid: { left: 70, right: 30, top: 10, bottom: 20 },
    xAxis: { type: 'value', axisLabel: { color: '#8fa3b8' }, splitLine: { lineStyle: { color: '#2a3f55', type: 'dashed' } } },
    yAxis: { type: 'category', data: names, axisLabel: { color: '#8fa3b8', fontSize: 11 } },
    series: [{
      type: 'bar', data: vals,
      itemStyle: { color: '#10b981', borderRadius: [0, 4, 4, 0] },
      barWidth: '60%',
    }],
  });
  chart.off('click');
  chart.on('click', (params) => {
    document.getElementById('table-city-filter').value = params.name;
    loadJobs(1);
  });
}

// ---- Industry Distribution (Pie) ----
function renderIndustryChart(data) {
  if (!data || data.length === 0) return;
  const chart = state.charts['chart-industry'];
  if (!chart) return;
  chart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    series: [{
      type: 'pie', radius: ['40%', '70%'], center: ['50%', '55%'],
      data: data,
      label: { color: '#8fa3b8', fontSize: 11 },
      emphasis: { label: { fontSize: 16, fontWeight: 'bold' } },
      itemStyle: { borderRadius: 4, borderColor: '#1e3043', borderWidth: 2 },
    }],
    color: ['#3b82f6', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#ec4899', '#06b6d4', '#f97316', '#84cc16', '#64748b'],
  });
  chart.off('click');
  chart.on('click', (params) => {
    document.getElementById('table-industry-filter').value = params.name;
    loadJobs(1);
  });
}

// ---- Education Distribution (Ring Pie) ----
function renderEducationChart(data) {
  if (!data || data.length === 0) return;
  const chart = state.charts['chart-education'];
  if (!chart) return;
  chart.setOption({
    backgroundColor: 'transparent',
    tooltip: { trigger: 'item', formatter: '{b}: {c} ({d}%)' },
    series: [{
      type: 'pie', radius: ['45%', '72%'], center: ['50%', '55%'],
      data: data,
      label: { color: '#8fa3b8', fontSize: 11 },
      emphasis: { label: { fontSize: 16, fontWeight: 'bold' } },
      itemStyle: { borderRadius: 4, borderColor: '#1e3043', borderWidth: 2 },
    }],
    color: ['#8b5cf6', '#3b82f6', '#06b6d4', '#10b981', '#f59e0b', '#ec4899'],
  });
  chart.off('click');
  chart.on('click', (params) => {
    document.getElementById('table-edu-filter').value = params.name;
    loadJobs(1);
  });
}

// ---- Experience Distribution (Bar) ----
function renderExperienceChart(data) {
  if (!data || data.length === 0) return;
  const chart = state.charts['chart-experience'];
  if (!chart) return;
  chart.setOption({
    ...baseOption(),
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: data.map(d => d.name), axisLabel: { color: '#8fa3b8', fontSize: 10, rotate: 20 } },
    yAxis: { type: 'value', name: '职位数', axisLabel: { color: '#8fa3b8' }, splitLine: { lineStyle: { color: '#2a3f55', type: 'dashed' } } },
    series: [{
      type: 'bar', data: data.map(d => d.value),
      itemStyle: { color: '#f59e0b', borderRadius: [4, 4, 0, 0] },
      barWidth: '50%',
    }],
  });
}

// ---- Publish Time Trend (Line) ----
function renderTimeChart(data) {
  if (!data || data.length === 0) return;
  const chart = state.charts['chart-time'];
  if (!chart) return;
  chart.setOption({
    ...baseOption(),
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: data.map(d => d.name), axisLabel: { color: '#8fa3b8', fontSize: 11, rotate: 30 } },
    yAxis: { type: 'value', name: '职位数', axisLabel: { color: '#8fa3b8' }, splitLine: { lineStyle: { color: '#2a3f55', type: 'dashed' } } },
    series: [{
      type: 'line', data: data.map(d => d.value),
      smooth: true, symbol: 'circle', symbolSize: 6,
      lineStyle: { color: '#06b6d4', width: 2.5 },
      itemStyle: { color: '#06b6d4' },
      areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
        { offset: 0, color: 'rgba(6,182,212,0.3)' },
        { offset: 1, color: 'rgba(6,182,212,0.02)' },
      ]) },
    }],
    grid: { left: 10, right: 30, top: 10, bottom: 50, containLabel: true },
  });
}

// ============================================================================
//  API: Load Jobs → Render Table
// ============================================================================
async function loadJobs(pageOverride) {
  if (pageOverride !== undefined) state.page = pageOverride;

  const params = new URLSearchParams({
    page: state.page,
    page_size: state.pageSize,
    search: document.getElementById('table-search').value.trim(),
    city: document.getElementById('table-city-filter').value,
    education: document.getElementById('table-edu-filter').value,
    industry: document.getElementById('table-industry-filter').value,
    experience: document.getElementById('table-exp-filter').value,
    sort_by: state.sortBy,
    sort_order: state.sortOrder,
  });

  try {
    const res = await fetch(`/api/jobs?${params}`);
    const data = await res.json();
    renderTable(data);
    updateFilters(data.filters);
  } catch (err) {
    console.error('Jobs loading failed:', err);
  }
}

function renderTable(data) {
  const tbody = document.getElementById('jobs-tbody');
  state.totalPages = data.total_pages;
  state.page = data.page;

  if (!data.data || data.data.length === 0) {
    tbody.innerHTML = '<tr><td colspan="9" class="loading-row">暂无数据</td></tr>';
  } else {
    tbody.innerHTML = data.data.map((job, idx) => `
      <tr>
        <td title="${esc(job.job_name)}">${esc(job.job_name)}</td>
        <td class="salary-col">${esc(job.salary)}</td>
        <td title="${esc(job.company_name)}">${esc(job.company_name)}</td>
        <td>${esc(job.city)}</td>
        <td>${esc(job.education)}</td>
        <td>${esc(job.experience)}</td>
        <td>${esc(job.industry)}</td>
        <td>${esc(job.publish_time)}</td>
        <td><span class="link-btn" onclick="showDetail(${idx})">详情</span></td>
      </tr>
    `).join('');
  }

  document.getElementById('table-count').textContent = `共 ${data.total} 条`;
  document.getElementById('page-info').textContent = `第 ${state.page}/${state.totalPages} 页`;
  document.getElementById('btn-prev').disabled = state.page <= 1;
  document.getElementById('btn-next').disabled = state.page >= state.totalPages;
}

function updateFilters(filters) {
  if (!filters) return;
  const filterEls = [
    { id: 'table-city-filter', key: 'cities' },
    { id: 'table-edu-filter', key: 'educations' },
    { id: 'table-industry-filter', key: 'industries' },
    { id: 'table-exp-filter', key: 'experiences' },
  ];
  filterEls.forEach(({ id, key }) => {
    const sel = document.getElementById(id);
    const currentVal = sel.value;
    const options = filters[key] || [];
    sel.innerHTML = `<option value="">${sel.options[0]?.text || '全部'}</option>` +
      options.map(o => `<option value="${esc(o)}">${esc(o)}</option>`).join('');
    sel.value = currentVal; // Restore selection
  });
}

function sortTable(field) {
  if (state.sortBy === field) {
    state.sortOrder = state.sortOrder === 'asc' ? 'desc' : 'asc';
  } else {
    state.sortBy = field;
    state.sortOrder = 'asc';
  }
  // Update column header icons
  document.querySelectorAll('#jobs-table th').forEach(th => {
    th.classList.remove('sorted');
    th.textContent = th.getAttribute('data-sort') + ' ▸';
  });
  const activeTh = document.querySelector(`#jobs-table th[data-sort="${field}"]`);
  if (activeTh) {
    activeTh.classList.add('sorted');
    activeTh.textContent = field === 'job_name' ? '职位名称' :
      field === 'salary' ? '薪资' : field === 'company_name' ? '公司' :
      field === 'city' ? '城市' : field === 'education' ? '学历' :
      field === 'experience' ? '经验' : field === 'industry' ? '行业' :
      field === 'publish_time' ? '发布日期' : field;
    activeTh.textContent += state.sortOrder === 'asc' ? ' ▲' : ' ▼';
  }
  loadJobs(1);
}

function prevPage() { if (state.page > 1) { state.page--; loadJobs(); } }
function nextPage() { if (state.page < state.totalPages) { state.page++; loadJobs(); } }

// ============================================================================
//  Detail Modal
// ============================================================================
function showDetail(idx) {
  const tbody = document.getElementById('jobs-tbody');
  const rows = tbody.querySelectorAll('tr');
  const row = rows[idx];
  if (!row) return;

  const cells = row.querySelectorAll('td');
  const fields = ['职位名称', '薪资', '公司', '城市', '学历', '经验', '行业', '发布日期'];
  let html = '';
  for (let i = 0; i < Math.min(fields.length, cells.length); i++) {
    html += `<div class="detail-row">
      <span class="detail-label">${fields[i]}</span>
      <span class="detail-value">${cells[i].textContent}</span>
    </div>`;
  }

  document.getElementById('modal-title').textContent = cells[0]?.textContent || '职位详情';
  document.getElementById('modal-body').innerHTML = html;
  document.getElementById('modal-overlay').classList.add('active');
}

function closeModal() {
  document.getElementById('modal-overlay').classList.remove('active');
}

// ============================================================================
//  Spider Control
// ============================================================================
async function startSpider() {
  const keyword = document.getElementById('spider-keyword').value.trim();
  const recruitType = parseInt(document.getElementById('spider-recruit-type').value);
  const maxPages = parseInt(document.getElementById('spider-max-pages').value);

  if (!keyword) { alert('请输入搜索关键词'); return; }
  if (maxPages < 1 || maxPages > 50) { alert('页数范围 1-50'); return; }

  document.getElementById('btn-start').disabled = true;
  document.getElementById('btn-stop').disabled = false;
  setSpiderStatus('running', '🟢 正在运行...');

  try {
    const res = await fetch('/api/spider/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ keyword, recruit_type: recruitType, max_pages: maxPages }),
    });
    const data = await res.json();

    if (data.success) {
      state.spiderRunning = true;
      clearLog();
      startLogStream();
      startStatusPolling();
      document.getElementById('log-badge').classList.remove('hidden');
    } else {
      alert(data.message);
      resetSpiderUI();
    }
  } catch (err) {
    console.error('Spider start failed:', err);
    resetSpiderUI();
  }
}

async function stopSpider() {
  try {
    await fetch('/api/spider/stop', { method: 'POST' });
    document.getElementById('btn-stop').disabled = true;
    setSpiderStatus('idle', '⚪ 已停止');
    document.getElementById('log-badge').classList.add('hidden');
    state.spiderRunning = false;
  } catch (err) {
    console.error('Spider stop failed:', err);
  }
}

function resetSpiderUI() {
  document.getElementById('btn-start').disabled = false;
  document.getElementById('btn-stop').disabled = true;
  setSpiderStatus('idle', '⚪ 就绪');
  document.getElementById('log-badge').classList.add('hidden');
  state.spiderRunning = false;
}

function setSpiderStatus(cls, text) {
  const el = document.getElementById('spider-status-text');
  el.className = `spider-status ${cls}`;
  el.textContent = text;
}

// ---- SSE Log Stream ----
let logEventSource = null;

function startLogStream() {
  if (logEventSource) {
    logEventSource.close();
  }
  logEventSource = new EventSource('/api/spider/logs');

  logEventSource.onmessage = (event) => {
    const d = JSON.parse(event.data);
    appendLog(d.line);
    if (d.done) {
      logEventSource.close();
      logEventSource = null;
      onSpiderComplete();
    }
  };

  logEventSource.onerror = () => {
    if (logEventSource) {
      logEventSource.close();
      logEventSource = null;
    }
    onSpiderComplete();
  };
}

function appendLog(line) {
  state.logLines.push(line);
  // Keep only last 500 lines
  if (state.logLines.length > 500) state.logLines.shift();

  const container = document.getElementById('log-lines');
  let cls = '';
  if (line.startsWith('[系统]')) cls = 'system';
  else if (line.includes('ERROR') || line.includes('❌')) cls = 'error';
  else if (line.includes('✅') || line.includes('完成')) cls = 'success';

  const div = document.createElement('div');
  div.className = `log-line ${cls}`;
  div.textContent = line;
  container.appendChild(div);

  // Auto scroll
  const logContent = document.getElementById('log-content');
  logContent.scrollTop = logContent.scrollHeight;
}

function clearLog() {
  state.logLines = [];
  document.getElementById('log-lines').innerHTML = '';
}

function toggleLog() {
  // Not much to toggle with current design, just focus
  document.getElementById('log-content').scrollTop = document.getElementById('log-content').scrollHeight;
}

// ---- Status Polling ----
let statusInterval = null;

function startStatusPolling() {
  if (statusInterval) clearInterval(statusInterval);
  statusInterval = setInterval(async () => {
    try {
      const res = await fetch('/api/spider/status');
      const data = await res.json();
      if (data.running) {
        const progress = data.progress || 0;
        const total = data.total_pages || 0;
        setSpiderStatus('running', `🟢 爬取中... 第${progress}/${total}页`);
      }
    } catch (err) {}
  }, 2000);
}

function stopStatusPolling() {
  if (statusInterval) {
    clearInterval(statusInterval);
    statusInterval = null;
  }
}

function onSpiderComplete() {
  state.spiderRunning = false;
  resetSpiderUI();
  stopStatusPolling();
  document.getElementById('log-badge').classList.add('hidden');
  // Auto refresh data
  setTimeout(() => {
    loadStats();
    loadJobs();
  }, 500);
}

// ============================================================================
//  Utilities
// ============================================================================
function esc(str) {
  if (!str) return '-';
  const s = String(str);
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function refreshAll() {
  loadStats();
  loadJobs();
}

function exportCSV() {
  window.location.href = '/api/export/csv';
}

// Close modal on Escape key
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closeModal();
});
