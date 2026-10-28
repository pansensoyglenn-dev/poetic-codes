import { createClient } from '@supabase/supabase-js';

const supabase = createClient(
  process.env.NEXT_PUBLIC_SUPABASE_URL,
  process.env.SUPABASE_SERVICE_ROLE_KEY
);

export const config = {
  api: {
    bodyParser: false,
  },
};

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

  const adminKey = req.headers['x-admin-key'];
  if (adminKey !== process.env.ADMIN_KEY) {
    return res.status(401).json({ error: 'Unauthorized' });
  }

  try {
    const chunks = [];
    for await (const chunk of req) {
      chunks.push(chunk);
    }
    const buffer = Buffer.concat(chunks);

    if (!buffer.length) {
      return res.status(400).json({ error: 'No image data received' });
    }

    const filename = `cover-${Date.now()}.jpg`;

    const { data, error } = await supabase.storage
      .from('covers')
      .upload(filename, buffer, {
        contentType: req.headers['content-type'] || 'image/jpeg',
        upsert: false
      });

    if (error) throw error;

    const { data: publicUrlData } = supabase.storage
      .from('covers')
      .getPublicUrl(filename);

    return res.status(200).json({ url: publicUrlData.publicUrl });

  } catch (error) {
    console.error('Upload Error:', error);
    return res.status(500).json({ error: 'Failed to upload image', details: error.message });
  }
}
