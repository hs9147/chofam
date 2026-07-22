const express = require('express');
const { requireApiKey } = require('../middleware/apiKeyAuth');
const billingService = require('../services/billingService');
const { billingLogs } = require('../services/firestore');
const asyncHandler = require('../middleware/asyncHandler');

const router = express.Router();

router.use(requireApiKey);

// 결제 승인(청구) API 사용을 허용할 소스 목록 (PAYOUT_SOURCES 패턴)
function getBillingSources() {
  return (process.env.BILLING_SOURCES || 'mentor').split(',');
}

router.use((req, res, next) => {
  if (!getBillingSources().includes(req.source)) {
    console.warn(`[BillingAuth] Forbidden source: '${req.source}'`);
    return res.status(403).json({ ok: false, error: 'forbidden' });
  }
  if (!billingService.isConfigured()) {
    return res.status(503).json({ ok: false, error: 'billing_not_configured' });
  }
  next();
});

// POST /billing/confirm  { paymentKey, orderId, amount }
router.post('/confirm', asyncHandler(async (req, res) => {
  const { paymentKey, orderId, amount } = req.body || {};
  if (!paymentKey || !orderId) {
    return res.status(400).json({ ok: false, error: 'payment_fields_required' });
  }
  if (!Number.isInteger(amount) || amount <= 0) {
    return res.status(400).json({ ok: false, error: 'invalid_amount' });
  }

  const result = await billingService.confirmPayment({ paymentKey, orderId, amount });

  await billingLogs.add({
    type: 'payment_confirmed',
    source: req.source,
    paymentKey: result.paymentKey,
    orderId: result.orderId,
    amount,
    status: result.status,
    createdAt: new Date(),
  });
  res.json({ ok: true, ...result });
}));

module.exports = router;
