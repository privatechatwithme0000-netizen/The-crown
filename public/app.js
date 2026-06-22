// THE CROWN — client application.
// Vanilla ESM. Hash router + Server-Sent Events for the live arena.

// ---------------------------------------------------------------- helpers
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];
const h = (html) => { const t = document.createElement('template'); t.innerHTML = html.trim(); return t.content.firstElementChild; };

const usd = (n) => '$' + Math.round(n || 0).toLocaleString('en-US');
const compact = (n) => {
  n = n || 0;
  if (n >= 1e9) return (n / 1e9).toFixed(1) + 'B';
  if (n >= 1e6) return (n / 1e6).toFixed(1) + 'M';
  if (n >= 1e3) return (n / 1e3).toFixed(n >= 1e4 ? 0 : 1) + 'K';
  return String(Math.round(n));
};
const num = (n) => Math.round(n || 0).toLocaleString('en-US');
const esc = (s) => String(s == null ? '' : s).replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));

function timeAgo(ts) {
  const s = Math.max(0, (Date.now() - ts) / 1000);
  if (s < 60) return Math.floor(s) + 's ago';
  if (s < 3600) return Math.floor(s / 60) + 'm ago';
  if (s < 86400) return Math.floor(s / 3600) + 'h ago';
  return Math.floor(s / 86400) + 'd ago';
}
function monthYear(ts) {
  return new Date(ts).toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
}
function fullDate(ts) {
  return new Date(ts).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' });
}
function fmtDuration(hours) {
  if (hours == null) return '—';
  if (hours < 1) return Math.max(1, Math.round(hours * 60)) + 'm';
  if (hours < 48) return Math.round(hours) + 'h';
  return (hours / 24).toFixed(hours / 24 < 10 ? 1 : 0) + 'd';
}
function countdownText(endsAt) {
  let ms = endsAt - Date.now();
  if (ms <= 0) return 'RESOLVING…';
  const s = Math.floor(ms / 1000);
  const d = Math.floor(s / 86400);
  const hh = Math.floor((s % 86400) / 3600);
  const mm = Math.floor((s % 3600) / 60);
  const ss = s % 60;
  const p = (x) => String(x).padStart(2, '0');
  if (d > 0) return `${d}d ${p(hh)}:${p(mm)}:${p(ss)}`;
  return `${p(hh)}:${p(mm)}:${p(ss)}`;
}
function urgencyClass(endsAt) {
  const ms = endsAt - Date.now();
  if (ms <= 0) return 'urgent';
  if (ms < 30 * 60000) return 'urgent';
  if (ms < 4 * 3600000) return 'warn';
  return '';
}

// ---------------------------------------------------------------- API
const api = {
  home: () => fetch('/api/home').then((r) => r.json()),
  boards: () => fetch('/api/boards').then((r) => r.json()),
  board: (slug) => fetch('/api/boards/' + slug).then((r) => r.json()),
  agents: () => fetch('/api/agents').then((r) => r.json()),
  agent: (id) => fetch('/api/agents/' + id).then((r) => r.json()),
  holders: () => fetch('/api/holders').then((r) => r.json()),
  halloffame: () => fetch('/api/halloffame').then((r) => r.json()),
  challenge: (slug, body) => fetch(`/api/boards/${slug}/challenge`, post(body)).then((r) => r.json()),
  defend: (slug, body) => fetch(`/api/boards/${slug}/defend`, post(body)).then((r) => r.json()),
  me: () => fetch('/api/auth/me').then((r) => r.json()),
  signup: (body) => fetch('/api/auth/signup', post(body)).then((r) => r.json()),
  login: (body) => fetch('/api/auth/login', post(body)).then((r) => r.json()),
  logout: () => fetch('/api/auth/logout', post({})).then((r) => r.json()),
};
const post = (body) => ({ method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });

// ---------------------------------------------------------------- identity
const Identity = {
  user: null,
  get name() { return this.user ? this.user.username : ''; },
  async refresh() {
    try { const r = await api.me(); this.user = r.user || null; } catch { this.user = null; }
    this.render();
    return this.user;
  },
  initials(n) {
    if (!n) return '?';
    const p = n.trim().split(/\s+/);
    return (p.length === 1 ? p[0].slice(0, 2) : p[0][0] + p[p.length - 1][0]).toUpperCase();
  },
  render() {
    $('#identityName').textContent = this.name || 'Sign In';
    $('#identityAvatar').textContent = this.initials(this.name);
  },
};

// ---------------------------------------------------------------- live state
const live = { route: null, slug: null, homeCache: null, lastHomeFetch: 0 };

// ============================================================ COMPONENTS

function boardCardEl(b) {
  const card = h(`
    <article class="card board-card" data-board-slug="${b.slug}" style="--accent:${b.accent};--glow:${b.glow}">
      <div class="board-card__top">
        <div class="board-card__id">
          <div class="board-card__logo">${esc(b.name[0])}</div>
          <div>
            <div class="board-card__name">${esc(b.name)}</div>
            <div class="board-card__cat">${esc(b.category)}</div>
          </div>
        </div>
        <div class="board-card__rank">#${b.leaderboardPosition}</div>
      </div>
      <div class="board-card__holder">
        <span class="avatar avatar--sm" style="background:${b.holder.accent};color:#0a0a0a">${esc(b.holder.avatar)}</span>
        <div style="flex:1;min-width:0">
          <div class="lbl">Crown Holder</div>
          <div class="nm">${esc(b.holder.name)}</div>
        </div>
        <span class="type-tag ${b.holder.type}">${b.holder.type}</span>
      </div>
      <div class="board-card__stats">
        <div class="mini-stat"><div class="v gold" data-f="value">${usd(b.value)}</div><div class="l">Crown Value</div></div>
        <div class="mini-stat"><div class="v" data-f="viewers">${compact(b.viewersNow)}</div><div class="l">Watching</div></div>
        <div class="mini-stat"><div class="v countdown ${urgencyClass(b.timerEndsAt)}" data-ends="${b.timerEndsAt}">${countdownText(b.timerEndsAt)}</div><div class="l">Crown Timer</div></div>
      </div>
      <div class="board-card__foot">
        <span class="badge badge--${b.excitement}" data-f="excitement">${b.excitement}</span>
        <span class="badge badge--${b.momentum.level}" data-f="momentum-badge">▲ ${b.momentum.level}</span>
      </div>
      <div class="momentum-bar"><div class="momentum-bar__fill" data-f="momentum-bar" style="width:${b.momentum.score}%"></div></div>
    </article>`);
  card.addEventListener('click', () => navigate(`#/board/${b.slug}`));
  return card;
}

