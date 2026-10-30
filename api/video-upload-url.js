import { createClient } from '@supabase/supabase-js';

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL,
  process.env.SUPABASE_SERVICE_ROLE_KEY
);

const BUCKET = 'videos';

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', 'https://poetic-codes.pages.dev');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, X-Admin-Key');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  if (req.method !== 'POST') {
    return res.status(405).json({ error: 'Method Not Allowed' });
  }

  const rawAdminKey = req.headers['x-admin-key'];
  const adminKey = Array.isArray(rawAdminKey) ? rawAdminKey[0] : rawAdminKey;

  if (!process.env.ADMIN_KEY || adminKey !== process.env.ADMIN_KEY) {
    return res.status(401).json({ error: 'Unauthorized' });
  }

  try {
    const requested = String(req.query.filename || 'video.mp4');
    const safe = requested.replace(/[^a-zA-Z0-9._-]/g, '_').replace(/\.mp4$/i, '').slice(0, 80);
    const path = `video-${Date.now()}-${safe || 'article'}.mp4`;

    const { data, error } = await supabase.storage.from(BUCKET).createSignedUploadUrl(path);
    if (error) throw error;

    const { data: publicUrlData } = supabase.storage.from(BUCKET).getPublicUrl(path);

    return res.status(200).json({
      uploadUrl: data.signedUrl,
      url: publicUrlData.publicUrl,
      path,
    });
  } catch (error) {
    console.error('Video upload URL error:', error);
    return res.status(500).json({ error: 'Failed to create upload URL', details: error.message });
  }
}
