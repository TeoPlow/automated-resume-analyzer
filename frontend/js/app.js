/**
 * Main application controller — navigation, init, helpers
 */

// ========== Utility functions (global) ==========

function escapeHtml(str) {
  if (!str) return '';
  const div = document.createElement('div');
  div.textContent = str;
  return div.innerHTML;
}

function formatDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString('ru-RU', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

function formatSalary(val) {
  if (val == null) return '—';
  return val.toLocaleString('ru-RU') + ' ₽';
}

function formatSalaryRange(min, max) {
  if (!min && !max) return '—';
  if (min && max) return `${min.toLocaleString('ru-RU')} – ${max.toLocaleString('ru-RU')} ₽`;
  if (min) return `от ${min.toLocaleString('ru-RU')} ₽`;
  return `до ${max.toLocaleString('ru-RU')} ₽`;
}

function statusBadge(status) {
  const map = {
    uploaded: 'badge-info',
    processing: 'badge-warning',
    parsed: 'badge-success',
    failed: 'badge-danger',
  };
  return map[status] || 'badge-gray';
}

function statusBadgeVacancy(status) {
  const map = {
    draft: 'badge-gray',
    open: 'badge-success',
    closed: 'badge-warning',
    archived: 'badge-info',
  };
  return map[status] || 'badge-gray';
}

function scoreClass(score) {
  if (score >= 70) return 'score-high';
  if (score >= 40) return 'score-mid';
  return 'score-low';
}

function renderMatchResult(r) {
  const score = r.final_score ?? 0;
  const explanations = r.explanations || [];
  return `
    <div class="result-card">
      <div class="result-header">
        <div style="display:flex;align-items:center;gap:0.75rem">
          <div class="score-badge ${scoreClass(score)}">${score.toFixed(1)}</div>
          <div>
            <h4>${escapeHtml(r.candidate_name || r.candidate_id || '—')}</h4>
            ${r.vacancy_title ? `<span class="text-muted">${escapeHtml(r.vacancy_title)}</span>` : ''}
          </div>
        </div>
        <span class="badge badge-gray">#${r.rank || '—'}</span>
      </div>
      <div class="score-breakdown">
        ${renderScoreBar('Skills', r.skill_score)}
        ${renderScoreBar('Experience', r.experience_score)}
        ${renderScoreBar('Grade', r.grade_score)}
        ${renderScoreBar('Location', r.location_score)}
        ${renderScoreBar('Salary', r.salary_score)}
      </div>
      ${explanations.length ? `
        <details class="explanation-card" style="margin-top:0.5rem">
          <summary style="cursor:pointer;font-size:0.8rem;font-weight:600;color:var(--gray-600)">Подробности</summary>
          ${explanations.map(ex => `
            <div class="factor-row">
              <span><strong>${escapeHtml(ex.factor)}</strong> — ${ex.score?.toFixed(1)} × ${ex.weight?.toFixed(2)} = ${ex.impact?.toFixed(1)}</span>
              <span class="factor-detail">${escapeHtml(ex.detail || '')}</span>
            </div>
          `).join('')}
        </details>
      ` : ''}
    </div>`;
}

function renderScoreBar(label, value) {
  const v = value ?? 0;
  return `
    <div class="score-factor">
      <span style="width:80px;font-weight:600">${label}</span>
      <div class="score-factor-bar">
        <div class="score-factor-fill" style="width:${v}%;background:${v >= 70 ? 'var(--success)' : v >= 40 ? 'var(--warning)' : 'var(--danger)'}"></div>
      </div>
      <span style="width:35px;text-align:right">${v.toFixed(0)}</span>
    </div>`;
}

function renderPagination(containerId, pagination, onPageChange) {
  const container = document.getElementById(containerId);
  if (!pagination || pagination.total <= pagination.limit) {
    container.innerHTML = '';
    return;
  }
  const totalPages = Math.ceil(pagination.total / pagination.limit);
  const currentPage = Math.floor(pagination.offset / pagination.limit);
  let html = '';
  html += `<button ${currentPage === 0 ? 'disabled' : ''} onclick="this.blur()">←</button>`;
  for (let i = 0; i < totalPages && i < 10; i++) {
    html += `<button class="${i === currentPage ? 'active' : ''}">${i + 1}</button>`;
  }
  html += `<button ${currentPage >= totalPages - 1 ? 'disabled' : ''}>→</button>`;
  container.innerHTML = html;

  container.querySelectorAll('button').forEach((btn, idx) => {
    btn.addEventListener('click', () => {
      if (idx === 0 && currentPage > 0) {
        onPageChange((currentPage - 1) * pagination.limit);
      } else if (idx === container.children.length - 1 && currentPage < totalPages - 1) {
        onPageChange((currentPage + 1) * pagination.limit);
      } else if (idx > 0 && idx < container.children.length - 1) {
        onPageChange((idx - 1) * pagination.limit);
      }
    });
  });
}

function debounce(fn, ms) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}


