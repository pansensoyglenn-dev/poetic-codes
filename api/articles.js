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

  const adminKey = req.headers['x-admin-key'];
  const isAuthorized = adminKey === process.env.ADMIN_KEY;

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
    if (!isAuthorized) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    try {
      const { title, category, date, body, summary, tags, photoUrl, videoUrl } = req.body;

      const query = `
        INSERT INTO articles (title, category, date, content_type, content, excerpt, tags, photo_url, video_url, created_at)
        VALUES ($1, $2, $3, 'html', $4, $5, $6, $7, $8, NOW())
        RETURNING *;
      `;
      
      const values = [
        title, category, date || new Date().toISOString().split('T')[0], 
        body, summary || '', JSON.stringify(tags || []), 
        photoUrl || null, videoUrl || null
      ];

      const result = await pool.query(query, values);
      return res.status(201).json({ success: true, article: result.rows[0] });
    } catch (error) {
      console.error('Insert Error:', error);
      return res.status(500).json({ error: 'Failed to save article', details: error.message });
    }
  }

  if (req.method === 'PUT') {
    if (!isAuthorized) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    try {
      const id = req.query.id;
      const { title, category, date, body, summary, tags, photoUrl, videoUrl } = req.body;

      const query = `
        UPDATE articles 
        SET title = $1, category = $2, date = $3, content = $4, excerpt = $5, tags = $6, photo_url = $7, video_url = $8
        WHERE id = $9
        RETURNING *;
      `;
      
      const values = [
        title, category, date || new Date().toISOString().split('T')[0], 
        body, summary || '', JSON.stringify(tags || []), 
        photoUrl || null, videoUrl || null, id
      ];

      const result = await pool.query(query, values);
      if (result.rowCount === 0) return res.status(404).json({ error: 'Article not found' });
      return res.status(200).json({ success: true, article: result.rows[0] });
    } catch (error) {
      console.error('Update Error:', error);
      return res.status(500).json({ error: 'Failed to update article', details: error.message });
    }
  }

  if (req.method === 'DELETE') {
    if (!isAuthorized) {
      return res.status(401).json({ error: 'Unauthorized' });
    }

    try {
      const id = req.query.id;
      const result = await pool.query('DELETE FROM articles WHERE id = $1 RETURNING *', [id]);
      if (result.rowCount === 0) return res.status(404).json({ error: 'Article not found' });
      return res.status(200).json({ success: true });
    } catch (error) {
      console.error('Delete Error:', error);
      return res.status(500).json({ error: 'Failed to delete article', details: error.message });
    }
  }

  return res.status(405).json({ error: 'Method Not Allowed' });
}
