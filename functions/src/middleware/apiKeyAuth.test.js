const { requireAdmin } = require('./apiKeyAuth');

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

    // Suppress console.warn during tests
    jest.spyOn(console, 'warn').mockImplementation(() => {});
  });

  afterEach(() => {
    process.env = originalEnv;
    jest.restoreAllMocks();
  });

  it('should call next() when req.source is the default admin source (CHO-FAM-admin)', () => {
    delete process.env.MAIL_ADMIN_SOURCES;
    req.source = 'CHO-FAM-admin';

    requireAdmin(req, res, next);

    expect(next).toHaveBeenCalledTimes(1);
    expect(res.status).not.toHaveBeenCalled();
    expect(res.json).not.toHaveBeenCalled();
  });

  it('should call next() when req.source matches a custom admin source (CHO-FAM-admin)', () => {
    process.env.MAIL_ADMIN_SOURCES = 'CHO-FAM-admin';
    req.source = 'CHO-FAM-admin';

    requireAdmin(req, res, next);

    expect(next).toHaveBeenCalledTimes(1);
    expect(res.status).not.toHaveBeenCalled();
    expect(res.json).not.toHaveBeenCalled();
  });

  it('should call next() when req.source matches one of multiple admin sources', () => {
    process.env.MAIL_ADMIN_SOURCES = 'admin1,admin2';
    req.source = 'admin2';

    requireAdmin(req, res, next);

    expect(next).toHaveBeenCalledTimes(1);
    expect(res.status).not.toHaveBeenCalled();
    expect(res.json).not.toHaveBeenCalled();
  });

  it('should return 403 Forbidden when req.source does not match the admin source', () => {
    process.env.MAIL_ADMIN_SOURCES = 'CHO-FAM-admin';
    req.source = 'some-other-source';

    requireAdmin(req, res, next);

    expect(next).not.toHaveBeenCalled();
    expect(res.status).toHaveBeenCalledWith(403);
    expect(res.json).toHaveBeenCalledWith({ ok: false, error: 'forbidden' });
  });

  it('should return 403 Forbidden when req.source is undefined', () => {
    process.env.MAIL_ADMIN_SOURCES = 'CHO-FAM-admin';
    req.source = undefined;

    requireAdmin(req, res, next);

    expect(next).not.toHaveBeenCalled();
    expect(res.status).toHaveBeenCalledWith(403);
    expect(res.json).toHaveBeenCalledWith({ ok: false, error: 'forbidden' });
  });
});
