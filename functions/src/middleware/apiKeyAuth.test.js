const { requireAdmin, requireApiKey } = require('./apiKeyAuth');

describe('apiKeyAuth middleware', () => {
  let req;
  let res;
  let next;
  let requireApiKeyFn;
  let requireAdminFn;
  const originalEnv = process.env;

  beforeEach(() => {
    jest.resetModules();
    process.env = { ...originalEnv };
    const auth = require('./apiKeyAuth');
    requireApiKeyFn = auth.requireApiKey;
    requireAdminFn = auth.requireAdmin;

    req = {
      header: jest.fn(),
      source: undefined
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
    delete process.env.MAIL_ADMIN_SOURCES;
    jest.restoreAllMocks();
  });

  describe('requireApiKey', () => {
    it('should authenticate with a valid API key and set req.source', () => {
      process.env.MAIL_API_KEYS = JSON.stringify({ 'valid-key-123': 'service-a' });
      req.header.mockReturnValue('valid-key-123');

      requireApiKeyFn(req, res, next);

      expect(req.header).toHaveBeenCalledWith('x-api-key');
      expect(req.source).toBe('service-a');
      expect(next).toHaveBeenCalled();
      expect(res.status).not.toHaveBeenCalled();
    });

    it('should reject when MAIL_API_KEYS env is missing', () => {
      req.header.mockReturnValue('valid-key-123');

      requireApiKeyFn(req, res, next);

      expect(next).not.toHaveBeenCalled();
      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith({ ok: false, error: 'invalid_api_key' });
    });

    it('should reject when MAIL_API_KEYS is invalid JSON', () => {
      process.env.MAIL_API_KEYS = 'invalid-json';
      req.header.mockReturnValue('valid-key-123');

      requireApiKeyFn(req, res, next);

      expect(next).not.toHaveBeenCalled();
      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith({ ok: false, error: 'invalid_api_key' });
    });

    it('should reject when API key is missing from request header', () => {
      process.env.MAIL_API_KEYS = JSON.stringify({ 'valid-key-123': 'service-a' });
      req.header.mockReturnValue(undefined);

      requireApiKeyFn(req, res, next);

      expect(next).not.toHaveBeenCalled();
      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith({ ok: false, error: 'invalid_api_key' });
    });

    it('should reject when API key is an empty string', () => {
      process.env.MAIL_API_KEYS = JSON.stringify({ 'valid-key-123': 'service-a' });
      req.header.mockReturnValue('');

      requireApiKeyFn(req, res, next);

      expect(next).not.toHaveBeenCalled();
      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith({ ok: false, error: 'invalid_api_key' });
    });

    it('should reject when API key is only whitespace', () => {
      process.env.MAIL_API_KEYS = JSON.stringify({ 'valid-key-123': 'service-a' });
      req.header.mockReturnValue('   ');

      requireApiKeyFn(req, res, next);

      expect(next).not.toHaveBeenCalled();
      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith({ ok: false, error: 'invalid_api_key' });
    });

    it('should reject when API key is invalid', () => {
      process.env.MAIL_API_KEYS = JSON.stringify({ 'valid-key-123': 'service-a' });
      req.header.mockReturnValue('invalid-key-456');

      requireApiKeyFn(req, res, next);

      expect(next).not.toHaveBeenCalled();
      expect(res.status).toHaveBeenCalledWith(401);
      expect(res.json).toHaveBeenCalledWith({ ok: false, error: 'invalid_api_key' });
    });
  });

  describe('requireAdmin', () => {
    it('should authenticate when req.source is a valid admin source', () => {
      process.env.MAIL_ADMIN_SOURCES = 'cho-fam-admin,other-admin';
      req.source = 'cho-fam-admin';

      requireAdminFn(req, res, next);

      expect(next).toHaveBeenCalled();
      expect(res.status).not.toHaveBeenCalled();
    });

    it('should reject when req.source is not an admin source', () => {
      process.env.MAIL_ADMIN_SOURCES = 'cho-fam-admin,other-admin';
      req.source = 'regular-service';

      requireAdminFn(req, res, next);

      expect(next).not.toHaveBeenCalled();
      expect(res.status).toHaveBeenCalledWith(403);
      expect(res.json).toHaveBeenCalledWith({ ok: false, error: 'forbidden' });
    });

    it('should reject when req.source is undefined', () => {
      process.env.MAIL_ADMIN_SOURCES = 'cho-fam-admin';
      req.source = undefined;

      requireAdminFn(req, res, next);

      expect(next).not.toHaveBeenCalled();
      expect(res.status).toHaveBeenCalledWith(403);
      expect(res.json).toHaveBeenCalledWith({ ok: false, error: 'forbidden' });
    });

    it('should use default admin source if MAIL_ADMIN_SOURCES is not defined', () => {
      delete process.env.MAIL_ADMIN_SOURCES;
      req.source = 'cho-fam-admin';

      requireAdminFn(req, res, next);

      expect(next).toHaveBeenCalled();
      expect(res.status).not.toHaveBeenCalled();
    });
  });
});
