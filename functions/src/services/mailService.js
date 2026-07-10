const sgMail = require('@sendgrid/mail');
const { mailLogs, mailTemplates } = require('./firestore');

const FROM_ADDRESS = process.env.MAIL_FROM_ADDRESS || 'noreply@CHO-FAM.web.app';

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

async function dispatch({ to, templateId, templateKey, location = 'ko', dynamicData, source }) {
  ensureInitialized();

  console.log(`Sending email to ${to} (templateId: ${templateId}, templateKey: ${templateKey}, location: ${location})`);

  const logRef = await mailLogs.add({
    to,
    templateId: templateId || null,
    templateKey: templateKey || null,
    location: location || null,
    dynamicData: dynamicData || {},
    source,
    status: 'pending',
    createdAt: new Date(),
  });

  try {
    let mailOptions = {
      to,
      from: FROM_ADDRESS,
    };

    if (templateKey) {
      const doc = await mailTemplates.doc(templateKey).get();
      if (!doc.exists) {
        throw new Error(`mail_template_not_found: ${templateKey}`);
      }

      const data = doc.data();
      const localeTemplates = data.templates || {};
      const template = localeTemplates[location] || localeTemplates['ko'] || Object.values(localeTemplates)[0];
      if (!template) {
        throw new Error(`no_available_template_locale: ${templateKey}`);
      }

      const subject = renderTemplate(template.title, dynamicData || {});
      const html = renderTemplate(template.body, dynamicData || {});

      mailOptions.subject = subject;
      mailOptions.html = html;
    } else if (templateId) {
      mailOptions.templateId = templateId;
      mailOptions.dynamicTemplateData = dynamicData || {};
    } else {
      throw new Error('templateId_or_templateKey_required');
    }

    await sgMail.send(mailOptions);
    await logRef.update({ status: 'sent', sentAt: new Date() });
    return { id: logRef.id, status: 'sent' };
  } catch (err) {
    const errorMessage = err.response?.body?.errors?.[0]?.message || err.message;
    console.error(`Failed to send email to ${to}: ${errorMessage}`);
    const messageWithSender = `${errorMessage} (sender: ${FROM_ADDRESS})`;
    await logRef.update({ status: 'failed', error: messageWithSender, failedAt: new Date() });
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
  const { to, templateId, templateKey, location, dynamicData, source } = doc.data();
  return dispatch({ to, templateId, templateKey, location, dynamicData, source });
}

module.exports = { dispatch, resend };
