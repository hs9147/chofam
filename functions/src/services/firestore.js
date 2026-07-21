const admin = require('firebase-admin');

if (!admin.apps.length) {
  admin.initializeApp();
}

const db = admin.firestore();
const mailLogs = db.collection('mail_logs');
const mailTemplates = db.collection('mail_templates');
const payoutLogs = db.collection('payout_logs');
const billingLogs = db.collection('billing_logs');

module.exports = { db, mailLogs, mailTemplates, payoutLogs, billingLogs };
