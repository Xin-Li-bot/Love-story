const ANNIVERSARY = new Date('2022-12-25T00:00:00+08:00');
const API_TIMEOUT_MS = 12000;
const MAX_UPLOAD_BYTES = 5 * 1024 * 1024;
const ALLOWED_UPLOAD_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp']);
const DATE_FORMATTER = new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' });
const MESSAGE_TIME_FORMATTER = new Intl.DateTimeFormat('zh-CN', {
  year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit'
});
const INTEGER_FORMATTER = new Intl.NumberFormat('zh-CN');
const state = {
  timeline: [],
  timelineLoaded: false,
  timelinePromise: null,
  messages: [],
  messagesLoaded: false,
  messagesPromise: null,
  wishes: [],
  wishlistPending: new Set(),
  photos: [],
  galleryLimit: 12,
  lightboxIndex: 0,
  zoom: 1,
  panX: 0,
  panY: 0,
  lightboxPointers: new Map(),
  gesture: null,
  adminAuthenticated: false,
  adminSessionChecked: false,
  adminSessionPromise: null,
  musicPlaying: false,
  confetti: null,
  uploadPromise: null,
  previewObjectUrl: '',
  overlayReturnFocus: null
};

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
const bind = (selector, eventName, handler, options) => $(selector)?.addEventListener(eventName, handler, options);

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>'"]/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  })[character]);
}

function refreshIcons() {
  if (window.lucide) lucide.createIcons();
}

async function apiRequest(url, options = {}) {
  const { timeoutMs = API_TIMEOUT_MS, ...requestOptions } = options;
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), timeoutMs);

  try {
    const response = await fetch(url, {
      ...requestOptions,
      credentials: 'same-origin',
      signal: controller.signal
    });
    if (!response.ok) {
      let detail = `请求失败（${response.status}）`;
      try {
        const payload = await response.json();
        detail = payload.detail || detail;
      } catch {
        if (response.status >= 500) detail = '服务器暂时无法处理请求，请稍后重试';
      }
      const error = new Error(detail);
      error.status = response.status;
      throw error;
    }
    if (response.status === 204) return null;
    return response.json();
  } catch (error) {
    if (error.name === 'AbortError') {
      const timeoutError = new Error('请求超时，请检查网络后重试');
      timeoutError.status = 408;
      throw timeoutError;
    }
    throw error;
  } finally {
    clearTimeout(timeout);
  }
}

let toastTimer;
function showToast(message) {
  const toast = $('#toast');
  if (!toast) return;
  toast.textContent = message;
  toast.classList.add('show');
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => toast.classList.remove('show'), 3200);
}

function formatDate(dateValue) {
  const date = new Date(`${dateValue}T00:00:00`);
  if (Number.isNaN(date.valueOf())) return dateValue;
  return DATE_FORMATTER.format(date);
}

function formatMessageTime(dateValue) {
  const original = String(dateValue || '');
  const normalized = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}(?::\d{2})?$/.test(original)
    ? `${original.replace(' ', 'T')}Z`
    : original;
  const date = new Date(normalized);
  return Number.isNaN(date.valueOf()) ? original : MESSAGE_TIME_FORMATTER.format(date);
}

function formatInteger(value) {
  return INTEGER_FORMATTER.format(value);
}

function updateRelationshipClock() {
  const now = new Date();
  const elapsedMilliseconds = Math.max(0, now - ANNIVERSARY);
  const elapsedSeconds = Math.floor(elapsedMilliseconds / 1000);
  const elapsedDays = Math.floor(elapsedSeconds / 86400);

  $('#days-count').textContent = formatInteger(elapsedDays);

  let nextAnniversary = new Date(now.getFullYear(), 11, 25, 0, 0, 0, 0);
  if (nextAnniversary <= now) {
    nextAnniversary = new Date(now.getFullYear() + 1, 11, 25, 0, 0, 0, 0);
  }

  const remainingSeconds = Math.max(0, Math.floor((nextAnniversary - now) / 1000));
  const days = Math.floor(remainingSeconds / 86400);
  const hours = Math.floor((remainingSeconds % 86400) / 3600);
  const minutes = Math.floor((remainingSeconds % 3600) / 60);
  const seconds = remainingSeconds % 60;

  $('#countdown-days').textContent = String(days);
  $('#countdown-hours').textContent = String(hours).padStart(2, '0');
  $('#countdown-minutes').textContent = String(minutes).padStart(2, '0');
  $('#countdown-seconds').textContent = String(seconds).padStart(2, '0');

  const totalHours = Math.floor(elapsedSeconds / 3600);
  const totalMinutes = Math.floor(elapsedSeconds / 60);
  $('#countdown-exact').textContent = `共同走过 ${formatInteger(elapsedSeconds)} 秒 · ${formatInteger(totalMinutes)} 分钟 · ${formatInteger(totalHours)} 小时`;
}

const revealObserver = new IntersectionObserver(entries => {
  entries.forEach(entry => {
    if (entry.isIntersecting) {
      entry.target.classList.add('visible');
      revealObserver.unobserve(entry.target);
    }
  });
}, { threshold: 0.08, rootMargin: '0px 0px -40px' });

function observeRevealElements() {
  $$('.reveal:not(.visible)').forEach(element => revealObserver.observe(element));
}

function timelineItemKey(item, index) {
  return item.id == null ? `position:${index}` : `id:${item.id}`;
}

function rebuildPhotos() {
  const items = [...state.timeline].sort((first, second) => first.date.localeCompare(second.date));
  state.photos = items.flatMap((item, index) => {
    if (!item.image || !String(item.image).trim()) return [];
    return [{
      key: timelineItemKey(item, index),
      src: item.image,
      thumbnail: item.thumbnail || '',
      title: item.title,
      date: item.date
    }];
  });
}

