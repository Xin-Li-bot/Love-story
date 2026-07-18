    const ANNIVERSARY = new Date('2022-12-25T00:00:00+08:00');
    const state = {
      timeline: [],
      photos: [],
      galleryLimit: 12,
      lightboxIndex: 0,
      zoom: 1,
      adminAuthenticated: false,
      adminSessionChecked: false,
      wishes: [],
      anniversaries: [],
      messages: [],
      capsules: [],
      moods: [],
      dateIdeas: [],
      quotes: [],
      musicPlaying: false
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

    function adminHeaders() {
      // 管理员认证由 httpOnly Cookie（love_story_session）自动携带，无需额外请求头
      return {};
    }

    async function apiRequest(url, options = {}) {
      const response = await fetch(url, { credentials: 'same-origin', ...options });
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
      return new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: 'long', day: 'numeric' }).format(date);
    }

    function formatInteger(value) {
      return new Intl.NumberFormat('zh-CN').format(value);
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

    async function loadTimeline() {
      try {
        state.timeline = await apiRequest('/api/timeline');
        state.photos = state.timeline
          .filter(item => item.image && item.image.trim())
          .map(item => ({ src: item.image, title: item.title, date: item.date }));
        renderTimeline();
        renderGallery();
      } catch (error) {
        $('#timeline-list').innerHTML = `<p class="text-center text-[14px]" style="color:var(--muted)">${escapeHtml(error.message)}</p>`;
        $('#gallery-grid').innerHTML = `<p class="col-span-full text-center text-[14px]" style="color:var(--muted)">相册暂时无法载入。</p>`;
      }
    }

    function createTimelineCard(item) {
      const image = item.image ? `
        <button class="timeline-image-button" type="button" data-photo-src="${escapeHtml(item.image)}" aria-label="放大查看 ${escapeHtml(item.title)}">
          <img class="timeline-image" src="${escapeHtml(item.image)}" alt="${escapeHtml(item.title)}" loading="lazy">
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
        const card = `<div>${createTimelineCard(item)}</div>`;
        const spacer = '<div class="timeline-spacer"></div>';
        return `<div class="timeline-row">${index % 2 === 0 ? `${card}${spacer}` : `${spacer}${card}`}</div>`;
      }).join('');

      $$('[data-photo-src]', container).forEach(button => {
        button.addEventListener('click', () => {
          const photoIndex = state.photos.findIndex(photo => photo.src === button.dataset.photoSrc);
          openLightbox(Math.max(0, photoIndex));
        });
      });

      refreshIcons();
      observeRevealElements();
    }

    function renderGallery() {
      const grid = $('#gallery-grid');
      const visiblePhotos = state.photos.slice(0, state.galleryLimit);
      if (!visiblePhotos.length) {
        grid.innerHTML = '<p class="col-span-full text-center text-[14px]" style="color:var(--muted)">还没有可以展示的照片。</p>';
        return;
      }

      grid.innerHTML = visiblePhotos.map((photo, index) => `
        <button class="gallery-card reveal rounded-3xl shadow-[0_4px_20px_rgb(0,0,0,0.03)] hover:-translate-y-1 hover:shadow-[0_12px_30px_rgb(0,0,0,0.08)] transition-all duration-500 ease-out" type="button" data-gallery-index="${index}" aria-label="放大查看 ${escapeHtml(photo.title)}">
          <img class="gallery-image" src="${escapeHtml(photo.src)}" alt="${escapeHtml(photo.title)}" loading="lazy">
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
        const wishes = await apiRequest('/api/wishlist');
        state.wishes = wishes;
        renderWishlist(wishes);
      } catch (error) {
        $('#wishlist-grid').innerHTML = `<p class="text-center text-[14px]" style="color:var(--muted)">${escapeHtml(error.message)}</p>`;
      }
    }

    function renderWishlist(wishes) {
      const icons = ['map-pinned', 'sparkles', 'music-2', 'cat', 'sunrise', 'castle'];
      const grid = $('#wishlist-grid');
      grid.innerHTML = wishes.map((wish, index) => `
        <button class="wish-card reveal rounded-3xl shadow-[0_4px_20px_rgb(0,0,0,0.03)] hover:-translate-y-1 hover:shadow-[0_12px_30px_rgb(0,0,0,0.08)] transition-all duration-500 ease-out ${wish.completed ? 'completed' : ''}" type="button" data-wish-id="${wish.id}" aria-pressed="${Boolean(wish.completed)}">
          <span class="flex items-center gap-4 min-w-0">
            <span class="wish-icon"><i data-lucide="${icons[index % icons.length]}" class="w-5 h-5"></i></span>
            <span class="min-w-0">
              <strong class="wish-title block text-[15px] font-semibold">${escapeHtml(wish.title)}</strong>
              <small class="block mt-1 text-[11px]" style="color:var(--faint)">${wish.completed ? `完成于 ${escapeHtml(wish.completed_at || '某个美好时刻')}` : '等待我们一起完成'}</small>
            </span>
          </span>
          <span class="wish-checkbox" aria-hidden="true"><i data-lucide="check"></i></span>
        </button>`).join('');

      $$('.wish-card', grid).forEach(button => {
        button.addEventListener('click', () => toggleWish(button.dataset.wishId));
      });

      refreshIcons();
      observeRevealElements();
    }

    async function toggleWish(wishId) {
      if (!requireAdmin()) {
        showToast('完成心愿需要先进入我们的秘密后台');
        return;
      }

      const wish = (state.wishes || []).find(item => String(item.id) === String(wishId));
      const desired = wish ? !Boolean(wish.completed) : true;
      try {
        await apiRequest(`/api/wishlist/${encodeURIComponent(wishId)}`, {
          method: 'PATCH',
          headers: { ...adminHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify({ completed: desired })
        });
        await loadWishlist();
        showToast('心愿状态已经更新');
      } catch (error) {
        handleAdminError(error);
      }
    }

    function daysBetween(fromDate, toDate) {
      const start = new Date(fromDate.getFullYear(), fromDate.getMonth(), fromDate.getDate());
      const end = new Date(toDate.getFullYear(), toDate.getMonth(), toDate.getDate());
      return Math.round((end - start) / 86400000);
    }

    function describeAnniversary(item, today) {
      const base = new Date(`${item.date}T00:00:00`);
      if (Number.isNaN(base.valueOf())) {
        return { badge: '纪念', number: '--', label: '', sub: item.date };
      }
      if (item.recurring) {
        let next = new Date(today.getFullYear(), base.getMonth(), base.getDate());
        if (next < today) next = new Date(today.getFullYear() + 1, base.getMonth(), base.getDate());
        const remaining = daysBetween(today, next);
        const years = next.getFullYear() - base.getFullYear();
        if (remaining === 0) {
          return { badge: '每年', number: '今天', label: `第 ${years} 个纪念日`, sub: `${formatDate(item.date)} 起` };
        }
        return { badge: '每年', number: formatInteger(remaining), label: `天后 · 第 ${years} 个纪念日`, sub: `${formatDate(item.date)} 起` };
      }
      const diff = daysBetween(today, base);
      if (diff === 0) return { badge: '纪念', number: '今天', label: '就是今天', sub: formatDate(item.date) };
      if (diff > 0) return { badge: '纪念', number: formatInteger(diff), label: '天后到来', sub: formatDate(item.date) };
      return { badge: '纪念', number: formatInteger(Math.abs(diff)), label: '天前发生', sub: formatDate(item.date) };
    }

    async function loadAnniversaries() {
      try {
        const items = await apiRequest('/api/anniversaries');
        state.anniversaries = items;
        renderAnniversaries(items);
      } catch (error) {
        const grid = $('#anniversary-grid');
        if (grid) grid.innerHTML = `<p class="text-center text-[14px]" style="color:var(--muted)">${escapeHtml(error.message)}</p>`;
      }
    }

    function renderAnniversaries(items) {
      const grid = $('#anniversary-grid');
      if (!grid) return;
      if (!items.length) {
        grid.innerHTML = '<p class="text-center text-[14px]" style="color:var(--muted)">还没有记录纪念日，去后台添加你们值得铭记的日子吧。</p>';
        return;
      }
      const icons = ['calendar-heart', 'gift', 'cake', 'heart', 'star', 'sparkles'];
      const now = new Date();
      const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      grid.innerHTML = items.map((item, index) => {
        const info = describeAnniversary(item, today);
        const note = item.note ? `<p class="anniversary-note">${escapeHtml(item.note)}</p>` : '';
        return `<article class="anniversary-card reveal shadow-[0_4px_20px_rgb(0,0,0,0.03)] hover:-translate-y-1 hover:shadow-[0_12px_30px_rgb(0,0,0,0.08)] transition-all duration-500 ease-out">
          <div class="anniversary-card-head">
            <span class="anniversary-icon"><i data-lucide="${icons[index % icons.length]}" class="w-5 h-5"></i></span>
            <div class="min-w-0">
              <strong class="block text-[15px] font-semibold truncate">${escapeHtml(item.title)}</strong>
              <span class="anniversary-date">${escapeHtml(info.sub)}</span>
            </div>
          </div>
          <span class="anniversary-badge">${escapeHtml(info.badge)}</span>
          <div class="anniversary-countdown">
            <span class="anniversary-count">${escapeHtml(info.number)}</span>
            <span class="anniversary-count-label">${escapeHtml(info.label)}</span>
          </div>
          ${note}
        </article>`;
      }).join('');
      refreshIcons();
      observeRevealElements();
    }

    function renderDashboard() {
      const grid = $('#dashboard-grid');
      if (!grid) return;
      const now = new Date();
      const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      const days = Math.max(0, daysBetween(ANNIVERSARY, today));
      const wishesDone = (state.wishes || []).filter(item => item.completed).length;
      const tiles = [
        { icon: 'heart', number: formatInteger(days), label: '相恋天数' },
        { icon: 'clock', number: formatInteger((state.timeline || []).length), label: '时光记忆' },
        { icon: 'image', number: formatInteger((state.photos || []).length), label: '相册照片' },
        { icon: 'sparkles', number: `${formatInteger(wishesDone)}/${formatInteger((state.wishes || []).length)}`, label: '心愿达成' },
        { icon: 'calendar-heart', number: formatInteger((state.anniversaries || []).length), label: '纪念日' },
        { icon: 'mail', number: formatInteger((state.messages || []).length), label: '收到祝福' }
      ];
      grid.innerHTML = tiles.map(tile => `
        <div class="stat-tile reveal">
          <span class="stat-icon"><i data-lucide="${tile.icon}" class="w-5 h-5"></i></span>
          <span class="stat-number">${escapeHtml(tile.number)}</span>
          <span class="stat-label">${escapeHtml(tile.label)}</span>
        </div>`).join('');
      refreshIcons();
      observeRevealElements();
    }

    async function loadCapsules() {
      try {
        const items = await apiRequest('/api/capsules');
        state.capsules = items;
        renderCapsules(items);
      } catch (error) {
        const grid = $('#capsule-grid');
        if (grid) grid.innerHTML = `<p class="text-center text-[14px]" style="color:var(--muted)">${escapeHtml(error.message)}</p>`;
      }
    }

    function renderCapsules(items) {
      const grid = $('#capsule-grid');
      if (!grid) return;
      if (!items.length) {
        grid.innerHTML = '<p class="text-center text-[14px]" style="color:var(--muted)">还没有时间胶囊，去后台写一封给未来的信吧。</p>';
        return;
      }
      const now = new Date();
      const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      grid.innerHTML = items.map(item => {
        if (item.locked) {
          const unlock = new Date(`${item.unlock_date}T00:00:00`);
          const remaining = Math.max(0, daysBetween(today, unlock));
          return `<article class="capsule-card locked reveal">
            <div class="capsule-head"><span class="capsule-icon"><i data-lucide="lock" class="w-5 h-5"></i></span><strong class="capsule-title">${escapeHtml(item.title)}</strong></div>
            <p class="capsule-locked-copy">这封信还在等待被开启</p>
            <div class="capsule-countdown"><span class="capsule-count">${escapeHtml(formatInteger(remaining))}</span><span class="capsule-count-label">天后开启 · ${escapeHtml(formatDate(item.unlock_date))}</span></div>
          </article>`;
        }
        return `<article class="capsule-card reveal">
          <div class="capsule-head"><span class="capsule-icon open"><i data-lucide="mail-open" class="w-5 h-5"></i></span><strong class="capsule-title">${escapeHtml(item.title)}</strong></div>
          <p class="capsule-body">${escapeHtml(item.body)}</p>
          <span class="capsule-date">开启于 ${escapeHtml(formatDate(item.unlock_date))}</span>
        </article>`;
      }).join('');
      refreshIcons();
      observeRevealElements();
    }

    async function loadMoods() {
      try {
        const items = await apiRequest('/api/moods');
        state.moods = items;
        renderMoodHeatmap(items);
      } catch (error) {
        const wrap = $('#mood-heatmap');
        if (wrap) wrap.innerHTML = `<p class="text-center text-[14px]" style="color:var(--muted)">${escapeHtml(error.message)}</p>`;
      }
    }

    function renderMoodHeatmap(items) {
      const wrap = $('#mood-heatmap');
      if (!wrap) return;
      const levelByDate = {};
      const noteByDate = {};
      items.forEach(mood => { levelByDate[mood.date] = mood.level; noteByDate[mood.date] = mood.note || ''; });
      const now = new Date();
      const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
      const start = new Date(today);
      start.setDate(start.getDate() - 363);
      start.setDate(start.getDate() - start.getDay());
      const cursor = new Date(start);
      const columns = [];
      while (cursor <= today) {
        const week = [];
        for (let day = 0; day < 7; day += 1) {
          if (cursor > today) {
            week.push(null);
          } else {
            const iso = `${cursor.getFullYear()}-${String(cursor.getMonth() + 1).padStart(2, '0')}-${String(cursor.getDate()).padStart(2, '0')}`;
            week.push({ iso, level: levelByDate[iso] || 0, note: noteByDate[iso] || '' });
          }
          cursor.setDate(cursor.getDate() + 1);
        }
        columns.push(week);
      }
      wrap.innerHTML = columns.map(week => `<div class="mood-week">${week.map(cell => {
        if (!cell) return '<span class="mood-cell empty"></span>';
        const label = cell.level ? `${cell.iso}：心情 ${cell.level}/5${cell.note ? ' · ' + cell.note : ''}` : `${cell.iso}：暂无记录`;
        return `<span class="mood-cell" data-level="${cell.level}" title="${escapeHtml(label)}"></span>`;
      }).join('')}</div>`).join('');
    }

    async function submitPublicMood(event) {
      event.preventDefault();
      const button = $('#public-mood-submit');
      if (button) button.disabled = true;
      try {
        const date = $('#public-mood-date').value;
        if (!date) { showToast('请选择日期'); return; }
        const payload = {
          level: Number($('#public-mood-level').value),
          note: $('#public-mood-note').value.trim()
        };
        await apiRequest(`/api/moods/${encodeURIComponent(date)}`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        $('#public-mood-note').value = '';
        await loadMoods();
        if (state.adminAuthenticated) await loadAdminMoods();
        showToast('这一天的心情已经记录');
      } catch (error) {
        showToast(error.message);
      } finally {
        if (button) button.disabled = false;
      }
    }

    async function submitPublicCapsule(event) {
      event.preventDefault();
      const button = $('#public-capsule-submit');
      if (button) button.disabled = true;
      try {
        const payload = {
          title: $('#public-capsule-title').value.trim(),
          body: $('#public-capsule-body').value.trim(),
          unlock_date: $('#public-capsule-date').value
        };
        if (!payload.title || !payload.body || !payload.unlock_date) {
          showToast('请填写标题、内容和开启日期');
          return;
        }
        await apiRequest('/api/capsules', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        $('#public-capsule-form').reset();
        await loadCapsules();
        if (state.adminAuthenticated) await loadAdminCapsules();
        showToast('这封信已经封存');
      } catch (error) {
        showToast(error.message);
      } finally {
        if (button) button.disabled = false;
      }
    }

    function initInlineAddDefaults() {
      const now = new Date();
      const iso = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}-${String(now.getDate()).padStart(2, '0')}`;
      const moodDate = $('#public-mood-date');
      if (moodDate && !moodDate.value) moodDate.value = iso;
      const capsuleDate = $('#public-capsule-date');
      if (capsuleDate) capsuleDate.min = iso;
    }

    let rouletteTimer;
    async function loadDateIdeas() {
      try {
        const items = await apiRequest('/api/date-ideas');
        state.dateIdeas = items;
        renderRoulette();
      } catch (error) {
        const display = $('#roulette-display');
        if (display) display.textContent = error.message;
      }
    }

    function renderRoulette() {
      const display = $('#roulette-display');
      const button = $('#roulette-spin-button');
      if (!display) return;
      if (!state.dateIdeas.length) {
        display.textContent = '还没有约会点子，去后台添加一些吧';
        delete display.dataset.picked;
        if (button) button.disabled = true;
        return;
      }
      if (button) button.disabled = false;
      if (!display.dataset.picked) display.textContent = '点击下面的按钮，交给缘分决定';
    }

    function spinRoulette() {
      const ideas = state.dateIdeas;
      if (!ideas.length) return;
      const display = $('#roulette-display');
      const button = $('#roulette-spin-button');
      if (!display) return;
      clearInterval(rouletteTimer);
      display.classList.add('spinning');
      if (button) button.disabled = true;
      let ticks = 0;
      const total = 18 + Math.floor(Math.random() * (ideas.length + 4));
      rouletteTimer = setInterval(() => {
        display.textContent = ideas[Math.floor(Math.random() * ideas.length)].text;
        ticks += 1;
        if (ticks >= total) {
          clearInterval(rouletteTimer);
          display.textContent = ideas[Math.floor(Math.random() * ideas.length)].text;
          display.dataset.picked = '1';
          display.classList.remove('spinning');
          if (button) button.disabled = false;
          showToast('今天就这样约定啦');
        }
      }, 80);
    }

    async function loadLoveQuotes() {
      try {
        const items = await apiRequest('/api/love-quotes');
        state.quotes = items;
        renderLoveQuote(false);
      } catch (error) {
        const card = $('#quote-card');
        if (card) card.textContent = error.message;
      }
    }

    function renderLoveQuote(randomize) {
      const card = $('#quote-card');
      const button = $('#quote-shuffle-button');
      if (!card) return;
      if (!state.quotes.length) {
        card.textContent = '还没有情话，去后台写下第一句吧。';
        if (button) button.disabled = true;
        return;
      }
      if (button) button.disabled = false;
      let index;
      if (randomize) {
        index = Math.floor(Math.random() * state.quotes.length);
      } else {
        index = Math.floor(Date.now() / 86400000) % state.quotes.length;
      }
      card.textContent = state.quotes[index].text;
    }

    async function loadMessages() {
      try {
        const messages = await apiRequest('/api/messages');
        state.messages = messages;
        renderMessages(messages);
      } catch (error) {
        $('#message-list').innerHTML = `<p class="text-[14px]" style="color:var(--muted)">${escapeHtml(error.message)}</p>`;
      }
    }

    function renderMessages(messages) {
      const container = $('#message-list');
      if (!messages.length) {
        container.innerHTML = '<p class="text-[14px]" style="color:var(--muted)">还没有留言，来留下第一份祝福吧。</p>';
        return;
      }

      container.innerHTML = messages.map(message => `
        <article class="message-bubble reveal rounded-3xl shadow-[0_4px_20px_rgb(0,0,0,0.03)] hover:-translate-y-1 hover:shadow-[0_12px_30px_rgb(0,0,0,0.08)] transition-all duration-500 ease-out">
          <div class="flex items-start justify-between gap-5">
            <div class="flex items-center gap-3 min-w-0">
              <span class="w-10 h-10 grid place-items-center shrink-0 rounded-full text-white text-[13px] font-bold" style="background:var(--rose)">${escapeHtml(message.nickname.slice(0, 1))}</span>
              <div class="min-w-0"><strong class="block truncate text-[14px]">${escapeHtml(message.nickname)}</strong><span class="block mt-1 text-[10px]" style="color:var(--faint)">留下了一份祝福</span></div>
            </div>
            <time class="shrink-0 text-[10px]" style="color:var(--faint)">${escapeHtml(String(message.created_at).slice(0, 16))}</time>
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
        await loadMessages();
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
      if (window.confetti) {
        const endTime = Date.now() + 1400;
        const colors = ['#ad7480', '#e2a8b1', '#f3d9de', '#ffffff', '#7f9b8a', '#ffd166'];

        (function frame() {
          confetti({
            particleCount: 9,
            angle: 60,
            spread: 70,
            startVelocity: 46,
            origin: { x: 0, y: 0.72 },
            colors
          });
          confetti({
            particleCount: 9,
            angle: 120,
            spread: 70,
            startVelocity: 46,
            origin: { x: 1, y: 0.72 },
            colors
          });
          if (Date.now() < endTime) requestAnimationFrame(frame);
        })();

        setTimeout(() => confetti({ particleCount: 180, spread: 110, origin: { y: 0.55 }, colors }), 180);
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

    // ===== Apple-style Spring Engine (RAF, ~2KB, 零依赖) =====
    // 用 Apple 的 damping+response 双参数模型；从当前呈现值出发、可注入初速度、随时 retarget → 可中断
    function createSpring({ damping = 1, response = 0.4, onUpdate, onRest }) {
      let value = 0, target = 0, velocity = 0, raf = null, last = 0;
      const stiffness = (2 * Math.PI / response) ** 2;
      const damper = (4 * Math.PI * damping) / response;
      function frame(now) {
        const dt = Math.min((now - last) / 1000, 1 / 30); last = now;
        const a = -stiffness * (value - target) - damper * velocity;
        velocity += a * dt; value += velocity * dt;
        onUpdate(value);
        if (Math.abs(velocity) < 0.05 && Math.abs(value - target) < 0.05) {
          value = target; onUpdate(value); raf = null; onRest && onRest(); return;
        }
        raf = requestAnimationFrame(frame);
      }
      return {
        set(v) { value = v; velocity = 0; },
        stop() { if (raf) { cancelAnimationFrame(raf); raf = null; } },
        to(t, initialV) {
          target = t;
          if (initialV != null) velocity = initialV;
          if (!raf) { last = performance.now(); raf = requestAnimationFrame(frame); }
        },
        get value() { return value; }
      };
    }

    // Apple §6 动量投影（指数衰减，非物理教科书公式） / §9 橡皮筋边界阻尼
    function projectMomentum(v, decel) { decel = decel || 0.998; return (v / 1000) * decel / (1 - decel); }
    function rubberband(x, dim, c) { c = c || 0.55; return (x * dim * c) / (dim + c * Math.abs(x)); }

    function openLightbox(index) {
      if (!state.photos.length) return;
      state.lightboxIndex = (index + state.photos.length) % state.photos.length;
      state.zoom = 1;
      renderLightbox();
      $('#lightbox').classList.add('open');
      document.body.classList.add('modal-open');
    }

    function renderLightbox() {
      const photo = state.photos[state.lightboxIndex];
      const image = $('#lightbox-image');
      image.src = photo.src;
      image.alt = photo.title;
      image.style.transition = '';
      image.style.transform = `translateX(0px) scale(${state.zoom})`;
      $('#lightbox-caption').textContent = `${photo.title} · ${formatDate(photo.date)}`;
      $('#lightbox-count').textContent = `${state.lightboxIndex + 1} / ${state.photos.length}`;
    }

    function closeLightbox() {
      $('#lightbox').classList.remove('open');
      if (!$('.modal.open')) document.body.classList.remove('modal-open');
    }

    function moveLightbox(direction) {
      state.lightboxIndex = (state.lightboxIndex + direction + state.photos.length) % state.photos.length;
      state.zoom = 1;
      renderLightbox();
    }

    function changeZoom(amount) {
      state.zoom = Math.min(3, Math.max(1, state.zoom + amount));
      $('#lightbox-image').style.transform = `translateX(0px) scale(${state.zoom})`;
    }

    // Apple §2/§5/§6/§9/§10: Lightbox 触屏滑动切图——1:1 跟手、速度接力、动量投影、边缘橡皮筋
    function attachLightboxSwipe() {
      const stage = $('#lightbox-stage');
      const image = $('#lightbox-image');
      if (!stage || !image) return;
      let dragging = false, startX = 0, curX = 0, history = [];
      const spring = createSpring({
        damping: 0.8, response: 0.35,
        onUpdate: v => { image.style.transform = `translateX(${v}px) scale(1)`; }
      });

      stage.addEventListener('pointerdown', e => {
        if (state.zoom !== 1 || !state.photos.length) return; // 放大态不切图
        dragging = true; startX = e.clientX; curX = 0;
        history = [{ x: e.clientX, t: performance.now() }];
        spring.stop(); spring.set(0);
        image.style.transition = 'none';
        try { stage.setPointerCapture(e.pointerId); } catch (_) {}
      });

      stage.addEventListener('pointermove', e => {
        if (!dragging) return;
        curX = e.clientX - startX;
        const W = stage.clientWidth || window.innerWidth;
        const atStart = state.lightboxIndex === 0 && curX > 0;
        const atEnd = state.lightboxIndex === state.photos.length - 1 && curX < 0;
        const applied = (atStart || atEnd) ? rubberband(curX, W) : curX; // 边缘橡皮筋
        image.style.transform = `translateX(${applied}px) scale(1)`;
        history.push({ x: e.clientX, t: performance.now() });
        if (history.length > 6) history.shift();
      });

      function endDrag() {
        if (!dragging) return; dragging = false;
        const first = history[0], last = history[history.length - 1];
        const dt = (last.t - first.t) || 16;
        const velocity = (last.x - first.x) / dt * 1000; // px/s
        const W = stage.clientWidth || window.innerWidth;
        const projected = curX + projectMomentum(velocity);
        image.style.transition = '';
        if (projected < -W * 0.25 && state.lightboxIndex < state.photos.length - 1) {
          // 甩向下一张：先让当前图带速度滑出，再换图归位
          spring.set(curX);
          spring.to(-W, velocity);
          setTimeout(() => { moveLightbox(1); }, 180);
        } else if (projected > W * 0.25 && state.lightboxIndex > 0) {
          spring.set(curX);
          spring.to(W, velocity);
          setTimeout(() => { moveLightbox(-1); }, 180);
        } else {
          spring.set(curX);
          spring.to(0, velocity); // §5 回弹并接力释放速度
        }
      }
      stage.addEventListener('pointerup', endDrag);
      stage.addEventListener('pointercancel', endDrag);
    }

    function openModal(modalId) {
      $(`#${modalId}`)?.classList.add('open');
      document.body.classList.add('modal-open');
    }

    function closeModal(modalId) {
      $(`#${modalId}`)?.classList.remove('open');
      if (!$('.modal.open') && !$('#lightbox').classList.contains('open')) document.body.classList.remove('modal-open');
      if (modalId === 'admin-modal' && location.pathname === '/admin') history.replaceState({}, '', '/');
    }

    function requireAdmin() {
      if (state.adminAuthenticated) return true;
      openModal('login-modal');
      setTimeout(() => $('#admin-password')?.focus(), 100);
      return false;
    }

    async function checkAdminSession() {
      try {
        const session = await apiRequest('/api/admin/session');
        state.adminAuthenticated = session?.authenticated === true;
      } catch {
        state.adminAuthenticated = false;
      } finally {
        state.adminSessionChecked = true;
      }
      return state.adminAuthenticated;
    }

    function clearAdminSession() {
      state.adminAuthenticated = false;
      state.adminSessionChecked = true;
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
        closeModal('login-modal');
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
      loadAdminAnniversaries();
      loadAdminWishlist();
      loadAdminCapsules();
      loadAdminMoods();
      loadAdminDateIdeas();
      loadAdminQuotes();
    }

    async function logoutAdmin() {
      try {
        await apiRequest('/api/admin/logout', { method: 'POST', headers: adminHeaders() });
      } catch {}
      clearAdminSession();
      closeModal('admin-modal');
      showToast('已经退出管理后台');
    }

    function setTimelinePreview(source = '') {
      const preview = $('#upload-preview');
      if (!source) {
        preview.removeAttribute('src');
        preview.classList.add('hidden');
        return;
      }
      preview.src = source;
      preview.classList.remove('hidden');
    }

    async function uploadPhoto({ silent = false } = {}) {
      const file = $('#photo-file').files[0];
      if (!file) {
        if (!silent) showToast('请先选择一张照片');
        return '';
      }

      const button = $('#upload-button');
      button.disabled = true;
      $('#upload-status').textContent = '正在上传并安全保存照片…';

      try {
        const formData = new FormData();
        formData.append('file', file);
        const result = await apiRequest('/api/admin/upload', {
          method: 'POST',
          headers: adminHeaders(),
          body: formData
        });
        $('#timeline-image').value = result.url;
        $('#photo-file').value = '';
        setTimelinePreview(result.url);
        $('#upload-status').textContent = '照片上传完成，地址已自动填写。';
        if (!silent) showToast('照片上传成功');
        return result.url;
      } catch (error) {
        $('#upload-status').textContent = error.message;
        if (!silent) handleAdminError(error);
        throw error;
      } finally {
        button.disabled = false;
      }
    }

    function resetTimelineForm() {
      $('#timeline-form').reset();
      $('#editing-timeline-id').value = '';
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
        if ($('#photo-file').files[0]) image = await uploadPhoto({ silent: true });
        const payload = {
          date: $('#timeline-date').value,
          title: $('#timeline-title').value.trim(),
          description: $('#timeline-description').value.trim(),
          image
        };
        await apiRequest(editId ? `/api/admin/timeline/${encodeURIComponent(editId)}` : '/api/timeline', {
          method: editId ? 'PUT' : 'POST',
          headers: { ...adminHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        resetTimelineForm();
        await loadTimeline();
        await loadAdminTimeline();
        showToast(editId ? '这段时光已经更新' : '新的回忆已经加入时光机');
      } catch (error) {
        handleAdminError(error);
      } finally {
        submitButton.disabled = false;
      }
    }

    async function loadAdminTimeline() {
      if (!state.adminAuthenticated) return;
      try {
        const timeline = await apiRequest('/api/timeline');
        state.timeline = timeline;
        const container = $('#admin-timeline-list');
        $('#admin-timeline-count').textContent = `${timeline.length} 条记录`;
        container.innerHTML = timeline.length ? [...timeline].sort((a, b) => b.date.localeCompare(a.date)).map(item => {
          const thumbnail = item.image
            ? `<img class="admin-timeline-thumb" src="${escapeHtml(item.image)}" alt="${escapeHtml(item.title)}">`
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
      } catch (error) {
        handleAdminError(error);
      }
    }

    function startTimelineEdit(timelineId) {
      const item = state.timeline.find(entry => entry.id === timelineId);
      if (!item) {
        showToast('未找到这条时光记录，请刷新后重试');
        return;
      }
      $('#editing-timeline-id').value = item.id;
      $('#timeline-date').value = item.date;
      $('#timeline-title').value = item.title;
      $('#timeline-description').value = item.description;
      $('#timeline-image').value = item.image || '';
      $('#photo-file').value = '';
      $('#timeline-form-heading').textContent = '编辑这段时光';
      $('#timeline-form-hint').textContent = '保留原图无需重新选择照片；选择新照片后会替换原图。';
      $('#timeline-submit-button').innerHTML = '<i data-lucide="save" class="w-4 h-4"></i><span>保存修改</span>';
      $('#cancel-timeline-edit-button').classList.remove('hidden');
      $('#upload-status').textContent = item.image ? '当前已关联照片。' : '当前未关联照片。';
      setTimelinePreview(item.image || '');
      refreshIcons();
      $('#timeline-form').scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    async function deleteTimeline(timelineId) {
      const item = state.timeline.find(entry => entry.id === timelineId);
      if (!item || !confirm(`确定删除“${item.title}”吗？此操作无法恢复。`)) return;
      try {
        await apiRequest(`/api/admin/timeline/${encodeURIComponent(timelineId)}`, {
          method: 'DELETE',
          headers: adminHeaders()
        });
        if ($('#editing-timeline-id').value === timelineId) resetTimelineForm();
        await loadTimeline();
        await loadAdminTimeline();
        showToast('这段时光已经删除');
      } catch (error) {
        handleAdminError(error);
      }
    }

    async function loadAdminMessages() {
      if (!state.adminAuthenticated) return;
      try {
        const messages = await apiRequest('/api/messages');
        const container = $('#admin-message-list');
        container.innerHTML = messages.length ? messages.map(message => `
          <div class="flex items-center gap-4 py-4 border-b" style="border-color:var(--line)">
            <div class="min-w-0 flex-1">
              <div class="text-[13px] font-semibold">${escapeHtml(message.nickname)}</div>
              <div class="mt-1 truncate text-[11px]" style="color:var(--muted)">${escapeHtml(message.content)}</div>
            </div>
            <button class="icon-button admin-delete-button" type="button" data-message-id="${message.id}" title="删除留言" aria-label="删除 ${escapeHtml(message.nickname)} 的留言"><i data-lucide="trash-2" class="w-4 h-4"></i></button>
          </div>`).join('') : '<p class="text-[13px]" style="color:var(--muted)">暂无留言。</p>';

        $$('.admin-delete-button', container).forEach(button => {
          button.addEventListener('click', () => deleteMessage(button.dataset.messageId));
        });
        refreshIcons();
      } catch (error) {
        handleAdminError(error);
      }
    }

    async function deleteMessage(messageId) {
      if (!confirm('确定删除这条留言吗？')) return;
      try {
        await apiRequest(`/api/messages/${messageId}`, { method: 'DELETE', headers: adminHeaders() });
        await Promise.all([loadAdminMessages(), loadMessages()]);
        showToast('留言已经删除');
      } catch (error) {
        handleAdminError(error);
      }
    }

    async function loadAdminWishlist() {
      if (!state.adminAuthenticated) return;
      try {
        const wishes = await apiRequest('/api/wishlist');
        state.wishes = wishes;
        const container = $('#admin-wishlist-list');
        $('#admin-wishlist-count').textContent = `${wishes.length} 个心愿`;
        container.innerHTML = wishes.length ? wishes.map(wish => `
          <div class="flex items-center gap-4 py-4 border-b" style="border-color:var(--line)">
            <div class="min-w-0 flex-1">
              <div class="truncate text-[13px] font-semibold">${escapeHtml(wish.title)}</div>
              <div class="mt-1 text-[11px]" style="color:var(--muted)">${wish.completed ? '已完成' : '待完成'}</div>
            </div>
            <button class="icon-button admin-wishlist-edit-button" type="button" data-wish-id="${escapeHtml(String(wish.id))}" title="编辑心愿" aria-label="编辑 ${escapeHtml(wish.title)}"><i data-lucide="pencil" class="w-4 h-4"></i></button>
            <button class="icon-button admin-wishlist-delete-button" type="button" data-wish-id="${escapeHtml(String(wish.id))}" title="删除心愿" aria-label="删除 ${escapeHtml(wish.title)}"><i data-lucide="trash-2" class="w-4 h-4"></i></button>
          </div>`).join('') : '<p class="text-[13px]" style="color:var(--muted)">还没有心愿。</p>';
        $$('.admin-wishlist-edit-button', container).forEach(button => {
          button.addEventListener('click', () => startWishEdit(button.dataset.wishId));
        });
        $$('.admin-wishlist-delete-button', container).forEach(button => {
          button.addEventListener('click', () => deleteWish(button.dataset.wishId));
        });
        refreshIcons();
      } catch (error) {
        handleAdminError(error);
      }
    }

    function resetWishlistForm() {
      $('#wishlist-form').reset();
      $('#editing-wish-id').value = '';
      $('#wishlist-form-heading').textContent = '添加一个新心愿';
      $('#wishlist-submit-button').innerHTML = '<i data-lucide="plus" class="w-4 h-4"></i><span>加入心愿单</span>';
      $('#cancel-wishlist-edit-button').classList.add('hidden');
      refreshIcons();
    }

    function startWishEdit(wishId) {
      const wish = (state.wishes || []).find(item => String(item.id) === String(wishId));
      if (!wish) {
        showToast('未找到这个心愿，请刷新后重试');
        return;
      }
      $('#editing-wish-id').value = wish.id;
      $('#wishlist-title-input').value = wish.title;
      $('#wishlist-form-heading').textContent = '编辑这个心愿';
      $('#wishlist-submit-button').innerHTML = '<i data-lucide="save" class="w-4 h-4"></i><span>保存修改</span>';
      $('#cancel-wishlist-edit-button').classList.remove('hidden');
      refreshIcons();
      $('#wishlist-form').scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    async function submitWish(event) {
      event.preventDefault();
      const editId = $('#editing-wish-id').value;
      const submitButton = $('#wishlist-submit-button');
      submitButton.disabled = true;
      try {
        const payload = { title: $('#wishlist-title-input').value.trim() };
        await apiRequest(editId ? `/api/admin/wishlist/${encodeURIComponent(editId)}` : '/api/wishlist', {
          method: editId ? 'PUT' : 'POST',
          headers: { ...adminHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        resetWishlistForm();
        await loadWishlist();
        await loadAdminWishlist();
        showToast(editId ? '心愿已经更新' : '新的心愿已经加入心愿单');
      } catch (error) {
        handleAdminError(error);
      } finally {
        submitButton.disabled = false;
      }
    }

    async function deleteWish(wishId) {
      const wish = (state.wishes || []).find(item => String(item.id) === String(wishId));
      if (!wish || !confirm(`确定删除心愿“${wish.title}”吗？此操作无法恢复。`)) return;
      try {
        await apiRequest(`/api/admin/wishlist/${encodeURIComponent(wishId)}`, {
          method: 'DELETE',
          headers: adminHeaders()
        });
        if ($('#editing-wish-id').value === String(wishId)) resetWishlistForm();
        await loadWishlist();
        await loadAdminWishlist();
        showToast('心愿已经删除');
      } catch (error) {
        handleAdminError(error);
      }
    }

    async function loadAdminAnniversaries() {
      if (!state.adminAuthenticated) return;
      try {
        const items = await apiRequest('/api/anniversaries');
        state.anniversaries = items;
        const container = $('#admin-anniversaries-list');
        $('#admin-anniversaries-count').textContent = `${items.length} 个纪念日`;
        container.innerHTML = items.length ? items.map(item => `
          <div class="flex items-center gap-4 py-4 border-b" style="border-color:var(--line)">
            <div class="min-w-0 flex-1">
              <div class="truncate text-[13px] font-semibold">${escapeHtml(item.title)}</div>
              <div class="mt-1 text-[11px]" style="color:var(--muted)">${escapeHtml(formatDate(item.date))}${item.recurring ? ' · 每年循环' : ''}</div>
            </div>
            <button class="icon-button admin-anniversary-edit-button" type="button" data-anniversary-id="${escapeHtml(String(item.id))}" title="编辑纪念日" aria-label="编辑 ${escapeHtml(item.title)}"><i data-lucide="pencil" class="w-4 h-4"></i></button>
            <button class="icon-button admin-anniversary-delete-button" type="button" data-anniversary-id="${escapeHtml(String(item.id))}" title="删除纪念日" aria-label="删除 ${escapeHtml(item.title)}"><i data-lucide="trash-2" class="w-4 h-4"></i></button>
          </div>`).join('') : '<p class="text-[13px]" style="color:var(--muted)">还没有纪念日。</p>';
        $$('.admin-anniversary-edit-button', container).forEach(button => {
          button.addEventListener('click', () => startAnniversaryEdit(button.dataset.anniversaryId));
        });
        $$('.admin-anniversary-delete-button', container).forEach(button => {
          button.addEventListener('click', () => deleteAnniversary(button.dataset.anniversaryId));
        });
        refreshIcons();
      } catch (error) {
        handleAdminError(error);
      }
    }

    function resetAnniversaryForm() {
      $('#anniversary-form').reset();
      $('#editing-anniversary-id').value = '';
      $('#anniversary-recurring-input').checked = true;
      $('#anniversary-form-heading').textContent = '添加一个纪念日';
      $('#anniversary-submit-button').innerHTML = '<i data-lucide="plus" class="w-4 h-4"></i><span>加入纪念日</span>';
      $('#cancel-anniversary-edit-button').classList.add('hidden');
      refreshIcons();
    }

    function startAnniversaryEdit(anniversaryId) {
      const item = (state.anniversaries || []).find(entry => String(entry.id) === String(anniversaryId));
      if (!item) {
        showToast('未找到这个纪念日，请刷新后重试');
        return;
      }
      $('#editing-anniversary-id').value = item.id;
      $('#anniversary-title-input').value = item.title;
      $('#anniversary-date-input').value = item.date;
      $('#anniversary-note-input').value = item.note || '';
      $('#anniversary-recurring-input').checked = Boolean(item.recurring);
      $('#anniversary-form-heading').textContent = '编辑这个纪念日';
      $('#anniversary-submit-button').innerHTML = '<i data-lucide="save" class="w-4 h-4"></i><span>保存修改</span>';
      $('#cancel-anniversary-edit-button').classList.remove('hidden');
      refreshIcons();
      $('#anniversary-form').scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    async function submitAnniversary(event) {
      event.preventDefault();
      const editId = $('#editing-anniversary-id').value;
      const submitButton = $('#anniversary-submit-button');
      submitButton.disabled = true;
      try {
        const payload = {
          title: $('#anniversary-title-input').value.trim(),
          date: $('#anniversary-date-input').value,
          recurring: $('#anniversary-recurring-input').checked,
          note: $('#anniversary-note-input').value.trim()
        };
        await apiRequest(editId ? `/api/admin/anniversaries/${encodeURIComponent(editId)}` : '/api/anniversaries', {
          method: editId ? 'PUT' : 'POST',
          headers: { ...adminHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        resetAnniversaryForm();
        await loadAnniversaries();
        await loadAdminAnniversaries();
        showToast(editId ? '纪念日已经更新' : '新的纪念日已经加入');
      } catch (error) {
        handleAdminError(error);
      } finally {
        submitButton.disabled = false;
      }
    }

    async function deleteAnniversary(anniversaryId) {
      const item = (state.anniversaries || []).find(entry => String(entry.id) === String(anniversaryId));
      if (!item || !confirm(`确定删除纪念日“${item.title}”吗？此操作无法恢复。`)) return;
      try {
        await apiRequest(`/api/admin/anniversaries/${encodeURIComponent(anniversaryId)}`, {
          method: 'DELETE',
          headers: adminHeaders()
        });
        if ($('#editing-anniversary-id').value === String(anniversaryId)) resetAnniversaryForm();
        await loadAnniversaries();
        await loadAdminAnniversaries();
        showToast('纪念日已经删除');
      } catch (error) {
        handleAdminError(error);
      }
    }

    async function loadAdminCapsules() {
      if (!state.adminAuthenticated) return;
      try {
        const items = await apiRequest('/api/admin/capsules');
        state.capsules = items;
        const container = $('#admin-capsules-list');
        $('#admin-capsules-count').textContent = `${items.length} 封`;
        container.innerHTML = items.length ? items.map(item => `
          <div class="flex items-center gap-4 py-4 border-b" style="border-color:var(--line)">
            <div class="min-w-0 flex-1">
              <div class="truncate text-[13px] font-semibold">${escapeHtml(item.title)}</div>
              <div class="mt-1 text-[11px]" style="color:var(--muted)">${escapeHtml(formatDate(item.unlock_date))}${item.locked ? ' · 未开启' : ' · 已开启'}</div>
            </div>
            <button class="icon-button admin-capsule-edit-button" type="button" data-capsule-id="${escapeHtml(String(item.id))}" title="编辑胶囊" aria-label="编辑 ${escapeHtml(item.title)}"><i data-lucide="pencil" class="w-4 h-4"></i></button>
            <button class="icon-button admin-capsule-delete-button" type="button" data-capsule-id="${escapeHtml(String(item.id))}" title="删除胶囊" aria-label="删除 ${escapeHtml(item.title)}"><i data-lucide="trash-2" class="w-4 h-4"></i></button>
          </div>`).join('') : '<p class="text-[13px]" style="color:var(--muted)">还没有时间胶囊。</p>';
        $$('.admin-capsule-edit-button', container).forEach(button => {
          button.addEventListener('click', () => startCapsuleEdit(button.dataset.capsuleId));
        });
        $$('.admin-capsule-delete-button', container).forEach(button => {
          button.addEventListener('click', () => deleteCapsule(button.dataset.capsuleId));
        });
        refreshIcons();
      } catch (error) {
        handleAdminError(error);
      }
    }

    function resetCapsuleForm() {
      $('#capsule-form').reset();
      $('#editing-capsule-id').value = '';
      $('#capsule-form-heading').textContent = '写一封给未来的信';
      $('#capsule-submit-button').innerHTML = '<i data-lucide="plus" class="w-4 h-4"></i><span>封存这封信</span>';
      $('#cancel-capsule-edit-button').classList.add('hidden');
      refreshIcons();
    }

    function startCapsuleEdit(capsuleId) {
      const item = (state.capsules || []).find(entry => String(entry.id) === String(capsuleId));
      if (!item) {
        showToast('未找到这个胶囊，请刷新后重试');
        return;
      }
      $('#editing-capsule-id').value = item.id;
      $('#capsule-title-input').value = item.title;
      $('#capsule-body-input').value = item.body || '';
      $('#capsule-date-input').value = item.unlock_date;
      $('#capsule-form-heading').textContent = '编辑这封信';
      $('#capsule-submit-button').innerHTML = '<i data-lucide="save" class="w-4 h-4"></i><span>保存修改</span>';
      $('#cancel-capsule-edit-button').classList.remove('hidden');
      refreshIcons();
      $('#capsule-form').scrollIntoView({ behavior: 'smooth', block: 'start' });
    }

    async function submitCapsule(event) {
      event.preventDefault();
      const editId = $('#editing-capsule-id').value;
      const submitButton = $('#capsule-submit-button');
      submitButton.disabled = true;
      try {
        const payload = {
          title: $('#capsule-title-input').value.trim(),
          body: $('#capsule-body-input').value.trim(),
          unlock_date: $('#capsule-date-input').value
        };
        await apiRequest(editId ? `/api/admin/capsules/${encodeURIComponent(editId)}` : '/api/capsules', {
          method: editId ? 'PUT' : 'POST',
          headers: { ...adminHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        resetCapsuleForm();
        await loadCapsules();
        await loadAdminCapsules();
        showToast(editId ? '这封信已经更新' : '这封信已经封存');
      } catch (error) {
        handleAdminError(error);
      } finally {
        submitButton.disabled = false;
      }
    }

    async function deleteCapsule(capsuleId) {
      const item = (state.capsules || []).find(entry => String(entry.id) === String(capsuleId));
      if (!item || !confirm(`确定删除胶囊“${item.title}”吗？此操作无法恢复。`)) return;
      try {
        await apiRequest(`/api/admin/capsules/${encodeURIComponent(capsuleId)}`, {
          method: 'DELETE',
          headers: adminHeaders()
        });
        if ($('#editing-capsule-id').value === String(capsuleId)) resetCapsuleForm();
        await loadCapsules();
        await loadAdminCapsules();
        showToast('这封信已经删除');
      } catch (error) {
        handleAdminError(error);
      }
    }

    async function loadAdminMoods() {
      if (!state.adminAuthenticated) return;
      try {
        const items = await apiRequest('/api/moods');
        state.moods = items;
        const container = $('#admin-moods-list');
        $('#admin-moods-count').textContent = `${items.length} 天记录`;
        const recent = [...items].sort((a, b) => b.date.localeCompare(a.date)).slice(0, 30);
        container.innerHTML = recent.length ? recent.map(mood => `
          <div class="flex items-center gap-4 py-3 border-b" style="border-color:var(--line)">
            <span class="mood-cell" data-level="${mood.level}"></span>
            <div class="min-w-0 flex-1">
              <div class="text-[13px] font-semibold">${escapeHtml(mood.date)} · 心情 ${escapeHtml(String(mood.level))}/5</div>
              ${mood.note ? `<div class="mt-1 truncate text-[11px]" style="color:var(--muted)">${escapeHtml(mood.note)}</div>` : ''}
            </div>
            <button class="icon-button admin-mood-delete-button" type="button" data-mood-date="${escapeHtml(mood.date)}" title="删除记录" aria-label="删除 ${escapeHtml(mood.date)} 的心情"><i data-lucide="trash-2" class="w-4 h-4"></i></button>
          </div>`).join('') : '<p class="text-[13px]" style="color:var(--muted)">还没有心情记录。</p>';
        $$('.admin-mood-delete-button', container).forEach(button => {
          button.addEventListener('click', () => deleteMood(button.dataset.moodDate));
        });
        refreshIcons();
      } catch (error) {
        handleAdminError(error);
      }
    }

    async function submitMood(event) {
      event.preventDefault();
      const submitButton = $('#mood-submit-button');
      submitButton.disabled = true;
      try {
        const date = $('#mood-date-input').value;
        if (!date) { showToast('请选择日期'); return; }
        const payload = {
          level: Number($('#mood-level-input').value),
          note: $('#mood-note-input').value.trim()
        };
        await apiRequest(`/api/moods/${encodeURIComponent(date)}`, {
          method: 'PUT',
          headers: { ...adminHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        $('#mood-note-input').value = '';
        await loadMoods();
        await loadAdminMoods();
        showToast('这一天的心情已经记录');
      } catch (error) {
        handleAdminError(error);
      } finally {
        submitButton.disabled = false;
      }
    }

    async function deleteMood(moodDate) {
      if (!confirm(`确定删除 ${moodDate} 的心情记录吗？`)) return;
      try {
        await apiRequest(`/api/admin/moods/${encodeURIComponent(moodDate)}`, { method: 'DELETE', headers: adminHeaders() });
        await loadMoods();
        await loadAdminMoods();
        showToast('这天的心情记录已删除');
      } catch (error) {
        handleAdminError(error);
      }
    }

    async function loadAdminDateIdeas() {
      if (!state.adminAuthenticated) return;
      try {
        const items = await apiRequest('/api/date-ideas');
        state.dateIdeas = items;
        renderRoulette();
        const container = $('#admin-date-ideas-list');
        $('#admin-date-ideas-count').textContent = `${items.length} 个点子`;
        container.innerHTML = items.length ? items.map(idea => `
          <div class="flex items-center gap-4 py-3 border-b" style="border-color:var(--line)">
            <div class="min-w-0 flex-1 truncate text-[13px] font-semibold">${escapeHtml(idea.text)}</div>
            <button class="icon-button admin-date-idea-delete-button" type="button" data-idea-id="${escapeHtml(String(idea.id))}" title="删除点子" aria-label="删除 ${escapeHtml(idea.text)}"><i data-lucide="trash-2" class="w-4 h-4"></i></button>
          </div>`).join('') : '<p class="text-[13px]" style="color:var(--muted)">还没有约会点子。</p>';
        $$('.admin-date-idea-delete-button', container).forEach(button => {
          button.addEventListener('click', () => deleteDateIdea(button.dataset.ideaId));
        });
        refreshIcons();
      } catch (error) {
        handleAdminError(error);
      }
    }

    async function submitDateIdea(event) {
      event.preventDefault();
      const submitButton = $('#date-idea-submit-button');
      submitButton.disabled = true;
      try {
        const payload = { text: $('#date-idea-input').value.trim() };
        await apiRequest('/api/date-ideas', {
          method: 'POST',
          headers: { ...adminHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        $('#date-idea-form').reset();
        await loadDateIdeas();
        await loadAdminDateIdeas();
        showToast('新的约会点子已经加入');
      } catch (error) {
        handleAdminError(error);
      } finally {
        submitButton.disabled = false;
      }
    }

    async function deleteDateIdea(ideaId) {
      const idea = (state.dateIdeas || []).find(entry => String(entry.id) === String(ideaId));
      if (!idea || !confirm(`确定删除约会点子“${idea.text}”吗？`)) return;
      try {
        await apiRequest(`/api/admin/date-ideas/${encodeURIComponent(ideaId)}`, { method: 'DELETE', headers: adminHeaders() });
        await loadDateIdeas();
        await loadAdminDateIdeas();
        showToast('约会点子已经删除');
      } catch (error) {
        handleAdminError(error);
      }
    }

    async function loadAdminQuotes() {
      if (!state.adminAuthenticated) return;
      try {
        const items = await apiRequest('/api/love-quotes');
        state.quotes = items;
        const container = $('#admin-quotes-list');
        $('#admin-quotes-count').textContent = `${items.length} 句情话`;
        container.innerHTML = items.length ? items.map(quote => `
          <div class="flex items-center gap-4 py-3 border-b" style="border-color:var(--line)">
            <div class="min-w-0 flex-1 text-[13px]" style="color:var(--ink)">${escapeHtml(quote.text)}</div>
            <button class="icon-button admin-quote-delete-button" type="button" data-quote-id="${escapeHtml(String(quote.id))}" title="删除情话" aria-label="删除情话"><i data-lucide="trash-2" class="w-4 h-4"></i></button>
          </div>`).join('') : '<p class="text-[13px]" style="color:var(--muted)">还没有情话。</p>';
        $$('.admin-quote-delete-button', container).forEach(button => {
          button.addEventListener('click', () => deleteQuote(button.dataset.quoteId));
        });
        refreshIcons();
      } catch (error) {
        handleAdminError(error);
      }
    }

    async function submitQuote(event) {
      event.preventDefault();
      const submitButton = $('#quote-submit-button');
      submitButton.disabled = true;
      try {
        const payload = { text: $('#quote-input').value.trim() };
        await apiRequest('/api/love-quotes', {
          method: 'POST',
          headers: { ...adminHeaders(), 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        $('#quote-form').reset();
        await loadLoveQuotes();
        await loadAdminQuotes();
        showToast('新的情话已经加入');
      } catch (error) {
        handleAdminError(error);
      } finally {
        submitButton.disabled = false;
      }
    }

    async function deleteQuote(quoteId) {
      const quote = (state.quotes || []).find(entry => String(entry.id) === String(quoteId));
      if (!quote || !confirm('确定删除这句情话吗？')) return;
      try {
        await apiRequest(`/api/admin/love-quotes/${encodeURIComponent(quoteId)}`, { method: 'DELETE', headers: adminHeaders() });
        await loadLoveQuotes();
        await loadAdminQuotes();
        showToast('情话已经删除');
      } catch (error) {
        handleAdminError(error);
      }
    }

    async function changeAdminPassword(event) {
      event.preventDefault();
      try {
        await apiRequest('/api/admin/password', {
          method: 'PUT',
          headers: { ...adminHeaders(), 'Content-Type': 'application/json' },
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

      bind('#admin-button', 'click', async () => {
        if (!state.adminSessionChecked) await checkAdminSession();
        state.adminAuthenticated ? openAdminPanel() : openModal('login-modal');
      });
      bind('#menu-button', 'click', () => $('#mobile-menu').classList.toggle('open'));
      $$('#mobile-menu a').forEach(link => link.addEventListener('click', () => $('#mobile-menu').classList.remove('open')));

      bind('#login-form', 'submit', loginAdmin);
      bind('#logout-button', 'click', logoutAdmin);
      bind('#upload-button', 'click', uploadPhoto);
      bind('#timeline-form', 'submit', addTimelineEntry);
      bind('#cancel-timeline-edit-button', 'click', resetTimelineForm);
      bind('#password-form', 'submit', changeAdminPassword);
      bind('#wishlist-form', 'submit', submitWish);
      bind('#cancel-wishlist-edit-button', 'click', resetWishlistForm);
      bind('#anniversary-form', 'submit', submitAnniversary);
      bind('#cancel-anniversary-edit-button', 'click', resetAnniversaryForm);
      bind('#capsule-form', 'submit', submitCapsule);
      bind('#cancel-capsule-edit-button', 'click', resetCapsuleForm);
      bind('#mood-form', 'submit', submitMood);
      bind('#date-idea-form', 'submit', submitDateIdea);
      bind('#quote-form', 'submit', submitQuote);
      bind('#roulette-spin-button', 'click', spinRoulette);
      bind('#quote-shuffle-button', 'click', () => renderLoveQuote(true));
      bind('#public-mood-form', 'submit', submitPublicMood);
      bind('#public-capsule-form', 'submit', submitPublicCapsule);
      initInlineAddDefaults();

      bind('#photo-file', 'change', event => {
        const file = event.target.files[0];
        if (!file) return;
        setTimelinePreview(URL.createObjectURL(file));
        $('#upload-status').textContent = '将于保存时自动上传这张照片。';
      });

      bind('#timeline-image', 'change', event => setTimelinePreview(event.target.value.trim()));
      bind('#upload-preview', 'error', () => {
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
          if (button.dataset.tab === 'admin-anniversaries-panel') loadAdminAnniversaries();
          if (button.dataset.tab === 'admin-messages-panel') loadAdminMessages();
          if (button.dataset.tab === 'admin-wishlist-panel') loadAdminWishlist();
          if (button.dataset.tab === 'admin-capsules-panel') loadAdminCapsules();
          if (button.dataset.tab === 'admin-moods-panel') loadAdminMoods();
          if (button.dataset.tab === 'admin-roulette-panel') loadAdminDateIdeas();
          if (button.dataset.tab === 'admin-quotes-panel') loadAdminQuotes();
        });
      });

      bind('#lightbox-close-button', 'click', closeLightbox);
      bind('#lightbox-prev-button', 'click', () => moveLightbox(-1));
      bind('#lightbox-next-button', 'click', () => moveLightbox(1));
      bind('#zoom-in-button', 'click', () => changeZoom(0.25));
      bind('#zoom-out-button', 'click', () => changeZoom(-0.25));
      bind('#lightbox-stage', 'wheel', event => {
        event.preventDefault();
        changeZoom(event.deltaY < 0 ? 0.2 : -0.2);
      }, { passive: false });

      attachLightboxSwipe(); // Apple §2/§10: 触屏滑动切图手势

      document.addEventListener('keydown', event => {
        if (event.key === 'Escape') {
          closeLightbox();
          $$('.modal.open').forEach(modal => closeModal(modal.id));
        }
        if ($('#lightbox').classList.contains('open')) {
          if (event.key === 'ArrowLeft') moveLightbox(-1);
          if (event.key === 'ArrowRight') moveLightbox(1);
          if (event.key === '+') changeZoom(0.25);
          if (event.key === '-') changeZoom(-0.25);
        }
      });
    }

    async function initializePage() {
      const savedTheme = localStorage.getItem('love_theme') || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
      applyTheme(savedTheme);
      bindPageEvents();
      refreshIcons();
      observeRevealElements();
      updateRelationshipClock();
      setInterval(updateRelationshipClock, 1000);
      await Promise.all([loadTimeline(), loadWishlist(), loadAnniversaries(), loadMessages(), loadCapsules(), loadMoods(), loadDateIdeas(), loadLoveQuotes()]);
      renderDashboard();

      if (location.hash) {
        requestAnimationFrame(() => {
          document.querySelector(location.hash)?.scrollIntoView({ block: 'start' });
        });
      }

      if (location.pathname === '/admin') {
        await checkAdminSession();
        setTimeout(() => state.adminAuthenticated ? openAdminPanel() : openModal('login-modal'), 180);
      }
    }

    initializePage();