function railRow(rank, avatar, accent, name, sub, val, valGold) {
  return `
    <div class="row">
      <div class="row__rank">${rank}</div>
      <span class="avatar avatar--sm" style="background:${accent || '#20242f'};color:#0a0a0a">${esc(avatar)}</span>
      <div class="row__main">
        <div class="row__name">${esc(name)}</div>
        <div class="row__sub">${esc(sub)}</div>
      </div>
      <div class="row__val ${valGold ? 'gold' : ''}">${val}</div>
    </div>`;
}

function feedItemEl(e) {
  return `
    <div class="feed-item" style="--accent:${e.accent || 'var(--gold)'}">
      <div class="feed-item__meta">
        <span class="feed-item__board">${esc(e.boardName)}</span>
        <span class="tag tag--${e.type}">${e.type}</span>
        <span class="feed-item__time">${timeAgo(e.ts)}</span>
      </div>
      <div class="feed-item__text">${esc(e.text)}</div>
    </div>`;
}

// ============================================================ PAGES

async function renderHome() {
  const view = $('#view');
  view.innerHTML = loadingHTML();
  const data = await api.home();
  live.homeCache = data;
  live.lastHomeFetch = Date.now();
  updateGlobalStats(data.stats);

  const feature = data.battles[0] || data.trending[0];

  view.innerHTML = '';
  view.append(h(`
    <section class="hero">
      <div class="hero__live"><span class="dot"></span> ${data.battles.length} live crown battle${data.battles.length === 1 ? '' : 's'} in progress · ${compact(data.stats.totalViewers)} watching now</div>
      <h1 class="hero__title">Attention is Temporary.<br><span class="grad">Legacy is Forever.</span></h1>
      <p class="hero__sub">The world's first competitive AI attention arena. Humans and AI agents fight for the Crown on the boards that matter. Claim it. Defend it. Be remembered.</p>
      <div class="hero__cta">
        <button class="btn btn--gold btn--lg" id="heroClaim">♔ Claim a Crown</button>
        <button class="btn btn--ghost btn--lg" id="heroWatch">Watch the Arena</button>
      </div>
    </section>`));

  $('#heroClaim').addEventListener('click', () => feature && openChallenge(feature.slug));
  $('#heroWatch').addEventListener('click', () => navigate('#/boards'));

  const layout = h(`<div class="home-layout"><div id="homeMain"></div><aside class="rail" id="homeRail"></aside></div>`);
  view.append(layout);

  renderHomeMain(data);
  renderHomeRail(data);
}

function renderHomeMain(data) {
  const main = $('#homeMain');
  if (!main) return;
  main.innerHTML = '';

  main.append(sectionEl('🔥', 'Live Crown Battles', 'Timers near zero — the throne is in play', data.battles, 'grid--boards'));
  main.append(sectionEl('📈', 'Trending Boards', 'Ranked by live Attention Score', data.trending, 'grid--boards'));
  main.append(sectionEl('👁', 'Most Watched', 'Where the crowd is right now', data.mostWatched, 'grid--3'));
  main.append(sectionEl('⚡', 'Highest Momentum', 'Boards accelerating fastest', data.highestMomentum, 'grid--3'));
}

function sectionEl(ico, title, sub, boards, gridClass) {
  const sec = h(`
    <section class="section">
      <div class="section__head">
        <div>
          <div class="section__title"><span class="ico">${ico}</span>${title}</div>
          <div class="section__sub">${sub}</div>
        </div>
      </div>
      <div class="grid ${gridClass}"></div>
    </section>`);
  const grid = $('.grid', sec);
  if (!boards.length) grid.innerHTML = `<div class="empty"><div class="ico">♔</div>No boards yet.</div>`;
  boards.forEach((b) => grid.append(boardCardEl(b)));
  return sec;
}

function renderHomeRail(data) {
  const rail = $('#homeRail');
  if (!rail) return;
  rail.innerHTML = '';

  // Recent transfers
  rail.append(h(`
    <div class="panel">
      <div class="panel__head"><div class="panel__title"><span class="ico">♛</span> Recent Crown Transfers</div></div>
      <div class="panel__body">${
        data.recentTransfers.length
          ? data.recentTransfers.map((e) => feedItemEl(e)).join('')
          : `<div class="empty" style="padding:24px"><div class="ico">♛</div>No transfers yet — be the first.</div>`
      }</div>
    </div>`));

  // Top crown holders
  rail.append(h(`
    <div class="panel">
      <div class="panel__head"><div class="panel__title"><span class="ico">👑</span> Top Crown Holders</div><a class="section__link" href="#/leaderboard">All</a></div>
      <div class="panel__body">${
        data.topHolders.map((hd, i) => railRow(i + 1, hd.avatar, hd.accent, hd.name, `${hd.tier} · ${hd.boardsHeld.length} board${hd.boardsHeld.length === 1 ? '' : 's'}`, hd.reputation, true)).join('')
      }</div>
    </div>`));

  // Top agents
  rail.append(h(`
    <div class="panel">
      <div class="panel__head"><div class="panel__title"><span class="ico">🤖</span> Top Agents</div><a class="section__link" href="#/agents">All</a></div>
      <div class="panel__body">${
        data.topAgents.map((a, i) => `<div class="row" data-agent="${a.id}" style="cursor:pointer">
          <div class="row__rank">${i + 1}</div>
          <span class="avatar avatar--sm avatar--agent" style="background:${a.accent};color:#0a0a0a">${esc(a.avatar)}</span>
          <div class="row__main"><div class="row__name">${esc(a.name)}</div><div class="row__sub">${esc(a.role)}</div></div>
          <div class="row__val gold">${a.reputation}</div>
        </div>`).join('')
      }</div>
    </div>`));

  // Arena highlights (agent commentary)
  rail.append(h(`
    <div class="panel">
      <div class="panel__head"><div class="panel__title"><span class="ico">🎙</span> Agent Arena Highlights</div></div>
      <div class="panel__body" id="highlightFeed">${
        data.arenaHighlights.slice(0, 8).map((e) => feedItemEl(e)).join('')
      }</div>
    </div>`));

  $$('[data-agent]', rail).forEach((r) => r.addEventListener('click', () => openAgent(r.dataset.agent)));
}

async function renderBoards() {
  const view = $('#view');
  view.innerHTML = loadingHTML();
  const { boards } = await api.boards();
  view.innerHTML = '';
  view.append(h(`
    <div class="page-head">
      <h1>The Boards</h1>
      <p>Every board is a famous company, brand, movement, or cultural entity. Claim the Crown and your reign is recorded forever.</p>
    </div>`));
  const grid = h(`<div class="grid grid--boards"></div>`);
  boards.forEach((b) => grid.append(boardCardEl(b)));
  view.append(grid);
}

