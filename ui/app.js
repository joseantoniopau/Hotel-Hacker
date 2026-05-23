/* ============================================================
   hotel-hacker / app.js
   Vanilla JS — no framework. Wires the brutalist UI to the
   FastAPI server on 127.0.0.1:8788.
   ============================================================ */

(function () {
  'use strict';

  const $ = (s, root) => (root || document).querySelector(s);
  const $$ = (s, root) => Array.from((root || document).querySelectorAll(s));

  const REDUCED_MOTION = window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // ----------------------------------------------------------------
  // Tiny state
  // ----------------------------------------------------------------
  const state = {
    hotels: [],          // raw normalized hotels from /api/search
    ranked: [],          // ranked rows from /api/rank
    balances: { currencies: {}, programs: {}, cards: [] },
    fhrInputs: [],
    quota: null,
    expandedRowIndex: null,
  };

  // ----------------------------------------------------------------
  // fetch helper with friendly error envelope unwrapping
  // ----------------------------------------------------------------
  async function api(path, opts) {
    const res = await fetch(path, Object.assign({
      headers: { 'Content-Type': 'application/json' },
    }, opts || {}));
    let payload;
    try { payload = await res.json(); } catch (_) { payload = null; }
    if (!res.ok) {
      const msg = (payload && payload.error) || `${res.status} ${res.statusText}`;
      throw new Error(msg);
    }
    return payload;
  }

  // ----------------------------------------------------------------
  // formatters
  // ----------------------------------------------------------------
  function fmtMoney(n) {
    if (n === null || n === undefined || isNaN(n)) return '—';
    const num = Number(n);
    const sign = num < 0 ? '−' : '';
    const abs = Math.abs(num);
    return sign + '$' + abs.toLocaleString('en-US', {
      maximumFractionDigits: 0,
      minimumFractionDigits: 0,
    });
  }
  function fmtInt(n) {
    if (n === null || n === undefined || isNaN(n)) return '—';
    return Number(n).toLocaleString('en-US');
  }

  // ----------------------------------------------------------------
  // View switching
  // ----------------------------------------------------------------
  function showView(name) {
    $$('.view').forEach(v => v.classList.toggle('active', v.id === 'view-' + name));
    $$('.sidebar .nav-item').forEach(b => b.classList.toggle('active', b.dataset.view === name));
    // close any expanded row on view-switch
    collapseAllRows();
  }

  $$('.sidebar .nav-item').forEach(btn => {
    btn.addEventListener('click', () => {
      showView(btn.dataset.view);
      // close mobile nav after pick
      const sb = $('#sidebar');
      if (window.matchMedia('(max-width: 720px)').matches) {
        sb.classList.add('mobile-hidden');
      }
    });
  });

  $('#hamburger').addEventListener('click', () => {
    $('#sidebar').classList.toggle('mobile-hidden');
  });

  // ----------------------------------------------------------------
  // Counter ticker (Polish 11)
  // ----------------------------------------------------------------
  function animateCounter(el, target, duration) {
    if (!el) return;
    if (REDUCED_MOTION) {
      el.textContent = '$' + Number(target).toLocaleString('en-US');
      return;
    }
    const start = performance.now();
    const from = 0;
    function step(now) {
      const t = Math.min(1, (now - start) / duration);
      // ease-out cubic
      const eased = 1 - Math.pow(1 - t, 3);
      const value = Math.round(from + (target - from) * eased);
      el.textContent = '$' + value.toLocaleString('en-US');
      if (t < 1) requestAnimationFrame(step);
    }
    requestAnimationFrame(step);
  }

  // Kick the ticker once on mount.
  animateCounter($('#ticker'), 847234, 1800);

  // ----------------------------------------------------------------
  // IntersectionObserver fade-in (Polish 10)
  // ----------------------------------------------------------------
  if (!REDUCED_MOTION && 'IntersectionObserver' in window) {
    const io = new IntersectionObserver((entries) => {
      entries.forEach((entry, idx) => {
        if (entry.isIntersecting) {
          const el = entry.target;
          // staggered delay across a batch
          const delay = (idx % 6) * 60;
          el.style.animationDelay = delay + 'ms';
          el.classList.add('fade-in');
          io.unobserve(el);
        }
      });
    }, { threshold: 0.08 });
    document.addEventListener('DOMContentLoaded', () => {
      $$('.card, .step').forEach(el => io.observe(el));
    });
    // Hot pass for already-rendered items
    setTimeout(() => $$('.card, .step').forEach(el => io.observe(el)), 0);
  }

  // ----------------------------------------------------------------
  // Initial defaults — sensible dates
  // ----------------------------------------------------------------
  (function seedDates() {
    const today = new Date();
    const ci = new Date(today.getTime() + 30 * 86400000);
    const co = new Date(today.getTime() + 33 * 86400000);
    const iso = d => d.toISOString().slice(0, 10);
    $('#check_in').value = iso(ci);
    $('#check_out').value = iso(co);
  })();

  // ----------------------------------------------------------------
  // Account quota
  // ----------------------------------------------------------------
  async function refreshQuota() {
    try {
      const a = await api('/api/account');
      state.quota = a;
      const used = a.searches_used_this_month ?? 0;
      const left = a.searches_remaining ?? (a.plan_searches_left ?? 250);
      const total = used + left;
      $('#quota').textContent = `SerpApi: ${left} / ${total} left this month`;
    } catch (e) {
      $('#quota').textContent = 'SerpApi: — / —';
    }
  }
  refreshQuota();

  // ----------------------------------------------------------------
  // Search
  // ----------------------------------------------------------------
  $('#search-form').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const btn = $('#btn-search');
    const status = $('#search-status');
    const body = {
      q: $('#q').value.trim(),
      check_in: $('#check_in').value,
      check_out: $('#check_out').value,
      adults: Number($('#adults').value) || 2,
      currency: $('#currency').value || 'USD',
    };
    if (!body.q) { $('#q').focus(); return; }
    btn.disabled = true;
    const originalLabel = btn.textContent;
    btn.textContent = 'SEARCHING...';
    status.textContent = 'Calling Google Hotels...';
    try {
      const data = await api('/api/search', { method: 'POST', body: JSON.stringify(body) });
      state.hotels = data.hotels || [];
      status.textContent = `Found ${state.hotels.length} properties. Ranking...`;
      populateFhrPropertyDropdown();
      await runRank();
      showView('results');
      refreshQuota();
      status.textContent = `Done. Showing ${state.ranked.length} ranked.`;
    } catch (err) {
      status.textContent = 'Error: ' + err.message;
      toast('Search failed: ' + err.message);
    } finally {
      btn.disabled = false;
      btn.textContent = originalLabel;
    }
  });

  function collectFhrInputs() {
    // Only collect when the panel is open AND a property is picked.
    const det = $('#fhr-panel');
    if (!det || !det.open) return [];
    const propId = $('#fhr-property').value;
    if (!propId) return [];
    const property = state.hotels.find(h => (h.hotel_id || '') === propId);
    if (!property) return [];
    const bfr = parseFloat($('#fhr-bfr').value);
    const offer = parseFloat($('#fhr-offer').value);
    const perks = {};
    $$('#fhr-panel input[type="checkbox"][data-perk]').forEach(cb => {
      perks[cb.dataset.perk] = cb.checked;
    });
    return [{
      hotel_id: propId,
      property_name: property.name || '',
      best_flexible_rate_usd: isNaN(bfr) ? null : bfr,
      applicable_offer_credit_usd: isNaN(offer) ? null : offer,
      property_currency: $('#fhr-currency').value || 'USD',
      perks: perks,
    }];
  }

  async function runRank() {
    state.fhrInputs = collectFhrInputs();
    const body = {
      hotels: state.hotels,
      balances: state.balances,
      fhr_inputs: state.fhrInputs,
    };
    const data = await api('/api/rank', { method: 'POST', body: JSON.stringify(body) });
    state.ranked = data.ranked || [];
    renderResults();
  }

  $('#btn-rerank').addEventListener('click', async () => {
    if (!state.hotels.length) { toast('Run a search first.'); return; }
    try { await runRank(); toast('Re-ranked with FHR inputs.'); }
    catch (e) { toast('Re-rank failed: ' + e.message); }
  });

  function populateFhrPropertyDropdown() {
    const sel = $('#fhr-property');
    if (!sel) return;
    sel.innerHTML = '<option value="">— pick a property —</option>' +
      state.hotels.map(h =>
        `<option value="${escapeAttr(h.hotel_id || '')}">${escapeHtml(h.name || '(unnamed)')}</option>`
      ).join('');
  }

  // ----------------------------------------------------------------
  // Render results table
  // ----------------------------------------------------------------
  function renderResults() {
    const tbody = $('#results-body');
    if (!state.ranked.length) {
      tbody.innerHTML = '<tr><td colspan="9" class="muted" style="text-align:center; padding: 32px;">No results.</td></tr>';
      $('#top-pick-body').textContent = 'No results yet.';
      $('#results-meta').textContent = '—';
      return;
    }
    // Top pick
    const top = state.ranked[0];
    const topName = top.normalized?.name || '(unnamed)';
    const topEff = fmtMoney(top.effective_usd);
    const topRaw = fmtMoney(top.raw_usd);
    const topChannel = (top.recommended_channel || 'direct').toUpperCase();
    $('#top-pick-body').innerHTML = `<strong>${escapeHtml(topName)}</strong> &mdash; net <span class="accent">${topEff}</span> after ranking (raw ${topRaw}) via <span class="brass">${escapeHtml(topChannel)}</span>. ${escapeHtml(top.explanation || '')}`;

    $('#results-meta').textContent =
      `${state.ranked.length} ranked · ${state.hotels.length} found · ${state.fhrInputs.length} FHR overlay${state.fhrInputs.length === 1 ? '' : 's'}`;

    tbody.innerHTML = state.ranked.map((row, i) => renderRow(row, i)).join('');

    // Wire row click handlers
    $$('#results-body tr.data-row').forEach(tr => {
      tr.addEventListener('click', () => toggleRow(Number(tr.dataset.idx)));
    });
  }

  const BRAND_DOMAIN = {
    'Marriott Bonvoy': 'marriott.com',
    'Marriott': 'marriott.com',
    'Hilton Honors': 'hilton.com',
    'Hilton': 'hilton.com',
    'World of Hyatt': 'hyatt.com',
    'Hyatt': 'hyatt.com',
    'IHG One Rewards': 'ihg.com',
    'IHG': 'ihg.com',
    'Accor Live Limitless': 'all.accor.com',
    'Accor Live Limitless (ALL)': 'all.accor.com',
    'Accor': 'all.accor.com',
    'Wyndham Rewards': 'wyndhamhotels.com',
    'Wyndham': 'wyndhamhotels.com',
    'Choice Privileges': 'choicehotels.com',
    'Choice': 'choicehotels.com',
    'Best Western Rewards': 'bestwestern.com',
    'Best Western': 'bestwestern.com',
    'Radisson Rewards Americas': 'radissonhotelsamericas.com',
    'Radisson': 'radissonhotelsamericas.com',
  };
  function brandDomain(name, brand) {
    if (brand && BRAND_DOMAIN[brand]) return BRAND_DOMAIN[brand];
    if (!name) return null;
    const nm = name.toLowerCase();
    for (const [k, v] of Object.entries(BRAND_DOMAIN)) {
      const token = k.split(/\s+/)[0].toLowerCase();
      if (nm.includes(token)) return v;
    }
    // luxury independents — best effort
    if (nm.includes('four seasons')) return 'fourseasons.com';
    if (nm.includes('ritz-carlton') || nm.includes('ritz carlton')) return 'ritzcarlton.com';
    if (nm.includes('park hyatt')) return 'hyatt.com';
    if (nm.includes('andaz')) return 'hyatt.com';
    if (nm.includes('st. regis') || nm.includes('st regis')) return 'marriott.com';
    if (nm.includes('rosewood')) return 'rosewoodhotels.com';
    if (nm.includes('mandarin oriental')) return 'mandarinoriental.com';
    if (nm.includes('aman')) return 'aman.com';
    if (nm.includes('peninsula')) return 'peninsula.com';
    if (nm.includes('belmond')) return 'belmond.com';
    if (nm.includes('sofitel')) return 'all.accor.com';
    if (nm.includes('marriott')) return 'marriott.com';
    if (nm.includes('hilton')) return 'hilton.com';
    if (nm.includes('hyatt')) return 'hyatt.com';
    if (nm.includes('apa hotel')) return 'apahotel.com';
    return null;
  }
  function faviconImg(name, brand) {
    const dom = brandDomain(name, brand);
    if (!dom) return '<span class="brand-favicon" aria-hidden="true"></span>';
    const url = `https://www.google.com/s2/favicons?sz=64&domain=${encodeURIComponent(dom)}`;
    return `<img class="brand-favicon" alt="" src="${url}" loading="lazy" onerror="this.dataset.missing=1">`;
  }

  function renderRow(row, i) {
    const n = row.normalized || {};
    const loc = n.location || {};
    const nights = n.nights ?? '—';
    const raw = fmtMoney(row.raw_usd);
    const eff = fmtMoney(row.effective_usd);
    const channel = (row.recommended_channel || 'direct').toUpperCase();
    const badges = (row.badges || []).map(b => badgeChip(b)).join('');
    const notes = escapeHtml((row.channel_reason || row.explanation || '').slice(0, 70));
    const topDealCls = (i === 0) ? ' top-deal' : '';
    const fav = faviconImg(n.name, n.brand);
    return `
      <tr class="data-row${topDealCls}" data-idx="${i}">
        <td class="rank">${row.score_rank ?? (i + 1)}</td>
        <td><span class="hotel-cell">${fav}<strong class="hotel-name" title="${escapeHtml(n.name || '')}">${escapeHtml(n.name || '(unnamed)')}</strong></span></td>
        <td class="muted">${escapeHtml(loc.city || '')}${loc.country ? ', ' + escapeHtml(loc.country) : ''}</td>
        <td class="num">${nights}</td>
        <td class="num raw">${raw}</td>
        <td class="num effective">${eff}</td>
        <td>${escapeHtml(channel)}</td>
        <td><div class="badges">${badges}</div></td>
        <td class="muted">${notes}</td>
      </tr>`;
  }

  function badgeChip(b) {
    const map = {
      'REFUNDABLE': 'refundable',
      'FHR': 'fhr',
      'PTS': 'pts',
      '5TH-FREE': 'fifth',
      '4TH-FREE': 'fourth',
      'CCY-NOTE': 'ccy',
      'TOS-RISK': 'tos',
      'LEGAL': 'legal',
      'GRAY': 'gray',
    };
    const cls = map[b] || 'gray';
    return `<span class="badge ${cls}">${escapeHtml(b)}</span>`;
  }

  function toggleRow(i) {
    const tbody = $('#results-body');
    const existing = tbody.querySelector('tr.row-detail-row');
    const existingIdx = existing ? Number(existing.dataset.detailFor) : -1;
    if (existing) existing.remove();
    $$('#results-body tr.data-row').forEach(t => t.classList.remove('expanded'));
    if (existingIdx === i) { state.expandedRowIndex = null; return; }
    const row = state.ranked[i];
    if (!row) return;
    const tr = $$('#results-body tr.data-row')[i];
    if (!tr) return;
    tr.classList.add('expanded');
    const detailTr = document.createElement('tr');
    detailTr.className = 'row-detail-row';
    detailTr.dataset.detailFor = String(i);
    detailTr.innerHTML = `<td colspan="9"><div class="row-detail">${renderBreakdown(row)}</div></td>`;
    tr.parentNode.insertBefore(detailTr, tr.nextSibling);
    state.expandedRowIndex = i;
  }

  function collapseAllRows() {
    const tbody = $('#results-body');
    if (!tbody) return;
    tbody.querySelectorAll('tr.row-detail-row').forEach(r => r.remove());
    tbody.querySelectorAll('tr.data-row.expanded').forEach(r => r.classList.remove('expanded'));
    state.expandedRowIndex = null;
  }

  function renderBreakdown(row) {
    const b = row.breakdown || {};
    const n = row.normalized || {};
    const lines = [
      { k: 'Raw total (after taxes & fees)', v: fmtMoney(b.raw_total_usd ?? row.raw_usd), cls: '' },
      { k: 'Points value applied',          v: '− ' + fmtMoney(b.points_value_usd),       cls: 'neg' },
      { k: 'Free-night value',               v: '− ' + fmtMoney(b.free_night_value_usd),   cls: 'neg' },
      { k: 'FHR credit value',               v: '− ' + fmtMoney(b.fhr_value_usd),          cls: 'neg' },
      { k: 'FHR currency haircut',           v: '+ ' + fmtMoney(b.fhr_haircut_usd),        cls: 'pos' },
      { k: 'Flexibility penalty (non-refundable)', v: '+ ' + fmtMoney(b.flexibility_penalty_usd), cls: 'pos' },
      { k: 'Currency arbitrage',             v: (Number(b.currency_arb_usd) >= 0 ? '+ ' : '') + fmtMoney(b.currency_arb_usd), cls: Number(b.currency_arb_usd) >= 0 ? 'pos' : 'neg' },
    ];
    const kvHtml = '<div class="kv-grid">' + lines.map(L =>
      `<span class="k">${escapeHtml(L.k)}</span><span class="v ${L.cls}">${L.v}</span>`
    ).join('') + `<span class="k total">EFFECTIVE COST</span><span class="v total">${fmtMoney(row.effective_usd)}</span></div>`;
    const linesHtml = kvHtml;

    const explain = escapeHtml(row.explanation || '');
    const reason = escapeHtml(row.channel_reason || '');
    const hotelName = escapeHtml(n.name || 'this hotel');
    const arrival = escapeHtml(n.check_in || '');

    return `
      ${linesHtml}
      <p class="muted micro mt-3">${explain}</p>
      <p class="muted micro">${reason}</p>
      <div class="actions">
        <button class="btn ghost" data-act="copy-explain" data-row-i="${row._i ?? ''}">COPY EXPLANATION</button>
        <button class="btn secondary" data-act="upgrade-email"
                data-hotel="${escapeAttr(n.name || '')}"
                data-arrival="${escapeAttr(arrival)}">
          DRAFT UPGRADE EMAIL
        </button>
      </div>
    `;
  }

  // Delegate clicks inside detail rows
  document.addEventListener('click', (ev) => {
    const target = ev.target.closest('[data-act]');
    if (!target) return;
    const act = target.dataset.act;
    if (act === 'upgrade-email') {
      ev.stopPropagation();
      openUpgradeEmail(target.dataset.hotel, target.dataset.arrival);
    } else if (act === 'copy-explain') {
      ev.stopPropagation();
      const detail = target.closest('.row-detail');
      const text = detail ? detail.innerText : '';
      copyText(text).then(() => toast('Copied breakdown.'));
    }
  });

  // ----------------------------------------------------------------
  // Upgrade-email modal
  // ----------------------------------------------------------------
  async function openUpgradeEmail(hotel, arrival) {
    const modalBg = $('#modal-bg');
    const draftEl = $('#modal-draft');
    draftEl.textContent = 'Drafting...';
    modalBg.classList.add('show');
    try {
      const data = await api('/api/draft-upgrade-email', {
        method: 'POST',
        body: JSON.stringify({
          hotel_name: hotel || '',
          arrival_date: arrival || '',
        }),
      });
      const subject = data.subject || '';
      const body = data.body || '';
      draftEl.textContent = `Subject: ${subject}\n\n${body}`;
      draftEl.dataset.copy = `Subject: ${subject}\n\n${body}`;
    } catch (e) {
      draftEl.textContent = 'Could not draft email: ' + e.message;
    }
  }
  $('#btn-modal-close').addEventListener('click', () => $('#modal-bg').classList.remove('show'));
  $('#btn-modal-copy').addEventListener('click', () => {
    const text = $('#modal-draft').dataset.copy || $('#modal-draft').textContent || '';
    copyText(text).then(() => toast('Draft copied.'));
  });
  $('#modal-bg').addEventListener('click', (ev) => {
    if (ev.target === $('#modal-bg')) $('#modal-bg').classList.remove('show');
  });

  function copyText(text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text);
    }
    // Fallback
    return new Promise((res) => {
      const ta = document.createElement('textarea');
      ta.value = text;
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand('copy'); } catch (_) {}
      document.body.removeChild(ta);
      res();
    });
  }

  // ----------------------------------------------------------------
  // Toast
  // ----------------------------------------------------------------
  let toastTimer = null;
  function toast(msg) {
    const t = $('#toast');
    t.textContent = msg;
    t.classList.add('show');
    if (toastTimer) clearTimeout(toastTimer);
    toastTimer = setTimeout(() => t.classList.remove('show'), 2400);
  }

  // ----------------------------------------------------------------
  // Balances — load + save
  // ----------------------------------------------------------------
  const DEFAULT_CURRENCIES = [
    'Amex Membership Rewards',
    'Chase Ultimate Rewards',
    'Citi ThankYou',
    'Capital One Miles',
    'Bilt Rewards',
  ];
  const DEFAULT_PROGRAMS = [
    'World of Hyatt',
    'Marriott Bonvoy',
    'Hilton Honors',
    'IHG One Rewards',
    'Accor Live Limitless',
  ];
  const DEFAULT_CARDS = [
    'Amex Platinum',
    'Amex Business Platinum',
    'Amex Centurion',
    'Chase Sapphire Reserve',
    'Capital One Venture X',
  ];

  function renderBalances() {
    const cur = $('#bal-currencies');
    const pro = $('#bal-programs');
    const car = $('#bal-cards');
    cur.innerHTML = DEFAULT_CURRENCIES.map(name => `
      <div class="field">
        <label>${escapeHtml(name)}</label>
        <input type="number" min="0" step="1000" data-bal-currency="${escapeAttr(name)}"
               value="${Number(state.balances.currencies?.[name] || 0)}">
      </div>
    `).join('');
    pro.innerHTML = DEFAULT_PROGRAMS.map(name => `
      <div class="field">
        <label>${escapeHtml(name)}</label>
        <input type="number" min="0" step="1000" data-bal-program="${escapeAttr(name)}"
               value="${Number(state.balances.programs?.[name] || 0)}">
      </div>
    `).join('');
    car.innerHTML = DEFAULT_CARDS.map(name => `
      <label>
        <input type="checkbox" data-bal-card="${escapeAttr(name)}"
               ${(state.balances.cards || []).includes(name) ? 'checked' : ''}>
        ${escapeHtml(name)}
      </label>
    `).join('');
  }

  async function loadBalances() {
    try {
      const data = await api('/api/balances');
      state.balances = {
        currencies: data.currencies || {},
        programs: data.programs || {},
        cards: data.cards || [],
      };
    } catch (_) {
      state.balances = { currencies: {}, programs: {}, cards: [] };
    }
    renderBalances();
  }
  loadBalances();

  $('#bal-form').addEventListener('submit', async (ev) => {
    ev.preventDefault();
    const status = $('#bal-status');
    const next = { currencies: {}, programs: {}, cards: [] };
    $$('[data-bal-currency]').forEach(i => {
      next.currencies[i.dataset.balCurrency] = Number(i.value) || 0;
    });
    $$('[data-bal-program]').forEach(i => {
      next.programs[i.dataset.balProgram] = Number(i.value) || 0;
    });
    $$('[data-bal-card]:checked').forEach(c => {
      next.cards.push(c.dataset.balCard);
    });
    // optimistic
    const prev = state.balances;
    state.balances = next;
    status.textContent = 'Saving...';
    try {
      await api('/api/balances', { method: 'POST', body: JSON.stringify(next) });
      status.textContent = 'Saved.';
      toast('Balances saved.');
    } catch (e) {
      state.balances = prev;
      status.textContent = 'Error: ' + e.message;
      toast('Save failed: ' + e.message);
    }
  });

  // ----------------------------------------------------------------
  // Keyboard
  // ----------------------------------------------------------------
  document.addEventListener('keydown', (ev) => {
    // Ignore when typing in inputs
    const tag = (ev.target && ev.target.tagName) || '';
    const inForm = /INPUT|TEXTAREA|SELECT/.test(tag);
    if (ev.key === '/' && !inForm) {
      ev.preventDefault();
      $('#q').focus();
      showView('search');
    } else if (ev.key === 'Escape') {
      // close modal first, then collapse row
      const modal = $('#modal-bg');
      if (modal.classList.contains('show')) {
        modal.classList.remove('show');
      } else {
        collapseAllRows();
      }
    }
  });

  // ----------------------------------------------------------------
  // HTML / attr escapers
  // ----------------------------------------------------------------
  function escapeHtml(s) {
    if (s === null || s === undefined) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  }
  function escapeAttr(s) { return escapeHtml(s); }

})();
