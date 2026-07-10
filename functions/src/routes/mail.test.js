const request = require('supertest');
const express = require('express');

// Mock middleware and firestore before importing the router
jest.mock('../middleware/apiKeyAuth', () => ({
  requireApiKey: (req, res, next) => next(),
  requireAdmin: (req, res, next) => next()
}));

const mockSet = jest.fn();
const mockUpdate = jest.fn();
const mockGet = jest.fn();
const mockDelete = jest.fn();

const mockMailTemplates = {
  doc: jest.fn(() => ({
    get: mockGet,
    set: mockSet,
    update: mockUpdate,
    delete: mockDelete,
  })),
  orderBy: jest.fn().mockReturnThis(),
  get: jest.fn()
};

jest.mock('../services/firestore', () => ({
  mailLogs: {
    orderBy: jest.fn().mockReturnThis(),
    where: jest.fn().mockReturnThis(),
    limit: jest.fn().mockReturnThis(),
    get: jest.fn()
  },
  mailTemplates: mockMailTemplates
}));

const mailRouter = require('./mail');

const app = express();
app.use(express.json());
app.use('/mail', mailRouter);

describe('Mail Routes - POST /mail/templates', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('should return 400 if body is empty', async () => {
    const res = await request(app)
      .post('/mail/templates')
      .send({});

    expect(res.status).toBe(400);
    expect(res.body).toEqual({ ok: false, error: 'key_and_templates_required' });
  });

  it('should return 400 if key is missing', async () => {
    const res = await request(app)
      .post('/mail/templates')
      .send({ templates: { subject: 'test' } });

    expect(res.status).toBe(400);
    expect(res.body).toEqual({ ok: false, error: 'key_and_templates_required' });
  });

  it('should return 400 if templates is missing', async () => {
    const res = await request(app)
      .post('/mail/templates')
      .send({ key: 'test_key' });

    expect(res.status).toBe(400);
    expect(res.body).toEqual({ ok: false, error: 'key_and_templates_required' });
  });

  it('should return 400 if templates is not an object', async () => {
    const res = await request(app)
      .post('/mail/templates')
      .send({ key: 'test_key', templates: 'not an object' });

    expect(res.status).toBe(400);
    expect(res.body).toEqual({ ok: false, error: 'key_and_templates_required' });
  });

  it('should return 400 if key has invalid format (symbols)', async () => {
    const res = await request(app)
      .post('/mail/templates')
      .send({ key: 'invalid-key!', templates: { subject: 'test' } });

    expect(res.status).toBe(400);
    expect(res.body).toEqual({ ok: false, error: 'invalid_key_format' });
  });

  it('should return 400 if key has invalid format (spaces)', async () => {
    const res = await request(app)
      .post('/mail/templates')
      .send({ key: 'invalid key', templates: { subject: 'test' } });

    expect(res.status).toBe(400);
    expect(res.body).toEqual({ ok: false, error: 'invalid_key_format' });
  });

  it('should set new document if it does not exist', async () => {
    mockGet.mockResolvedValueOnce({ exists: false });
    mockSet.mockResolvedValueOnce();

    const res = await request(app)
      .post('/mail/templates')
      .send({ key: 'valid_key_123', templates: { subject: 'test' }, description: 'test desc' });

    expect(res.status).toBe(200);
    expect(res.body).toEqual({ ok: true, key: 'valid_key_123' });
    expect(mockSet).toHaveBeenCalledWith(expect.objectContaining({
      key: 'valid_key_123',
      description: 'test desc',
      templates: { subject: 'test' },
      createdAt: expect.any(Date),
      updatedAt: expect.any(Date),
    }));
    expect(mockUpdate).not.toHaveBeenCalled();
  });

  it('should update existing document if it exists', async () => {
    mockGet.mockResolvedValueOnce({ exists: true });
    mockUpdate.mockResolvedValueOnce();

    const res = await request(app)
      .post('/mail/templates')
      .send({ key: 'existing_key', templates: { subject: 'new_test' } }); // no description

    expect(res.status).toBe(200);
    expect(res.body).toEqual({ ok: true, key: 'existing_key' });
    expect(mockUpdate).toHaveBeenCalledWith(expect.objectContaining({
      key: 'existing_key',
      description: '', // defaults to empty string
      templates: { subject: 'new_test' },
      updatedAt: expect.any(Date),
    }));
    expect(mockSet).not.toHaveBeenCalled();
  });

  it('should return 500 if DB operation fails', async () => {
    // Suppress console.error output for expected error log in express app err handler
    const originalConsoleError = console.error;
    console.error = jest.fn();

    mockGet.mockRejectedValueOnce(new Error('DB Error'));

    // We need an error handler in the test app
    const testApp = express();
    testApp.use(express.json());
    testApp.use('/mail', mailRouter);
    testApp.use((err, req, res, next) => {
        res.status(500).json({ ok: false, error: 'internal_error' });
    });

    const res = await request(testApp)
      .post('/mail/templates')
      .send({ key: 'valid_key_123', templates: { subject: 'test' } });

    expect(res.status).toBe(500);
    expect(res.body).toEqual({ ok: false, error: 'internal_error' });

    console.error = originalConsoleError;
  });
});