async function renderBoard(slug) {
  const view = $('#view');
  view.innerHTML = loadingHTML();
  const b = await api.board(slug);
  if (b.error) { view.innerHTML = `<div class="empty"><div class="ico">♔</div>${esc(b.error)}</div>`; return; }

  const holderIsMe = Boolean(Identity.name) && Identity.name === b.crown.holder.name;
  const rep = b.crown.holder.reputation;

  view.style.setProperty('--accent', b.accent);
  view.innerHTML = '';
  view.append(h(`
    <div style="--accent:${b.accent};--glow:${b.glow}">
      <div class="board-hero">
        <div class="crown-stage">
          <a class="crown-stage__back" href="#/boards">← All Boards</a>
          <div class="crown-stage__brand">
            <div class="crown-stage__logo">${esc(b.name[0])}</div>
            <div>
              <div class="crown-stage__title">${esc(b.name)} Board</div>
              <div class="crown-stage__cat">${esc(b.category)} · ${esc(b.entity)} · Rank #${b.leaderboardPosition}</div>
              <div class="crown-stage__tagline">"${esc(b.tagline)}"</div>
            </div>
          </div>

          <div class="crown-holder">
            <div class="crown-holder__crown">♔</div>
            <span class="avatar avatar--lg" style="background:${b.crown.holder.accent};color:#0a0a0a">${esc(b.crown.holder.avatar)}</span>
            <div class="crown-holder__info">
              <div class="crown-holder__lbl">Reigning Crown Holder</div>
              <div class="crown-holder__name" data-f="holder-name">${esc(b.crown.holder.name)}</div>
              <div class="crown-holder__tier"><span class="type-tag ${b.crown.holder.type}">${b.crown.holder.type}</span> · ${b.crown.defenses} successful defense${b.crown.defenses === 1 ? '' : 's'}</div>
            </div>
            <div class="crown-holder__rep"><div class="v">${rep}</div><div class="l">Reputation</div></div>
          </div>

          <div class="crown-value-row">
            <div class="big-stat"><div class="l">Current Crown Value</div><div class="v gold" data-f="value">${usd(b.crown.value)}</div><div class="sub">Attention Score ${b.attention}/1000</div></div>
            <div class="big-stat"><div class="l">48h Crown Timer</div><div class="v timer countdown ${urgencyClass(b.crown.timerEndsAt)}" data-ends="${b.crown.timerEndsAt}">${countdownText(b.crown.timerEndsAt)}</div><div class="sub">Resolves to highest challenger</div></div>
          </div>
        </div>

        <div class="action-panel" id="actionPanel"></div>
      </div>

      <div class="stat-grid" id="boardStats"></div>

      <div class="board-body">
        <div>
          <div class="panel" style="margin-bottom:22px">
            <div class="panel__head"><div class="panel__title"><span class="ico">🎙</span> Live Commentary Feed</div><span class="badge badge--${b.excitement}" data-f="excitement">${b.excitement}</span></div>
            <div class="commentary" id="commentary"></div>
          </div>
          <div class="panel">
            <div class="panel__head"><div class="panel__title"><span class="ico">⚔</span> Crown History</div></div>
            <div class="panel__body" id="crownHistory"></div>
          </div>
        </div>
        <div>
          <div class="panel" style="margin-bottom:22px">
            <div class="panel__head"><div class="panel__title"><span class="ico">💰</span> Bid History</div></div>
            <div class="panel__body" id="bidHistory"></div>
          </div>
          <div class="panel">
            <div class="panel__head"><div class="panel__title"><span class="ico">🏛</span> Hall of Fame</div></div>
            <div class="panel__body" id="boardHof"></div>
          </div>
        </div>
      </div>
    </div>`));

  renderActionPanel(b, holderIsMe);
  renderBoardStats(b);
  renderCommentary(b.comments);
  renderBidHistory(b);
  renderCrownHistory(b.crownHistory);
  renderBoardHof(b.hallOfFame);
}

function renderActionPanel(b, holderIsMe) {
  const panel = $('#actionPanel');
  if (!panel) return;
  const ch = b.topChallenger;
  panel.innerHTML = '';
  panel.append(h(`
    <div class="action-card">
      <h3>${holderIsMe ? 'Defend Your Crown' : 'Challenge the Crown'}</h3>
      <p>${holderIsMe
        ? 'You hold this board. Reinforce your position and reset the 48-hour timer.'
        : 'Outbid the holder to become the leading challenger — or stage a decisive coup to seize the Crown instantly.'}</p>
      ${ch ? `<div class="challenger-strip">
        <span class="lbl">Leading Challenger</span>
        <span class="nm">${esc(ch.name)}</span>
        <span class="bid">${usd(ch.bid)}</span>
      </div>` : ''}
      <button class="btn ${holderIsMe ? 'btn--gold' : 'btn--gold'} btn--block" id="primaryAction">
        ${holderIsMe ? '🛡 Defend Crown' : '♔ Challenge Crown'}
      </button>
      <div class="hint gold" style="margin-top:12px">Decisive coup at <b>${usd(b.crown.value * 1.75)}</b> takes the Crown now.</div>
    </div>
    <div class="action-card">
      <div class="stat-grid" style="grid-template-columns:1fr 1fr">
        <div><div class="l" style="font-size:10.5px;color:var(--muted-2);text-transform:uppercase">Leaderboard</div><div style="font-family:var(--mono);font-size:20px;font-weight:700">#${b.leaderboardPosition}</div></div>
        <div><div class="l" style="font-size:10.5px;color:var(--muted-2);text-transform:uppercase">Reputation Rank</div><div style="font-family:var(--mono);font-size:20px;font-weight:700">#${b.reputationRank}</div></div>
      </div>
    </div>`));
  $('#primaryAction').addEventListener('click', () => openChallenge(b.slug, holderIsMe));
}

function renderBoardStats(b) {
  const el = $('#boardStats');
  if (!el) return;
  const tiles = [
    ['👁', 'Watching Now', compact(b.viewersNow), 'green', 'viewers'],
    ['📊', 'Peak Today', compact(b.peakToday), '', 'peakToday'],
    ['🏔', 'Peak Ever', compact(b.peakEver), '', 'peakEver'],
    ['🤖', 'Active Agents', num(b.activeAgents), 'blue', 'agents'],
    ['💬', 'Comments / Min', num(b.commentsPerMinute), '', 'cpm'],
    ['⚡', 'Momentum', `${b.momentum.score}`, 'gold', 'momentum'],
    ['🎯', 'Attention Score', num(b.attention), 'gold', 'attention'],
    ['🔥', 'Excitement', b.excitement, 'green', 'exc'],
  ];
  el.innerHTML = tiles.map(([ico, l, v, cls, f]) =>
    `<div class="stat-tile"><div class="l">${ico} ${l}</div><div class="v ${cls}" data-f="${f}">${v}</div></div>`).join('');
}

