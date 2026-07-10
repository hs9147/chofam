const request = require('supertest');
const app = require('../app');
const mailService = require('../services/mailService');

jest.mock('../services/mailService', () => ({
  dispatch: jest.fn(),
  resend: jest.fn(),
}));

jest.mock('../services/firestore', () => ({
  mailLogs: {
    orderBy: jest.fn().mockReturnThis(),
    where: jest.fn().mockReturnThis(),
    limit: jest.fn().mockReturnThis(),
    get: jest.fn().mockResolvedValue({ docs: [] }),
    doc: jest.fn(),
  },
  mailTemplates: {
    orderBy: jest.fn().mockReturnThis(),
    get: jest.fn().mockResolvedValue({ docs: [] }),
    doc: jest.fn(),
  }
}));

describe('Mail Routes', () => {
  const originalEnv = process.env;

  beforeEach(() => {
    jest.resetModules();
    process.env = { ...originalEnv };
    process.env.MAIL_API_KEYS = JSON.stringify({ 'test-api-key': 'test-source' });
    jest.clearAllMocks();
  });

  afterEach(() => {
    process.env = originalEnv;
    jest.restoreAllMocks();
  });

  describe('POST /mail/send', () => {
    it('should return 400 error when to parameter is missing', async () => {
      const response = await request(app)
        .post('/mail/send')
        .set('x-api-key', 'test-api-key')
        .send({
          templateKey: 'test-template'
        });

      expect(response.status).toBe(400);
      expect(response.body).toEqual({
        ok: false,
        error: 'to_required'
      });
      expect(mailService.dispatch).not.toHaveBeenCalled();
    });

    it('should return 400 error when to parameter is an invalid email format', async () => {
      const response = await request(app)
        .post('/mail/send')
        .set('x-api-key', 'test-api-key')
        .send({
          to: 'invalid-email',
          templateKey: 'test-template'
        });

      expect(response.status).toBe(400);
      expect(response.body).toEqual({
        ok: false,
        error: 'invalid_email_format'
      });
      expect(mailService.dispatch).not.toHaveBeenCalled();
    });

    it('should return 400 error when templateKey parameter is missing', async () => {
      const response = await request(app)
        .post('/mail/send')
        .set('x-api-key', 'test-api-key')
        .send({
          to: 'test@example.com'
        });

      expect(response.status).toBe(400);
      expect(response.body).toEqual({
        ok: false,
        error: 'templateKey_required'
      });
      expect(mailService.dispatch).not.toHaveBeenCalled();
    });

    it('should return 400 error when body is completely empty', async () => {
      const response = await request(app)
        .post('/mail/send')
        .set('x-api-key', 'test-api-key')
        .send();

      expect(response.status).toBe(400);
      expect(response.body).toEqual({
        ok: false,
        error: 'to_required'
      });
      expect(mailService.dispatch).not.toHaveBeenCalled();
    });

    it('should dispatch email and return 200 when all required parameters are provided', async () => {
      mailService.dispatch.mockResolvedValue({ messageId: '123' });

      const response = await request(app)
        .post('/mail/send')
        .set('x-api-key', 'test-api-key')
        .send({
          to: 'test@example.com',
          templateKey: 'test-template',
          location: 'Test Location',
          dynamicData: { foo: 'bar' }
        });

      expect(response.status).toBe(200);
      expect(response.body).toEqual({
        ok: true,
        messageId: '123'
      });
      expect(mailService.dispatch).toHaveBeenCalledWith({
        to: 'test@example.com',
        templateKey: 'test-template',
        location: 'Test Location',
        dynamicData: { foo: 'bar' },
        source: 'test-source'
      });
    });
  });
});