async function fetchTimeline({ force = false } = {}) {
  if (state.timelinePromise) {
    if (!force) return state.timelinePromise;
    try { await state.timelinePromise; } catch {}
  }
  if (state.timelineLoaded && !force) return state.timeline;

  state.timelinePromise = apiRequest('/api/timeline')
    .then(timeline => {
      state.timeline = timeline;
      state.timelineLoaded = true;
      rebuildPhotos();
      return timeline;
    })
    .finally(() => {
      state.timelinePromise = null;
    });
  return state.timelinePromise;
}

async function loadTimeline(options = {}) {
  try {
    await fetchTimeline(options);
    renderTimeline();
    renderGallery();
  } catch (error) {
    $('#timeline-list').innerHTML = `<p class="text-center text-[14px]" style="color:var(--muted)">${escapeHtml(error.message)}</p>`;
    $('#gallery-grid').innerHTML = '<p class="col-span-full text-center text-[14px]" style="color:var(--muted)">相册暂时无法载入。</p>';
  }
}

async function refreshTimelineViews() {
  await fetchTimeline({ force: true });
  renderTimeline();
  renderGallery();
  renderAdminTimeline();
}

function createTimelineCard(item, photoIndex) {
  const previewSource = item.thumbnail || item.image;
  const image = item.image ? `
    <button class="timeline-image-button" type="button" data-photo-index="${photoIndex}" aria-label="放大查看 ${escapeHtml(item.title)}">
      <img class="timeline-image" src="${escapeHtml(previewSource)}" alt="${escapeHtml(item.title)}" loading="lazy" decoding="async">
    </button>` : '';
  const photoNote = item.image ? '' : `
    <div class="memory-photo-note" role="note" aria-label="这段回忆暂未收录照片">
      <i data-lucide="image-plus" class="w-3.5 h-3.5"></i>
      <span>影像待补充</span>
    </div>`;

  return `
    <article class="timeline-card reveal rounded-3xl shadow-[0_4px_20px_rgb(0,0,0,0.03)] hover:-translate-y-1 hover:shadow-[0_12px_30px_rgb(0,0,0,0.08)] transition-all duration-500 ease-out">
      ${image}
      <div class="timeline-card-body">
        <time class="timeline-date" datetime="${escapeHtml(item.date)}"><i data-lucide="calendar-heart" class="w-3.5 h-3.5"></i>${escapeHtml(formatDate(item.date))}</time>
        <h3 class="timeline-title">${escapeHtml(item.title)}</h3>
        <p class="timeline-copy">${escapeHtml(item.description)}</p>
        ${photoNote}
      </div>
    </article>`;
}

function renderTimeline() {
  const container = $('#timeline-list');
  const items = [...state.timeline].sort((first, second) => first.date.localeCompare(second.date));
  if (!items.length) {
    container.innerHTML = '<p class="text-center text-[14px]" style="color:var(--muted)">还没有时光记录。</p>';
    return;
  }

  container.innerHTML = items.map((item, index) => {
    const photoIndex = state.photos.findIndex(photo => photo.key === timelineItemKey(item, index));
    const card = `<div>${createTimelineCard(item, photoIndex)}</div>`;
    const spacer = '<div class="timeline-spacer"></div>';
    return `<div class="timeline-row">${index % 2 === 0 ? `${card}${spacer}` : `${spacer}${card}`}</div>`;
  }).join('');

  $$('[data-photo-index]', container).forEach(button => {
    button.addEventListener('click', () => openLightbox(Number(button.dataset.photoIndex)));
  });

  refreshIcons();
  observeRevealElements();
}

function renderGallery() {
  const grid = $('#gallery-grid');
  const visiblePhotos = state.photos.slice(0, state.galleryLimit);
  if (!visiblePhotos.length) {
    grid.innerHTML = '<p class="col-span-full text-center text-[14px]" style="color:var(--muted)">还没有可以展示的照片。</p>';
    $('#gallery-more-button').classList.add('hidden');
    return;
  }

  grid.innerHTML = visiblePhotos.map((photo, index) => `
    <button class="gallery-card reveal rounded-3xl shadow-[0_4px_20px_rgb(0,0,0,0.03)] hover:-translate-y-1 hover:shadow-[0_12px_30px_rgb(0,0,0,0.08)] transition-all duration-500 ease-out" type="button" data-gallery-index="${index}" aria-label="放大查看 ${escapeHtml(photo.title)}">
      <img class="gallery-image" src="${escapeHtml(photo.thumbnail || photo.src)}" alt="${escapeHtml(photo.title)}" loading="lazy" decoding="async">
      <span class="gallery-caption">${escapeHtml(photo.title)}</span>
    </button>`).join('');

  $$('.gallery-card', grid).forEach(button => {
    button.addEventListener('click', () => openLightbox(Number(button.dataset.galleryIndex)));
  });

  $('#gallery-more-button').classList.toggle('hidden', state.photos.length <= state.galleryLimit);
  observeRevealElements();
}

async function loadWishlist() {
  try {
    state.wishes = await apiRequest('/api/wishlist');
    renderWishlist();
  } catch (error) {
    $('#wishlist-grid').innerHTML = `<p class="text-center text-[14px]" style="color:var(--muted)">${escapeHtml(error.message)}</p>`;
  }
}

