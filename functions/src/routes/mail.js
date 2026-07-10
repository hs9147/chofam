const express = require('express');
const { requireApiKey, requireAdmin } = require('../middleware/apiKeyAuth');
const mailService = require('../services/mailService');
const { mailLogs, mailTemplates } = require('../services/firestore');

const router = express.Router();

router.use(requireApiKey);

// POST /mail/send  { to, templateId, templateKey, location, dynamicData }
router.post('/send', async (req, res, next) => {
  try {
    const { to, templateId, templateKey, location, dynamicData } = req.body || {};
    if (!to) {
      return res.status(400).json({ ok: false, error: 'to_required' });
    }
    if (!templateId && !templateKey) {
      return res.status(400).json({ ok: false, error: 'templateId_or_templateKey_required' });
    }
    const result = await mailService.dispatch({
      to,
      templateId,
      templateKey,
      location,
      dynamicData,
      source: req.source
    });
    res.json({ ok: true, ...result });
  } catch (err) {
    next(err);
  }
});

// GET /mail/logs?source=liv-ay&status=failed&limit=50
router.get('/logs', requireAdmin, async (req, res, next) => {
  try {
    const { source, status, limit } = req.query;
    let query = mailLogs.orderBy('createdAt', 'desc');
    if (source) query = query.where('source', '==', source);
    if (status) query = query.where('status', '==', status);
    query = query.limit(Math.min(Number(limit) || 50, 200));

    const snapshot = await query.get();
    const logs = snapshot.docs.map((doc) => ({ id: doc.id, ...doc.data() }));
    res.json({ ok: true, logs });
  } catch (err) {
    next(err);
  }
});

// POST /mail/logs/:id/resend
router.post('/logs/:id/resend', requireAdmin, async (req, res, next) => {
  try {
    const result = await mailService.resend(req.params.id);
    res.json({ ok: true, ...result });
  } catch (err) {
    next(err);
  }
});

// ── mail templates CRUD ────────────────────────────────────────────

// GET /mail/templates
router.get('/templates', requireAdmin, async (req, res, next) => {
  try {
    const snapshot = await mailTemplates.orderBy('createdAt', 'desc').get();
    const templates = snapshot.docs.map((doc) => ({ id: doc.id, ...doc.data() }));
    res.json({ ok: true, templates });
  } catch (err) {
    next(err);
  }
});

// GET /mail/templates/:key
router.get('/templates/:key', requireAdmin, async (req, res, next) => {
  try {
    const doc = await mailTemplates.doc(req.params.key).get();
    if (!doc.exists) {
      return res.status(404).json({ ok: false, error: 'template_not_found' });
    }
    res.json({ ok: true, template: { id: doc.id, ...doc.data() } });
  } catch (err) {
    next(err);
  }
});

// POST /mail/templates
router.post('/templates', requireAdmin, async (req, res, next) => {
  try {
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
  } catch (err) {
    next(err);
  }
});

// DELETE /mail/templates/:key
router.delete('/templates/:key', requireAdmin, async (req, res, next) => {
  try {
    const docRef = mailTemplates.doc(req.params.key);
    const doc = await docRef.get();
    if (!doc.exists) {
      return res.status(404).json({ ok: false, error: 'template_not_found' });
    }
    await docRef.delete();
    res.json({ ok: true, key: req.params.key });
  } catch (err) {
    next(err);
  }
});

module.exports = router;
