import { Pool } from 'pg';

const pool = new Pool({
  connectionString: process.env.DATABASE_URL,
  ssl: {
    rejectUnauthorized: false
  }
});

export default async function handler(req, res) {
  res.setHeader('Access-Control-Allow-Origin', 'https://poetic-codes.pages.dev');
  res.setHeader('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS');
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type, X-Admin-Key');

  if (req.method === 'OPTIONS') {
    return res.status(200).end();
  }

  if (req.method === 'GET') {
    try {
      const result = await pool.query('SELECT * FROM articles ORDER BY created_at DESC');
      return res.status(200).json(result.rows);
    } catch (error) {
      console.error('Database Error:', error);
      return res.status(500).json({ error: 'Failed to fetch articles', details: error.message });
    }
  }

  if (req.method === 'POST') {
    const adminKey = req.headers['x-admin-key'];
    if (adminKey !== process.env.ADMIN_KEY) {
      return res.status(401).json({ error: 'Unauthorized: Invalid or missing Admin Key' });
    }

    try {
      const { title, category, date, body, summary, tags, photoUrl, videoUrl } = req.body;

      if (!title || !body) {
        return res.status(400).json({ error: 'Title and body are required' });
      }

      const query = `
        INSERT INTO articles (title, category, date, content_type, content, excerpt, tags, photo_url, video_url, created_at)
        VALUES ($1, $2, $3, 'html', $4, $5, $6, $7, $8, NOW())
        RETURNING *;
      `;
      
      const values = [
        title, 
        category, 
        date || new Date().toISOString().split('T')[0], 
        body, 
        summary || '', 
        JSON.stringify(tags || []), 
        photoUrl || null, 
        videoUrl || null
      ];

      const result = await pool.query(query, values);
      return res.status(201).json({ success: true, article: result.rows[0] });

    } catch (error) {
      console.error('Database Insert Error:', error);
      return res.status(500).json({ error: 'Failed to save article', details: error.message });
    }
  }

  return res.status(405).json({ error: 'Method Not Allowed' });
}
