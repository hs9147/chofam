const { requireAdmin, requireApiKey, parseKeys, _resetCache } = require('./apiKeyAuth');

describe('apiKeyAuth middleware', () => {
  let req;
  let res;
  let next;
  const originalEnv = process.env;

  beforeEach(() => {
    jest.resetModules();
    process.env = { ...originalEnv };
    _resetCache();
    req = {
      header: jest.fn(),
    };
    res = {
      status: jest.fn().mockReturnThis(),
      json: jest.fn(),
    };
    next = jest.fn();

    jest.clearAllMocks();

    jest.spyOn(console, 'warn').mockImplementation(() => {});
    jest.spyOn(console, 'log').mockImplementation(() => {});
    jest.spyOn(console, 'error').mockImplementation(() => {});
  });

  afterEach(() => {
    delete process.env.MAIL_API_KEYS;
    jest.restoreAllMocks();
  });

  describe('requireApiKey middleware', () => {
    it('should authenticate with a valid API key and set req.source', () => {
      process.env.MAIL_API_KEYS = JSON.stringify({ 'valid-key-123': 'service-a' });
      req.header.mockReturnValue('valid-key-123');

      requireApiKey(req, res, next);

      expect(req.header).toHaveBeenCalledWith('x-api-key');
      expect(req.source).toBe('service-a');
      expect(next).toHaveBeenCalled();
      expect(res.status).not.toHaveBeenCalled();
    });

    it('should reject when MAIL_API_KEYS env is missing', () => {
      req.header.mockReturnValue('valid-key-123');

      requireApiKey(req, res, next);

      expect(next).not.toHaveBeenCalled();
      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith({ ok: false, error: 'invalid_api_key' });
    });

    it('should reject when MAIL_API_KEYS is invalid JSON', () => {
      process.env.MAIL_API_KEYS = 'invalid-json';
      req.header.mockReturnValue('valid-key-123');

      requireApiKey(req, res, next);

      expect(next).not.toHaveBeenCalled();
      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith({ ok: false, error: 'invalid_api_key' });
    });

    it('should reject when API key is missing from request header', () => {
      process.env.MAIL_API_KEYS = JSON.stringify({ 'valid-key-123': 'service-a' });
      req.header.mockReturnValue(undefined);

      requireApiKey(req, res, next);

      expect(next).not.toHaveBeenCalled();
      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith({ ok: false, error: 'invalid_api_key' });
    });

    it('should reject when API key is invalid', () => {
      process.env.MAIL_API_KEYS = JSON.stringify({ 'valid-key-123': 'service-a' });
      req.header.mockReturnValue('invalid-key-456');

      requireApiKey(req, res, next);

      expect(next).not.toHaveBeenCalled();
      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith({ ok: false, error: 'invalid_api_key' });
    });
  });

  describe('parseKeys', () => {
    it('should return an empty object when MAIL_API_KEYS is missing', () => {
      delete process.env.MAIL_API_KEYS;
      const keys = parseKeys();
      expect(keys).toEqual({});
      expect(console.warn).toHaveBeenCalledWith('[AuthDebug] MAIL_API_KEYS environment variable is not defined or empty.');
    });

    it('should return an empty object when MAIL_API_KEYS is empty string', () => {
      process.env.MAIL_API_KEYS = '';
      const keys = parseKeys();
      expect(keys).toEqual({});
      expect(console.warn).toHaveBeenCalledWith('[AuthDebug] MAIL_API_KEYS environment variable is not defined or empty.');
    });

    it('should correctly parse and return object for valid JSON', () => {
      process.env.MAIL_API_KEYS = JSON.stringify({ key1: 'source1', key2: 'source2' });
      const keys = parseKeys();
      expect(keys).toEqual({ key1: 'source1', key2: 'source2' });
    });

    it('should return empty object and log error for invalid JSON', () => {
      process.env.MAIL_API_KEYS = 'invalid-json';
      const keys = parseKeys();
      expect(keys).toEqual({});
      expect(console.error).toHaveBeenCalledWith('[AuthDebug] Failed to parse MAIL_API_KEYS JSON', expect.any(Error));
    });

    it('should correctly mask keys in debug log', () => {
      process.env.MAIL_API_KEYS = JSON.stringify({ short: 'src', longkey123: 'src2' });
      parseKeys();

      const expectedMasked = JSON.stringify({
        '***': 'src',
        'longk***': 'src2'
      });
      expect(console.log).toHaveBeenCalledWith(`[AuthDebug] Loading MAIL_API_KEYS. Raw (Masked): ${expectedMasked}`);
    });

    it('should handle invalid format during masking gracefully', () => {
      process.env.MAIL_API_KEYS = 'invalid';
      parseKeys();
      expect(console.log).toHaveBeenCalledWith(`[AuthDebug] Loading MAIL_API_KEYS. Raw (Masked): Invalid format/Too short`);
    });

    it('should cache parsed keys to prevent multiple parse operations', () => {
      process.env.MAIL_API_KEYS = JSON.stringify({ key: 'val' });
      const parseSpy = jest.spyOn(JSON, 'parse');

      // First call should parse
      const keys1 = parseKeys();

      // Second call should return cached
      const keys2 = parseKeys();

      expect(keys1).toEqual(keys2);
      expect(keys1).toBe(keys2); // Same object reference
      // parseKeys masks then parses, so JSON.parse is called twice per env var change
      expect(parseSpy).toHaveBeenCalledTimes(2);

      parseSpy.mockRestore();
    });

    it('should invalidate cache when MAIL_API_KEYS changes', () => {
      process.env.MAIL_API_KEYS = JSON.stringify({ key1: 'val1' });
      const keys1 = parseKeys();
      expect(keys1).toEqual({ key1: 'val1' });

      process.env.MAIL_API_KEYS = JSON.stringify({ key2: 'val2' });
      const keys2 = parseKeys();
      expect(keys2).toEqual({ key2: 'val2' });
    });
  });

  describe('requireAdmin middleware', () => {
    it('should authenticate when request source is an admin source', () => {
      req.source = 'cho-fam-admin';
      requireAdmin(req, res, next);
      expect(next).toHaveBeenCalled();
      expect(res.status).not.toHaveBeenCalled();
    });

    it('should reject when request source is not an admin source', () => {
      req.source = 'service-a';
      requireAdmin(req, res, next);
      expect(next).not.toHaveBeenCalled();
      expect(res.status).toHaveBeenCalledWith(403);
      expect(res.json).toHaveBeenCalledWith({ ok: false, error: 'forbidden' });
    });

    it('should reject when request source is undefined', () => {
      requireAdmin(req, res, next);
      expect(next).not.toHaveBeenCalled();
      expect(res.status).toHaveBeenCalledWith(403);
      expect(res.json).toHaveBeenCalledWith({ ok: false, error: 'forbidden' });
    });

    it('should use custom admin sources if MAIL_ADMIN_SOURCES env is set', () => {
      process.env.MAIL_ADMIN_SOURCES = 'custom-admin1,custom-admin2';
      req.source = 'custom-admin2';
      requireAdmin(req, res, next);
      expect(next).toHaveBeenCalled();
      expect(res.status).not.toHaveBeenCalled();
    });
  });
});