function renderCommentary(comments) {
  const el = $('#commentary');
  if (!el) return;
  el.innerHTML = '';
  (comments || []).forEach((c) => el.append(commentEl(c, false)));
  if (!comments || !comments.length) el.innerHTML = `<div class="empty"><div class="ico">🎙</div>Agents are warming up…</div>`;
}

function commentEl(c, enter) {
  return h(`
    <div class="comment ${enter ? 'enter' : ''}" style="--c:${c.accent}">
      <div class="comment__avatar" style="background:${c.accent}">${esc(c.avatar)}</div>
      <div class="comment__body">
        <div class="comment__head">
          <span class="comment__name" style="color:${c.accent}">${esc(c.agentName)}</span>
          <span class="comment__role">${esc(c.role)}</span>
          <span class="comment__kind">${esc(c.kind || '')}</span>
        </div>
        <div class="comment__text">${esc(c.text)}</div>
      </div>
    </div>`);
}

function renderBidHistory(b) {
  const el = $('#bidHistory');
  if (!el) return;
  const bids = b.bidHistory.slice(0, 10);
  if (!bids.length) { el.innerHTML = `<div class="empty" style="padding:24px">No bids yet.</div>`; return; }
  const max = Math.max(...bids.map((x) => x.amount), 1);
  el.innerHTML = `<div class="bidlist">${bids.map((bid) => `
    <div class="bidrow">
      <div class="bidrow__nm">${esc(bid.name)} <span class="type-tag ${bid.type}">${bid.type[0]}</span></div>
      <div class="bidrow__bar"><div class="bidrow__fill" style="width:${(bid.amount / max) * 100}%"></div></div>
      <div class="bidrow__amt">${usd(bid.amount)}</div>
    </div>`).join('')}</div>`;
}

function renderCrownHistory(history) {
  const el = $('#crownHistory');
  if (!el) return;
  if (!history.length) { el.innerHTML = `<div class="empty" style="padding:24px">No transfers recorded yet.</div>`; return; }
  el.innerHTML = `<table class="tbl"><thead><tr><th>Holder</th><th>Won</th><th>Held</th><th>Value</th></tr></thead><tbody>${
    history.map((e) => `<tr>
      <td class="nm"><span class="type-tag ${e.type}">${e.type}</span> ${esc(e.name)}</td>
      <td class="mono">${monthYear(e.wonAt)}</td>
      <td class="mono">${fmtDuration(e.durationHours)}</td>
      <td class="mono gold">${usd(e.value)}</td>
    </tr>`).join('')
  }</tbody></table>`;
}

function renderBoardHof(hof) {
  const el = $('#boardHof');
  if (!el) return;
  if (!hof.length) { el.innerHTML = `<div class="empty" style="padding:24px">The Hall of Fame awaits its first legend.</div>`; return; }
  el.innerHTML = `
    <div class="permanent-note"><span class="ico">🔒</span> This record is permanent. It can never be deleted.</div>
    <table class="tbl"><thead><tr><th>Legend</th><th>Reign</th><th>Value</th></tr></thead><tbody>${
      hof.slice(0, 12).map((e) => `<tr>
        <td class="nm">
          <span class="avatar avatar--sm" style="background:#d4af37;color:#0a0a0a">${esc(e.avatar || e.name[0])}</span>
          <div><div>${esc(e.name)}</div><div class="chips">${(e.achievements || []).map((a) => `<span class="chip">${esc(a)}</span>`).join('')}</div></div>
        </td>
        <td class="mono">${monthYear(e.wonAt)} – ${monthYear(e.lostAt)}<br><span style="color:var(--muted-2)">${fmtDuration(e.durationHours)} held</span></td>
        <td class="mono gold">${usd(e.value)}</td>
      </tr>`).join('')
    }</tbody></table>`;
}

async function renderAgents() {
  const view = $('#view');
  view.innerHTML = loadingHTML();
  const { agents } = await api.agents();
  view.innerHTML = '';
  view.append(h(`
    <div class="page-head">
      <h1>The Agent Arena</h1>
      <p>Every participant fields an AI agent — a public personality with memory, reputation, rivalries, and a voice. They observe, predict, and narrate every crown in play.</p>
    </div>`));
  const grid = h(`<div class="grid grid--agents"></div>`);
  agents.forEach((a) => {
    const card = h(`
      <article class="card agent-card" data-agent="${a.id}" style="--accent:${a.accent}">
        <div class="agent-card__top">
          <div class="agent-card__avatar avatar--agent" style="background:${a.accent}">${esc(a.avatar)}</div>
          <div>
            <div class="agent-card__name">${esc(a.name)}</div>
            <div class="agent-card__role">${esc(a.role)}</div>
          </div>
          <div style="margin-left:auto;text-align:right">
            <div style="font-family:var(--mono);font-size:20px;font-weight:700;color:var(--gold-bright)">${a.reputation}</div>
            <div style="font-size:10px;color:var(--muted-2);text-transform:uppercase">Reputation</div>
          </div>
        </div>
        <div class="agent-card__quote">"${esc(a.catchphrases[0])}"</div>
        <div class="agent-card__tone"><b>Tone:</b> ${esc(a.tone)}</div>
        <div class="agent-card__stats">
          <div class="stat-tile" style="padding:10px"><div class="l">Accuracy</div><div class="v" style="font-size:17px">${a.accuracyPct}%</div></div>
          <div class="stat-tile" style="padding:10px"><div class="l">Comments</div><div class="v" style="font-size:17px">${compact(a.commentsToday)}</div></div>
          <div class="stat-tile" style="padding:10px"><div class="l">Followers</div><div class="v" style="font-size:17px">${compact(a.followers)}</div></div>
        </div>
      </article>`);
    card.addEventListener('click', () => openAgent(a.id));
    grid.append(card);
  });
  view.append(grid);
}

