'use strict';

const csrf = document.querySelector('meta[name="csrf-token"]').content;
const toast = document.querySelector('#toast');
let toastTimeout;
function showToast(message) {
  toast.textContent = message;
  toast.hidden = false;
  clearTimeout(toastTimeout);
  toastTimeout = setTimeout(() => { toast.hidden = true; }, 3500);
}

document.addEventListener('click', (event) => {
  const close = event.target.closest('[data-close]');
  if (close) close.closest('dialog')?.close();
  const trigger = event.target.closest('[data-dialog]');
  if (trigger) document.getElementById(trigger.dataset.dialog)?.showModal();
  const dismiss = event.target.closest('[data-dismiss]');
  if (dismiss) dismiss.closest('.flash').remove();
  const passwordButton = event.target.closest('[data-password]');
  if (passwordButton) {
    const input = document.getElementById(passwordButton.dataset.password);
    const show = input.type === 'password';
    input.type = show ? 'text' : 'password';
    passwordButton.textContent = show ? 'Скрыть' : 'Показать';
    passwordButton.setAttribute('aria-label', show ? 'Скрыть пароль' : 'Показать пароль');
  }
  const deleteButton = event.target.closest('[data-delete-url]');
  if (deleteButton) {
    document.querySelector('#delete-form').action = deleteButton.dataset.deleteUrl;
    document.querySelector('#delete-description').textContent = `«${deleteButton.dataset.deleteTitle}» будет удалён из каталога. Это действие нельзя отменить.`;
    document.querySelector('#delete-dialog').showModal();
  }
});

document.querySelectorAll('dialog').forEach((dialog) => {
  dialog.addEventListener('click', (event) => {
    if (event.target !== dialog) return;
    const bounds = dialog.getBoundingClientRect();
    if (event.clientX < bounds.left || event.clientX > bounds.right ||
        event.clientY < bounds.top || event.clientY > bounds.bottom) dialog.close();
  });
});

document.querySelectorAll('.favorite-form').forEach((form) => {
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    const button = form.querySelector('button');
    button.disabled = true;
    try {
      const response = await fetch(form.action, {
        method: 'POST', body: new FormData(form),
        headers: {Accept: 'application/json', 'X-CSRF-Token': csrf}
      });
      if (response.redirected) { window.location.assign(response.url); return; }
      if (!response.ok) throw new Error('save failed');
      const data = await response.json();
      document.querySelectorAll('.favorite-form').forEach((other) => {
        if (other.action !== form.action) return;
        const target = other.querySelector('button');
        target.classList.toggle('is-saved', data.saved);
        target.setAttribute('aria-pressed', String(data.saved));
        if (target.classList.contains('favorite-text')) {
          target.textContent = data.saved ? 'В избранном ✓' : 'В избранное';
        } else target.setAttribute('aria-label', data.saved ? 'Убрать из избранного' : 'В избранное');
      });
      showToast(data.saved ? '✓ Материал сохранён' : 'Материал убран из избранного');
    } catch {
      showToast('Не удалось сохранить. Обнови страницу и попробуй ещё раз.');
    } finally { button.disabled = false; }
  });
});

const catalogForm = document.querySelector('#catalog-form');
if (catalogForm) {
  const panel = document.querySelector('#filters-panel');
  const openFilters = () => {
    panel.classList.add('is-open');
    panel.setAttribute('role', 'dialog');
    panel.setAttribute('aria-modal', 'true');
    panel.setAttribute('aria-label', 'Фильтры каталога');
    panel.querySelector('[data-filter-close]').focus();
  };
  const closeFilters = () => {
    panel.classList.remove('is-open');
    panel.removeAttribute('role');
    panel.removeAttribute('aria-modal');
    document.querySelector('[data-filter-open]').focus();
  };
  document.querySelector('[data-filter-open]').addEventListener('click', openFilters);
  document.querySelector('[data-filter-close]').addEventListener('click', closeFilters);
  document.addEventListener('keydown', (event) => {
    if (!panel.classList.contains('is-open')) return;
    if (event.key === 'Escape') closeFilters();
    if (event.key === 'Tab') {
      const focusable = [...panel.querySelectorAll('a,button,input,select')].filter(el => el.getClientRects().length);
      const first = focusable[0], last = focusable.at(-1);
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
      if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    }
  });
  catalogForm.querySelectorAll('[data-auto-submit]').forEach((input) => {
    input.addEventListener('change', () => {
      if (input.hasAttribute('data-course') && input.checked) {
        catalogForm.querySelectorAll('[data-course]').forEach(other => { if (other !== input) other.checked = false; });
      }
      if (window.matchMedia('(min-width: 768px)').matches || input.name === 'sort') catalogForm.requestSubmit();
    });
  });
}

