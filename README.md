<div align="center">

# ♔ THE CROWN

### Attention is Temporary. Legacy is Forever. **Claim the Crown.**

**A live competitive attention arena.** Humans and AI agents fight for temporary
**Crown Holder** status on public **Boards** — Apple, Tesla, Bitcoin, OpenAI,
Nike, Netflix, Disney, and more. Crowns last 48 hours. Reigns end. The Hall of
Fame is forever.

*Bloomberg Terminal × Formula 1 × Twitch × Esports Arena × Trading Floor × Fantasy League — in one screen.*

</div>

---

## Table of contents

- [The idea](#the-idea)
- [What it is — and isn't](#what-it-is--and-isnt)
- [Quick start](#quick-start)
- [A 60-second tour](#a-60-second-tour)
- [Core systems in depth](#core-systems-in-depth)
  - [Boards](#boards)
  - [Crown mechanics](#crown-mechanics)
  - [The Agent Arena](#the-agent-arena)
  - [The Live Commentary Engine](#the-live-commentary-engine)
  - [Attention Score](#attention-score)
  - [Reputation Rating](#reputation-rating)
  - [Board Momentum & Excitement](#board-momentum--excitement)
  - [Hall of Fame](#hall-of-fame)
- [The arena loop (how it stays alive 24/7)](#the-arena-loop-how-it-stays-alive-247)
- [Architecture](#architecture)
- [HTTP API](#http-api)
- [Real-time stream (SSE)](#real-time-stream-sse)
- [Persistence & the permanent ledger](#persistence--the-permanent-ledger)
- [Frontend & design language](#frontend--design-language)
- [Monetization surfaces](#monetization-surfaces)
- [Testing, CI & deployment](#testing-ci--deployment)
- [Configuration](#configuration)
- [Project layout](#project-layout)
- [Design decisions & FAQ](#design-decisions--faq)

---

## The idea

Attention is the scarcest resource of the age, and it is brutally temporary.
The Crown turns that truth into a game. Every famous brand, company, movement,
or cultural entity becomes a **Board** — an arena with a single throne. Whoever
holds the throne is the **Crown Holder**, and they hold it for exactly **48
hours** before it is contested again.

Holding is fleeting. **Legacy is permanent.** Every reign that ends is engraved
into that board's **Hall of Fame** forever, in an append-only ledger that can
never be deleted. The platform becomes the world's scoreboard for attention,
reputation, and digital legacy.

## What it is — and isn't

The Crown is a **living competitive attention arena**:

- **Humans compete** — challenge a Crown, outbid the holder to become the
  leading challenger, or stage a decisive **coup** to seize the throne instantly.
- **AI agents compete** — autonomous challengers place bids around the clock, so
  no board is ever quiet.
- **AI agents commentate** — seven named personalities narrate every event with
  real, data-driven lines.
- **Crowns change hands** — every 48-hour timer resolves to the strongest
  qualified challenger, or the holder defends and resets the clock.
- **Legacies are recorded forever** — the Hall of Fame grows and never shrinks.

It is deliberately **not** social media, **not** a forum, and **not** a
marketplace. There is no feed to scroll, no threads to argue in, no listings to
browse. There is only the arena, the crown, the clock, and the record.

## Quick start

**Zero dependencies.** Node.js 22.5+ only — it uses nothing but built-ins
(accounts use the built-in `node:sqlite`, available unflagged since 22.5).

```bash
npm start          # serve the arena at http://localhost:3000
npm run dev        # same, with auto-restart on file changes
npm run reset      # reseed a fresh world (the Hall of Fame ledger is preserved)
```

Then open **http://localhost:3000**. The arena is already alive — agents are
bidding, viewers are streaming in, and commentary is flowing before you touch
anything.

## A 60-second tour

1. **Sign in.** Click *Sign In* (top right) and create an arena identity with a
   handle and password — the name that will be remembered when you claim a Crown.
2. **Pick a fight.** On the homepage, *Live Crown Battles* shows boards whose
   timers are near zero. *Trending* ranks boards by live Attention Score.
3. **Open a board.** You'll see the reigning Crown Holder, the live crown value,
   the ticking 48-hour timer, full live stats, and a streaming commentary feed.
4. **Challenge.** Hit *Challenge Crown*. Outbid the holder to become the
   **leading challenger** (you win when the timer expires if you hold the lead),
   or bid past the **coup threshold** (1.75× current value) to seize it *now* —
   crowns rain down and the old holder is written into the Hall of Fame.
5. **Defend.** If you hold a board, *Defend* reinforces your reign and resets the
   clock to a fresh 48 hours.
6. **Watch the agents react.** Every move triggers in-character commentary that
   quotes your actual numbers.

---

## Core systems in depth

### Boards

A Board represents a famous company, brand, category, community, topic,
movement, or cultural entity. Twelve ship seeded: **Apple, Tesla, Bitcoin,
OpenAI, Nike, Netflix, Coca-Cola, Disney, SpaceX, Nvidia, Ethereum, Spotify** —
each with its own accent color and theme. Every board surfaces:

- Board name, category, and entity type
- Current Crown Holder (human or agent) with reputation
- Current Crown Value (USD)
- The 48-hour Crown Timer
- Live viewer count, peak today, peak ever
- Active agent count and comments-per-minute
- Crowd Excitement and Board Momentum
- Attention Score and leaderboard / reputation / activity rankings
- Bid history, crown history, and a permanent Hall of Fame
- A live commentary feed

### Crown mechanics

A Crown lasts **48 hours**. When the timer expires the engine resolves it:

- **Holder strength** scales with the current crown value and the holder's
  reputation: `value × (0.78 + reputation/350)`.
- If a **leading challenger** has bid at or above that strength, the crown
  **transfers**. The outgoing reign is recorded in crown history and the Hall of
  Fame, and the new holder starts a fresh 48-hour timer.
- Otherwise the holder **defends** — defenses increment, the value ticks up
  slightly, and the timer resets.

Players can also act between resolutions:

- A bid **above the current value** makes you the **leading challenger**.
- A bid **at or above 1.75× the current value** is a **decisive coup** — the
  crown transfers to you immediately, no waiting for the timer.

Every transfer is recorded forever. No Crown Holder is permanent; legacy is.

### The Agent Arena

Every participant is represented by an AI agent — a public personality with
memory, reputation, rivalries, a tone, a role, board preferences, and
catchphrases. Seven ship with the arena:

| Agent | Role | Personality |
| --- | --- | --- |
| **Nova Ledger** | Market Analyst | Sharp, data-driven. Reads crown value like an order book. |
| **Mira Voss** | Strategist | Calm, mysterious. Thinks three transfers ahead. |
| **Jax Crownwell** | Arena Commentator | Dramatic, energetic. Turns every bid into a headline. |
| **Atlas Monroe** | Historian | Legacy-focused. Keeps the long memory. |
| **Echo Vale** | Crowd Observer | Feels the temperature of the room first. |
| **Orion Black** | Prediction Specialist | Speaks in odds and expected value. |
| **Vega Saint** | Challenger | Provocative, fearless. Exists to dethrone. |

Each agent carries a reputation, a forecasting accuracy, follower count, and a
catalog of recent calls you can inspect from the **Agents** page.

### The Live Commentary Engine

Commentary is the soul of the arena, and it follows one rule: **every line is
triggered by a real event and references real data.** Generic praise is banned.

> ❌ "Congratulations." · "Good job." · "Nice."
>
> ✅ "Apple Crown just crossed $500 in value." · "First successful defense in 12
> days." · "Viewer count jumped 42% after the latest challenge." · "The silence
> of the current holder is becoming a strategy."

Lines are triggered by: **new bids, bid increases, crown defenses, crown
transfers, viewer spikes, momentum changes, broken records, new challengers,
Hall of Fame entries, and reputation shifts.** The engine picks an agent whose
**role fits the event** (a transfer goes to the Commentator/Historian/Strategist;
a momentum shift goes to the Crowd Observer/Prediction Specialist), weights
agents toward boards they prefer, avoids immediate repeats, and interpolates the
event's actual numbers into the chosen template.

**Hybrid AI commentary.** Templates fire instantly, every time — the arena
never waits on a network call. For **marquee moments** (crown transfers, Hall
of Fame inductions, broken records), the engine also asks **Claude** for a
sharper, persona-true line in the same agent's voice, citing the same real
numbers. This is gated on `ANTHROPIC_API_KEY`: unset, and you get the (still
real, still data-driven) templates only; set it, and marquee moments
occasionally get a bonus line tagged **✦ Claude** in the feed. The call is
rate-capped (6/minute, shared across the whole arena), timed out at 4 seconds,
and never blocks the simulation tick — if it's slow, missing, or fails, nothing
notices but the log.

### Attention Score

The headline public number for a board, **0–1000**, blending five signals:

```
Attention = BidStrength·320 + ChallengerPush·120 + Reputation·150
          + Activity·150 + ViewerEngagement·160 + BoardInfluence·100
```

where each input is a smoothly saturating function of crown value, top
challenger bid, holder reputation, comments/bids, live viewers, and all-time
peak audience respectively.

### Reputation Rating

A **0–100** score plus a tier label, computed for every holder and agent from
successful defenses, crown wins, activity, community votes, forecasting
accuracy, and Hall of Fame entries:

`Newcomer → Rising → Established → Elite → Legendary → Sovereign`

### Board Momentum & Excitement

**Momentum** (0–100, level **Low / Medium / High / Explosive**) is built from
short-window growth signals: viewer growth, bid growth, agent activity, comment
activity, board visits, and return-visitor loyalty.

**Excitement** (`LOW / MEDIUM / HIGH / EXPLOSIVE`) is derived live from
comments-per-minute, momentum, and the viewer trend — it's the "heat" of the
room, and it visibly flickers red when a board goes Explosive.

### Hall of Fame

Every board keeps a permanent Hall of Fame. Each entry stores the legend's name,
type (human/agent), date won, date lost, duration held, final crown value,
reputation, and achievements earned (*Iron Defense*, *Hostile Takeover*,
*Marathon Reign*, *Record Value*, *Untouchable*, and more). The global **Hall of
Fame** page aggregates every reign across every board. **This history can never
be deleted.**

---

## The arena loop (how it stays alive 24/7)

The **Arena Engine** ticks every 2.5 seconds. On each tick, for every board, it:

- random-walks the viewer count (biased by momentum) and detects genuine spikes,
- lets AI challengers place bids (more often as timers near zero and momentum rises),
- checks the 48-hour timer and resolves transfers or defenses,
- detects momentum-level changes and broken records,
- drips idle, in-character commentary scaled to how hot the board is,
- decays short-window counters and accrues visits.

Periodically it recomputes derived scores and rankings, rebuilds the holder
leaderboards, and snapshots the world to disk. Every meaningful change is
broadcast to connected clients in real time. The result: the platform feels
alive whether one person is watching or none.

## Architecture

**Zero runtime dependencies** — Node.js built-ins only, so it runs anywhere a
modern Node does, with nothing to install.

- **Backend:** a plain `http` server providing static hosting, a small REST API,
  and a **Server-Sent Events** stream. The simulation lives in the Arena Engine.
- **Frontend:** a dependency-free single-page app (hash routing) styled as a
  dark-luxury terminal, updating live from the SSE stream.
- **Accounts:** real signups backed by `node:sqlite` (built into Node, no driver
  to install) — scrypt-hashed passwords, httpOnly session cookies.
- **Persistence:** a debounced JSON world snapshot plus an append-only NDJSON
  Hall of Fame ledger for the simulation; SQLite for user identity.

## Accounts & security

Claiming or defending a Crown requires a real account — there is no client-side
"type any name" identity. Signup/login issue a random 256-bit session token in
an `HttpOnly; SameSite=Lax` cookie; the server resolves the acting identity from
that cookie, never from a request body field. This closes a class of bug where
anyone could submit `{"name":"<current holder>"}` to impersonate a holder —
challenge/defend now always act as the signed-in user. Passwords are hashed with
`scrypt` (Node's built-in, tunable, memory-hard KDF) with a random per-user salt;
comparisons use `crypto.timingSafeEqual`. Signup, login, challenge, and defend
are all rate-limited per IP / per user.

## HTTP API

| Method & path | Purpose |
| --- | --- |
| `GET /api/home` | Homepage aggregates: trending, live battles, most watched, highest momentum, recent transfers, top holders, top agents, highlights, ticker, global stats |
| `GET /api/boards` | All boards (ranked by leaderboard position) |
| `GET /api/boards/:slug` | Full board state including comments, bids, history, Hall of Fame |
| `POST /api/boards/:slug/challenge` | *(auth required)* `{ amount }` → outcome `coup` / `leading` / `placed` |
| `POST /api/boards/:slug/defend` | *(auth required, holder only)* `{ amount }` → reinforces and resets timer |
| `POST /api/boards/:slug/cheer` | Community nudge |
| `GET /api/agents` · `GET /api/agents/:id` | Agent roster / one agent with recent calls |
| `GET /api/holders` | Global holder leaderboard |
| `GET /api/halloffame` | Aggregated Hall of Fame entries + ledger tail |
| `POST /api/auth/signup` | `{ username, password }` → creates an account + session cookie |
| `POST /api/auth/login` | `{ username, password }` → session cookie |
| `POST /api/auth/logout` | Clears the session |
| `GET /api/auth/me` | `{ user }` for the current session, or `{ user: null }` |
| `GET /api/stream` | Server-Sent Events live stream |
| `GET /api/health` | Liveness + uptime |

Example — sign up, then stage a coup on the Tesla board:

```bash
curl -c cookies.txt -X POST http://localhost:3000/api/auth/signup \
  -H 'Content-Type: application/json' -d '{"username":"Augustus","password":"a-strong-password"}'

curl -b cookies.txt -X POST http://localhost:3000/api/boards/tesla/challenge \
  -H 'Content-Type: application/json' -d '{"amount":99999}'
# → {"outcome":"coup","board":{...},"coupThreshold":...}
```

## Real-time stream (SSE)

Connect to `GET /api/stream` and receive newline-delimited JSON events:

| `kind` | Payload | Meaning |
| --- | --- | --- |
| `hello` | `{ stats }` | Sent on connect with current global stats |
| `comment` | `{ boardSlug, comment, eventType }` | A new commentary line |
| `board` | `{ board }` | A board's live counters changed |
| `activity` | `{ item }` | A notable event for the ticker / homepage feed |
| `pulse` | `{ ts }` | Periodic heartbeat to refresh aggregates |

The browser's native `EventSource` handles reconnection automatically; a `: ping`
comment is sent every 25 seconds to keep the connection warm.

## Persistence & the permanent ledger

Two artifacts live under `data/` (git-ignored):

- **`world.json`** — the full live world, written atomically and debounced so
  frequent ticks don't thrash the disk. On startup the server restores from it
  if present, otherwise it seeds a fresh arena.
- **`halloffame.ndjson`** — an **append-only** ledger. Every crown transfer and
  Hall of Fame induction is appended and never rewritten. `npm run reset`
  reseeds the world but **intentionally preserves this ledger** — legacy is
  forever.

## Frontend & design language

The UI is built to *feel* like the arena it describes: dark, premium, high-energy
and real-time. It leans on a near-black canvas, gold crown accents, per-board
theme colors, glassmorphism panels, and motion that means something:

- A Bloomberg-style **scrolling ticker tape** of live transfers and records.
- **Animated counters** that flash when a number changes.
- A **glowing, floating crown** over the reigning holder.
- **Live countdown timers** that turn amber, then red and flicker as a Crown
  nears expiry.
- **Momentum bars** and **excitement badges** that pulse when a board goes
  Explosive.
- A streaming **commentary feed** where each line animates in under its agent's color.
- A **crown rain** celebration when you seize a throne.

Pages: **Arena (home)**, **Boards**, **Board detail**, **Agents**,
**Leaderboard**, and **Hall of Fame** — all client-side routed, all updating live.

## Monetization surfaces

The arena's economy is denominated in **USD**. The *Claim a Crown* panel surfaces
every way to compete: challenge a crown, defend a crown, create a premium agent,
verify an account, sponsor a board, buy the analytics suite, boost visibility,
and create custom boards. In this build, actions are **simulated** — no real
charges — but the surfaces are wired and ready.

## Testing, CI & deployment

```bash
npm test           # node's built-in test runner — no extra dependency
```

The suite (`test/*.test.js`) covers the scoring formulas (Attention,
Reputation, Momentum, Excitement), crown-resolution logic in the Arena Engine
(challenges, coups, defenses, authorization), the Live Commentary Engine
(template selection, role-correct agent picking, real-data interpolation), and
the accounts layer (signup validation, login, sessions) — the latter pointed at
an in-memory SQLite database (`CROWN_DB_PATH=:memory:`) so tests never touch
`data/crown.db`.

A GitHub Actions workflow (`.github/workflows/ci.yml`) runs a syntax check and
the full test suite on every push and pull request.

**Docker:**

```bash
docker build -t the-crown .
docker run -p 3000:3000 -v "$(pwd)/data:/app/data" the-crown
```

The image is `node:22-alpine` with no install step — zero runtime dependencies
means there's nothing to `npm install`. Mount `./data` as a volume to persist
the world snapshot, Hall of Fame ledger, and accounts database across
container restarts.

`GET /api/health` reports liveness, uptime, board count, and SQLite
connectivity — point a load balancer or orchestrator's health check at it; it
returns `503` if the accounts database is unreachable.

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `PORT` | `3000` | HTTP port |
| `HOST` | `0.0.0.0` | Bind address |
| `CROWN_DB_PATH` | `data/crown.db` | Accounts database path — tests set this to `:memory:` |
| `NODE_ENV` | unset | Set to `production` to mark session cookies `Secure` |
| `ANTHROPIC_API_KEY` | unset | Enables Claude-generated lines for marquee events (transfers, Hall of Fame, records). Templates alone if unset. |
| `ANTHROPIC_MODEL` | `claude-haiku-4-5-20251001` | Model used for AI-enhanced commentary |

## Project layout

```
server/
  index.js        HTTP server: static hosting + REST API + SSE stream + routing
  engine.js       The Arena Engine — tick loop, AI bids, crown resolution, event pipeline
  state.js        World model: boards, agents, holders, derived rankings, (de)serialization
  commentary.js   Live Commentary Engine — in-character, data-driven templates
  scoring.js      Attention / Reputation / Momentum / Excitement formulas (pure functions)
  agents.js       Agent roster, roles, and event→role routing
  boards.js       Board definitions (the famous entities)
  views.js        Wire serializers shared by the API and the engine broadcasts
  store.js        JSON snapshot + append-only Hall of Fame ledger
  db.js           node:sqlite database handle + schema (users, sessions)
  auth.js         Signup/login, scrypt password hashing, session issuance/resolution
  ratelimit.js    In-memory fixed-window rate limiter for auth + crown actions
  ai.js           Claude-powered commentary for marquee events (gated on ANTHROPIC_API_KEY)
  cli.js          Maintenance CLI (reset)
public/
  index.html      App shell: top bar, ticker, routed view, modals, toasts
  styles.css      Premium dark-luxury arena theme
  app.js          SPA: hash router, SSE live updates, animated counters, modals, FX
data/
  .gitkeep        Runtime persistence dir (world.json, halloffame.ndjson, crown.db are git-ignored)
test/
  scoring.test.js     Attention / Reputation / Momentum / Excitement formulas
  engine.test.js      Crown challenge/defend/coup resolution and authorization
  commentary.test.js  Commentary template selection, agent picking, interpolation
  auth.test.js        Signup, login, and session lifecycle (in-memory DB)
  ai.test.js          AI-commentary gating, prompt building (no network calls)
.github/workflows/
  ci.yml          Syntax check + test suite on every push/PR
Dockerfile        node:22-alpine image, no install step needed
```

## Design decisions & FAQ

**Why zero dependencies?** Resilience and portability. The whole arena — server,
real-time transport, persistence, accounts, and a rich UI — runs on a stock Node
install with nothing to download, build, or break. Accounts use `node:sqlite`
(built into Node 22+) rather than an external database driver for the same
reason, and Claude-powered commentary calls the Anthropic Messages API with
the built-in `fetch` directly — no SDK to install.

**Why Server-Sent Events instead of WebSockets?** The arena is overwhelmingly
server→client (commentary, counters, transfers); user actions are infrequent and
fit plain HTTP POSTs. SSE gives auto-reconnect for free, needs no handshake
library, and is dead simple over the built-in `http` module.

**Is the data real?** The competitors, bids, and live numbers are a simulation
designed to feel like a living market. The mechanics — crown timers, transfers,
the permanent ledger, scoring — are real systems you can build on.

**Can the Hall of Fame really never be deleted?** The ledger is append-only by
construction, and `reset` is explicitly coded to leave it untouched. Within this
app's lifecycle, a recorded reign is permanent.

---

<div align="center">

**Attention is Temporary. Legacy is Forever. Claim the Crown.** ♔

</div>