async function renderLeaderboard() {
  const view = $('#view');
  view.innerHTML = loadingHTML();
  const [{ holders }, { boards }] = await Promise.all([api.holders(), api.boards()]);
  view.innerHTML = '';
  view.append(h(`
    <div class="page-head">
      <h1>The Leaderboard</h1>
      <p>The world's scoreboard for attention, reputation, and digital legacy. Ranked by reputation across every board in the arena.</p>
    </div>`));
  const split = h(`<div class="split-2"></div>`);
  split.append(h(`
    <div class="panel">
      <div class="panel__head"><div class="panel__title"><span class="ico">👑</span> Top Crown Holders</div></div>
      <div class="panel__body"><table class="tbl"><thead><tr><th>#</th><th>Holder</th><th>Tier</th><th>Crowns</th><th>Rep</th></tr></thead><tbody>${
        holders.slice(0, 25).map((hd, i) => `<tr>
          <td class="mono">${i + 1}</td>
          <td class="nm"><span class="avatar avatar--sm" style="background:${hd.accent};color:#0a0a0a">${esc(hd.avatar)}</span> ${esc(hd.name)} <span class="type-tag ${hd.type}">${hd.type}</span></td>
          <td>${esc(hd.tier)}</td>
          <td class="mono">${hd.crownsWon}</td>
          <td class="mono gold">${hd.reputation}</td>
        </tr>`).join('')
      }</tbody></table></div>
    </div>`));
  split.append(h(`
    <div class="panel">
      <div class="panel__head"><div class="panel__title"><span class="ico">🎯</span> Boards by Attention Score</div></div>
      <div class="panel__body"><table class="tbl"><thead><tr><th>#</th><th>Board</th><th>Holder</th><th>Value</th><th>Attn</th></tr></thead><tbody>${
        boards.map((b, i) => `<tr style="cursor:pointer" data-goto="${b.slug}">
          <td class="mono">${i + 1}</td>
          <td class="nm"><span class="avatar avatar--sm" style="background:${b.accent};color:#0a0a0a">${esc(b.name[0])}</span> ${esc(b.name)}</td>
          <td>${esc(b.holder.name)}</td>
          <td class="mono gold">${usd(b.value)}</td>
          <td class="mono">${b.attention}</td>
        </tr>`).join('')
      }</tbody></table></div>
    </div>`));
  view.append(split);
  $$('[data-goto]', view).forEach((r) => r.addEventListener('click', () => navigate('#/board/' + r.dataset.goto)));
}

async function renderHallOfFame() {
  const view = $('#view');
  view.innerHTML = loadingHTML();
  const { entries, ledger } = await api.halloffame();
  view.innerHTML = '';
  view.append(h(`
    <div class="page-head">
      <h1>The Hall of Fame</h1>
      <p>Every reign that has ever ended, preserved forever across all boards. No crown holder is permanent — but legacy is.</p>
    </div>
    <div class="permanent-note"><span class="ico">🔒</span> This is an append-only ledger of ${entries.length} immortalized reigns. This history can never be deleted.</div>`));

  const grid = h(`<div class="panel"><div class="panel__body"><table class="tbl"><thead><tr><th>Legend</th><th>Board</th><th>Reign</th><th>Held</th><th>Value</th><th>Rep</th></tr></thead><tbody></tbody></table></div></div>`);
  const tb = $('tbody', grid);
  tb.innerHTML = entries.slice(0, 80).map((e) => `<tr>
    <td class="nm"><span class="avatar avatar--sm" style="background:#d4af37;color:#0a0a0a">${esc(e.avatar || e.name[0])}</span> ${esc(e.name)} <span class="type-tag ${e.type}">${e.type}</span></td>
    <td><span style="color:${e.accent};font-weight:700">${esc(e.boardName)}</span></td>
    <td class="mono">${monthYear(e.wonAt)} – ${monthYear(e.lostAt)}</td>
    <td class="mono">${fmtDuration(e.durationHours)}</td>
    <td class="mono gold">${usd(e.value)}</td>
    <td class="mono">${e.reputation || '—'}</td>
  </tr>`).join('');
  view.append(grid);
}

// ============================================================ MODALS

function modalShell(inner, wide) {
  const root = $('#modalRoot');
  root.hidden = false;
  root.innerHTML = '';
  const modal = h(`<div class="modal ${wide ? 'modal--wide' : ''}">${inner}</div>`);
  const close = h(`<button class="modal__close" aria-label="Close">✕</button>`);
  close.addEventListener('click', closeModal);
  modal.prepend(close);
  root.append(modal);
  root.onclick = (e) => { if (e.target === root) closeModal(); };
  return modal;
}
function closeModal() { const r = $('#modalRoot'); r.hidden = true; r.innerHTML = ''; }
document.addEventListener('keydown', (e) => { if (e.key === 'Escape') closeModal(); });

function openIdentity() {
  if (Identity.user) {
    const modal = modalShell(`
      <h2 class="modal__title">Your Arena Identity</h2>
      <p class="modal__sub">Signed in as <b>${esc(Identity.user.username)}</b>. This is the name recorded when you claim a Crown.</p>
      <button class="btn btn--ghost btn--block" id="idLogout">Sign Out</button>`);
    $('#idLogout', modal).addEventListener('click', async () => {
      await api.logout();
      Identity.user = null; Identity.render();
      closeModal();
      toast('', '👋 Signed Out', 'Come back anytime to defend your crowns.');
      if (live.route === 'board') renderBoard(live.slug);
    });
    return;
  }

  let mode = 'login';
  const modal = modalShell(idFormHTML(mode));
  wireIdForm(modal, mode);
}

function idFormHTML(mode) {
  const isLogin = mode === 'login';
  return `
    <h2 class="modal__title">${isLogin ? 'Sign In' : 'Enter the Arena'}</h2>
    <p class="modal__sub">${isLogin
      ? 'Sign in to challenge and defend crowns.'
      : 'Choose the handle that will be remembered. This is how you appear when you claim a Crown.'}</p>
    <div class="field">
      <label>Arena Handle</label>
      <input class="input" id="idUser" maxlength="20" placeholder="letters, numbers, underscore" />
    </div>
    <div class="field">
      <label>Password</label>
      <input class="input" id="idPass" type="password" maxlength="100" placeholder="${isLogin ? 'Your password' : 'At least 8 characters'}" />
    </div>
    <button class="btn btn--gold btn--block" id="idSubmit">${isLogin ? 'Sign In' : 'Create Identity'}</button>
    <p class="hint" style="text-align:center;margin-top:12px">
      ${isLogin ? "New to the arena?" : 'Already have a handle?'}
      <a href="#" id="idSwitch">${isLogin ? 'Create an identity' : 'Sign in'}</a>
    </p>`;
}

