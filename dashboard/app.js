/* USVI Federal Spending - reads data/summary.json (pipeline/step5_export.py) */
(async function () {
  const C = { ink: '#0E2A3B', coral: '#C8553D', coralL: '#E8836B', sea: '#2F7F86', seaL: '#8CC2C4', sand: '#D9CBB0', line: '#EFE9DE', muted: '#6B7C89', faint: '#9AA7B1' };
  const S = await fetch('data/summary.json').then((r) => r.json()).catch(() => null);
  if (!S) { document.getElementById('updated').textContent = 'Data files are missing - run the pipeline first.'; return; }

  const nf = (v, d = 0) => v == null ? '–' : Number(v).toLocaleString('en-US', { maximumFractionDigits: d, minimumFractionDigits: d });
  // $1.23B / $45.6M / $812K / $950
  const money = (v, d) => {
    if (v == null) return '–';
    const a = Math.abs(v), s = v < 0 ? '−$' : '$';
    if (a >= 1e9) return `${s}${nf(a / 1e9, d ?? (a >= 1e10 ? 1 : 2))}B`;
    if (a >= 1e6) return `${s}${nf(a / 1e6, d ?? (a >= 1e8 ? 0 : 1))}M`;
    if (a >= 1e3) return `${s}${nf(a / 1e3, 0)}K`;
    return `${s}${nf(a, 0)}`;
  };
  const cents = (v) => v == null ? '–' : (v < 0 ? '−$' : '$') + nf(Math.abs(v), 2);
  const pct = (v, d = 0) => v == null ? '–' : `${nf(100 * v, d)}%`;
  const esc = (s) => String(s ?? '').replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  const dateTxt = (s) => { if (!s) return '–'; const [y, m, d] = s.slice(0, 10).split('-').map(Number); return `${MON[m - 1]} ${d}, ${y}`; };
  const monthTxt = (s) => { if (!s) return '–'; const [y, m] = s.slice(0, 7).split('-').map(Number); return `${MON[m - 1]} ${y}`; };
  const astTxt = (s) => {
    if (!s) return '–';
    const t = new Date(/[zZ+]/.test(s.slice(10)) ? s : `${s.length <= 16 ? s + ':00' : s}Z`);
    return t.toLocaleString('en-US', { timeZone: 'America/St_Thomas', month: 'short', day: 'numeric', year: 'numeric', hour: 'numeric', minute: '2-digit' }) + ' AST';
  };
  // "DEPARTMENT OF HOMELAND SECURITY (DHS)" style names are already cased; contractor names are upper case
  const SMALL = new Set(['of', 'and', 'the', 'for', 'in', 'on', 'at', 'to', 'de']);
  const KEEP = /^(LLC|LLP|LP|INC|USA|US|USVI|VI|II|III|IV|JV|PC|PLLC|WAPA|UVI|HOVENSA|AECOM|CDM|DBA|WSP|GEC|CAE|HDR|GHD|SAIC|CH2M|N\.A\.|N\.V\.)\.?,?$/;
  const title = (s) => {
    if (!s) return '';
    if (/[a-z]/.test(s)) return s;
    return s.toLowerCase().split(/(\s+)/).map((w, i) => {
      const up = w.toUpperCase();
      if (KEEP.test(up)) return up.replace('INC', 'Inc');
      if (i > 0 && SMALL.has(w)) return w;
      return w.replace(/(^|[-/(&.'])([a-z])/g, (m, p, c) => p + c.toUpperCase());
    }).join('');
  };
  const agencyShort = (s) => (s || '').replace(/^Department of (the )?/, '').replace(/ \(([A-Z]+)\)$/, ' ($1)');

  const m = S.meta, k = S.kpis;
  const rf = m.recent_from_fy, rt = m.recent_to_fy;
  const health = Object.fromEntries(S.health.map((h) => [h.source, h]));
  const tx = health.usaspending_transactions;
  document.getElementById('updated').textContent =
    `Fiscal years ${m.first_fy}–${m.current_fy} · ${nf(m.transactions)} transactions on ${nf(m.awards)} awards · latest action ${dateTxt(m.latest_action_date)} · checked daily, last ${astTxt(tx?.last_success_utc)}`;
  document.getElementById('built').textContent = `Built ${astTxt(m.generated_utc)}.`;

  /* ---------- Alerts ---------- */
  const sevTxt = { warning: 'Check', info: 'New' };
  document.getElementById('alerts').innerHTML = S.alerts.filter((a) => a.alert_key !== 'reconcile' || S.reconciliation.some((r) => !r.matches && r.fiscal_year <= m.current_fy - 2)).map((a) => {
    const lines = String(a.message || '').split('\n').filter(Boolean);
    const body = lines.length > 1 || lines[0]?.startsWith('- ')
      ? `<ul>${lines.slice(0, 6).map((l) => `<li>${esc(l.replace(/^- /, '').replace(/ https?:\/\/\S+$/, ''))}</li>`).join('')}</ul>`
      : `<p>${esc(lines[0] || '')}</p>`;
    return `<div class="alert ${a.severity}"><span class="sev">${sevTxt[a.severity] || 'Notice'}</span><div><b>${esc(a.title)}</b>${body}</div></div>`;
  }).join('');

  /* ---------- KPIs ---------- */
  const yr = (fy, g) => S.years.filter((r) => r.fiscal_year === fy && (!g || r.award_group === g)).reduce((s, r) => s + r.obligations, 0);
  const last = m.current_fy - 1;
  const lastContracts = yr(last, 'contracts');
  const kp = [
    [`FY${last} obligations`, money(k.last_fy_total), `All award types · contracts ${money(lastContracts)}`],
    [`FY${rf}–FY${rt} total`, money(k.recent_total), `Grants ${money(k.recent_grants)} · contracts ${money(k.recent_contracts)}`],
    ['Contract dollars to local firms', pct(k.recent_local_share), `FY${rf}–FY${rt} · ${money(k.recent_off_island)} went to off-island primes`],
    ['Contracts ending in 24 months', nf(k.leads), `Worth ${money(k.leads_value)} · ${nf(k.leads_off_island)} held by off-island primes`],
  ];
  document.getElementById('kpis').innerHTML = kp.map(([l, v, s]) => `<div class="kpi"><div class="l">${l}</div><div class="v">${v}</div><div class="s">${s}</div></div>`).join('');

  /* ---------- Headline ---------- */
  const fema = S.agencies.find((a) => /Homeland Security/.test(a.agency));
  const femaShare = fema ? fema.obligations / k.recent_total : null;
  const govt = S.recipient_kinds.find((r) => r.recipient_kind === 'Territorial government');
  const kindsTotal = S.recipient_kinds.reduce((s, r) => s + Math.max(0, r.obligations), 0);
  const peak = [...new Set(S.years.map((r) => r.fiscal_year))].map((fy) => ({ fy, v: yr(fy) })).sort((a, b) => b.v - a.v)[0];
  document.getElementById('finding').innerHTML =
    `From FY${rf} to FY${rt}, federal agencies committed <em>${money(k.recent_total)}</em> to work in the Virgin Islands. ` +
    (femaShare != null ? `${pct(femaShare)} came through Homeland Security, almost all of it FEMA disaster recovery, ` : '') +
    (govt ? `and ${pct(govt.obligations / kindsTotal)} went to the territorial government. ` : '') +
    `Contracts are a small slice, and only <em>${pct(k.recent_local_share)}</em> of contract dollars went to firms based here.`;
  const top = S.contractors[0];
  document.getElementById('facts').innerHTML = [
    [money(peak.v), `FY${peak.fy}, the largest year on record`],
    [money(k.all_years_total), `All obligations since FY${m.first_fy}`],
    [nf(m.contractors), 'Prime contractors with USVI work since FY2008'],
    [top ? money(top.obligated_recent) : '–', top ? `${esc(title(top.recipient_name))}, the largest contractor FY${rf}–FY${rt}` : ''],
  ].map(([b, s]) => `<div><b>${b}</b><span>${s}</span></div>`).join('');

  /* ---------- Chart defaults ---------- */
  Chart.defaults.font.family = "'Satoshi', system-ui, sans-serif";
  Chart.defaults.font.size = 12;
  Chart.defaults.color = C.muted;
  const small = () => window.innerWidth < 560;
  const grid = { color: C.line, drawTicks: false };

  /* ---------- Obligations by year ---------- */
  const GROUPS = [['grants', 'Grants', C.sea], ['direct_payments', 'Direct payments', C.seaL], ['contracts', 'Contracts', C.coral], ['loans', 'Loans', C.ink], ['other', 'Other', C.sand]];
  const fys = [...new Set(S.years.map((r) => r.fiscal_year))].sort((a, b) => a - b);
  let yearChart;
  const drawYears = (mode) => {
    const groups = mode === 'contracts' ? GROUPS.filter((g) => g[0] === 'contracts') : GROUPS;
    const ds = groups.map(([g, label, color]) => ({ label, backgroundColor: color, borderRadius: 2, data: fys.map((fy) => yr(fy, g)), stack: 's' }));
    if (yearChart) yearChart.destroy();
    yearChart = new Chart(document.getElementById('cYears'), {
      type: 'bar',
      data: { labels: fys.map((f) => small() ? `'${String(f).slice(2)}` : `FY${String(f).slice(2)}`), datasets: ds },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { position: 'bottom', labels: { boxWidth: 10, boxHeight: 10, usePointStyle: false } },
          tooltip: { callbacks: { title: (it) => `Fiscal year ${fys[it[0].dataIndex]}${fys[it[0].dataIndex] >= m.current_fy - 1 ? ' (still being reported)' : ''}`, label: (c) => ` ${c.dataset.label}: ${money(c.raw)}` } },
        },
        scales: {
          x: { stacked: true, grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, autoSkipPadding: 4 } },
          y: { stacked: true, grid, border: { display: false }, ticks: { callback: (v) => money(v, 0), maxTicksLimit: 6 } },
        },
      },
    });
  };
  drawYears('all');
  document.querySelectorAll('#yearToggle button').forEach((b) => b.addEventListener('click', () => {
    document.querySelectorAll('#yearToggle button').forEach((x) => x.setAttribute('aria-pressed', x === b));
    drawYears(b.dataset.k);
    document.getElementById('yearsNote').textContent = b.dataset.k === 'contracts'
      ? `Contracts alone: ${money(yr(last, 'contracts'))} in FY${last}. They peaked at ${money(cPeak.v)} in FY${cPeak.fy}.`
      : yearsNote;
  }));
  const cPeak = fys.map((fy) => ({ fy, v: yr(fy, 'contracts') })).sort((a, b) => b.v - a.v)[0];
  const neg = S.years.filter((r) => r.obligations < 0 && r.fiscal_year >= m.current_fy - 1);
  const yearsNote = `FY${m.current_fy} began on October 1 and is still filling in. ` +
    (neg.length ? `It shows ${money(neg.reduce((s, r) => s + r.obligations, 0))} net, because agencies reduced earlier awards (de-obligations) before new ones were reported. ` : '') +
    `From FY2018 the totals are dominated by FEMA's recovery money after Hurricanes Irma and Maria; most of the FY2024–FY2025 peak is FEMA Public Assistance under the Maria disaster declaration (DR-4340), paid to the territorial government for rebuilding.`;
  document.getElementById('yearsNote').textContent = yearsNote;

  /* ---------- Agencies and recipients ---------- */
  const meterList = (el, items) => {
    const max = Math.max(...items.map((i) => i.total), 1);
    document.getElementById(el).innerHTML = items.map((i) => `<li>
      <span class="nm">${esc(i.name)}${i.note ? `<small>${esc(i.note)}</small>` : ''}</span>
      <span class="val">${money(i.total)}${i.sub ? `<small>${i.sub}</small>` : ''}</span>
      <span class="meter">${(i.parts || [[i.total, '']]).map(([v, c]) => `<i class="${c}" style="width:${Math.max(0, 100 * v / max).toFixed(2)}%"></i>`).join('')}</span></li>`).join('');
  };
  document.getElementById('agSub').textContent = `Obligations FY${rf}–FY${rt} · coral is contracts, teal grants, light teal other assistance`;
  meterList('agencies', S.agencies.slice(0, 9).map((a) => ({
    name: agencyShort(a.agency), note: a.largest_sub_agency && a.largest_sub_agency !== a.agency ? `Largest: ${a.largest_sub_agency}` : '',
    total: a.obligations, sub: pct(a.obligations / k.recent_total),
    parts: [[a.contracts || 0, 'c'], [a.grants || 0, 'g'], [a.other_assistance || 0, 'o']],
  })));
  document.getElementById('rkSub').textContent = `Obligations FY${rf}–FY${rt}, by the kind of recipient`;
  meterList('kinds', S.recipient_kinds.filter((r) => r.obligations > 0).map((r) => ({ name: r.recipient_kind, total: r.obligations, sub: pct(r.obligations / kindsTotal) })));

  /* ---------- Local share ---------- */
  const ls = S.local_share.filter((r) => r.fiscal_year <= m.current_fy);
  new Chart(document.getElementById('cLocal'), {
    data: {
      labels: ls.map((r) => small() ? `'${String(r.fiscal_year).slice(2)}` : `FY${String(r.fiscal_year).slice(2)}`),
      datasets: [
        { type: 'bar', label: 'Local firms', data: ls.map((r) => r.local_obligations), backgroundColor: C.sea, stack: 's', yAxisID: 'y', borderRadius: 2 },
        { type: 'bar', label: 'Off-island firms', data: ls.map((r) => r.off_island_obligations), backgroundColor: C.sand, stack: 's', yAxisID: 'y', borderRadius: 2 },
        { type: 'line', label: 'Local share', data: ls.map((r) => r.contract_obligations > 0 ? 100 * r.local_obligations / r.contract_obligations : null), borderColor: C.coral, backgroundColor: C.coral, pointRadius: 2.5, borderWidth: 2, yAxisID: 'p', tension: 0 },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false, interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { position: 'bottom', labels: { boxWidth: 10, boxHeight: 10 } },
        tooltip: { callbacks: { label: (c) => c.dataset.yAxisID === 'p' ? ` Local share: ${nf(c.raw, 1)}%` : ` ${c.dataset.label}: ${money(c.raw)}` } },
      },
      scales: {
        x: { stacked: true, grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, autoSkipPadding: 4 } },
        y: { stacked: true, grid, border: { display: false }, ticks: { callback: (v) => money(v, 0), maxTicksLimit: 5 } },
        p: { position: 'right', min: 0, max: 100, grid: { display: false }, border: { display: false }, ticks: { callback: (v) => `${v}%`, maxTicksLimit: 5 } },
      },
    },
  });

  /* ---------- NAICS ---------- */
  document.getElementById('naicsSub').textContent = `Contract obligations FY${rf}–FY${rt} by industry (NAICS) · teal is the part won by local firms`;
  meterList('naics', S.naics.slice(0, 9).map((n) => ({
    name: title(n.naics_description) || n.naics_code, note: `NAICS ${n.naics_code} · ${nf(n.contracts)} contracts, ${nf(n.contractors)} contractors`,
    total: n.obligations, parts: [[Math.max(0, n.local_obligations), 'g'], [n.obligations - Math.max(0, n.local_obligations), 'c']],
  })));

  /* ---------- Leads ---------- */
  const endPill = (l) => {
    const c = l.ends_in === 'Within 6 months' ? 'soon' : l.ends_in === '6 to 12 months' ? 'mid' : '';
    return `<span class="pill2 ${c}">${l.months_left <= 0 ? '< 1 mo' : `${l.months_left} mo`}</span>${monthTxt(l.current_end_date)}${l.has_options_left ? `<small>Options to ${monthTxt(l.potential_end_date)}</small>` : ''}`;
  };
  const leadState = { win: 'all', off: false, q: '', n: 12 };
  const drawLeads = () => {
    const q = leadState.q.toLowerCase();
    const rows = S.leads.filter((l) => (leadState.win === 'all' || l.ends_in === leadState.win) && (!leadState.off || !l.prime_is_local)
      && (!q || [l.awarding_agency, l.awarding_sub_agency, l.awarding_office, l.prime_contractor, l.naics_description, l.psc_description, l.description].join(' ').toLowerCase().includes(q)));
    const tb = document.querySelector('#tLeads tbody');
    tb.innerHTML = rows.slice(0, leadState.n).map((l) => `<tr>
      <td class="wrapc"><a href="${esc(l.permalink)}" target="_blank" rel="noopener">${esc(title(l.naics_description || l.psc_description) || 'Contract')}</a><small>${esc((l.description || '').slice(0, 140))}${(l.description || '').length > 140 ? '…' : ''}</small></td>
      <td class="wrapc">${esc(l.awarding_sub_agency || l.awarding_agency)}<small>${esc(title(l.awarding_office || ''))}</small></td>
      <td class="wrapc"><span class="pill2 ${l.prime_is_local ? 'ok' : 'off'}">${l.prime_is_local ? 'Local' : esc(l.prime_state || 'Off-island')}</span>${esc(title(l.prime_contractor))}${l.set_aside && !/NO SET ASIDE/i.test(l.set_aside) ? `<small>${esc(title(l.set_aside))}</small>` : ''}</td>
      <td>${endPill(l)}<span class="mval">${money(l.contract_value)}</span></td>
      <td class="n">${money(l.contract_value)}</td></tr>`).join('') || `<tr><td colspan="5" class="empty">No contracts match these filters.</td></tr>`;
    const btn = document.getElementById('leadMore');
    btn.textContent = rows.length > leadState.n ? `Show ${Math.min(24, rows.length - leadState.n)} more of ${rows.length - leadState.n}` : '';
  };
  document.getElementById('leadsSub').textContent = `${nf(S.leads.length)} contracts performed in the USVI, worth $25,000 or more, whose current end date falls in the next 24 months. When one ends, the agency usually buys the work again, and the winner often needs local help.`;
  document.querySelectorAll('#leadToggle button').forEach((b) => b.addEventListener('click', () => {
    document.querySelectorAll('#leadToggle button').forEach((x) => x.setAttribute('aria-pressed', x === b));
    leadState.win = b.dataset.k; leadState.n = 12; drawLeads();
  }));
  document.getElementById('leadOff').addEventListener('change', (e) => { leadState.off = e.target.checked; leadState.n = 12; drawLeads(); });
  document.getElementById('leadSearch').addEventListener('input', (e) => { leadState.q = e.target.value; leadState.n = 12; drawLeads(); });
  document.getElementById('leadMore').addEventListener('click', () => { leadState.n += 24; drawLeads(); });
  drawLeads();

  /* ---------- Contractors ---------- */
  document.getElementById('ctRecentH').textContent = `FY${rf}–FY${rt}`;
  document.getElementById('ctSub').textContent = `Prime contractors with USVI work, largest first · ${nf(m.contractors)} in all, every one in the CSV`;
  const flags = (c) => [c.sba_8a && '8(a)', c.woman_owned && 'Woman-owned', c.veteran_owned && 'Veteran-owned', c.hubzone && 'HUBZone'].filter(Boolean).join(' · ');
  const ctState = { q: '', n: 12 };
  const drawCt = () => {
    const q = ctState.q.toLowerCase();
    const rows = S.contractors.filter((c) => !q || [c.recipient_name, c.recipient_city, c.main_agency, c.main_naics_description].join(' ').toLowerCase().includes(q));
    document.querySelector('#tCt tbody').innerHTML = rows.slice(0, ctState.n).map((c) => `<tr>
      <td><b>${esc(title(c.recipient_name))}</b><small>${[c.business_size && title(c.business_size), flags(c)].filter(Boolean).map(esc).join(' · ')}</small></td>
      <td><span class="pill2 ${c.is_local_recipient ? 'ok' : 'off'}">${c.is_local_recipient ? 'Local' : esc(c.recipient_state || 'Abroad')}</span>${esc(title(c.recipient_city || ''))}</td>
      <td class="n">${money(c.obligated_recent)}</td>
      <td class="n">${money(c.obligated_all_years)}<small>${nf(c.contracts)} contracts</small></td>
      <td>${esc(title(c.main_naics_description || ''))}<small>${esc(agencyShort(c.main_agency || ''))}</small></td></tr>`).join('') || `<tr><td colspan="5" class="empty">No contractor matches. The CSV has all ${nf(m.contractors)}.</td></tr>`;
    document.getElementById('ctMore').textContent = rows.length > ctState.n ? `Show ${Math.min(24, rows.length - ctState.n)} more` : '';
  };
  document.getElementById('ctSearch').addEventListener('input', (e) => { ctState.q = e.target.value; ctState.n = 12; drawCt(); });
  document.getElementById('ctMore').addEventListener('click', () => { ctState.n += 24; drawCt(); });
  drawCt();

  /* ---------- Subawards ---------- */
  const drawSub = (kind) => {
    const rows = S.subcontracting.filter((s) => s.kind === kind).slice(0, 12);
    document.querySelector('#tSub tbody').innerHTML = rows.map((s) => `<tr>
      <td><b>${esc(title(s.prime))}</b><small>${esc(agencyShort(s.agency || ''))}${s.prime_state ? ` · ${esc(s.prime_state)}` : ''}</small></td>
      <td class="n">${nf(s.subawards)}<small>${nf(s.subawardees)} recipients</small></td>
      <td class="n">${money(s.subaward_amount)}</td>
      <td class="n">${pct(s.subaward_amount > 0 ? s.to_local_firms / s.subaward_amount : null)}</td>
      <td>${esc(title(s.top_subawardees || ''))}</td></tr>`).join('') || `<tr><td colspan="5" class="empty">No subawards reported.</td></tr>`;
  };
  document.querySelectorAll('#subToggle button').forEach((b) => b.addEventListener('click', () => {
    document.querySelectorAll('#subToggle button').forEach((x) => x.setAttribute('aria-pressed', x === b));
    drawSub(b.dataset.k);
  }));
  drawSub('subcontract');

  /* ---------- Reconciliation ---------- */
  const byFy = {};
  S.reconciliation.forEach((r) => { const o = byFy[r.fiscal_year] ||= { ours: 0, official: 0, ok: true }; o.ours += r.ours; o.official += r.official; o.ok = o.ok && r.matches; });
  const recFys = Object.keys(byFy).map(Number).sort((a, b) => b - a);
  const closed = recFys.filter((f) => f <= m.current_fy - 2);
  const closedOk = closed.filter((f) => byFy[f].ok).length;
  document.getElementById('checks').innerHTML = [
    [`${closedOk} of ${closed.length}`, `Completed fiscal years matching USAspending to the dollar, by award type`],
    [nf(m.transactions), 'Transactions added up, each with a unique key'],
    [astTxt(health.usaspending_official?.last_success_utc).replace(/, \d{4},/, ','), 'USAspending totals last fetched'],
  ].map(([b, s]) => `<div><b>${b}</b><span>${s}</span></div>`).join('');
  document.querySelector('#tRecon tbody').innerHTML = recFys.map((f) => {
    const o = byFy[f], open = f >= m.current_fy - 1;
    const st = o.ok ? '<span class="pill2 ok">Matches</span>' : open ? '<span class="pill2 warn">Still reporting</span>' : '<span class="pill2 soon">Differs</span>';
    return `<tr><td>FY${f}${open ? ' <small>Open year</small>' : ''}</td><td class="n">${cents(o.ours)}</td><td class="n">${cents(o.official)}</td><td class="n">${cents(o.ours - o.official)}</td><td>${st}</td></tr>`;
  }).join('');

  document.getElementById('howFinding').innerHTML = `<b>Finding.</b> Only ${pct(k.recent_local_share)} of contract dollars spent in the territory from FY${rf} to FY${rt} went to USVI-based firms. ${nf(k.leads_off_island)} of the ${nf(k.leads)} contracts ending in the next two years are held by off-island primes, a ready list of companies that may need local partners.`;
})();
