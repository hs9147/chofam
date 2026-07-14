// 발송 파이프: nodemailer + SMTP 릴레이 (provider 중립 — SMTP_* 시크릿만 갈아끼우면
// SES/SMTP2GO/Brevo 등 어떤 릴레이든 사용 가능). 템플릿·로그·인증은 자체 구현 그대로.
const nodemailer = require('nodemailer');
const { mailLogs, mailTemplates } = require('./firestore');

const FROM_ADDRESS = process.env.MAIL_FROM_ADDRESS || 'contact@cho-fam.com';

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

let transporter = null;
function getTransporter() {
  if (!transporter) {
    const port = Number(process.env.SMTP_PORT || 587);
    transporter = nodemailer.createTransport({
      host: process.env.SMTP_HOST,
      port,
      secure: port === 465, // 465=implicit TLS, 587=STARTTLS
      auth: { user: process.env.SMTP_USER, pass: process.env.SMTP_PASS },
    });
  }
  return transporter;
}

function renderTemplate(text, data) {
  if (!text) return '';
  return text.replace(/\{\{\s*(\w+)\s*\}\}/g, (match, key) => {
    return data[key] !== undefined ? data[key] : match;
  });
}

async function dispatch({ to, templateKey, location = 'ko', dynamicData = {}, source }) {
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

    await getTransporter().sendMail(mailOptions);
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
    // nodemailer SMTP 오류는 message에 서버 응답이 담긴다 (SendGrid SDK의 중첩 구조와 다름)
    const errorMessage = err.message;
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