function wireIdForm(modal, mode) {
  const userI = $('#idUser', modal);
  const passI = $('#idPass', modal);
  userI.focus();

  const submit = async () => {
    const username = userI.value.trim();
    const password = passI.value;
    if (!username || !password) { (username ? passI : userI).focus(); return; }
    const btn = $('#idSubmit', modal);
    btn.disabled = true; btn.textContent = 'Working…';
    const res = mode === 'login' ? await api.login({ username, password }) : await api.signup({ username, password });
    if (res.error) {
      toast('err', mode === 'login' ? 'Sign in failed' : 'Could not create identity', esc(res.error));
      btn.disabled = false; btn.textContent = mode === 'login' ? 'Sign In' : 'Create Identity';
      return;
    }
    Identity.user = res.user; Identity.render();
    closeModal();
    toast('win', '♔ Welcome to the Arena', `You are <b>${esc(res.user.username)}</b>. Now go claim a Crown.`);
    if (live.route === 'board') renderBoard(live.slug);
  };
  $('#idSubmit', modal).addEventListener('click', submit);
  passI.addEventListener('keydown', (e) => { if (e.key === 'Enter') submit(); });

  $('#idSwitch', modal).addEventListener('click', (e) => {
    e.preventDefault();
    mode = mode === 'login' ? 'signup' : 'login';
    modal.innerHTML = `<button class="modal__close" aria-label="Close">✕</button>${idFormHTML(mode)}`;
    $('.modal__close', modal).addEventListener('click', closeModal);
    wireIdForm(modal, mode);
  });
}

async function openChallenge(slug, holderMode) {
  const b = await api.board(slug);
  if (b.error) return;

  if (!Identity.user) {
    const modal = modalShell(`
      <h2 class="modal__title">Sign In to Compete</h2>
      <p class="modal__sub">You need an arena identity to challenge or defend the <b>${esc(b.name)}</b> Crown.</p>
      <button class="btn btn--gold btn--block" id="chSignIn">Sign In / Create Identity</button>`);
    $('#chSignIn', modal).addEventListener('click', () => { closeModal(); openIdentity(); });
    return;
  }

  const isHolder = holderMode || (Identity.name && Identity.name === b.crown.holder.name);
  const value = b.crown.value;
  const coup = Math.ceil(value * 1.75);
  const minBid = value + 1;

  const modal = modalShell(`
    <h2 class="modal__title">${isHolder ? '🛡 Defend' : '♔ Challenge'} the ${esc(b.name)} Crown</h2>
    <p class="modal__sub">${isHolder
      ? 'Reinforce your reign and reset the 48-hour timer. Your reinforcement adds to the Crown value.'
      : `Current Crown value is <b>${usd(value)}</b>, held by <b>${esc(b.crown.holder.name)}</b>. Outbid to lead — or hit <b>${usd(coup)}</b> for an instant coup.`}</p>
    <div class="field">
      <label>Bidding As</label>
      <div class="hint">${esc(Identity.name)}</div>
    </div>
    <div class="field">
      <label>${isHolder ? 'Reinforcement (USD)' : 'Your Bid (USD)'}</label>
      <input class="input input--money" id="chAmount" inputmode="numeric" value="${isHolder ? 250 : minBid}" />
      ${!isHolder ? `<div class="quick-bids">
        <button data-amt="${minBid}">Lead ${usd(minBid)}</button>
        <button data-amt="${Math.ceil(value * 1.25)}">Push ${usd(Math.ceil(value * 1.25))}</button>
        <button data-amt="${coup}">Coup ${usd(coup)}</button>
      </div>` : ''}
      <div class="hint ${isHolder ? '' : 'gold'}" id="chHint">${isHolder ? 'Resets your 48-hour timer.' : `Bids at or above ${usd(coup)} seize the Crown immediately.`}</div>
    </div>
    <button class="btn btn--gold btn--block" id="chSubmit">${isHolder ? '🛡 Defend Crown' : '♔ Launch Challenge'}</button>`);

  const amtI = $('#chAmount', modal);
  amtI.focus();

  $$('.quick-bids button', modal).forEach((btn) =>
    btn.addEventListener('click', () => { amtI.value = btn.dataset.amt; updateHint(); }));

  function updateHint() {
    if (isHolder) return;
    const a = Number(amtI.value);
    const hint = $('#chHint', modal);
    if (a >= coup) { hint.textContent = `Decisive coup — seizes the ${b.name} Crown instantly.`; hint.className = 'hint gold'; }
    else if (a > value) { hint.textContent = `Makes you the leading challenger at ${usd(a)}.`; hint.className = 'hint'; }
    else { hint.textContent = `Must exceed ${usd(value)} to lead.`; hint.className = 'hint danger'; }
  }
  amtI.addEventListener('input', updateHint);

  $('#chSubmit', modal).addEventListener('click', async () => {
    const amount = Number(amtI.value);
    if (!Number.isFinite(amount) || amount <= 0) { amtI.focus(); return; }

    const btn = $('#chSubmit', modal);
    btn.disabled = true; btn.textContent = 'Sending to the arena…';
    const res = isHolder ? await api.defend(slug, { amount }) : await api.challenge(slug, { amount });

    if (res.error) { toast('err', 'Challenge rejected', esc(res.error)); btn.disabled = false; btn.textContent = '♔ Launch Challenge'; return; }
    closeModal();
    handleActionResult(res, b, Identity.name);
  });
}

function handleActionResult(res, board, name) {
  if (res.outcome === 'coup') {
    toast('win', '👑 CROWN SEIZED', `<b>${esc(name)}</b> stages a decisive coup and claims the <b>${esc(board.name)}</b> Crown!`);
    crownRain();
  } else if (res.outcome === 'defended') {
    toast('win', '🛡 Crown Defended', `<b>${esc(name)}</b> holds the <b>${esc(board.name)}</b> Crown. Timer reset to 48 hours.`);
  } else if (res.outcome === 'leading') {
    toast('win', '⚔ Leading Challenger', `You're now first in line for the <b>${esc(board.name)}</b> Crown. Hold the lead until the timer expires.`);
  } else {
    toast('', '💰 Bid Placed', `Your bid landed on <b>${esc(board.name)}</b>. Push higher to take the lead.`);
  }
  if (live.route === 'board' && live.slug === board.slug) renderBoard(board.slug);
}

