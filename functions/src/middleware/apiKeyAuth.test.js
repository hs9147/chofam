describe('apiKeyAuth middleware', () => {
  let req;
  let res;
  let next;
  let requireApiKey;
  let requireAdmin;
  const originalEnv = process.env;

  beforeEach(() => {
    jest.resetModules();
    process.env = { ...originalEnv };

    // We must re-require the module inside beforeEach to reset its module-level cache
    const authModule = require('./apiKeyAuth');
    requireApiKey = authModule.requireApiKey;
    requireAdmin = authModule.requireAdmin;

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

  it('should reject when API key header is empty string', () => {
    process.env.MAIL_API_KEYS = JSON.stringify({ 'valid-key-123': 'service-a' });
    req.header.mockReturnValue('');

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
