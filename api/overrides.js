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

async function kvGet(c) {
  const raw = await c.get('score_overrides');
  return raw ? JSON.parse(raw) : {};
}

async function kvSet(c, value) {
  await c.set('score_overrides', JSON.stringify(value));
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
      return res.json(overrides);
    }

    if (req.method === 'POST') {
      const { player, team, date, score, key: rawKey } = req.body;
      const overrides = await kvGet(c);
      const key = rawKey || `${player}|${team}|${date}`;
      if (!key || key === 'undefined|undefined|undefined') return res.status(400).json({ error: 'key or player+team+date required' });
      if (score === null || score === undefined) {
        delete overrides[key];
      } else {
        overrides[key] = score;
      }
      await kvSet(c, overrides);
      return res.json({ ok: true });
    }

    res.status(405).json({ error: 'Method not allowed' });
  } catch (e) {
    res.status(500).json({ error: e.message });
  } finally {
    c.disconnect();
  }
};
