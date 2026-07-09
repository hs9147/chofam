const sgMail = require('@sendgrid/mail');
const { mailLogs } = require('./firestore');

const FROM_ADDRESS = process.env.MAIL_FROM_ADDRESS || 'hichofam@gmail.com';

let initialized = false;
function ensureInitialized() {
  if (!initialized) {
    sgMail.setApiKey(process.env.SENDGRID_API_KEY);
    initialized = true;
  }
}

async function dispatch({ to, templateId, dynamicData, source }) {
  ensureInitialized();

  console.log(`Sending email to ${to} (template: ${templateId}, code: ${dynamicData?.code})`);

  const logRef = await mailLogs.add({
    to,
    templateId,
    dynamicData: dynamicData || {},
    source,
    status: 'pending',
    createdAt: new Date(),
  });

  try {
    await sgMail.send({
      to,
      from: FROM_ADDRESS,
      templateId,
      dynamicTemplateData: dynamicData || {},
    });
    await logRef.update({ status: 'sent', sentAt: new Date() });
    return { id: logRef.id, status: 'sent' };
  } catch (err) {
    const errorMessage = err.response?.body?.errors?.[0]?.message || err.message;
    console.error(`Failed to send email from ${FROM_ADDRESS} to ${to} (code: ${dynamicData?.code}): ${errorMessage}`);
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
  const { to, templateId, dynamicData, source } = doc.data();
  return dispatch({ to, templateId, dynamicData, source });
}

module.exports = { dispatch, resend };
