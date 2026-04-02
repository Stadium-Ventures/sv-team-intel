const KV_URL = process.env.KV_REST_API_URL;
const KV_TOKEN = process.env.KV_REST_API_TOKEN;

async function kvGet() {
  const res = await fetch(`${KV_URL}/get/score_overrides`, {
    headers: { Authorization: `Bearer ${KV_TOKEN}` },
  });
  const data = await res.json();
  return data.result ? JSON.parse(data.result) : {};
}

async function kvSet(value) {
  await fetch(KV_URL, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${KV_TOKEN}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(['SET', 'score_overrides', JSON.stringify(value)]),
  });
}

module.exports = async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(200).end();

  try {
    if (req.method === 'GET') {
      const overrides = await kvGet();
      return res.json(overrides);
    }

    if (req.method === 'POST') {
      const { player, team, score } = req.body;
      if (!player || !team) return res.status(400).json({ error: 'player and team required' });
      const overrides = await kvGet();
      const key = `${player}|${team}`;
      if (score === null || score === undefined) {
        delete overrides[key];
      } else {
        overrides[key] = score;
      }
      await kvSet(overrides);
      return res.json({ ok: true });
    }

    res.status(405).json({ error: 'Method not allowed' });
  } catch (e) {
    res.status(500).json({ error: e.message });
  }
};