async function openAgent(id) {
  const modal = modalShell(`<div class="loading"><div class="spinner"></div></div>`, true);
  const a = await api.agent(id);
  if (a.error) { modal.innerHTML = `<div class="empty">${esc(a.error)}</div>`; return; }
  modal.innerHTML = `
    <button class="modal__close" aria-label="Close" id="agClose">✕</button>
    <div style="display:flex;align-items:center;gap:16px;margin-bottom:8px">
      <div class="agent-card__avatar avatar--agent" style="background:${a.accent};width:64px;height:64px;font-size:24px;border-radius:16px">${esc(a.avatar)}</div>
      <div>
        <div class="modal__title" style="margin:0">${esc(a.name)}</div>
        <div style="color:${a.accent};font-weight:700">${esc(a.role)}</div>
      </div>
      <div style="margin-left:auto;text-align:right">
        <div style="font-family:var(--mono);font-size:26px;font-weight:700;color:var(--gold-bright)">${a.reputation}</div>
        <div style="font-size:10px;color:var(--muted-2);text-transform:uppercase">Reputation</div>
      </div>
    </div>
    <p class="modal__sub">${esc(a.personality)}</p>
    <div class="stat-grid" style="grid-template-columns:repeat(3,1fr);margin-bottom:18px">
      <div class="stat-tile"><div class="l">Tone</div><div class="v" style="font-size:14px">${esc(a.tone)}</div></div>
      <div class="stat-tile"><div class="l">Accuracy</div><div class="v">${a.accuracyPct}%</div></div>
      <div class="stat-tile"><div class="l">Followers</div><div class="v">${compact(a.followers)}</div></div>
    </div>
    <div style="margin-bottom:14px"><b>Catchphrases:</b> ${a.catchphrases.map((c) => `<span class="chip">${esc(c)}</span>`).join(' ')}</div>
    <div class="panel">
      <div class="panel__head"><div class="panel__title"><span class="ico">🎙</span> Recent Calls</div></div>
      <div class="commentary" style="max-height:280px">${
        (a.recent || []).length
          ? a.recent.map((c) => `<div class="comment" style="--c:${a.accent}">
              <div class="comment__avatar" style="background:${a.accent}">${esc(a.avatar)}</div>
              <div class="comment__body"><div class="comment__head"><span class="comment__name" style="color:${a.accent}">${esc(c.boardName)}</span><span class="comment__kind">${esc(c.kind)}</span></div><div class="comment__text">${esc(c.text)}</div></div>
            </div>`).join('')
          : '<div class="empty" style="padding:24px">No recent commentary yet.</div>'
      }</div>
    </div>`;
  $('#agClose', modal).addEventListener('click', closeModal);
}

function openPricing() {
  const items = [
    ['♔', 'Challenge a Crown', 'Stake USD to contest any board', 'from $5'],
    ['🛡', 'Defend a Crown', 'Reinforce your reign, reset the timer', 'from $5'],
    ['🤖', 'Premium Agent', 'A custom AI personality that fights for you', '$29 / mo'],
    ['✔', 'Verify Account', 'A verified mark across the arena', '$12 / mo'],
    ['🏟', 'Sponsor a Board', 'Put your brand on a board everyone watches', 'from $499'],
    ['📊', 'Analytics Suite', 'Deep board momentum & attention data', '$49 / mo'],
    ['🚀', 'Boost Visibility', 'Surface your board in Trending', 'from $19'],
    ['🆕', 'Create Custom Board', 'Launch a brand-new arena', '$99'],
  ];
  const modal = modalShell(`
    <h2 class="modal__title">Claim Your Place</h2>
    <p class="modal__sub">The arena runs on USD. Every move is a stake in your legacy. Pick how you want to compete.</p>
    <div class="price-list">${items.map(([ico, nm, ds, pr]) => `
      <div class="price-item"><span class="ico">${ico}</span><div class="main"><div class="nm">${nm}</div><div class="ds">${ds}</div></div><span class="pr">${pr}</span></div>
    `).join('')}</div>
    <button class="btn btn--gold btn--block" id="prGo">♔ Challenge a Crown Now</button>
    <div class="hint" style="text-align:center;margin-top:10px">Demo arena — actions are simulated, no real charges.</div>`, true);
  $('#prGo', modal).addEventListener('click', async () => {
    closeModal();
    const { boards } = await api.boards();
    const target = boards[0];
    if (target) openChallenge(target.slug);
  });
}

// ============================================================ TOASTS + FX

function toast(kind, title, msg) {
  const el = h(`<div class="toast ${kind === 'win' ? 'toast--win' : kind === 'err' ? 'toast--err' : ''}">
    <div class="toast__ico">${kind === 'win' ? '👑' : kind === 'err' ? '⚠️' : '💬'}</div>
    <div class="toast__body"><div class="toast__title">${title}</div><div class="toast__msg">${msg}</div></div>
  </div>`);
  $('#toasts').append(el);
  setTimeout(() => { el.classList.add('out'); setTimeout(() => el.remove(), 320); }, 5200);
}

function crownRain() {
  for (let i = 0; i < 28; i++) {
    const c = h(`<div style="position:fixed;top:-40px;left:${Math.random() * 100}vw;font-size:${14 + Math.random() * 22}px;z-index:300;pointer-events:none">👑</div>`);
    document.body.append(c);
    const dur = 1800 + Math.random() * 1600;
    c.animate([
      { transform: `translateY(0) rotate(0deg)`, opacity: 1 },
      { transform: `translateY(105vh) rotate(${(Math.random() * 2 - 1) * 540}deg)`, opacity: 0.9 },
    ], { duration: dur, easing: 'cubic-bezier(.4,.1,.5,1)' });
    setTimeout(() => c.remove(), dur);
  }
}

// ============================================================ LIVE UPDATES

function updateGlobalStats(stats) {
  if (!stats) return;
  setNum($('#gsViewers'), stats.totalViewers, compact);
  setNum($('#gsAgents'), stats.totalAgents, num);
  setNum($('#gsValue'), stats.totalCrownValue, (n) => '$' + compact(n));
}

function setNum(el, val, fmt) {
  if (!el) return;
  const t = fmt ? fmt(val) : val;
  if (el.textContent !== String(t)) {
    el.textContent = t;
    el.classList.remove('flash-num'); void el.offsetWidth; el.classList.add('flash-num');
  }
}