// ========== App Controller ==========

const App = (() => {
  const pages = ['dashboard', 'upload', 'candidates', 'candidate-detail', 'vacancies', 'vacancy-detail', 'matching', 'search', 'integrations'];

  async function init() {
    // Init sub-modules
    UploadPage.init();
    CandidatesPage.init();
    VacanciesPage.init();
    MatchingPage.init();
    SearchPage.init();
    IntegrationsPage.init();

    // Navigation
    document.querySelectorAll('.nav-item').forEach(el => {
      el.addEventListener('click', (e) => {
        e.preventDefault();
        navigate(el.dataset.page);
      });
    });

    // Logout
    document.getElementById('logout-btn').addEventListener('click', () => Auth.logout());

    // Login form
    document.getElementById('login-form').addEventListener('submit', handleLogin);

    // Check session
    if (Auth.isLoggedIn()) {
      const user = await Auth.loadUser();
      if (user) {
        enterApp();
        return;
      }
    }
    showLogin();
  }

  async function handleLogin(e) {
    e.preventDefault();
    const errEl = document.getElementById('login-error');
    errEl.classList.add('hidden');

    const username = document.getElementById('login-username').value;
    const password = document.getElementById('login-password').value;

    try {
      await Auth.login(username, password);
      enterApp();
    } catch (err) {
      errEl.textContent = err.message || 'Ошибка авторизации';
      errEl.classList.remove('hidden');
    }
  }

  function enterApp() {
    const user = Auth.getUser();
    document.getElementById('user-display').textContent = user.actor_id || 'User';
    document.getElementById('user-role').textContent = user.actor_type || '';

    // Show/hide admin items
    const adminItems = document.querySelectorAll('.nav-admin-only');
    adminItems.forEach(el => {
      el.style.display = Auth.isAdmin() ? '' : 'none';
    });

    document.getElementById('sidebar').classList.remove('hidden');
    document.getElementById('main-content').classList.add('with-sidebar');
    showLogin(false);
    navigate('dashboard');
  }

  function showLogin(show = true) {
    const loginPage = document.getElementById('page-login');
    if (show) {
      document.getElementById('sidebar').classList.add('hidden');
      document.getElementById('main-content').classList.remove('with-sidebar');
      // Hide all pages, show login
      pages.forEach(p => document.getElementById(`page-${p}`).classList.add('hidden'));
      loginPage.classList.remove('hidden');
      loginPage.classList.add('active');
    } else {
      loginPage.classList.add('hidden');
      loginPage.classList.remove('active');
    }
  }

  function navigate(page) {
    pages.forEach(p => {
      const el = document.getElementById(`page-${p}`);
      if (el) { el.classList.remove('active'); el.classList.add('hidden'); }
    });

    const target = document.getElementById(`page-${page}`);
    if (target) {
      target.classList.remove('hidden');
      target.classList.add('active');
    }

    // Update nav
    document.querySelectorAll('.nav-item').forEach(el => {
      el.classList.toggle('active', el.dataset.page === page);
    });

    // Load page data
    switch (page) {
      case 'dashboard': DashboardPage.load(); break;
      case 'candidates': CandidatesPage.load(); break;
      case 'vacancies': VacanciesPage.load(); break;
      case 'matching': MatchingPage.load(); break;
      case 'integrations': IntegrationsPage.load(); break;
    }
  }

  function openModal(id) {
    document.getElementById(id).classList.remove('hidden');
  }

  function closeModal(id) {
    document.getElementById(id).classList.add('hidden');
  }

  function showCreateVacancy() { VacanciesPage.showCreateForm(); }
  function showCreateKey() { IntegrationsPage.showCreateForm(); }
  function copyKey() { IntegrationsPage.copyKey(); }

  function toast(message, type = 'info') {
    const container = document.getElementById('toast-container');
    const el = document.createElement('div');
    el.className = `toast toast-${type}`;
    el.textContent = message;
    container.appendChild(el);
    setTimeout(() => el.remove(), 4000);
  }

  return { init, navigate, openModal, closeModal, showCreateVacancy, showCreateKey, copyKey, toast, showLogin };
})();

// Boot
document.addEventListener('DOMContentLoaded', () => App.init());
