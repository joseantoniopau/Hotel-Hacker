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

  // Hero ticker now mirrors the real SerpApi quota — written by refreshQuota().
  // (No animation needed: refreshQuota updates the number on every search.)

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
      const qEl = $('#quota');
      if (qEl) qEl.textContent = `${left} / ${total} hotel searches left`;
      const tEl = $('#ticker');
      if (tEl) tEl.textContent = String(left);
    } catch (e) {
      const qEl = $('#quota'); if (qEl) qEl.textContent = '— / —';
      const tEl = $('#ticker'); if (tEl) tEl.textContent = '—';
    }
  }
  refreshQuota();

  // ----------------------------------------------------------------
  // URL paste extraction — pull property name + dates + adults out of a
  // pasted Expedia / Booking / Hotels.com / TripAdvisor / chain URL so the
  // user can drop a link from any site and have it scored locally.
  // Returns { name, city, checkIn, checkOut, adults } or null.
  // ----------------------------------------------------------------
  function extractHotelFromUrl(raw) {
    let u;
    try { u = new URL(String(raw).trim()); } catch (_) { return null; }
    const host = u.hostname.replace(/^www\./, '').toLowerCase();
    const path = u.pathname;
    const params = u.searchParams;
    let name = null, city = null, checkIn = null, checkOut = null, adults = null;
    const titlecase = s => s.replace(/\b\w/g, c => c.toUpperCase());

    if (host.endsWith('expedia.com') || host.endsWith('expedia.co.uk') || host.endsWith('expedia.ca')) {
      const m = path.match(/\/([A-Za-z0-9_]+)-Hotels-([A-Za-z0-9_]+)\.h\d+/);
      if (m) { city = m[1].replace(/_/g, ' '); name = m[2].replace(/_/g, ' '); }
      checkIn = params.get('chkin');
      checkOut = params.get('chkout');
      const rm1 = params.get('rm1');
      if (rm1) { const am = rm1.match(/a(\d+)/); if (am) adults = parseInt(am[1], 10); }
    }
    else if (host.endsWith('booking.com')) {
      const m = path.match(/\/hotel\/[a-z]{2}\/([a-z0-9-]+)\.html?/i);
      if (m) name = titlecase(m[1].replace(/-/g, ' '));
      checkIn = params.get('checkin');
      checkOut = params.get('checkout');
      const ga = params.get('group_adults') || params.get('numberOfGuests');
      if (ga) adults = parseInt(ga, 10) || null;
    }
    else if (host.endsWith('hotels.com')) {
      const m = path.match(/\/ho\d+\/([a-z0-9-]+)\//i) || path.match(/\/([A-Za-z0-9_]+)-Hotels-([A-Za-z0-9_]+)\.h\d+/);
      if (m && m[2]) { city = m[1].replace(/_/g, ' '); name = m[2].replace(/_/g, ' '); }
      else if (m && m[1]) name = titlecase(m[1].replace(/-/g, ' '));
      checkIn = params.get('chkin') || params.get('q-check-in');
      checkOut = params.get('chkout') || params.get('q-check-out');
    }
    else if (host.endsWith('tripadvisor.com') || host.endsWith('tripadvisor.co.uk')) {
      const m = path.match(/Hotel_Review[^/]*-Reviews-([A-Za-z0-9_]+?)-([A-Za-z0-9_]+?)\.html/);
      if (m) {
        name = m[1].replace(/_/g, ' ');
        city = m[2].replace(/_/g, ' ').replace(/\s+(Lazio|Italy|France|Spain|Province|Region|State|Prefecture)$/i, '');
      }
    }
    else if (host.endsWith('hyatt.com')) {
      const seg = path.split('/').filter(Boolean);
      const slug = seg[seg.length - 1];
      if (slug && slug.includes('-')) name = titlecase(slug.replace(/-/g, ' '));
    }
    else if (host.endsWith('marriott.com')) {
      const m = path.match(/\/hotels\/travel\/[a-z0-9]+-([a-z0-9-]+)\/?/i);
      if (m) name = titlecase(m[1].replace(/-/g, ' '));
    }
    else if (host.endsWith('hilton.com')) {
      const m = path.match(/\/en\/hotels\/([a-z0-9-]+)\/?/i);
      if (m) name = titlecase(m[1].replace(/^[a-z]{3,4}-/, '').replace(/-/g, ' '));
    }
    else if (host.endsWith('ihg.com')) {
      const m = path.match(/\/([a-z0-9]+)\/hotels\/[a-z]{2}\/[a-z]{2}\/[a-z-]+\/[a-z]+\/hoteldetail/i);
      if (m) name = titlecase(m[1]);
    }

    if (!name) return null;
    return {
      name: name.trim(),
      city: (city || '').trim() || null,
      checkIn: (checkIn || '').match(/^\d{4}-\d{2}-\d{2}$/) ? checkIn : null,
      checkOut: (checkOut || '').match(/^\d{4}-\d{2}-\d{2}$/) ? checkOut : null,
      adults: (adults && adults >= 1 && adults <= 8) ? adults : null,
    };
  }
  // exposed for the test harness — also useful from the browser console.
  window.__hhExtractFromUrl = extractHotelFromUrl;

  function applyExtractedToForm(ex) {
    if (!ex) return false;
    const qEl = $('#q'); if (qEl) qEl.value = ex.name;
    if (ex.checkIn)  { const e = $('#check_in');  if (e) e.value = ex.checkIn; }
    if (ex.checkOut) { const e = $('#check_out'); if (e) e.value = ex.checkOut; }
    if (ex.adults)   { const e = $('#adults');    if (e) e.value = String(ex.adults); }
    const hint = $('#search-status');
    if (hint) {
      const parts = [`Detected: ${ex.name}`];
      if (ex.city) parts.push(`in ${ex.city}`);
      if (ex.checkIn && ex.checkOut) parts.push(`${ex.checkIn} → ${ex.checkOut}`);
      if (ex.adults) parts.push(`${ex.adults} adult${ex.adults === 1 ? '' : 's'}`);
      hint.textContent = parts.join(' · ') + ' — click FIND HOTELS to look it up.';
    }
    return true;
  }

  // Wire up paste handler on the destination field.
  (function wireUrlPaste() {
    const qEl = $('#q'); if (!qEl) return;
    qEl.addEventListener('paste', (e) => {
      const txt = (e.clipboardData || window.clipboardData || {}).getData?.('text') || '';
      if (!/^https?:\/\//i.test(txt.trim())) return;  // not a URL — let normal paste happen
      const ex = extractHotelFromUrl(txt);
      if (!ex) return;  // unrecognized site — let normal paste happen
      e.preventDefault();
      applyExtractedToForm(ex);
    });
  })();

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
      tbody.innerHTML = '<tr><td colspan="10" class="muted" style="text-align:center; padding: 32px;">No results.</td></tr>';
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

    // Map hook — render pins for all ranked rows with valid coords.
    try {
      if (window.HHMap && state.ranked.length > 0) {
        window.HHMap.render(state.ranked, ($('#q') && $('#q').value) || '');
      }
    } catch (_e) { /* never break renderResults if the map module fails */ }
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
    const channel = formatChannel(row.recommended_channel);
    const badges = (row.badges || []).map(b => badgeChip(b)).join('');
    const notes = escapeHtml((row.channel_reason || row.explanation || '').slice(0, 70));
    const topDealCls = (i === 0) ? ' top-deal' : '';
    const fav = faviconImg(n.name, n.brand);
    const book = bookLinks(n);
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
        <td class="book-links">${book}</td>
        <td class="muted">${notes}</td>
      </tr>`;
  }

  // ----------------------------------------------------------------
  // BOOK column — small links ordered so the most reliable booking path wins.
  // Hotel's own website first (brand-direct), then the rate's source (could be
  // an aggregator like vio.com — these sometimes have backend hiccups), then
  // a Google Maps lookup as a universal fallback.
  // ----------------------------------------------------------------
  function brandSearchUrl(domain, query) {
    const q = encodeURIComponent(query);
    switch (domain) {
      case 'marriott.com':
        return `https://www.marriott.com/search/findHotels.mi?destinationAddress.destination=${q}`;
      case 'hyatt.com':
        return `https://www.hyatt.com/search?destination=${q}`;
      case 'hilton.com':
        return `https://www.hilton.com/en/search/?query=${q}`;
      case 'ihg.com':
        return `https://www.ihg.com/hotels/us/en/find-hotels/hotel/list?destination=${q}`;
      default:
        return `https://www.${domain}/`;
    }
  }

  // Known third-party aggregators / resellers. We match the registrable domain
  // OR any subdomain of it (e.g. `deals.vio.com` should match `vio.com`). When
  // source_url points at one of these, we label it as a rate source rather
  // than the hotel's own site, since aggregators sometimes have backend
  // failures the actual hotel doesn't (e.g. vio.com's MySQL outages).
  const AGGREGATOR_DOMAINS = [
    'vio.com', 'agoda.com', 'booking.com', 'expedia.com', 'hotels.com',
    'priceline.com', 'kayak.com', 'trivago.com', 'tripadvisor.com',
    'orbitz.com', 'travelocity.com', 'getyourguide.com', 'tiket.com',
    'hotwire.com', 'wotif.com', 'ebookers.com', 'lastminute.com',
    'snaptravel.com', 'hotelplanner.com', 'amoma.com', 'reservationcounts.com',
  ];
  function isAggregatorHost(host) {
    if (!host) return false;
    const h = host.toLowerCase();
    return AGGREGATOR_DOMAINS.some(d => h === d || h.endsWith('.' + d));
  }

  function bookLinks(n) {
    n = n || {};
    const name = n.name ?? '';
    const loc = n.location || {};
    const city = loc.city ?? '';
    const country = loc.country ?? '';
    const lat = loc.lat;
    const lon = loc.lon;
    const parts = [];

    // 1) HOTEL — direct website of the hotel itself, when we can identify it.
    //    This is the most reliable click for actual booking. We try the
    //    source_url first (if it's the hotel's own site, not an aggregator),
    //    then fall back to the brand's chain search if we know the chain.
    let hotelDirectUrl = null;
    let hotelDirectLabel = null;
    const sourceUrl = n.source_url ?? '';
    let sourceHost = null;
    if (sourceUrl) {
      try {
        sourceHost = new URL(sourceUrl).hostname.replace(/^www\./, '') || null;
      } catch (_) { sourceHost = null; }
    }
    const sourceIsAggregator = isAggregatorHost(sourceHost);
    if (sourceHost && !sourceIsAggregator) {
      // The rate source IS the hotel's own website — that's the gold standard.
      hotelDirectUrl = sourceUrl;
      hotelDirectLabel = 'Hotel website';
    } else {
      // Source is an aggregator (or no source). Try chain-direct lookup.
      const dom = brandDomain(name, n.brand);
      if (dom) {
        const queryStr = [name, city, country].filter(Boolean).join(' ');
        hotelDirectUrl = brandSearchUrl(dom, queryStr || name);
        hotelDirectLabel = 'Hotel website';
      }
    }
    if (hotelDirectUrl) {
      parts.push(
        `<a href="${escapeAttr(hotelDirectUrl)}" target="_blank" rel="noopener noreferrer" title="Book on the hotel's own site">${escapeHtml(hotelDirectLabel)}</a>`
      );
    }

    // 2) AGGREGATOR (if applicable) — only shown if the SerpApi rate source
    //    differs from what we already linked above. Labeled so the user knows
    //    they're being sent to a third-party site that may have its own issues.
    if (sourceUrl && sourceUrl !== hotelDirectUrl && sourceHost) {
      const label = sourceIsAggregator ? `Rate source (${sourceHost})` : sourceHost;
      parts.push(
        `<a href="${escapeAttr(sourceUrl)}" target="_blank" rel="noopener noreferrer" title="Where Google Hotels found this rate — third-party site">${escapeHtml(label)}</a>`
      );
    }

    // 3) MAPS — always shown as a universal fallback (lookup by lat/lon or name)
    let mapsQuery;
    if (typeof lat === 'number' && typeof lon === 'number' && !isNaN(lat) && !isNaN(lon)) {
      mapsQuery = `${lat},${lon}`;
    } else {
      mapsQuery = [name, city, country].filter(Boolean).join(', ') || name || 'hotel';
    }
    const mapsUrl = `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(mapsQuery)}`;
    parts.push(
      `<a href="${escapeAttr(mapsUrl)}" target="_blank" rel="noopener noreferrer" title="Open in Google Maps">Maps</a>`
    );

    return parts.join('<span class="sep">·</span>');
  }

  function badgeChip(b) {
    const map = {
      'REFUNDABLE': { cls: 'refundable', label: 'Refundable' },
      'FHR':        { cls: 'fhr',        label: 'Fine Hotels & Resorts' },
      'PTS':        { cls: 'pts',        label: 'Points stay' },
      '5TH-FREE':   { cls: 'fifth',      label: 'Fifth night free' },
      '4TH-FREE':   { cls: 'fourth',     label: 'Fourth night free' },
      'CCY-NOTE':   { cls: 'ccy',        label: 'Currency note' },
      'TOS-RISK':   { cls: 'tos',        label: 'Booking risk' },
      'LEGAL':      { cls: 'legal',      label: 'Verified rate' },
      'GRAY':       { cls: 'gray',       label: 'Unverified' },
    };
    const e = map[b] || { cls: 'gray', label: String(b) };
    return `<span class="badge ${e.cls}" title="${escapeHtml(b)}">${escapeHtml(e.label)}</span>`;
  }

  function formatChannel(c) {
    const map = {
      'direct':        'Hotel website',
      'ota':           'Booking site',
      'fhr':           'Amex Fine Hotels & Resorts',
      'points-portal': 'Points portal',
      'points':        'Points portal',
    };
    return map[(c || '').toLowerCase()] || (c || '—');
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
    detailTr.innerHTML = `<td colspan="10"><div class="row-detail">${renderBreakdown(row)}</div></td>`;
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
      { k: 'Amex Fine Hotels & Resorts value', v: '− ' + fmtMoney(b.fhr_value_usd),         cls: 'neg' },
      { k: 'Currency haircut (non-USD folio)', v: '+ ' + fmtMoney(b.fhr_haircut_usd),       cls: 'pos' },
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
  // Expose for HHMap (detail panel) to re-use.
  window.__hhOpenUpgradeEmail = openUpgradeEmail;
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
  // Three sections (mirrors flight_hacker's editorial layout):
  //   1. TRANSFER CURRENCIES — bank points (Amex MR, Chase UR, …)
  //   2. HOTEL LOYALTY PROGRAMS — per-program direct balance
  //   3. ELITE CARDS — FHR-qualifying card checklist
  //
  // READ path:  GET /api/balances (server reads data/user_balances.json,
  //             falls back to data/user_balances.example.json).
  // WRITE path: POST /api/balances (server writes data/user_balances.json).
  // state.balances is the in-memory source of truth and is piped into every
  // /api/rank request via runRank() above.
  // ----------------------------------------------------------------

  // Transfer currencies — annotated with 1:1 hotel partners (display-only;
  // v1 ranker uses direct program balances only).
  const CURRENCY_ROWS = [
    { name: 'Amex Membership Rewards',  transfers: ['Hilton Honors (1:2)', 'Marriott Bonvoy (1:1)', 'Choice Privileges (1:1)'] },
    { name: 'Chase Ultimate Rewards',   transfers: ['World of Hyatt (1:1)', 'IHG One Rewards (1:1)', 'Marriott Bonvoy (1:1)'] },
    { name: 'Citi ThankYou',            transfers: ['Choice Privileges (1:2)', 'Wyndham Rewards (1:1)'] },
    { name: 'Capital One Miles',        transfers: ['Wyndham Rewards (1:1)', 'Accor ALL (2:1)'] },
    { name: 'Bilt Rewards',             transfers: ['Hilton Honors (1:1)', 'IHG One Rewards (1:1)', 'Marriott Bonvoy (1:1)'] },
  ];
  // Currency rows show a representative card-issuer favicon to keep the
  // visual rhythm with the hotel program rows below.
  const CURRENCY_BRAND = {
    'Amex Membership Rewards':  'americanexpress.com',
    'Chase Ultimate Rewards':   'chase.com',
    'Citi ThankYou':            'citi.com',
    'Capital One Miles':        'capitalone.com',
    'Bilt Rewards':             'biltrewards.com',
  };

  // Hotel loyalty programs — display name + free-night rule label.
  const PROGRAM_ROWS = [
    { name: 'World of Hyatt',           rule: '— (no free-night mechanic)' },
    { name: 'Marriott Bonvoy',          rule: '5th night free (5+ night award)' },
    { name: 'Hilton Honors',            rule: '5th night free (Gold+ award)' },
    { name: 'IHG One Rewards',          rule: '4th night free (Platinum+ award)' },
    { name: 'Accor Live Limitless',     rule: '— (fixed cash ratio)' },
    { name: 'Wyndham Rewards',          rule: '— (flat tier pricing)' },
    { name: 'Choice Privileges',        rule: '—' },
    { name: 'Best Western Rewards',     rule: '—' },
  ];

  // FHR-qualifying cards (per data/perk_rules.json#fhr_requires_card).
  // ONLY these cards gate FHR value in the ranker.
  const FHR_CARDS = [
    'Amex Platinum',
    'Amex Centurion',
    'Amex Business Platinum',
  ];

  function balanceFavicon(domain) {
    if (!domain) return '<span class="brand-favicon" aria-hidden="true"></span>';
    const url = `https://www.google.com/s2/favicons?sz=64&domain=${encodeURIComponent(domain)}`;
    return `<img class="brand-favicon" alt="" src="${url}" loading="lazy" onerror="this.dataset.missing=1">`;
  }

  function renderBalances() {
    const curBody = $('#bal-currencies-body');
    const proBody = $('#bal-programs-body');
    const car     = $('#bal-cards');
    if (!curBody || !proBody || !car) return;

    // TRANSFER CURRENCIES table — Program / Balance / Transfers To.
    // Inputs are wrapped in `.field` to inherit the existing brutal styling.
    curBody.innerHTML = CURRENCY_ROWS.map(row => {
      const val = Number(state.balances.currencies?.[row.name] || 0);
      const fav = balanceFavicon(CURRENCY_BRAND[row.name]);
      return `
        <tr>
          <td><span class="hotel-cell">${fav}<strong class="hotel-name">${escapeHtml(row.name)}</strong></span></td>
          <td class="num">
            <div class="field" style="margin:0;">
              <input type="number" min="0" step="1000"
                     data-bal-currency="${escapeAttr(row.name)}"
                     value="${val}"
                     style="text-align:right;">
            </div>
          </td>
          <td class="muted micro">${escapeHtml(row.transfers.join(' · '))}</td>
        </tr>
      `;
    }).join('');

    // HOTEL LOYALTY PROGRAMS table — favicon via the shared BRAND_DOMAIN map.
    proBody.innerHTML = PROGRAM_ROWS.map(row => {
      const val = Number(state.balances.programs?.[row.name] || 0);
      const fav = faviconImg(row.name, row.name);
      return `
        <tr>
          <td><span class="hotel-cell">${fav}<strong class="hotel-name">${escapeHtml(row.name)}</strong></span></td>
          <td class="num">
            <div class="field" style="margin:0;">
              <input type="number" min="0" step="1000"
                     data-bal-program="${escapeAttr(row.name)}"
                     value="${val}"
                     style="text-align:right;">
            </div>
          </td>
          <td class="muted micro">${escapeHtml(row.rule)}</td>
        </tr>
      `;
    }).join('');

    // ELITE CARDS — only FHR-qualifying cards.
    car.innerHTML = FHR_CARDS.map(name => `
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

    // Preserve any keys the UI doesn't render (forward-compatible) by merging
    // form values on top of the previously-loaded balances object.
    const prev = state.balances || { currencies: {}, programs: {}, cards: [] };
    const next = {
      currencies: Object.assign({}, prev.currencies || {}),
      programs:   Object.assign({}, prev.programs   || {}),
      cards:      (prev.cards || []).slice(),
    };
    $$('[data-bal-currency]').forEach(i => {
      next.currencies[i.dataset.balCurrency] = Number(i.value) || 0;
    });
    $$('[data-bal-program]').forEach(i => {
      next.programs[i.dataset.balProgram] = Number(i.value) || 0;
    });
    // Rebuild the FHR-card subset from the rendered checkboxes, but keep any
    // non-FHR card strings the user previously stored.
    const renderedCards = new Set(FHR_CARDS);
    next.cards = (next.cards || []).filter(c => !renderedCards.has(c));
    $$('[data-bal-card]:checked').forEach(c => {
      next.cards.push(c.dataset.balCard);
    });

    // optimistic — keep state.balances current so the next /api/rank uses it.
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

/* ============================================================
   HHMap — Google Maps view + side detail panel for the RESULTS tab.
   Self-contained module attached to window.HHMap so it can be
   driven from app.js without polluting globals (aside from the
   API-load callback `_hhmapApiReady`, which must be a global).
   ============================================================ */
(function () {
  'use strict';

  // ----- DOM helpers (local copies — we are outside the main IIFE) -----
  const $ = (s, root) => (root || document).querySelector(s);
  const REDUCED_MOTION = window.matchMedia &&
    window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // ----- module state -----
  const _state = {
    apiKey: null,           // GOOGLE_MAPS_API_KEY value (or null)
    keyFetched: false,      // whether /api/map-key has been resolved
    apiLoading: false,      // whether the Maps JS script is in flight
    apiReady: false,        // whether google.maps + .marker are loaded
    apiFailed: false,       // permanent failure (network blocked etc.)
    pendingRender: null,    // {rankedRows, queryStr} queued during load
    map: null,
    markers: [],            // [{el, marker, row, scoreRank, lat, lng}]
    bounds: null,
    currentRow: null,
  };

  // ----- format helpers -----
  function _fmtMoney(n) {
    if (n === null || n === undefined || isNaN(n)) return '—';
    const num = Number(n);
    const sign = num < 0 ? '−' : '';
    const abs = Math.abs(num);
    return sign + '$' + abs.toLocaleString('en-US', {
      maximumFractionDigits: 0, minimumFractionDigits: 0,
    });
  }
  function _esc(s) {
    if (s === null || s === undefined) return '';
    return String(s)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;').replace(/'/g, '&#39;');
  }
  function _validLatLng(loc) {
    if (!loc) return false;
    const la = Number(loc.lat), ln = Number(loc.lon);
    return Number.isFinite(la) && Number.isFinite(ln) &&
           la >= -90 && la <= 90 && ln >= -180 && ln <= 180 &&
           !(la === 0 && ln === 0);
  }

  // ----- dark map style (12 featureType entries) -----
  const HH_DARK_STYLE = [
    { elementType: 'geometry',          stylers: [{ color: '#0a0d12' }] },
    { elementType: 'labels.text.fill',  stylers: [{ color: '#a6a191' }] },
    { elementType: 'labels.text.stroke',stylers: [{ color: '#0a0d12' }] },
    { featureType: 'administrative',
      elementType: 'geometry.stroke',
      stylers: [{ color: '#3a4150' }] },
    { featureType: 'administrative.country',
      elementType: 'labels.text.fill',
      stylers: [{ color: '#B89968' }] },
    { featureType: 'administrative.locality',
      elementType: 'labels.text.fill',
      stylers: [{ color: '#a6a191' }] },
    { featureType: 'landscape',
      elementType: 'geometry.fill',
      stylers: [{ color: '#0a0d12' }] },
    { featureType: 'landscape.natural',
      elementType: 'geometry',
      stylers: [{ color: '#131820' }] },
    { featureType: 'poi',                stylers: [{ visibility: 'off' }] },
    { featureType: 'poi.park',
      elementType: 'geometry',
      stylers: [{ color: '#131820' }] },
    { featureType: 'road',
      elementType: 'geometry.fill',
      stylers: [{ color: '#232a35' }] },
    { featureType: 'road',
      elementType: 'geometry.stroke',
      stylers: [{ color: '#1a1f29' }] },
    { featureType: 'road',
      elementType: 'labels.text.fill',
      stylers: [{ color: '#6b6759' }] },
    { featureType: 'road.highway',
      elementType: 'geometry.fill',
      stylers: [{ color: '#2a3140' }] },
    { featureType: 'road.highway',
      elementType: 'geometry.stroke',
      stylers: [{ color: '#3a4150' }] },
    { featureType: 'road.arterial',
      elementType: 'geometry.fill',
      stylers: [{ color: '#232a35' }] },
    { featureType: 'road.local',
      elementType: 'geometry.fill',
      stylers: [{ color: '#1a1f29' }] },
    { featureType: 'transit',            stylers: [{ visibility: 'simplified' }] },
    { featureType: 'transit.station',
      elementType: 'geometry',
      stylers: [{ color: '#232a35' }] },
    { featureType: 'transit.line',
      elementType: 'geometry',
      stylers: [{ color: '#1a1f29' }] },
    { featureType: 'water',
      elementType: 'geometry',
      stylers: [{ color: '#131820' }] },
    { featureType: 'water',
      elementType: 'labels.text.fill',
      stylers: [{ color: '#3a4150' }] },
  ];

  // ----- API loader (mirrors URIEL pattern at index.html:11942-12011) -----
  function _injectScript(key, onLoad, onError) {
    if (window.google && window.google.maps && window.google.maps.marker) {
      _state.apiReady = true;
      onLoad(); return;
    }
    let src = 'https://maps.googleapis.com/maps/api/js?libraries=places,marker&v=weekly&callback=_hhmapApiReady';
    if (key) {
      src = 'https://maps.googleapis.com/maps/api/js?key=' +
            encodeURIComponent(key) +
            '&libraries=places,marker&v=weekly&callback=_hhmapApiReady';
    }
    window._hhmapApiReady = function () {
      _state.apiReady = true;
      _state.apiLoading = false;
      onLoad();
    };
    const s = document.createElement('script');
    s.src = src; s.async = true; s.defer = true;
    s.onerror = function () {
      _state.apiFailed = true;
      _state.apiLoading = false;
      console.warn('[hh-map] Google Maps JS failed to load (network blocked?)');
      onError && onError();
    };
    document.head.appendChild(s);
  }

  function _loadMapsAPI(onLoad, onError) {
    if (_state.apiReady) { onLoad(); return; }
    if (_state.apiFailed) { onError && onError(); return; }
    if (_state.apiLoading) {
      // Wait for the in-flight load.
      const t = setInterval(function () {
        if (_state.apiReady) { clearInterval(t); onLoad(); }
        else if (_state.apiFailed) { clearInterval(t); onError && onError(); }
      }, 80);
      return;
    }
    _state.apiLoading = true;
    if (_state.keyFetched) {
      _injectScript(_state.apiKey, onLoad, onError);
      return;
    }
    fetch('/api/map-key')
      .then(function (r) { return r.json(); })
      .catch(function () { return { key: null }; })
      .then(function (data) {
        _state.keyFetched = true;
        _state.apiKey = (data && data.key) ? data.key : null;
        if (!_state.apiKey) {
          console.info('[hh-map] No GOOGLE_MAPS_API_KEY — running watermarked dev mode.');
          _showNoKeyHint();
        }
        _injectScript(_state.apiKey, onLoad, onError);
      });
  }

  function _showNoKeyHint() {
    // One-time inline note inside the map toolbar explaining the watermark.
    const hintEl = document.getElementById('map-hint');
    if (!hintEl) return;
    if (hintEl.dataset.nokeyHint === '1') return;
    hintEl.dataset.nokeyHint = '1';
    hintEl.innerHTML =
      '— Google shows a faded "for development purposes only" overlay until you add a free Google Maps key. ' +
      '<a href="https://console.cloud.google.com/google/maps-apis/start" target="_blank" rel="noopener" style="color:var(--accent);">Get one (~3 min)</a>, ' +
      'then re-run <code style="background:var(--panel-2);padding:0 4px;">./setup-keys.sh</code>.';
  }

  // ----- pin DOM builder -----
  function _buildPinEl(scoreRank, effectiveUsd, isTop) {
    const root = document.createElement('div');
    root.className = 'hh-pin' + (isTop ? ' hh-pin--top' : '');
    root.setAttribute('role', 'button');
    root.setAttribute('aria-label', 'Rank ' + scoreRank);
    const num = document.createElement('span');
    num.className = 'hh-pin__num';
    num.textContent = String(scoreRank);
    root.appendChild(num);
    if (effectiveUsd !== undefined && effectiveUsd !== null && !isNaN(effectiveUsd)) {
      const price = document.createElement('span');
      price.className = 'hh-pin__price';
      price.textContent = _fmtMoney(effectiveUsd);
      root.appendChild(price);
    }
    return root;
  }

  // ----- map init -----
  function _showMapPanel() {
    const panel = document.getElementById('map-panel');
    if (panel) panel.removeAttribute('hidden');
  }
  function _showMapError(msg) {
    const canvas = document.getElementById('map-canvas');
    if (!canvas) return;
    canvas.innerHTML = '';
    const note = document.createElement('div');
    note.className = 'map-canvas__error';
    note.textContent = msg || 'Map unavailable — check internet connection';
    canvas.appendChild(note);
    _showMapPanel();
  }

  function _initMap(centerLat, centerLng) {
    const canvas = document.getElementById('map-canvas');
    if (!canvas) return null;
    // Clear any error placeholder from a previous attempt.
    canvas.innerHTML = '';
    const opts = {
      center: { lat: centerLat, lng: centerLng },
      zoom: 12,
      mapId: 'DEMO_MAP_ID',
      disableDefaultUI: false,
      zoomControl: true,
      mapTypeControl: false,
      streetViewControl: false,
      fullscreenControl: false,
      gestureHandling: 'greedy',
      backgroundColor: '#0a0d12',
      styles: HH_DARK_STYLE,
    };
    try {
      return new google.maps.Map(canvas, opts);
    } catch (e) {
      console.warn('[hh-map] Map ctor failed:', e);
      return null;
    }
  }

  function _clearMarkers() {
    for (const m of _state.markers) {
      try {
        if (m.marker) m.marker.map = null;
      } catch (_e) {}
    }
    _state.markers = [];
  }

  function _addMarkers(map, rows) {
    _clearMarkers();
    const bounds = new google.maps.LatLngBounds();
    let added = 0;
    for (const row of rows) {
      const n = row.normalized || {};
      const loc = n.location || {};
      if (!_validLatLng(loc)) continue;
      const scoreRank = row.score_rank || (added + 1);
      const isTop = (added === 0) || (scoreRank === 1);
      const el = _buildPinEl(scoreRank, row.effective_usd, isTop);
      let marker;
      try {
        marker = new google.maps.marker.AdvancedMarkerElement({
          map: map,
          position: { lat: Number(loc.lat), lng: Number(loc.lon) },
          content: el,
          title: n.name || ('Rank ' + scoreRank),
        });
      } catch (e) {
        console.warn('[hh-map] Marker create failed:', e);
        continue;
      }
      marker.addListener('click', function () {
        try { window.HHMap.openDetail(row); } catch (_e) {}
        try {
          document.dispatchEvent(new CustomEvent('hh:pin-clicked', {
            detail: { scoreRank: scoreRank },
          }));
        } catch (_e) {}
      });
      el.addEventListener('mouseenter', function () {
        el.classList.add('hh-pin--hover');
        try {
          document.dispatchEvent(new CustomEvent('hh:pin-hover', {
            detail: { scoreRank: scoreRank, state: 'enter' },
          }));
        } catch (_e) {}
      });
      el.addEventListener('mouseleave', function () {
        el.classList.remove('hh-pin--hover');
        try {
          document.dispatchEvent(new CustomEvent('hh:pin-hover', {
            detail: { scoreRank: scoreRank, state: 'leave' },
          }));
        } catch (_e) {}
      });
      bounds.extend({ lat: Number(loc.lat), lng: Number(loc.lon) });
      _state.markers.push({
        el: el, marker: marker, row: row, scoreRank: scoreRank,
        lat: Number(loc.lat), lng: Number(loc.lon),
      });
      added++;
    }
    _state.bounds = bounds;
    if (added > 1) {
      try { map.fitBounds(bounds, 24); } catch (_e) {}
    } else if (added === 1) {
      try { map.setCenter(bounds.getCenter()); map.setZoom(14); } catch (_e) {}
    }
    return added;
  }

  function _updateToolbar(pinCount) {
    const c = document.getElementById('map-count');
    if (c) c.textContent = pinCount + (pinCount === 1 ? ' pin' : ' pins');
  }

  // ----- detail panel -----
  function _streetViewIframeHtml(lat, lng) {
    const key = _state.apiKey;
    if (key) {
      const url = 'https://www.google.com/maps/embed/v1/streetview?key=' +
        encodeURIComponent(key) +
        '&location=' + lat + ',' + lng +
        '&heading=0&pitch=0&fov=80';
      return '<iframe src="' + url + '" width="100%" height="240" ' +
             'loading="lazy" style="border:0" allowfullscreen ' +
             'referrerpolicy="no-referrer-when-downgrade"></iframe>';
    }
    // Keyless fallback — works without an API key.
    const url = 'https://maps.google.com/maps?layer=c' +
      '&cbll=' + lat + ',' + lng +
      '&cbp=11,0,0,0,0&z=18&output=svembed';
    return '<iframe src="' + url + '" width="100%" height="240" ' +
           'loading="lazy" style="border:0" allowfullscreen></iframe>';
  }

  function _renderBreakdownKV(row) {
    const b = row.breakdown || {};
    const lines = [
      { k: 'Raw total (after taxes & fees)',
        v: _fmtMoney(b.raw_total_usd != null ? b.raw_total_usd : row.raw_usd),
        cls: '' },
      { k: 'Points value applied',
        v: '− ' + _fmtMoney(b.points_value_usd), cls: 'neg' },
      { k: 'Free-night value',
        v: '− ' + _fmtMoney(b.free_night_value_usd), cls: 'neg' },
      { k: 'Amex Fine Hotels & Resorts value',
        v: '− ' + _fmtMoney(b.fhr_value_usd), cls: 'neg' },
      { k: 'Currency haircut (non-USD folio)',
        v: '+ ' + _fmtMoney(b.fhr_haircut_usd), cls: 'pos' },
      { k: 'Flexibility penalty',
        v: '+ ' + _fmtMoney(b.flexibility_penalty_usd), cls: 'pos' },
      { k: 'Currency arbitrage',
        v: (Number(b.currency_arb_usd) >= 0 ? '+ ' : '') + _fmtMoney(b.currency_arb_usd),
        cls: Number(b.currency_arb_usd) >= 0 ? 'pos' : 'neg' },
    ];
    let html = '<div class="kv-grid">';
    for (const L of lines) {
      html += '<span class="k">' + _esc(L.k) + '</span>' +
              '<span class="v ' + L.cls + '">' + L.v + '</span>';
    }
    html += '<span class="k total">EFFECTIVE TOTAL</span>' +
            '<span class="v total">' + _fmtMoney(row.effective_usd) + '</span>';
    html += '</div>';
    return html;
  }

  function _renderBadges(badges) {
    if (!badges || !badges.length) return '';
    const map = {
      'REFUNDABLE': { cls: 'refundable', label: 'Refundable' },
      'FHR':        { cls: 'fhr',        label: 'Fine Hotels & Resorts' },
      'PTS':        { cls: 'pts',        label: 'Points stay' },
      '5TH-FREE':   { cls: 'fifth',      label: 'Fifth night free' },
      '4TH-FREE':   { cls: 'fourth',     label: 'Fourth night free' },
      'CCY-NOTE':   { cls: 'ccy',        label: 'Currency note' },
      'TOS-RISK':   { cls: 'tos',        label: 'Booking risk' },
      'LEGAL':      { cls: 'legal',      label: 'Verified rate' },
      'GRAY':       { cls: 'gray',       label: 'Unverified' },
    };
    return badges.map(function (b) {
      const e = map[b] || { cls: 'gray', label: String(b) };
      return '<span class="badge ' + e.cls + '" title="' + _esc(b) + '">' + _esc(e.label) + '</span>';
    }).join('');
  }

  function _openDetail(row) {
    const panel = document.getElementById('detail-panel');
    const backdrop = document.getElementById('detail-panel-backdrop');
    if (!panel || !row) return;
    _state.currentRow = row;
    const n = row.normalized || {};
    const loc = n.location || {};
    const city = loc.city || '';
    const country = loc.country || '';
    const subParts = [];
    if (city) subParts.push(city);
    if (country) subParts.push(country);
    const sub = subParts.join(', ');
    const nameEl = document.getElementById('dp-name');
    const subEl  = document.getElementById('dp-sub');
    if (nameEl) nameEl.textContent = n.name || '(unnamed)';
    if (subEl)  subEl.textContent  = sub || '—';

    // Stats
    const setText = (id, txt) => { const e = document.getElementById(id); if (e) e.textContent = txt; };
    setText('dp-raw',    _fmtMoney(row.raw_usd));
    setText('dp-eff',    _fmtMoney(row.effective_usd));
    setText('dp-nights', n.nights != null ? String(n.nights) : '—');
    setText('dp-rating', n.overall_rating != null ? String(n.overall_rating) : '—');

    // Explanation + breakdown + badges + addr
    const expEl = document.getElementById('dp-explanation');
    if (expEl) expEl.textContent = row.explanation || '—';
    const brEl  = document.getElementById('dp-breakdown');
    if (brEl)   brEl.innerHTML = _renderBreakdownKV(row);
    const bdgEl = document.getElementById('dp-badges');
    if (bdgEl)  bdgEl.innerHTML = _renderBadges(row.badges || []);
    const addrEl = document.getElementById('dp-addr');
    if (addrEl) addrEl.textContent = loc.address || sub || '—';

    // Street View iframe
    const sv = document.getElementById('dp-streetview');
    if (sv) {
      if (_validLatLng(loc)) {
        sv.innerHTML = _streetViewIframeHtml(Number(loc.lat), Number(loc.lon));
      } else {
        sv.innerHTML = '<div class="detail-panel__sv-fallback">No street view available</div>';
      }
    }

    // Actions
    const bookEl = document.getElementById('dp-book');
    if (bookEl) bookEl.href = n.source_url || '#';
    const mapsEl = document.getElementById('dp-maps');
    if (mapsEl) {
      const q = encodeURIComponent([n.name || '', city].filter(Boolean).join(', '));
      mapsEl.href = 'https://www.google.com/maps/search/?api=1&query=' + q;
    }
    const upEl = document.getElementById('dp-upgrade');
    if (upEl) {
      upEl.onclick = function () {
        try {
          if (typeof window.__hhOpenUpgradeEmail === 'function') {
            window.__hhOpenUpgradeEmail(n.name || '', n.check_in || '');
          }
        } catch (_e) {}
      };
    }

    // Reveal panel
    panel.hidden = false;
    panel.setAttribute('aria-hidden', 'false');
    if (backdrop) { backdrop.hidden = false; }
    // next tick for transition
    requestAnimationFrame(function () {
      panel.classList.add('open');
      if (backdrop) backdrop.classList.add('open');
    });
  }

  function _closeDetail() {
    const panel = document.getElementById('detail-panel');
    const backdrop = document.getElementById('detail-panel-backdrop');
    if (!panel) return;
    panel.classList.remove('open');
    if (backdrop) backdrop.classList.remove('open');
    const finish = function () {
      panel.hidden = true;
      panel.setAttribute('aria-hidden', 'true');
      if (backdrop) backdrop.hidden = true;
      // Drop street view to stop any audio/network.
      const sv = document.getElementById('dp-streetview');
      if (sv) sv.innerHTML = '<div class="detail-panel__sv-fallback">Loading street view…</div>';
    };
    if (REDUCED_MOTION) { finish(); }
    else { setTimeout(finish, 240); }
    _state.currentRow = null;
  }

  // Wire close-button + backdrop + Esc (idempotent — guard with a flag).
  function _wireOnce() {
    if (_wireOnce._done) return;
    _wireOnce._done = true;
    const close = document.getElementById('dp-close');
    if (close) close.addEventListener('click', _closeDetail);
    const backdrop = document.getElementById('detail-panel-backdrop');
    if (backdrop) backdrop.addEventListener('click', _closeDetail);
    document.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape') {
        const panel = document.getElementById('detail-panel');
        if (panel && panel.classList.contains('open')) {
          ev.stopPropagation();
          _closeDetail();
        }
      }
    });
  }

  // ----- highlight (called from app.js when a row is hovered, optional) -----
  function _highlightRow(scoreRank) {
    for (const m of _state.markers) {
      if (m.scoreRank === scoreRank) m.el.classList.add('hh-pin--hover');
      else m.el.classList.remove('hh-pin--hover');
    }
  }

  // ----- render entrypoint -----
  function _render(rankedRows, _queryStr) {
    _wireOnce();
    // Filter to rows with coords.
    const usable = (rankedRows || []).filter(function (r) {
      return _validLatLng(r && r.normalized && r.normalized.location);
    });
    _updateToolbar(usable.length);

    if (!usable.length) {
      // Show the panel with a friendly note so the user knows the map is "live"
      // but skipped — e.g. all results lack coords.
      _showMapPanel();
      const canvas = document.getElementById('map-canvas');
      if (canvas) {
        canvas.innerHTML = '<div class="map-canvas__error">No mappable coordinates in these results.</div>';
      }
      return;
    }

    _showMapPanel();

    _loadMapsAPI(function () {
      // Average lat/lon for initial center.
      let sumLat = 0, sumLng = 0;
      for (const r of usable) {
        sumLat += Number(r.normalized.location.lat);
        sumLng += Number(r.normalized.location.lon);
      }
      const cLat = sumLat / usable.length;
      const cLng = sumLng / usable.length;
      if (!_state.map) {
        _state.map = _initMap(cLat, cLng);
      } else {
        // Re-center for the new result set.
        try { _state.map.setCenter({ lat: cLat, lng: cLng }); } catch (_e) {}
      }
      if (!_state.map) { _showMapError(); return; }
      const added = _addMarkers(_state.map, usable);
      _updateToolbar(added);
    }, function () {
      _showMapError('Map unavailable — check internet connection');
    });
  }

  function _clear() {
    _clearMarkers();
    const panel = document.getElementById('map-panel');
    if (panel) panel.setAttribute('hidden', '');
    _updateToolbar(0);
  }

  // ----- public surface -----
  window.HHMap = {
    render: _render,
    openDetail: _openDetail,
    clear: _clear,
    highlightRow: _highlightRow,
  };

  // Light up the corresponding table row when a pin is hovered.
  document.addEventListener('hh:pin-hover', function (ev) {
    try {
      const sr = ev && ev.detail && ev.detail.scoreRank;
      const st = ev && ev.detail && ev.detail.state;
      if (!sr) return;
      const rows = document.querySelectorAll('#results-body tr.data-row');
      rows.forEach(function (tr) {
        const rk = tr.querySelector('.rank');
        const match = rk && rk.textContent.trim().replace(/^[★\s]+/, '') === String(sr);
        if (match) {
          if (st === 'enter') tr.classList.add('row-pin-hover');
          else tr.classList.remove('row-pin-hover');
        }
      });
    } catch (_e) {}
  });
})();