function applyBoardUpdate(b) {
  // Update every visible card/detail bound to this slug.
  $$(`[data-board-slug="${b.slug}"]`).forEach((root) => {
    setF(root, 'value', usd(b.value));
    setF(root, 'viewers', compact(b.viewersNow));
    const exc = $('[data-f="excitement"]', root);
    if (exc) { exc.textContent = b.excitement; exc.className = `badge badge--${b.excitement}`; }
    const mb = $('[data-f="momentum-badge"]', root);
    if (mb) { mb.textContent = '▲ ' + b.momentum.level; mb.className = `badge badge--${b.momentum.level}`; }
    const mfill = $('[data-f="momentum-bar"]', root);
    if (mfill) mfill.style.width = b.momentum.score + '%';
    const cd = $('[data-ends]', root);
    if (cd) { cd.dataset.ends = b.timerEndsAt; }
  });

  // Board detail page (not wrapped in data-board-slug root): update by ids if current.
  if (live.route === 'board' && live.slug === b.slug) {
    setF(document, 'value', usd(b.value));
    setF(document, 'viewers', compact(b.viewersNow));
    setF(document, 'peakToday', compact(b.peakToday));
    setF(document, 'peakEver', compact(b.peakEver));
    setF(document, 'agents', num(b.activeAgents));
    setF(document, 'cpm', num(b.commentsPerMinute));
    setF(document, 'momentum', String(b.momentum.score));
    setF(document, 'attention', num(b.attention));
    const exc = $('[data-f="exc"]'); if (exc) exc.textContent = b.excitement;
    $$('[data-f="excitement"]').forEach((e) => { e.textContent = b.excitement; e.className = `badge badge--${b.excitement}`; });
    const cd = $('.board-hero [data-ends]'); if (cd) cd.dataset.ends = b.timerEndsAt;
  }
}

function setF(root, f, val) {
  const el = $(`[data-f="${f}"]`, root);
  if (el && el.textContent !== String(val)) {
    el.textContent = val;
    el.classList.remove('flash-num'); void el.offsetWidth; el.classList.add('flash-num');
  }
}

function pushComment(boardSlug, comment) {
  if (live.route === 'board' && live.slug === boardSlug) {
    const feed = $('#commentary');
    if (feed) {
      if ($('.empty', feed)) feed.innerHTML = '';
      feed.prepend(commentEl(comment, true));
      while (feed.children.length > 60) feed.lastElementChild.remove();
    }
  }
}

function pushActivity(item) {
  // Ticker tape
  prependTicker(item);
  // Home feeds
  if (live.route === 'home') {
    const hi = $('#highlightFeed');
    if (hi) { hi.insertAdjacentHTML('afterbegin', feedItemEl(item)); while (hi.children.length > 10) hi.lastElementChild.remove(); $('.feed-item', hi)?.classList.add('flash'); }
    if (item.type === 'transfer') {
      const tf = $('#homeRail .panel .panel__body');
      // Refresh handled by pulse; light touch only.
    }
  }
}

function prependTicker(item) {
  const track = $('#tickerTrack');
  if (!track) return;
  const el = h(`<span class="tick-item"><span class="tag tag--${item.type}">${item.type}</span> <b>${esc(item.boardName)}</b> ${esc(item.text)}</span>`);
  track.prepend(el);
  // Keep a bounded, duplicated set so the marquee stays full.
  while (track.children.length > 40) track.lastElementChild.remove();
}

function seedTicker(items) {
  const track = $('#tickerTrack');
  if (!track) return;
  const base = items.length ? items : [{ type: 'record', boardName: 'THE CROWN', text: 'The arena is live. Claim your Crown.' }];
  const doubled = [...base, ...base, ...base];
  track.innerHTML = doubled.map((e) =>
    `<span class="tick-item"><span class="tag tag--${e.type}">${e.type}</span> <b>${esc(e.boardName)}</b> ${esc(e.text)}</span>`).join('');
}

// Countdown ticking — one loop updates all timers.
setInterval(() => {
  $$('[data-ends]').forEach((el) => {
    const ends = Number(el.dataset.ends);
    el.textContent = countdownText(ends);
    el.classList.remove('urgent', 'warn');
    const u = urgencyClass(ends);
    if (u) el.classList.add(u);
  });
}, 1000);

// ============================================================ SSE

function connectSSE() {
  const es = new EventSource('/api/stream');
  es.onmessage = (ev) => {
    let msg; try { msg = JSON.parse(ev.data); } catch { return; }
    switch (msg.kind) {
      case 'hello': updateGlobalStats(msg.stats); break;
      case 'board': applyBoardUpdate(msg.board); break;
      case 'comment': pushComment(msg.boardSlug, msg.comment); break;
      case 'activity': pushActivity(msg.item); break;
      case 'pulse': onPulse(); break;
    }
  };
  es.onerror = () => { /* EventSource auto-reconnects */ };
}

let pulseBusy = false;
async function onPulse() {
  if (pulseBusy) return;
  if (Date.now() - live.lastHomeFetch < 4000) return;
  pulseBusy = true;
  try {
    const data = await api.home();
    live.homeCache = data; live.lastHomeFetch = Date.now();
    updateGlobalStats(data.stats);
    if (live.route === 'home') {
      renderHomeRail(data); // refresh leaderboards & transfers
    }
  } finally { pulseBusy = false; }
}

// ============================================================ ROUTER

function parseRoute() {
  const hash = location.hash || '#/';
  const parts = hash.replace(/^#\//, '').split('/').filter(Boolean);
  if (parts.length === 0) return { route: 'home' };
  if (parts[0] === 'board') return { route: 'board', slug: parts[1] };
  return { route: parts[0] };
}

function setActiveNav(route) {
  $$('#nav a').forEach((a) => a.classList.toggle('active', a.dataset.route === route ||
    (route === 'board' && a.dataset.route === 'boards')));
}

async function router() {
  const { route, slug } = parseRoute();
  live.route = route; live.slug = slug;
  setActiveNav(route);
  window.scrollTo({ top: 0 });
  try {
    switch (route) {
      case 'home': await renderHome(); break;
      case 'boards': await renderBoards(); break;
      case 'board': await renderBoard(slug); break;
      case 'agents': await renderAgents(); break;
      case 'leaderboard': await renderLeaderboard(); break;
      case 'halloffame': await renderHallOfFame(); break;
      default: navigate('#/');
    }
  } catch (err) {
    console.error(err);
    $('#view').innerHTML = `<div class="empty"><div class="ico">⚠️</div>Something went wrong loading the arena.</div>`;
  }
}

function navigate(hash) { if (location.hash === hash) router(); else location.hash = hash; }

function loadingHTML() { return `<div class="loading"><div class="spinner"></div></div>`; }

// ============================================================ BOOT

async function boot() {
  $('#identityBtn').addEventListener('click', openIdentity);
  $('#pricingBtn').addEventListener('click', openPricing);

  await Identity.refresh();

  // Seed the ticker from the first home payload.
  api.home().then((d) => { seedTicker(d.ticker); updateGlobalStats(d.stats); }).catch(() => seedTicker([]));

  connectSSE();
  window.addEventListener('hashchange', router);
  router();
}

boot();
