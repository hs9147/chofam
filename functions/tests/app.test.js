const request = require('supertest');
const app = require('../src/app');

// Mock out the mail router so we can test app wiring independently
jest.mock('../src/routes/mail', () => {
  const express = require('express');
  const router = express.Router();
  router.get('/', (req, res) => res.json({ mocked: true }));
  // Force an error to test the error handler
  router.get('/error', (req, res, next) => {
    const err = new Error('Test Error');
    err.status = 400;
    next(err);
  });
  // Force an empty error
  router.get('/unhandled-error', (req, res, next) => {
    next(new Error());
  });
  return router;
});

describe('Express App (app.js)', () => {
  describe('Health Check Endpoints', () => {
    it('should return 200 and { ok: true } for /health', async () => {
      const response = await request(app).get('/health');
      expect(response.status).toBe(200);
      expect(response.body).toEqual({ ok: true });
    });

    it('should return 200 and { ok: true } for /api/health', async () => {
      const response = await request(app).get('/api/health');
      expect(response.status).toBe(200);
      expect(response.body).toEqual({ ok: true });
    });
  });

  describe('Mail Routes', () => {
    it('should mount mail routes at /mail', async () => {
      const response = await request(app).get('/mail');
      expect(response.status).toBe(200);
      expect(response.body).toEqual({ mocked: true });
    });

    it('should mount mail routes at /api/mail', async () => {
      const response = await request(app).get('/api/mail');
      expect(response.status).toBe(200);
      expect(response.body).toEqual({ mocked: true });
    });
  });

  describe('Global Error Handler', () => {
    beforeEach(() => {
      jest.spyOn(console, 'error').mockImplementation(() => {});
    });

    afterEach(() => {
      console.error.mockRestore();
    });

    it('should catch errors and return formatted JSON response', async () => {
      const response = await request(app).get('/mail/error');
      expect(response.status).toBe(400);
      expect(response.body).toEqual({ ok: false, error: 'Test Error' });
      expect(console.error).toHaveBeenCalled();
    });

    it('should default to 500 internal_error if status or message is missing', async () => {
      const response = await request(app).get('/mail/unhandled-error');

      expect(response.status).toBe(500);
      expect(response.body).toEqual({ ok: false, error: 'internal_error' });
      expect(console.error).toHaveBeenCalled();
    });
  });

  describe('CORS', () => {
      it('should allow CORS', async () => {
        const response = await request(app).get('/health').set('Origin', 'http://example.com');
        expect(response.headers['access-control-allow-origin']).toBe('http://example.com');
      });
  });
});
