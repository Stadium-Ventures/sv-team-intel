const Redis = require('ioredis');

function makeClient() {
  const url = process.env.REDIS_URL;
  if (!url) throw new Error('REDIS_URL not set');
  return new Redis(url, {
    connectTimeout: 10000,
    commandTimeout: 8000,
    maxRetriesPerRequest: 3,
    enableReadyCheck: false,
    lazyConnect: false,
  });
}

const KEY = 'score_overrides';
const META_KEY = 'score_overrides_meta';
const NOTES_KEY = 'score_overrides_notes';

async function kvGet(c) {
  const raw = await c.get(KEY);
  return raw ? JSON.parse(raw) : {};
}

async function kvSet(c, value) {
  await c.set(KEY, JSON.stringify(value));
}

async function kvGetMeta(c) {
  const raw = await c.get(META_KEY);
  return raw ? JSON.parse(raw) : {};
}

async function kvSetMeta(c, value) {
  await c.set(META_KEY, JSON.stringify(value));
}

async function kvGetNotes(c) {
  const raw = await c.get(NOTES_KEY);
  return raw ? JSON.parse(raw) : {};
}

async function kvSetNotes(c, value) {
  await c.set(NOTES_KEY, JSON.stringify(value));
}

module.exports = async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(200).end();

  const c = makeClient();
  try {
    if (req.method === 'GET') {
      const overrides = await kvGet(c);
      // ?meta=1 → include per-key updated_at timestamps + reason notes for the Edits view.
      if (req.query && req.query.meta === '1') {
        const meta = await kvGetMeta(c);
        const notes = await kvGetNotes(c);
        return res.json({ values: overrides, meta, notes });
      }
      return res.json(overrides);
    }

    if (req.method === 'POST') {
      const { player, team, date, score, key: rawKey, note } = req.body;
      const overrides = await kvGet(c);
      const meta = await kvGetMeta(c);
      const notes = await kvGetNotes(c);
      const key = rawKey || `${player}|${team}|${date}`;
      if (!key || key === 'undefined|undefined|undefined') return res.status(400).json({ error: 'key or player+team+date required' });
      if (score === null || score === undefined) {
        delete overrides[key];
        delete meta[key];
        delete notes[key];
      } else {
        overrides[key] = score;
        meta[key] = new Date().toISOString();
        // Optional free-text reason (currently only color overrides send it).
        // Empty/blank clears any prior note; undefined leaves it untouched.
        if (note !== undefined) {
          const trimmed = (typeof note === 'string' ? note.trim() : '');
          if (trimmed) notes[key] = trimmed;
          else delete notes[key];
        }
      }
      await kvSet(c, overrides);
      await kvSetMeta(c, meta);
      await kvSetNotes(c, notes);
      return res.json({ ok: true });
    }

    res.status(405).json({ error: 'Method not allowed' });
  } catch (e) {
    res.status(500).json({ error: e.message });
  } finally {
    c.disconnect();
  }
};
