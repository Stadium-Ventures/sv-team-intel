const Redis = require('ioredis');

const KEY = 'manual_records';

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
  return 'mr_' + Date.now().toString(36) + '_' + Math.random().toString(36).slice(2, 8);
}

// Valid record shape:
// { id, player, team, date: "YYYY-MM-DD", score: -2..2,
//   full_text?, workout?: bool, combine?: bool,
//   workout_dates?: [{date, time?, location?, tentative?}] }
function validate(body) {
  if (!body || typeof body !== 'object') return 'body must be an object';
  if (!body.player || typeof body.player !== 'string') return 'player (string) required';
  if (!body.team || typeof body.team !== 'string') return 'team (string) required';
  if (!body.date || !/^\d{4}-\d{2}-\d{2}$/.test(body.date)) return 'date must be YYYY-MM-DD';
  if (body.score === undefined || body.score === null) return 'score required';
  const s = Number(body.score);
  if (!Number.isFinite(s) || s < -2 || s > 2) return 'score must be between -2 and 2';
  if (body.workout_dates && !Array.isArray(body.workout_dates)) return 'workout_dates must be an array';
  if (Array.isArray(body.workout_dates)) {
    for (const wd of body.workout_dates) {
      if (!wd || !wd.date || !/^\d{4}-\d{2}-\d{2}$/.test(wd.date)) return 'each workout_dates[].date must be YYYY-MM-DD';
    }
  }
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
      const records = await kvGet(c);
      return res.json(records);
    }

    if (req.method === 'POST') {
      const body = req.body || {};
      const err = validate(body);
      if (err) return res.status(400).json({ error: err });
      const records = await kvGet(c);
      const id = body.id || newId();
      const prev = records[id];
      records[id] = {
        id,
        player: body.player,
        team: body.team,
        date: body.date,
        score: Number(body.score),
        full_text: body.full_text || '',
        workout: !!body.workout,
        combine: !!body.combine,
        workout_dates: Array.isArray(body.workout_dates) ? body.workout_dates.map(wd => ({
          date: wd.date,
          time: wd.time || null,
          location: wd.location || null,
          tentative: !!wd.tentative,
        })) : [],
        created_at: (prev && prev.created_at) || new Date().toISOString(),
        updated_at: new Date().toISOString(),
      };
      await kvSet(c, records);
      return res.json({ ok: true, id, record: records[id] });
    }

    if (req.method === 'DELETE') {
      const { id } = req.body || {};
      if (!id) return res.status(400).json({ error: 'id required' });
      const records = await kvGet(c);
      delete records[id];
      await kvSet(c, records);
      return res.json({ ok: true });
    }

    res.status(405).json({ error: 'Method not allowed' });
  } catch (e) {
    res.status(500).json({ error: e.message });
  } finally {
    c.disconnect();
  }
};
