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
    const maskedReqKey = key ? `${key.substring(0, 3)}***` : 'None';
    const registeredKeysInfo = Object.keys(keys).map(k => `${k.substring(0, 3)}***`).join(', ');
    console.warn(`[AuthError] Invalid API key request. Requested Key: ${maskedReqKey}, Currently Registered Keys: [${registeredKeysInfo}]`);
    return res.status(401).json({ ok: false, error: 'invalid_api_key' });
  }
  req.source = source;
  next();
}

function requireAdmin(req, res, next) {
  const adminSources = (process.env.MAIL_ADMIN_SOURCES || 'cho-fam-admin').split(',');
  if (!adminSources.includes(req.source)) {
    console.warn(`[AuthError] Forbidden. Requested Source: '${req.source}', Required Admin Sources: [${adminSources.join(', ')}]`);
    return res.status(403).json({ ok: false, error: 'forbidden' });
  }
  next();
}

module.exports = { requireApiKey, requireAdmin };