function renderWishlist() {
  const icons = ['map-pinned', 'sparkles', 'music-2', 'cat', 'sunrise', 'castle'];
  const grid = $('#wishlist-grid');
  grid.innerHTML = state.wishes.map((wish, index) => {
    const pending = state.wishlistPending.has(String(wish.id));
    return `
    <button class="wish-card reveal rounded-3xl shadow-[0_4px_20px_rgb(0,0,0,0.03)] hover:-translate-y-1 hover:shadow-[0_12px_30px_rgb(0,0,0,0.08)] transition-all duration-500 ease-out ${wish.completed ? 'completed' : ''}" type="button" data-wish-id="${escapeHtml(wish.id)}" aria-pressed="${Boolean(wish.completed)}" aria-busy="${pending}" ${pending ? 'disabled' : ''}>
      <span class="flex items-center gap-4 min-w-0">
        <span class="wish-icon"><i data-lucide="${icons[index % icons.length]}" class="w-5 h-5"></i></span>
        <span class="min-w-0">
          <strong class="wish-title block text-[15px] font-semibold">${escapeHtml(wish.title)}</strong>
          <small class="block mt-1 text-[11px]" style="color:var(--faint)">${wish.completed ? `完成于 ${escapeHtml(wish.completed_at ? formatMessageTime(wish.completed_at) : '某个美好时刻')}` : '等待我们一起完成'}</small>
        </span>
      </span>
      <span class="wish-checkbox" aria-hidden="true"><i data-lucide="check"></i></span>
    </button>`;
  }).join('');

  $$('.wish-card', grid).forEach(button => {
    button.addEventListener('click', () => toggleWish(button.dataset.wishId));
  });

  refreshIcons();
  observeRevealElements();
}

async function toggleWish(wishId) {
  const wishKey = String(wishId);
  if (state.wishlistPending.has(wishKey)) return;
  if (!state.adminSessionChecked) await checkAdminSession();
  if (!requireAdmin()) {
    showToast('完成心愿需要先进入我们的秘密后台');
    return;
  }

  const wish = state.wishes.find(item => String(item.id) === wishKey);
  if (!wish) return;
  state.wishlistPending.add(wishKey);
  renderWishlist();

  try {
    const desiredCompleted = !Boolean(wish.completed);
    const updated = await apiRequest(`/api/wishlist/${encodeURIComponent(wishId)}`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ completed: desiredCompleted })
    });
    if (updated) Object.assign(wish, updated);
    else await loadWishlist();
    showToast('心愿状态已经更新');
  } catch (error) {
    handleAdminError(error);
  } finally {
    state.wishlistPending.delete(wishKey);
    renderWishlist();
  }
}

async function fetchMessages({ force = false } = {}) {
  if (state.messagesPromise) {
    if (!force) return state.messagesPromise;
    try { await state.messagesPromise; } catch {}
  }
  if (state.messagesLoaded && !force) return state.messages;

  state.messagesPromise = apiRequest('/api/messages')
    .then(messages => {
      state.messages = messages;
      state.messagesLoaded = true;
      return messages;
    })
    .finally(() => {
      state.messagesPromise = null;
    });
  return state.messagesPromise;
}

async function loadMessages(options = {}) {
  try {
    await fetchMessages(options);
    renderMessages();
  } catch (error) {
    $('#message-list').innerHTML = `<p class="text-[14px]" style="color:var(--muted)">${escapeHtml(error.message)}</p>`;
  }
}

async function refreshMessageViews() {
  await fetchMessages({ force: true });
  renderMessages();
  renderAdminMessages();
}

function renderMessages() {
  const container = $('#message-list');
  if (!state.messages.length) {
    container.innerHTML = '<p class="text-[14px]" style="color:var(--muted)">还没有留言，来留下第一份祝福吧。</p>';
    return;
  }

  container.innerHTML = state.messages.map(message => `
    <article class="message-bubble reveal rounded-3xl shadow-[0_4px_20px_rgb(0,0,0,0.03)] hover:-translate-y-1 hover:shadow-[0_12px_30px_rgb(0,0,0,0.08)] transition-all duration-500 ease-out">
      <div class="flex items-start justify-between gap-5">
        <div class="flex items-center gap-3 min-w-0">
          <span class="w-10 h-10 grid place-items-center shrink-0 rounded-full text-white text-[13px] font-bold" style="background:var(--rose)">${escapeHtml(String(message.nickname).slice(0, 1))}</span>
          <div class="min-w-0"><strong class="block truncate text-[14px]">${escapeHtml(message.nickname)}</strong><span class="block mt-1 text-[10px]" style="color:var(--faint)">留下了一份祝福</span></div>
        </div>
        <time class="shrink-0 text-[10px]" datetime="${escapeHtml(message.created_at)}" style="color:var(--faint)">${escapeHtml(formatMessageTime(message.created_at))}</time>
      </div>
      <p class="m-0 mt-4 text-[14px] leading-7 break-words" style="color:var(--muted)">${escapeHtml(message.content)}</p>
    </article>`).join('');

  observeRevealElements();
}

async function submitMessage(event) {
  event.preventDefault();
  const submitButton = $('#message-submit-button');
  const nickname = $('#message-nickname').value.trim();
  const content = $('#message-content').value.trim();

  if (!nickname || !content) {
    showToast('请填写署名和想说的话');
    return;
  }

  submitButton.disabled = true;
  submitButton.classList.add('opacity-60');

  try {
    await apiRequest('/api/messages', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nickname, content })
    });

    event.target.reset();
    $('#message-character-count').textContent = '0';
    await refreshMessageViews();
    launchCelebration();
    showToast('祝福已经被我们认真收藏');
  } catch (error) {
    showToast(error.message);
  } finally {
    submitButton.disabled = false;
    submitButton.classList.remove('opacity-60');
  }
}

