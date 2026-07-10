const { requireApiKey, requireAdmin } = require('./apiKeyAuth');

describe('requireApiKey middleware', () => {
  let req;
  let res;
  let next;
  const originalEnv = process.env;

  beforeEach(() => {
    jest.resetModules();
    process.env = { ...originalEnv };
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

describe('requireAdmin middleware', () => {
  let req;
  let res;
  let next;
  const originalEnv = process.env;

  beforeEach(() => {
    jest.resetModules();
    process.env = { ...originalEnv };
    req = {};
    res = {
      status: jest.fn().mockReturnThis(),
      json: jest.fn(),
    };
    next = jest.fn();

    jest.clearAllMocks();

    jest.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    delete process.env.MAIL_ADMIN_SOURCES;
    jest.restoreAllMocks();
  });

  it('should allow access if req.source is in default admin sources', () => {
    req.source = 'cho-fam-admin';
    requireAdmin(req, res, next);
    expect(next).toHaveBeenCalled();
    expect(res.status).not.toHaveBeenCalled();
  });

  it('should allow access if req.source is in configured admin sources', () => {
    process.env.MAIL_ADMIN_SOURCES = 'custom-admin,another-admin';
    req.source = 'custom-admin';
    requireAdmin(req, res, next);
    expect(next).toHaveBeenCalled();
    expect(res.status).not.toHaveBeenCalled();
  });

  it('should reject access if req.source is not in admin sources', () => {
    req.source = 'regular-user';
    requireAdmin(req, res, next);
    expect(res.status).toHaveBeenCalledWith(403);
    expect(res.json).toHaveBeenCalledWith({ ok: false, error: 'forbidden' });
    expect(next).not.toHaveBeenCalled();
  });

  it('should update cached admin sources if environment variable changes', () => {
    // Initial call
    process.env.MAIL_ADMIN_SOURCES = 'admin-1';
    req.source = 'admin-1';
    requireAdmin(req, res, next);
    expect(next).toHaveBeenCalledTimes(1);

    // Change env var
    process.env.MAIL_ADMIN_SOURCES = 'admin-2';
    req.source = 'admin-2';
    requireAdmin(req, res, next);
    expect(next).toHaveBeenCalledTimes(2);

    // Old source should now be rejected
    req.source = 'admin-1';
    requireAdmin(req, res, next);
    expect(res.status).toHaveBeenCalledWith(403);
  });
});
