const express = require('express');
const { requireApiKey, requireAdmin } = require('../middleware/apiKeyAuth');
const mailService = require('../services/mailService');
const { mailLogs, mailTemplates } = require('../services/firestore');
const asyncHandler = require('../middleware/asyncHandler');

const router = express.Router();

router.use(requireApiKey);

// Regular expression for basic email validation
const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

// POST /mail/send  { to, templateKey, location, dynamicData }
router.post('/send', asyncHandler(async (req, res, next) => {
  const { to, templateKey, location, dynamicData } = req.body || {};
  if (!to) {
    return res.status(400).json({ ok: false, error: 'to_required' });
  }
  if (!emailRegex.test(to)) {
    return res.status(400).json({ ok: false, error: 'invalid_email_format' });
  }
  if (!templateKey) {
    return res.status(400).json({ ok: false, error: 'templateKey_required' });
  }
  const result = await mailService.dispatch({
    to,
    templateKey,
    location,
    dynamicData,
    source: req.source
  });
  res.json({ ok: true, ...result });
}));

// GET /mail/logs?source=liv-ay&status=failed&limit=50
router.get('/logs', requireAdmin, asyncHandler(async (req, res, next) => {
  const { source, status, limit } = req.query;
  let query = mailLogs.orderBy('createdAt', 'desc');
  if (source) query = query.where('source', '==', source);
  if (status) query = query.where('status', '==', status);
  query = query.limit(Math.min(Number(limit) || 50, 200));

  const snapshot = await query.get();
  const logs = snapshot.docs.map((doc) => ({ id: doc.id, ...doc.data() }));
  res.json({ ok: true, logs });
}));

// POST /mail/logs/:id/resend
router.post('/logs/:id/resend', requireAdmin, asyncHandler(async (req, res, next) => {
  const result = await mailService.resend(req.params.id);
  res.json({ ok: true, ...result });
}));

// ── mail templates CRUD ────────────────────────────────────────────

// GET /mail/templates
router.get('/templates', requireAdmin, asyncHandler(async (req, res, next) => {
  const snapshot = await mailTemplates.orderBy('createdAt', 'desc').get();
  const templates = snapshot.docs.map((doc) => ({ id: doc.id, ...doc.data() }));
  res.json({ ok: true, templates });
}));

// GET /mail/templates/:key
router.get('/templates/:key', requireAdmin, asyncHandler(async (req, res, next) => {
  const doc = await mailTemplates.doc(req.params.key).get();
  if (!doc.exists) {
    return res.status(404).json({ ok: false, error: 'template_not_found' });
  }
  res.json({ ok: true, template: { id: doc.id, ...doc.data() } });
}));

// POST /mail/templates
router.post('/templates', requireAdmin, asyncHandler(async (req, res, next) => {
  const { key, description, templates } = req.body || {};
  if (!key || !templates || typeof templates !== 'object') {
    return res.status(400).json({ ok: false, error: 'key_and_templates_required' });
  }

  if (!/^[a-zA-Z0-9_]+$/.test(key)) {
    return res.status(400).json({ ok: false, error: 'invalid_key_format' });
  }

  const docRef = mailTemplates.doc(key);
  const doc = await docRef.get();

  const now = new Date();
  const dataToSave = {
    key,
    description: description || '',
    templates,
    updatedAt: now,
  };

  if (doc.exists) {
    await docRef.update(dataToSave);
  } else {
    dataToSave.createdAt = now;
    await docRef.set(dataToSave);
  }

  res.json({ ok: true, key });
}));

// DELETE /mail/templates/:key
router.delete('/templates/:key', requireAdmin, asyncHandler(async (req, res, next) => {
  const docRef = mailTemplates.doc(req.params.key);
  const doc = await docRef.get();
  if (!doc.exists) {
    return res.status(404).json({ ok: false, error: 'template_not_found' });
  }
  await docRef.delete();
  res.json({ ok: true, key: req.params.key });
}));

module.exports = router;