const uploadForm = document.querySelector('#upload-form');
if (uploadForm) {
  const fileInput = document.querySelector('#file');
  const fileLabel = document.querySelector('#file-label');
  const fileError = document.querySelector('#file-error');
  const dropZone = document.querySelector('#drop-zone');
  const urlInput = document.querySelector('#external_url');
  const modeInput = document.querySelector('#source-mode');
  function updateMode(mode) {
    modeInput.value = mode;
    document.querySelector('#file-source').hidden = mode !== 'file';
    document.querySelector('#link-source').hidden = mode !== 'link';
    urlInput.required = mode === 'link';
    urlInput.disabled = mode !== 'link';
    fileInput.disabled = mode !== 'file';
    document.querySelectorAll('[data-source]').forEach(button => {
      button.classList.toggle('secondary', button.dataset.source !== mode);
      button.setAttribute('aria-pressed', String(button.dataset.source === mode));
    });
  }
  document.querySelectorAll('[data-source]').forEach(button => button.addEventListener('click', () => updateMode(button.dataset.source)));
  updateMode(modeInput.value);
  fileInput.addEventListener('change', () => {
    const file = fileInput.files[0];
    fileError.hidden = true;
    fileInput.setCustomValidity('');
    if (!file) { fileLabel.textContent = 'Перетащи файл сюда'; return; }
    fileLabel.textContent = file.name;
    const allowed = /\.(pdf|pptx|docx|png|jpe?g)$/i.test(file.name);
    if (!allowed || !file.size || file.size > 20 * 1024 * 1024) {
      const message = !allowed ? 'Выбери PDF, PPTX, DOCX, PNG или JPG.' : 'Нужен непустой файл до 20 МБ.';
      fileError.textContent = message;
      fileError.hidden = false;
      fileInput.setCustomValidity(message);
    }
  });
  ['dragenter','dragover'].forEach(name => dropZone.addEventListener(name, event => {
    event.preventDefault(); dropZone.classList.add('drag-over');
  }));
  ['dragleave','drop'].forEach(name => dropZone.addEventListener(name, event => {
    event.preventDefault(); dropZone.classList.remove('drag-over');
  }));
  dropZone.addEventListener('drop', event => {
    if (event.dataTransfer.files.length) {
      fileInput.files = event.dataTransfer.files;
      fileInput.dispatchEvent(new Event('change'));
    }
  });
}

const sheet = document.querySelector('#document-sheet');
if (sheet) {
  let zoom = 100;
  let page = 1;
  const totalPages = Number(sheet.closest('.document-viewer').dataset.totalPages);
  const firstPage = sheet.innerHTML;
  document.querySelectorAll('[data-page-step]').forEach(button => button.addEventListener('click', () => {
    page = Math.max(1, Math.min(totalPages, page + Number(button.dataset.pageStep)));
    document.querySelector('#document-page').textContent = String(page);
    document.querySelector('#preview-page').textContent = String(page);
    document.querySelector('[data-page-step="-1"]').disabled = page === 1;
    document.querySelector('[data-page-step="1"]').disabled = page === totalPages;
    if (page === 1) sheet.innerHTML = firstPage;
    else {
      const heading = document.createElement('h2');
      heading.textContent = `Практика · страница ${page}`;
      const task = document.createElement('p');
      task.textContent = `Задание ${page - 1}: создай массив из ${page + 2} целых чисел.`;
      const list = document.createElement('ol');
      ['Выведи все элементы массива.', 'Найди сумму элементов.', 'Найди наибольший элемент.',
        'Подсчитай количество положительных чисел.'].forEach(text => {
        const li = document.createElement('li');
        li.textContent = text;
        list.append(li);
      });
      const tip = document.createElement('p');
      tip.textContent = 'Проверь программу на нулях, отрицательных и одинаковых значениях.';
      sheet.replaceChildren(heading, task, list, tip);
    }
  }));
  document.querySelectorAll('[data-zoom]').forEach(button => button.addEventListener('click', () => {
    zoom = Math.min(150, Math.max(70, zoom + Number(button.dataset.zoom)));
    sheet.style.zoom = String(zoom / 100);
    document.querySelector('#zoom-label').textContent = `${zoom}%`;
  }));
}

document.querySelectorAll('.field-error').forEach(error => {
  if (error.hidden) return;
  const parent = error.parentElement;
  const input = parent.querySelector('input,select,textarea');
  if (!input) return;
  input.setAttribute('aria-invalid', 'true');
  if (!error.id) error.id = `error-${input.id || input.name}`;
  input.setAttribute('aria-describedby', error.id);
});
