/**
 * Matching page — run matching and view results
 */
const MatchingPage = (() => {
  async function load() {
    await loadVacancySelect();
  }

  async function loadVacancySelect() {
    const select = document.getElementById('matching-vacancy-select');
    try {
      const data = await API.get('/search/vacancies', { status: 'open', limit: 100 });
      const vacancies = data.data || [];
      select.innerHTML = '<option value="">Выберите вакансию...</option>' +
        vacancies.map(v => `<option value="${v.id}">${escapeHtml(v.title)} (${v.status})</option>`).join('');
    } catch (e) {
      select.innerHTML = '<option value="">Ошибка загрузки</option>';
    }
  }

  async function runMatching(e) {
    e.preventDefault();
    const vacancyId = document.getElementById('matching-vacancy-select').value;
    if (!vacancyId) {
      App.toast('Выберите вакансию', 'warning');
      return;
    }

    const body = {
      vacancy_id: vacancyId,
      top_k: parseInt(document.getElementById('matching-top-k').value) || 20,
      weights: {
        skills: parseFloat(document.getElementById('w-skills').value) || 0.4,
        experience: parseFloat(document.getElementById('w-experience').value) || 0.25,
        grade: parseFloat(document.getElementById('w-grade').value) || 0.15,
        location: parseFloat(document.getElementById('w-location').value) || 0.1,
        salary: parseFloat(document.getElementById('w-salary').value) || 0.1,
      },
    };

    const btn = document.querySelector('#matching-form button[type=submit]');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Запуск...';

    try {
      const runData = await API.post('/matching/run', body);
      const runId = runData.data.run_id;
      App.toast('Матчинг запущен', 'success');

      // Poll for results
      await pollResults(runId, vacancyId);
    } catch (e) {
      App.toast(e.message, 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Запустить';
    }
  }

  async function pollResults(runId, vacancyId) {
    const card = document.getElementById('matching-results-card');
    const content = document.getElementById('matching-results-content');
    card.style.display = 'block';
    content.innerHTML = '<div class="loading-overlay"><span class="spinner"></span> Ожидание результатов...</div>';

    let attempts = 0;
    const maxAttempts = 30;

    const poll = async () => {
      attempts++;
      try {
        const data = await API.get(`/matching/results/${runId}`);
        const run = data.data;

        if (run.status === 'completed') {
          const results = run.results || [];
          if (!results.length) {
            content.innerHTML = '<div class="empty-state">Нет подходящих кандидатов</div>';
            return;
          }
          content.innerHTML = `
            <p class="text-muted mb-1">Оценено кандидатов: ${run.total_candidates || results.length}</p>
            ${results.map(r => renderMatchResult(r)).join('')}`;
          return;
        }

        if (run.status === 'failed') {
          content.innerHTML = '<div class="error-text">Матчинг завершился с ошибкой</div>';
          return;
        }

        if (attempts < maxAttempts) {
          setTimeout(poll, 2000);
        } else {
          // Fallback: try loading by vacancy
          await loadByVacancy(vacancyId, content);
        }
      } catch (e) {
        // run_id might not have results yet, try by vacancy
        if (attempts < maxAttempts) {
          setTimeout(poll, 2000);
        } else {
          await loadByVacancy(vacancyId, content);
        }
      }
    };

    setTimeout(poll, 1500);
  }

  async function loadByVacancy(vacancyId, content) {
    try {
      const data = await API.get(`/matching/vacancies/${vacancyId}`);
      const results = data.data || [];
      if (!results.length) {
        content.innerHTML = '<div class="empty-state">Нет результатов</div>';
        return;
      }
      content.innerHTML = results.map(r => renderMatchResult(r)).join('');
    } catch (e) {
      content.innerHTML = '<div class="empty-state">Результаты ещё не готовы</div>';
    }
  }

  function init() {
    document.getElementById('matching-form').addEventListener('submit', runMatching);
  }

  return { load, init };
})();
