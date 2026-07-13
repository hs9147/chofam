const request = require('supertest');

jest.mock('../services/firestore', () => ({
  payoutLogs: { add: jest.fn().mockResolvedValue({}) },
  mailLogs: {},
  mailTemplates: {},
  db: {},
}));
jest.mock('../services/mailService', () => ({}));

describe('payout routes', () => {
  const API_KEY = 'test-payout-key-12345';

  let app;
  beforeEach(() => {
    jest.resetModules();
    process.env.MAIL_API_KEYS = JSON.stringify({ [API_KEY]: 'liv-ay', 'other-key-000000': 'other' });
    delete process.env.PAYOUT_SOURCES;
    process.env.TOSS_SECRET_KEY = 'test_sk';
    process.env.TOSS_SECURITY_KEY = require('crypto').randomBytes(32).toString('base64');
    require('../middleware/apiKeyAuth').resetCache();
    app = require('../app');
  });

  afterEach(() => {
    delete process.env.TOSS_SECRET_KEY;
    delete process.env.TOSS_SECURITY_KEY;
  });

  it('API 키 없으면 401', async () => {
    const res = await request(app).post('/payout/request').send({});
    expect(res.status).toBe(401);
  });

  it('허용되지 않은 소스는 403', async () => {
    const res = await request(app)
      .post('/payout/request')
      .set('x-api-key', 'other-key-000000')
      .send({ refPayoutId: 'p', sellerId: 's', amount: 10000 });
    expect(res.status).toBe(403);
  });

  it('토스 키 미설정이면 503 payout_not_configured', async () => {
    delete process.env.TOSS_SECRET_KEY;
    const res = await request(app)
      .post('/payout/request')
      .set('x-api-key', API_KEY)
      .send({ refPayoutId: 'p', sellerId: 's', amount: 10000 });
    expect(res.status).toBe(503);
    expect(res.body.error).toBe('payout_not_configured');
  });

  it('amount가 양의 정수가 아니면 400', async () => {
    const res = await request(app)
      .post('/payout/request')
      .set('x-api-key', API_KEY)
      .send({ refPayoutId: 'p', sellerId: 's', amount: -5 });
    expect(res.status).toBe(400);
    expect(res.body.error).toBe('invalid_amount');
  });

  it('셀러 등록 필수 필드 누락이면 400', async () => {
    const res = await request(app)
      .post('/payout/sellers')
      .set('x-api-key', API_KEY)
      .send({ refSellerId: 'u1' });
    expect(res.status).toBe(400);
    expect(res.body.error).toBe('seller_fields_required');
  });
});