function launchCelebration() {
  if (matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  if (window.confetti) {
    state.confetti ||= window.confetti.create(null, { resize: true, useWorker: false });
    const fireConfetti = state.confetti;
    const endTime = Date.now() + 1400;
    const colors = ['#ad7480', '#e2a8b1', '#f3d9de', '#ffffff', '#7f9b8a', '#ffd166'];

    (function frame() {
      fireConfetti({
        particleCount: 9,
        angle: 60,
        spread: 70,
        startVelocity: 46,
        origin: { x: 0, y: 0.72 },
        colors
      });
      fireConfetti({
        particleCount: 9,
        angle: 120,
        spread: 70,
        startVelocity: 46,
        origin: { x: 1, y: 0.72 },
        colors
      });
      if (Date.now() < endTime) requestAnimationFrame(frame);
    })();

    setTimeout(() => fireConfetti({ particleCount: 180, spread: 110, origin: { y: 0.55 }, colors }), 180);
  }

  const heartSymbols = ['♥', '♡', '❤', '✦'];
  for (let index = 0; index < 22; index += 1) {
    setTimeout(() => {
      const heart = document.createElement('span');
      heart.className = 'heart-particle';
      heart.textContent = heartSymbols[index % heartSymbols.length];
      heart.style.left = `${4 + Math.random() * 92}vw`;
      heart.style.top = `${66 + Math.random() * 24}vh`;
      heart.style.color = index % 3 === 0 ? '#895762' : '#d49aa5';
      heart.style.fontSize = `${17 + Math.random() * 18}px`;
      heart.style.animationDelay = `${Math.random() * 0.18}s`;
      document.body.appendChild(heart);
      setTimeout(() => heart.remove(), 2500);
    }, index * 55);
  }
}

async function toggleMusic() {
  const audio = $('#background-music');
  const dock = $('#music-dock');
  const button = $('#music-button');

  if (audio.paused) {
    try {
      await audio.play();
      state.musicPlaying = true;
      dock.classList.add('playing');
      button.setAttribute('aria-label', '暂停背景音乐');
      $('#music-state').textContent = '正在缓缓播放';
    } catch {
      showToast('浏览器阻止了播放，请再次点击唱片');
    }
  } else {
    audio.pause();
    state.musicPlaying = false;
    dock.classList.remove('playing');
    button.setAttribute('aria-label', '播放背景音乐');
    $('#music-state').textContent = '音乐已暂停';
  }
}

function currentOverlay() {
  return $('#lightbox.open') || $('.modal.open');
}

function setPageInert(inert) {
  $$('nav, main, footer, #music-dock, #mobile-menu').forEach(element => {
    element.inert = inert;
  });
}

function activateOverlay(overlay, preferredFocus) {
  if (!state.overlayReturnFocus && document.activeElement instanceof HTMLElement) {
    state.overlayReturnFocus = document.activeElement;
  }
  document.body.classList.add('modal-open');
  setPageInert(true);
  requestAnimationFrame(() => {
    const target = preferredFocus || overlay.querySelector('button, input, textarea, [tabindex]:not([tabindex="-1"])');
    target?.focus({ preventScroll: true });
  });
}

function deactivateOverlayIfIdle() {
  if (currentOverlay()) return;
  document.body.classList.remove('modal-open');
  setPageInert(false);
  const returnFocus = state.overlayReturnFocus;
  state.overlayReturnFocus = null;
  returnFocus?.focus?.({ preventScroll: true });
}

function trapOverlayFocus(event) {
  if (event.key !== 'Tab') return;
  const overlay = currentOverlay();
  if (!overlay) return;
  const focusable = $$('button:not([disabled]), input:not([disabled]), textarea:not([disabled]), a[href], [tabindex]:not([tabindex="-1"])', overlay)
    .filter(element => element.getClientRects().length > 0);
  if (!focusable.length) {
    event.preventDefault();
    return;
  }
  const first = focusable[0];
  const last = focusable[focusable.length - 1];
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}

function clampLightboxPan() {
  const stage = $('#lightbox-stage');
  const image = $('#lightbox-image');
  if (state.zoom <= 1 || !image.clientWidth || !image.clientHeight) {
    state.panX = 0;
    state.panY = 0;
    return;
  }
  const maxX = Math.max(0, (image.clientWidth * state.zoom - stage.clientWidth) / 2);
  const maxY = Math.max(0, (image.clientHeight * state.zoom - stage.clientHeight) / 2);
  state.panX = Math.min(maxX, Math.max(-maxX, state.panX));
  state.panY = Math.min(maxY, Math.max(-maxY, state.panY));
}

function applyLightboxTransform() {
  clampLightboxPan();
  $('#lightbox-image').style.transform = `translate3d(${state.panX}px, ${state.panY}px, 0) scale(${state.zoom})`;
  $('#lightbox-stage').classList.toggle('is-zoomed', state.zoom > 1);
}

function setZoom(nextZoom, clientX, clientY) {
  const oldZoom = state.zoom;
  const zoom = Math.min(3, Math.max(1, nextZoom));
  if (zoom === oldZoom) return;

  if (clientX != null && clientY != null && oldZoom > 0) {
    const rect = $('#lightbox-stage').getBoundingClientRect();
    const focusX = clientX - rect.left - rect.width / 2;
    const focusY = clientY - rect.top - rect.height / 2;
    const ratio = zoom / oldZoom;
    state.panX = focusX - (focusX - state.panX) * ratio;
    state.panY = focusY - (focusY - state.panY) * ratio;
  }

  state.zoom = zoom;
  applyLightboxTransform();
}

function changeZoom(amount, clientX, clientY) {
  setZoom(state.zoom + amount, clientX, clientY);
}

function resetLightboxTransform() {
  state.zoom = 1;
  state.panX = 0;
  state.panY = 0;
  state.lightboxPointers.clear();
  state.gesture = null;
  $('#lightbox-stage').classList.remove('is-interacting');
  applyLightboxTransform();
}

function openLightbox(index) {
  if (!state.photos.length || !Number.isFinite(index) || index < 0) return;
  state.lightboxIndex = (index + state.photos.length) % state.photos.length;
  renderLightbox();
  const lightbox = $('#lightbox');
  lightbox.classList.add('open');
  activateOverlay(lightbox, $('#lightbox-close-button'));
}

function renderLightbox() {
  const photo = state.photos[state.lightboxIndex];
  const image = $('#lightbox-image');
  resetLightboxTransform();
  image.src = photo.src;
  image.alt = photo.title;
  image.onload = applyLightboxTransform;
  $('#lightbox-caption').textContent = `${photo.title} · ${formatDate(photo.date)}`;
  $('#lightbox-count').textContent = `${state.lightboxIndex + 1} / ${state.photos.length}`;
}

function closeLightbox() {
  const lightbox = $('#lightbox');
  if (!lightbox.classList.contains('open')) return;
  lightbox.classList.remove('open');
  state.lightboxPointers.clear();
  state.gesture = null;
  $('#lightbox-stage').classList.remove('is-interacting');
  deactivateOverlayIfIdle();
}

function moveLightbox(direction) {
  if (!state.photos.length) return;
  state.lightboxIndex = (state.lightboxIndex + direction + state.photos.length) % state.photos.length;
  renderLightbox();
}

function openModal(modalId) {
  const modal = $(`#${modalId}`);
  if (!modal) return;
  modal.classList.add('open');
  const preferredFocus = modalId === 'login-modal' ? $('#admin-password') : modal.querySelector('.tab-button.active, button, input');
  activateOverlay(modal, preferredFocus);
}

function closeModal(modalId, { preservePath = false } = {}) {
  const modal = $(`#${modalId}`);
  if (!modal?.classList.contains('open')) return;
  modal.classList.remove('open');
  deactivateOverlayIfIdle();
  if (!preservePath && location.pathname === '/admin') history.replaceState({}, '', '/');
}

function requireAdmin() {
  if (state.adminAuthenticated) return true;
  openModal('login-modal');
  return false;
}

function clearAdminSession() {
  state.adminAuthenticated = false;
  state.adminSessionChecked = true;
}

async function checkAdminSession({ force = false } = {}) {
  if (state.adminSessionPromise) return state.adminSessionPromise;
  if (state.adminSessionChecked && !force) return state.adminAuthenticated;

  state.adminSessionPromise = apiRequest('/api/admin/session', { timeoutMs: 6000 })
    .then(session => {
      state.adminAuthenticated = session?.authenticated === true;
      return state.adminAuthenticated;
    })
    .catch(error => {
      state.adminAuthenticated = false;
      if (![401, 403, 404].includes(error.status)) console.warn('管理员会话探测失败', error);
      return false;
    })
    .finally(() => {
      state.adminSessionChecked = true;
      state.adminSessionPromise = null;
    });
  return state.adminSessionPromise;
}

function handleAdminError(error) {
  if (error.status === 401) {
    clearAdminSession();
    closeModal('admin-modal');
    openModal('login-modal');
    showToast('登录已经过期，请重新输入口令');
  } else {
    showToast(error.message);
  }
}

async function loginAdmin(event) {
  event.preventDefault();
  $('#login-error').textContent = '';

  try {
    await apiRequest('/api/admin/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ password: $('#admin-password').value })
    });
    state.adminAuthenticated = true;
    state.adminSessionChecked = true;
    event.target.reset();
    closeModal('login-modal', { preservePath: true });
    openAdminPanel();
    showToast('欢迎回到秘密后台');
  } catch (error) {
    $('#login-error').textContent = error.message;
  }
}

