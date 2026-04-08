/**
 * Dashboard page
 */
const DashboardPage = (() => {
  async function load() {
    try {
      const data = await API.get('/search/summary');
      const s = data.data;

      document.getElementById('stat-candidates').textContent = s.total_candidates ?? 0;
      document.getElementById('stat-vacancies').textContent = s.total_vacancies ?? 0;
      document.getElementById('stat-matches').textContent = s.total_matches ?? 0;

      renderBarChart('grades-chart', s.grades || [], 'grade', 'count');
      renderBarChart('skills-chart', (s.top_skills || []).slice(0, 10), 'skill', 'count');
      renderBarChart('locations-chart', s.locations || [], 'location', 'count');
    } catch (e) {
      console.error('Dashboard load error:', e);
    }
  }

  function renderBarChart(containerId, items, labelKey, valueKey) {
    const container = document.getElementById(containerId);
    if (!items.length) {
      container.innerHTML = '<div class="empty-state"><div class="empty-icon">📊</div>Нет данных</div>';
      return;
    }

    const max = Math.max(...items.map(i => i[valueKey] || 0), 1);
    let html = '<div class="bar-chart">';
    for (const item of items) {
      const val = item[valueKey] || 0;
      const pct = Math.round((val / max) * 100);
      html += `
        <div class="bar-row">
          <span class="bar-label">${escapeHtml(item[labelKey] || '—')}</span>
          <div class="bar-track">
            <div class="bar-fill" style="width:${pct}%">
              <span class="bar-value">${val}</span>
            </div>
          </div>
        </div>`;
    }
    html += '</div>';
    container.innerHTML = html;
  }

  return { load };
})();
