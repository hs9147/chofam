function parseKeys() {
  try {
    return JSON.parse(process.env.MAIL_API_KEYS || '{}');
  } catch (err) {
    console.error('Invalid MAIL_API_KEYS JSON', err);
    return {};
  }
}

function requireApiKey(req, res, next) {
  const key = req.header('x-api-key');
  const keys = parseKeys();
  const source = key && keys[key];
  if (!source) {
    console.warn('Invalid API key request.');
    return res.status(401).json({ ok: false, error: 'invalid_api_key' });
  }
  req.source = source;
  next();
}

function requireAdmin(req, res, next) {
  const adminSources = (process.env.MAIL_ADMIN_SOURCES || 'CHO-FAM-admin').split(',');
  if (!adminSources.includes(req.source)) {
    return res.status(403).json({ ok: false, error: 'forbidden' });
  }
  next();
}

module.exports = { requireApiKey, requireAdmin };