function openAdminPanel() {
  if (!state.adminAuthenticated) {
    openModal('login-modal');
    return;
  }
  openModal('admin-modal');
  history.replaceState({}, '', '/admin');
  loadAdminMessages();
  loadAdminTimeline();
}

async function logoutAdmin() {
  let serverSessionCleared = false;
  try {
    await apiRequest('/api/admin/logout', { method: 'POST' });
    serverSessionCleared = true;
  } catch (error) {
    // An already-expired session is also safely logged out. A network/server
    // failure cannot clear an HttpOnly cookie, so do not claim that it did.
    serverSessionCleared = [401, 403].includes(error.status);
  }
  clearAdminSession();
  closeModal('admin-modal');
  showToast(serverSessionCleared ? '已经退出管理后台' : '后台已关闭，但服务器会话注销失败，请稍后重试');
}

function revokeTimelinePreviewUrl() {
  if (!state.previewObjectUrl) return;
  URL.revokeObjectURL(state.previewObjectUrl);
  state.previewObjectUrl = '';
}

function setTimelinePreview(source = '', { objectUrl = false } = {}) {
  const preview = $('#upload-preview');
  if (state.previewObjectUrl && state.previewObjectUrl !== source) revokeTimelinePreviewUrl();
  if (objectUrl) state.previewObjectUrl = source;
  if (!source) {
    preview.removeAttribute('src');
    preview.classList.add('hidden');
    return;
  }
  preview.src = source;
  preview.classList.remove('hidden');
}

function isAllowedImagePath(value) {
  return !value || /^\/(?:static|photos)\/[^\s]+$/.test(value);
}

function validatePhotoFile(file, { notify = true } = {}) {
  if (!file) return false;
  if (!ALLOWED_UPLOAD_TYPES.has(file.type)) {
    const message = '仅支持 JPG、PNG 或 WebP 图片';
    $('#upload-status').textContent = message;
    if (notify) showToast(message);
    return false;
  }
  if (file.size > MAX_UPLOAD_BYTES) {
    const message = '图片不能超过 5 MiB，请压缩后重试';
    $('#upload-status').textContent = message;
    if (notify) showToast(message);
    return false;
  }
  return true;
}

async function uploadPhoto(options = {}) {
  if (state.uploadPromise) return state.uploadPromise;
  state.uploadPromise = performPhotoUpload(options);
  try {
    return await state.uploadPromise;
  } finally {
    state.uploadPromise = null;
  }
}

