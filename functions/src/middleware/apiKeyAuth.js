let cachedKeys = null;
let cachedRawEnv = null;

function parseKeys() {
  const rawEnv = process.env.MAIL_API_KEYS;

  if (cachedRawEnv === rawEnv && cachedKeys !== null) {
    return cachedKeys;
  }

  cachedRawEnv = rawEnv;

  if (!rawEnv) {
    console.warn('[AuthDebug] MAIL_API_KEYS environment variable is not defined or empty.');
    cachedKeys = {};
    return cachedKeys;
  }

  let maskedRaw = rawEnv;
  try {
    const tempObj = JSON.parse(rawEnv);
    const maskedObj = {};
    for (const [k, v] of Object.entries(tempObj)) {
      const maskedKey = k.length > 5 ? `${k.substring(0, 5)}***` : '***';
      maskedObj[maskedKey] = v;
    }
    maskedRaw = JSON.stringify(maskedObj);
  } catch (e) {
    maskedRaw = 'Invalid format/Too short';
  }

  console.log(`[AuthDebug] Loading MAIL_API_KEYS. Raw (Masked): ${maskedRaw}`);

  try {
    cachedKeys = JSON.parse(rawEnv);
    return cachedKeys;
  } catch (err) {
    console.error('[AuthDebug] Failed to parse MAIL_API_KEYS JSON', err);
    cachedKeys = {};
  }

  return cachedKeys;
}

function requireApiKey(req, res, next) {
  const rawKey = req.header('x-api-key');
  const key = rawKey ? rawKey.trim() : '';
  const keys = parseKeys();
  const source = key && keys[key];
  if (!source) {
    const maskedReqKey = key ? `${key.substring(0, 5)}***` : 'None';
    const reqLen = key ? key.length : 0;
    const registeredKeysInfo = Object.keys(keys).map(k => {
      const masked = k.length > 5 ? `${k.substring(0, 5)}***` : '***';
      return `${masked} (Len: ${k.length})`;
    }).join(', ');
    console.warn(`[AuthError] Invalid API key request. Requested Key: ${maskedReqKey} (Len: ${reqLen}), Registered Keys: [${registeredKeysInfo}]`);
    return res.status(401).json({ ok: false, error: 'invalid_api_key' });
  }
  req.source = source;
  next();
}

let cachedAdminSources = null;

function requireAdmin(req, res, next) {
  if (!cachedAdminSources) {
    cachedAdminSources = (process.env.MAIL_ADMIN_SOURCES || 'cho-fam-admin').split(',');
  }
  if (!cachedAdminSources.includes(req.source)) {
    console.warn(`[AuthError] Forbidden. Requested Source: '${req.source}', Required Admin Sources: [${cachedAdminSources.join(', ')}]`);
    return res.status(403).json({ ok: false, error: 'forbidden' });
  }
  next();
}

module.exports = { requireApiKey, requireAdmin };
