const Redis = require('ioredis');

const KEY = 'calendar_events';

function makeClient() {
  const url = process.env.DRAFTKV_KV_URL || process.env.DRAFTKV_REDIS_URL || process.env.KV_URL || process.env.REDIS_URL;
  if (!url) throw new Error('KV_URL/REDIS_URL not set');
  return new Redis(url, {
    connectTimeout: 10000,
    commandTimeout: 8000,
    maxRetriesPerRequest: 3,
    enableReadyCheck: false,
    lazyConnect: false,
  });
}

async function kvGet(c) {
  const raw = await c.get(KEY);
  return raw ? JSON.parse(raw) : {};
}

async function kvSet(c, value) {
  await c.set(KEY, JSON.stringify(value));
}

function newId() {
  return 'ev_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8);
}

// Valid event shape:
// { id, date: "YYYY-MM-DD", type: "workout"|"playoff"|"travel"|"other",
//   player, team?, title?, notes?, time?, location?, tentative? }
function validate(ev) {
  if (!ev || typeof ev !== 'object') return 'body must be an object';
  if (!ev.date || !/^\d{4}-\d{2}-\d{2}$/.test(ev.date)) return 'date must be YYYY-MM-DD';
  if (!ev.type || !['workout', 'playoff', 'travel', 'other'].includes(ev.type)) return 'type must be workout|playoff|travel|other';
  if (!ev.player || typeof ev.player !== 'string') return 'player (string) required';
  return null;
}

module.exports = async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(200).end();

  const c = makeClient();
  try {
    if (req.method === 'GET') {
      const events = await kvGet(c);
      return res.json(events);
    }

    if (req.method === 'POST') {
      const body = req.body || {};
      const err = validate(body);
      if (err) return res.status(400).json({ error: err });
      const events = await kvGet(c);
      const id = body.id || newId();
      const prev = events[id];
      events[id] = {
        id,
        date: body.date,
        type: body.type,
        player: body.player,
        team: body.team || null,
        title: body.title || null,
        notes: body.notes || null,
        time: body.time || null,
        location: body.location || null,
        tentative: !!body.tentative,
        confirmed: !!body.confirmed,
        created_at: (prev && prev.created_at) || new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      await kvSet(c, events);
      return res.json({ ok: true, id, event: events[id] });
    }

    if (req.method === 'DELETE') {
      const { id } = req.body || {};
      if (!id) return res.status(400).json({ error: 'id required' });
      const events = await kvGet(c);
      delete events[id];
      await kvSet(c, events);
      return res.json({ ok: true });
    }

    res.status(405).json({ error: 'Method not allowed' });
  } catch (e) {
    res.status(500).json({ error: e.message });
  } finally {
    c.disconnect();
  }
};
