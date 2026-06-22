// Claude-powered commentary.
//
// Templates fire instantly for every event — the arena never waits on a
// network call. For marquee moments (crown transfers, Hall of Fame
// inductions, broken records) we additionally ask Claude for a sharper,
// persona-true line, gated on ANTHROPIC_API_KEY. If the key is absent, the
// call fails, or it's too slow, we simply stay with the template line —
// this path is a bonus, never a dependency.

import { rateLimit } from './ratelimit.js';

const API_URL = 'https://api.anthropic.com/v1/messages';
const MODEL = process.env.ANTHROPIC_MODEL || 'claude-haiku-4-5-20251001';
const MAX_CALLS_PER_MINUTE = 6;
const TIMEOUT_MS = 4000;

export const aiEnabled = Boolean(process.env.ANTHROPIC_API_KEY);

export const MARQUEE_EVENTS = new Set(['transfer', 'halloffame', 'record']);

function usd(n) {
  return '$' + Math.round(n).toLocaleString('en-US');
}

function factsFor(event, board) {
  switch (event.type) {
    case 'transfer':
      return `${event.fromName} just lost the ${board.name} Crown to ${event.toName} after holding it for `
        + `${Math.round(event.durationHours)} hours. Final crown value: ${usd(event.value)}. `
        + (event.coup
          ? 'This was a decisive coup — an overwhelming bid that seized the crown instantly, no timer expiry needed.'
          : 'The 48-hour timer expired and the challenger\'s bid qualified to take it.');
    case 'halloffame':
      return `${event.name} has just been permanently inducted into the ${board.name} Hall of Fame: held the `
        + `crown for ${Math.round(event.durationHours)} hours at a final value of ${usd(event.value)}, `
        + `reputation ${event.reputation}.`;
    case 'record':
      return `A new record was just set on ${board.name}: ${event.record}.`;
    default:
      return `A notable event just happened on ${board.name}.`;
  }
}

export function buildPrompt(event, board, agent) {
  const system =
    `You are ${agent.name}, the ${agent.role} of a live competitive attention arena called The Crown. `
    + `Your tone: ${agent.tone}. Your personality: ${agent.personality} `
    + 'Write exactly one line of live commentary reacting to the event below — under 220 characters, '
    + 'no hashtags, no emoji, no surrounding quotation marks. Reference the real numbers given. '
    + 'Never write generic praise like "Congratulations" or "Nice" or "Good job" — every line must cite '
    + 'a specific fact from the event.';
  const user = factsFor(event, board);
  return { system, user };
}

/**
 * For marquee events only: ask Claude for a richer line in the given agent's
 * voice. Returns the text, or null if AI commentary isn't available right
 * now (disabled, rate-capped, or the call failed/timed out) — callers should
 * already have a template line on screen and treat this as a pure bonus.
 */
export async function maybeEnhance(event, board, agent) {
  if (!aiEnabled || !MARQUEE_EVENTS.has(event.type)) return null;
  if (!rateLimit('ai-global', { limit: MAX_CALLS_PER_MINUTE, windowMs: 60000 })) return null;

  const { system, user } = buildPrompt(event, board, agent);
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS);
  try {
    const res = await fetch(API_URL, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        'x-api-key': process.env.ANTHROPIC_API_KEY,
        'anthropic-version': '2023-06-01',
      },
      body: JSON.stringify({
        model: MODEL,
        max_tokens: 80,
        system,
        messages: [{ role: 'user', content: user }],
      }),
      signal: controller.signal,
    });
    if (!res.ok) return null;
    const data = await res.json();
    const text = data?.content?.[0]?.text?.trim();
    return text ? text.slice(0, 280) : null;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}
