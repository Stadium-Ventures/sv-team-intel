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

const CARDS_KEY = 'draftcard:cells';

async function getCards(c) {
  const raw = await c.get(CARDS_KEY);
  return raw ? JSON.parse(raw) : {};
}

// Per-player draft-card state:
//   cards[player] = { cells: { "<pickIndex>": { ci, combine, team } }, updated_at }
// Only per-square DELTAS off the engine-seeded board are stored:
//   ci      -> color index 0..4 (red/orange/yellow/light green/green), or -1 to force blank
//   combine -> bool, overrides the auto combine flag for that square
//   team    -> string, overrides the baked-in team for that pick
// The static board (pick #, team, slot value) and the engine-seeded colors live
// client-side; this only records the manual overlay.
module.exports = async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type');
  if (req.method === 'OPTIONS') return res.status(200).end();

  const c = makeClient();
  try {
    if (req.method === 'GET') {
      const player = (req.query && req.query.player) || '';
      if (!player) return res.status(400).json({ error: 'player required' });
      const cards = await getCards(c);
      const card = cards[player] || { cells: {}, updated_at: null };
      return res.json(card);
    }

    if (req.method === 'POST') {
      const { player, index, patch, action } = req.body || {};
      if (!player) return res.status(400).json({ error: 'player required' });
      const cards = await getCards(c);
      const card = cards[player] || { cells: {} };

      if (action === 'clear') {
        card.cells = {};
      } else {
        if (index === undefined || index === null) return res.status(400).json({ error: 'index required' });
        const i = String(index);
        const cur = card.cells[i] || {};
        const next = { ...cur };
        if (patch && 'ci' in patch) {
          if (patch.ci === null || patch.ci === undefined) delete next.ci;
          else next.ci = patch.ci;
        }
        if (patch && 'combine' in patch) {
          if (patch.combine === null || patch.combine === undefined) delete next.combine;
          else next.combine = !!patch.combine;
        }
        if (patch && 'team' in patch) {
          const t = String(patch.team || '').toUpperCase().slice(0, 5);
          if (t) next.team = t; else delete next.team;
        }
        // Drop the cell entirely if no deltas remain (keeps the blob lean).
        if (Object.keys(next).length === 0) delete card.cells[i];
        else card.cells[i] = next;
      }

      card.updated_at = new Date().toISOString();
      cards[player] = card;
      await c.set(CARDS_KEY, JSON.stringify(cards));
      return res.json({ ok: true, updated_at: card.updated_at });
    }

    res.status(405).json({ error: 'Method not allowed' });
  } catch (e) {
    res.status(500).json({ error: e.message });
  } finally {
    c.disconnect();
  }
};