async function performPhotoUpload({ silent = false } = {}) {
  const file = $('#photo-file').files[0];
  if (!file) {
    if (!silent) showToast('请先选择一张照片');
    return null;
  }
  if (!validatePhotoFile(file, { notify: !silent })) return null;

  const button = $('#upload-button');
  button.disabled = true;
  $('#upload-status').textContent = '正在上传并安全保存照片…';

  try {
    const formData = new FormData();
    formData.append('file', file);
    const result = await apiRequest('/api/admin/upload', {
      method: 'POST',
      body: formData,
      timeoutMs: 45000
    });
    $('#timeline-image').value = result.url;
    $('#timeline-thumbnail').value = result.thumbnail_url || result.thumbnail || '';
    $('#photo-file').value = '';
    setTimelinePreview(result.thumbnail_url || result.thumbnail || result.url);
    $('#upload-status').textContent = '照片上传完成，地址已自动填写。';
    if (!silent) showToast('照片上传成功');
    return result;
  } catch (error) {
    $('#upload-status').textContent = error.message;
    if (!silent) {
      handleAdminError(error);
      return null;
    }
    throw error;
  } finally {
    button.disabled = false;
  }
}

function resetTimelineForm() {
  revokeTimelinePreviewUrl();
  $('#timeline-form').reset();
  $('#editing-timeline-id').value = '';
  $('#timeline-thumbnail').value = '';
  $('#timeline-form-heading').textContent = '添加一段新时光';
  $('#timeline-form-hint').textContent = '选择照片后，保存时会自动上传并关联到这条记录。';
  $('#timeline-submit-button').innerHTML = '<i data-lucide="plus" class="w-4 h-4"></i><span>加入时光机</span>';
  $('#cancel-timeline-edit-button').classList.add('hidden');
  $('#upload-status').textContent = '';
  setTimelinePreview();
  refreshIcons();
}

async function addTimelineEntry(event) {
  event.preventDefault();
  const editId = $('#editing-timeline-id').value;
  const submitButton = $('#timeline-submit-button');
  submitButton.disabled = true;

  try {
    let image = $('#timeline-image').value.trim();
    let thumbnail = $('#timeline-thumbnail').value.trim();
    if ($('#photo-file').files[0]) {
      const upload = await uploadPhoto({ silent: true });
      if (!upload) throw new Error('照片未能上传，请检查文件后重试');
      image = upload.url;
      thumbnail = upload.thumbnail_url || upload.thumbnail || '';
    }
    if (!isAllowedImagePath(image) || !isAllowedImagePath(thumbnail)) {
      throw new Error('照片只能使用本站 /static/ 或 /photos/ 路径');
    }
    const payload = {
      date: $('#timeline-date').value,
      title: $('#timeline-title').value.trim(),
      description: $('#timeline-description').value.trim(),
      image,
      thumbnail
    };
    await apiRequest(editId ? `/api/admin/timeline/${encodeURIComponent(editId)}` : '/api/timeline', {
      method: editId ? 'PUT' : 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    });
    resetTimelineForm();
    await refreshTimelineViews();
    showToast(editId ? '这段时光已经更新' : '新的回忆已经加入时光机');
  } catch (error) {
    handleAdminError(error);
  } finally {
    submitButton.disabled = false;
  }
}

async function loadAdminTimeline(options = {}) {
  if (!state.adminAuthenticated) return;
  try {
    await fetchTimeline(options);
    renderAdminTimeline();
  } catch (error) {
    handleAdminError(error);
  }
}

function renderAdminTimeline() {
  const container = $('#admin-timeline-list');
  if (!container) return;
  $('#admin-timeline-count').textContent = `${state.timeline.length} 条记录`;
  container.innerHTML = state.timeline.length ? [...state.timeline].sort((a, b) => b.date.localeCompare(a.date)).map(item => {
    const thumbnailSource = item.thumbnail || item.image;
    const thumbnail = thumbnailSource
      ? `<img class="admin-timeline-thumb" src="${escapeHtml(thumbnailSource)}" alt="${escapeHtml(item.title)}" loading="lazy" decoding="async" width="48" height="48">`
      : '<span class="admin-timeline-thumb admin-timeline-empty-thumb"><i data-lucide="image-off" class="w-4 h-4"></i></span>';
    return `<div class="admin-timeline-row">
      ${thumbnail}
      <div class="min-w-0 flex-1">
        <div class="truncate text-[13px] font-semibold">${escapeHtml(item.title)}</div>
        <div class="mt-1 text-[11px]" style="color:var(--muted)">${escapeHtml(formatDate(item.date))}${item.image ? '' : ' · 未附照片'}</div>
      </div>
      <div class="flex items-center gap-1">
        <button class="icon-button admin-timeline-edit-button" type="button" data-timeline-id="${escapeHtml(item.id)}" title="编辑时光" aria-label="编辑 ${escapeHtml(item.title)}"><i data-lucide="pencil" class="w-4 h-4"></i></button>
        <button class="icon-button admin-timeline-delete-button" type="button" data-timeline-id="${escapeHtml(item.id)}" title="删除时光" aria-label="删除 ${escapeHtml(item.title)}"><i data-lucide="trash-2" class="w-4 h-4"></i></button>
      </div>
    </div>`;
  }).join('') : '<p class="text-[13px]" style="color:var(--muted)">还没有时光记录。</p>';
  $$('.admin-timeline-edit-button', container).forEach(button => {
    button.addEventListener('click', () => startTimelineEdit(button.dataset.timelineId));
  });
  $$('.admin-timeline-delete-button', container).forEach(button => {
    button.addEventListener('click', () => deleteTimeline(button.dataset.timelineId));
  });
  refreshIcons();
}

