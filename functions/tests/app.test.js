const request = require('supertest');
const app = require('../src/app');

describe('App Initialization', () => {
  it('should return ok for /health', async () => {
    const res = await request(app).get('/health');
    expect(res.statusCode).toEqual(200);
    expect(res.body).toEqual({ ok: true });
  });

  it('should return ok for /api/health', async () => {
    const res = await request(app).get('/api/health');
    expect(res.statusCode).toEqual(200);
    expect(res.body).toEqual({ ok: true });
  });
});
