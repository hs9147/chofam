const sgMail = require('@sendgrid/mail');
const { mailLogs, mailTemplates } = require('./firestore');

const FROM_ADDRESS = process.env.MAIL_FROM_ADDRESS || 'hichofam@gmail.com';

const templateCache = new Map();
const CACHE_TTL = 5 * 60 * 1000; // 5 minutes

async function getTemplate(templateKey) {
  const now = Date.now();
  const cached = templateCache.get(templateKey);
  if (cached && (now - cached.timestamp < CACHE_TTL)) {
    return cached.promise;
  }
  const promise = (async () => {
    const doc = await mailTemplates.doc(templateKey).get();
    if (!doc.exists) {
      return null;
    }
    return doc.data();
  })();

  templateCache.set(templateKey, { promise, timestamp: now });

  // Remove failed promise from cache to allow future retries
  promise.catch(() => {
    if (templateCache.get(templateKey)?.promise === promise) {
      templateCache.delete(templateKey);
    }
  });

  return promise;
}

function invalidateTemplateCache(templateKey) {
  templateCache.delete(templateKey);
}

let initialized = false;
function ensureInitialized() {
  if (!initialized) {
    sgMail.setApiKey(process.env.SENDGRID_API_KEY);
    initialized = true;
  }
}

function renderTemplate(text, data) {
  if (!text) return '';
  return text.replace(/\{\{\s*(\w+)\s*\}\}/g, (match, key) => {
    return data[key] !== undefined ? data[key] : match;
  });
}

async function dispatch({ to, templateKey, location = 'ko', dynamicData = {}, source }) {
  ensureInitialized();

  console.log(`Sending email to ${to} (templateKey: ${templateKey}, location: ${location})`);

  // Prefetch template (using cache)
  const templateData = await getTemplate(templateKey);

  try {
    let mailOptions = {
      to,
      from: FROM_ADDRESS,
    };

    if (!templateData) {
      throw new Error(`mail_template_not_found: ${templateKey}`);
    }

    const localeTemplates = templateData.templates || {};
    const template = localeTemplates[location] || localeTemplates['ko'] || Object.values(localeTemplates)[0];
    if (!template) {
      throw new Error(`no_available_template_locale: ${templateKey}`);
    }

    const subject = renderTemplate(template.title, dynamicData);
    const html = renderTemplate(template.body, dynamicData);

    mailOptions.subject = subject;
    mailOptions.html = html;

    await sgMail.send(mailOptions);
    const logRef = await mailLogs.add({
      to,
      templateKey,
      location,
      dynamicData,
      source,
      status: 'sent',
      createdAt: new Date(),
      sentAt: new Date(),
    });
    return { id: logRef.id, status: 'sent' };
  } catch (err) {
    const errorMessage = err.response?.body?.errors?.[0]?.message || err.message;
    console.error(`Failed to send email to ${to}: ${errorMessage}`);
    const messageWithSender = `${errorMessage} (sender: ${FROM_ADDRESS})`;
    const logRef = await mailLogs.add({
      to,
      templateKey,
      location,
      dynamicData,
      source,
      status: 'failed',
      error: messageWithSender,
      createdAt: new Date(),
      failedAt: new Date(),
    });
    const error = new Error(messageWithSender);
    error.status = 502;
    throw error;
  }
}

async function resend(logId) {
  const doc = await mailLogs.doc(logId).get();
  if (!doc.exists) {
    const error = new Error('mail_log_not_found');
    error.status = 404;
    throw error;
  }
  const { to, templateKey, location, dynamicData, source } = doc.data();
  return dispatch({ to, templateKey, location, dynamicData, source });
}

module.exports = { dispatch, resend, renderTemplate, invalidateTemplateCache };