function startTimelineEdit(timelineId) {
  const item = state.timeline.find(entry => String(entry.id) === String(timelineId));
  if (!item) {
    showToast('未找到这条时光记录，请刷新后重试');
    return;
  }
  $('#editing-timeline-id').value = item.id;
  $('#timeline-date').value = item.date;
  $('#timeline-title').value = item.title;
  $('#timeline-description').value = item.description;
  $('#timeline-image').value = item.image || '';
  $('#timeline-thumbnail').value = item.thumbnail || '';
  $('#photo-file').value = '';
  $('#timeline-form-heading').textContent = '编辑这段时光';
  $('#timeline-form-hint').textContent = '保留原图无需重新选择照片；选择新照片后会替换原图。';
  $('#timeline-submit-button').innerHTML = '<i data-lucide="save" class="w-4 h-4"></i><span>保存修改</span>';
  $('#cancel-timeline-edit-button').classList.remove('hidden');
  $('#upload-status').textContent = item.image ? '当前已关联照片。' : '当前未关联照片。';
  setTimelinePreview(item.thumbnail || item.image || '');
  refreshIcons();
  $('#timeline-form').scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function deleteTimeline(timelineId) {
  const item = state.timeline.find(entry => String(entry.id) === String(timelineId));
  if (!item || !confirm(`确定删除“${item.title}”吗？此操作无法恢复。`)) return;
  try {
    await apiRequest(`/api/admin/timeline/${encodeURIComponent(timelineId)}`, {
      method: 'DELETE'
    });
    if ($('#editing-timeline-id').value === String(timelineId)) resetTimelineForm();
    await refreshTimelineViews();
    showToast('这段时光已经删除');
  } catch (error) {
    handleAdminError(error);
  }
}

async function loadAdminMessages(options = {}) {
  if (!state.adminAuthenticated) return;
  try {
    await fetchMessages(options);
    renderAdminMessages();
  } catch (error) {
    handleAdminError(error);
  }
}

function renderAdminMessages() {
  const container = $('#admin-message-list');
  if (!container) return;
  container.innerHTML = state.messages.length ? state.messages.map(message => `
    <div class="flex items-center gap-4 py-4 border-b" style="border-color:var(--line)">
      <div class="min-w-0 flex-1">
        <div class="text-[13px] font-semibold">${escapeHtml(message.nickname)}</div>
        <div class="mt-1 truncate text-[11px]" style="color:var(--muted)">${escapeHtml(message.content)}</div>
      </div>
      <button class="icon-button admin-delete-button" type="button" data-message-id="${escapeHtml(message.id)}" title="删除留言" aria-label="删除 ${escapeHtml(message.nickname)} 的留言"><i data-lucide="trash-2" class="w-4 h-4"></i></button>
    </div>`).join('') : '<p class="text-[13px]" style="color:var(--muted)">暂无留言。</p>';

  $$('.admin-delete-button', container).forEach(button => {
    button.addEventListener('click', () => deleteMessage(button.dataset.messageId));
  });
  refreshIcons();
}

async function deleteMessage(messageId) {
  if (!confirm('确定删除这条留言吗？')) return;
  try {
    await apiRequest(`/api/messages/${encodeURIComponent(messageId)}`, { method: 'DELETE' });
    await refreshMessageViews();
    showToast('留言已经删除');
  } catch (error) {
    handleAdminError(error);
  }
}

async function changeAdminPassword(event) {
  event.preventDefault();
  try {
    await apiRequest('/api/admin/password', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        current_password: $('#current-password').value,
        new_password: $('#new-password').value
      })
    });
    event.target.reset();
    clearAdminSession();
    closeModal('admin-modal');
    showToast('口令已更新，请使用新口令重新登录');
  } catch (error) {
    handleAdminError(error);
  }
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  $('#theme-button').innerHTML = `<i data-lucide="${theme === 'dark' ? 'sun' : 'moon'}" class="w-[17px] h-[17px]"></i>`;
  refreshIcons();
}

function setMobileMenu(open) {
  $('#mobile-menu').classList.toggle('open', open);
  $('#menu-button').setAttribute('aria-expanded', String(open));
  $('#menu-button').setAttribute('aria-label', open ? '关闭导航' : '打开导航');
}

async function openAdminEntry() {
  const authenticated = await checkAdminSession({ force: true });
  if (authenticated) openAdminPanel();
  else openModal('login-modal');
}

async function handleAdminRoute() {
  openModal('login-modal');
  $('#login-error').textContent = '正在确认登录状态…';
  const authenticated = await checkAdminSession();
  if (authenticated) {
    closeModal('login-modal', { preservePath: true });
    openAdminPanel();
  } else {
    $('#login-error').textContent = '';
  }
}

function lightboxPointerMetrics() {
  const points = [...state.lightboxPointers.values()];
  if (points.length < 2) return null;
  const [first, second] = points;
  return {
    distance: Math.hypot(second.x - first.x, second.y - first.y),
    midX: (first.x + second.x) / 2,
    midY: (first.y + second.y) / 2
  };
}

function handleLightboxPointerDown(event) {
  if (event.pointerType === 'mouse' && event.button !== 0) return;
  event.currentTarget.setPointerCapture(event.pointerId);
  event.currentTarget.classList.add('is-interacting');
  state.lightboxPointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
  const metrics = lightboxPointerMetrics();
  state.gesture = metrics
    ? { type: 'pinch', ...metrics }
    : { type: 'pan', x: event.clientX, y: event.clientY };
}

function handleLightboxPointerMove(event) {
  if (!state.lightboxPointers.has(event.pointerId)) return;
  state.lightboxPointers.set(event.pointerId, { x: event.clientX, y: event.clientY });

  const metrics = lightboxPointerMetrics();
  if (metrics) {
    if (state.gesture?.type === 'pinch' && state.gesture.distance > 0) {
      state.panX += metrics.midX - state.gesture.midX;
      state.panY += metrics.midY - state.gesture.midY;
      setZoom(state.zoom * (metrics.distance / state.gesture.distance), metrics.midX, metrics.midY);
    }
    state.gesture = { type: 'pinch', ...metrics };
    return;
  }

  if (state.gesture?.type === 'pan' && state.zoom > 1) {
    state.panX += event.clientX - state.gesture.x;
    state.panY += event.clientY - state.gesture.y;
    applyLightboxTransform();
  }
  state.gesture = { type: 'pan', x: event.clientX, y: event.clientY };
}

