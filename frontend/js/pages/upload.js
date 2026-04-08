/**
 * Upload page
 */
const UploadPage = (() => {
  let selectedFile = null;

  function init() {
    const dropZone = document.getElementById('drop-zone');
    const fileInput = document.getElementById('file-input');
    const uploadBtn = document.getElementById('upload-btn');

    dropZone.addEventListener('click', () => fileInput.click());

    dropZone.addEventListener('dragover', (e) => {
      e.preventDefault();
      dropZone.classList.add('drag-over');
    });

    dropZone.addEventListener('dragleave', () => {
      dropZone.classList.remove('drag-over');
    });

    dropZone.addEventListener('drop', (e) => {
      e.preventDefault();
      dropZone.classList.remove('drag-over');
      if (e.dataTransfer.files.length) {
        selectFile(e.dataTransfer.files[0]);
      }
    });

    fileInput.addEventListener('change', () => {
      if (fileInput.files.length) selectFile(fileInput.files[0]);
    });

    uploadBtn.addEventListener('click', doUpload);
  }

  function selectFile(file) {
    const allowed = ['.pdf', '.docx', '.doc', '.txt'];
    const ext = '.' + file.name.split('.').pop().toLowerCase();
    if (!allowed.includes(ext)) {
      App.toast('Недопустимый формат файла', 'error');
      return;
    }
    if (file.size > 10 * 1024 * 1024) {
      App.toast('Файл слишком большой (макс. 10 МБ)', 'error');
      return;
    }
    selectedFile = file;
    document.querySelector('.drop-zone-content p').textContent = file.name;
    document.getElementById('upload-btn').disabled = false;
  }

  async function doUpload() {
    if (!selectedFile) return;
    const btn = document.getElementById('upload-btn');
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner"></span> Загрузка...';

    try {
      const fd = new FormData();
      fd.append('file', selectedFile);
      const source = document.getElementById('upload-source').value;

      const data = await API.upload('/profiles/resumes/upload', fd, { source });

      const result = document.getElementById('upload-result');
      result.classList.remove('hidden');
      result.innerHTML = `
        <div class="result-card" style="border-color: var(--success)">
          <h4 style="color: var(--success)">✓ Резюме загружено</h4>
          <div class="info-grid" style="margin-top:0.5rem">
            <div class="info-item">
              <span class="info-label">Resume ID</span>
              <span class="info-value">${data.data.resume_id}</span>
            </div>
            <div class="info-item">
              <span class="info-label">Candidate ID</span>
              <span class="info-value">${data.data.candidate_id || '—'}</span>
            </div>
            <div class="info-item">
              <span class="info-label">Статус</span>
              <span class="info-value"><span class="badge badge-info">${data.data.status}</span></span>
            </div>
          </div>
        </div>`;

      App.toast('Резюме успешно загружено', 'success');
      // Reset
      selectedFile = null;
      document.querySelector('.drop-zone-content p').textContent = 'Перетащите файл сюда или нажмите для выбора';
    } catch (e) {
      App.toast(e.message, 'error');
    } finally {
      btn.disabled = false;
      btn.textContent = 'Загрузить';
    }
  }

  return { init };
})();
