const request = require('supertest');

jest.mock('../services/firestore', () => ({
  billingLogs: { add: jest.fn().mockResolvedValue({}) },
  payoutLogs: {},
  mailLogs: {},
  mailTemplates: {},
  db: {},
}));
jest.mock('../services/mailService', () => ({}));

describe('billing routes', () => {
  const API_KEY = 'test-billing-key-12345';

  let app;
  beforeEach(() => {
    jest.resetModules();
    process.env.MAIL_API_KEYS = JSON.stringify({ [API_KEY]: 'mentor', 'other-key-000000': 'other' });
    delete process.env.BILLING_SOURCES;
    process.env.TOSS_SECRET_KEY = 'test_sk';
    require('../middleware/apiKeyAuth').resetCache();
    app = require('../app');
  });

  afterEach(() => {
    delete process.env.TOSS_SECRET_KEY;
  });

  it('API 키 없으면 401', async () => {
    const res = await request(app).post('/billing/confirm').send({});
    expect(res.status).toBe(401);
  });

  it('허용되지 않은 소스는 403', async () => {
    const res = await request(app)
      .post('/billing/confirm')
      .set('x-api-key', 'other-key-000000')
      .send({ paymentKey: 'pk', orderId: 'o1', amount: 1000 });
    expect(res.status).toBe(403);
  });

  it('토스 키 미설정이면 503 billing_not_configured', async () => {
    delete process.env.TOSS_SECRET_KEY;
    const res = await request(app)
      .post('/billing/confirm')
      .set('x-api-key', API_KEY)
      .send({ paymentKey: 'pk', orderId: 'o1', amount: 1000 });
    expect(res.status).toBe(503);
    expect(res.body.error).toBe('billing_not_configured');
  });

  it('필수 필드 누락이면 400', async () => {
    const res = await request(app)
      .post('/billing/confirm')
      .set('x-api-key', API_KEY)
      .send({ orderId: 'o1', amount: 1000 });
    expect(res.status).toBe(400);
    expect(res.body.error).toBe('payment_fields_required');
  });

  it('amount가 양의 정수가 아니면 400', async () => {
    const res = await request(app)
      .post('/billing/confirm')
      .set('x-api-key', API_KEY)
      .send({ paymentKey: 'pk', orderId: 'o1', amount: -5 });
    expect(res.status).toBe(400);
    expect(res.body.error).toBe('invalid_amount');
  });
});