function handleLightboxPointerEnd(event) {
  state.lightboxPointers.delete(event.pointerId);
  if (event.currentTarget.hasPointerCapture(event.pointerId)) {
    event.currentTarget.releasePointerCapture(event.pointerId);
  }
  const remaining = [...state.lightboxPointers.values()];
  if (!remaining.length) event.currentTarget.classList.remove('is-interacting');
  state.gesture = remaining.length === 1
    ? { type: 'pan', x: remaining[0].x, y: remaining[0].y }
    : null;
}

function bindPageEvents() {
  bind('#message-form', 'submit', submitMessage);
  bind('#message-content', 'input', event => $('#message-character-count').textContent = event.target.value.length);
  bind('#music-button', 'click', toggleMusic);
  bind('#gallery-more-button', 'click', () => {
    state.galleryLimit = state.photos.length;
    renderGallery();
  });

  bind('#theme-button', 'click', () => {
    const nextTheme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
    localStorage.setItem('love_theme', nextTheme);
    applyTheme(nextTheme);
  });

  bind('#admin-button', 'click', openAdminEntry);
  bind('#menu-button', 'click', () => setMobileMenu(!$('#mobile-menu').classList.contains('open')));
  $$('#mobile-menu a').forEach(link => link.addEventListener('click', () => setMobileMenu(false)));

  bind('#login-form', 'submit', loginAdmin);
  bind('#logout-button', 'click', logoutAdmin);
  bind('#upload-button', 'click', uploadPhoto);
  bind('#timeline-form', 'submit', addTimelineEntry);
  bind('#cancel-timeline-edit-button', 'click', resetTimelineForm);
  bind('#password-form', 'submit', changeAdminPassword);

  bind('#photo-file', 'change', event => {
    const file = event.target.files[0];
    if (!file) return;
    if (!validatePhotoFile(file)) {
      event.target.value = '';
      setTimelinePreview();
      return;
    }
    $('#timeline-thumbnail').value = '';
    setTimelinePreview(URL.createObjectURL(file), { objectUrl: true });
    $('#upload-status').textContent = '将于保存时自动上传这张照片。';
  });

  bind('#timeline-image', 'change', event => {
    const value = event.target.value.trim();
    $('#timeline-thumbnail').value = '';
    if (!isAllowedImagePath(value)) {
      setTimelinePreview();
      $('#upload-status').textContent = '照片只能使用本站 /static/ 或 /photos/ 路径。';
      return;
    }
    setTimelinePreview(value);
  });
  bind('#upload-preview', 'error', () => {
    revokeTimelinePreviewUrl();
    $('#upload-preview').classList.add('hidden');
    $('#upload-status').textContent = '这张照片无法预览，请检查地址或重新选择图片。';
  });

  $$('.modal-close-button').forEach(button => {
    button.addEventListener('click', () => closeModal(button.dataset.close));
  });

  $$('.modal').forEach(modal => {
    modal.addEventListener('click', event => {
      if (event.target === modal) closeModal(modal.id);
    });
  });

  $$('.tab-button').forEach(button => {
    button.addEventListener('click', () => {
      $$('.tab-button').forEach(tab => tab.classList.remove('active'));
      $$('.tab-panel').forEach(panel => panel.classList.remove('active'));
      button.classList.add('active');
      $(`#${button.dataset.tab}`).classList.add('active');
      if (button.dataset.tab === 'admin-timeline-panel') loadAdminTimeline();
      if (button.dataset.tab === 'admin-messages-panel') loadAdminMessages();
    });
  });

  bind('#lightbox-close-button', 'click', closeLightbox);
  bind('#lightbox-prev-button', 'click', () => moveLightbox(-1));
  bind('#lightbox-next-button', 'click', () => moveLightbox(1));
  bind('#zoom-in-button', 'click', () => changeZoom(0.25));
  bind('#zoom-out-button', 'click', () => changeZoom(-0.25));
  bind('#lightbox-stage', 'wheel', event => {
    event.preventDefault();
    changeZoom(event.deltaY < 0 ? 0.2 : -0.2, event.clientX, event.clientY);
  }, { passive: false });
  bind('#lightbox-stage', 'pointerdown', handleLightboxPointerDown);
  bind('#lightbox-stage', 'pointermove', handleLightboxPointerMove);
  bind('#lightbox-stage', 'pointerup', handleLightboxPointerEnd);
  bind('#lightbox-stage', 'pointercancel', handleLightboxPointerEnd);
  bind('#lightbox-stage', 'dblclick', event => {
    setZoom(state.zoom > 1 ? 1 : 2, event.clientX, event.clientY);
  });

  document.addEventListener('keydown', event => {
    trapOverlayFocus(event);
    if (event.key === 'Escape') {
      if ($('#lightbox').classList.contains('open')) closeLightbox();
      else {
        const modal = $('.modal.open');
        if (modal) closeModal(modal.id);
      }
      setMobileMenu(false);
      return;
    }
    if ($('#lightbox').classList.contains('open')) {
      if (event.key === 'ArrowLeft') moveLightbox(-1);
      if (event.key === 'ArrowRight') moveLightbox(1);
      if (event.key === '+') changeZoom(0.25);
      if (event.key === '-') changeZoom(-0.25);
    }
  });
  window.addEventListener('resize', applyLightboxTransform);
  window.addEventListener('beforeunload', revokeTimelinePreviewUrl);
}

function initializePage() {
  const savedTheme = localStorage.getItem('love_theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  applyTheme(savedTheme);
  bindPageEvents();
  refreshIcons();
  observeRevealElements();
  updateRelationshipClock();
  setInterval(updateRelationshipClock, 1000);

  if (location.pathname === '/admin') void handleAdminRoute();
  else void checkAdminSession();

  void Promise.allSettled([loadTimeline(), loadWishlist(), loadMessages()]);

  if (location.hash) {
    requestAnimationFrame(() => {
      try {
        document.querySelector(location.hash)?.scrollIntoView({ block: 'start' });
      } catch {}
    });
  }
}

initializePage();
