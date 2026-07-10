const { resend } = require('./mailService');
const { mailLogs } = require('./firestore');
const sgMail = require('@sendgrid/mail');

jest.mock('./firestore', () => ({
  mailLogs: {
    doc: jest.fn(),
    add: jest.fn(),
  },
  mailTemplates: {
    doc: jest.fn(),
  }
}));

jest.mock('@sendgrid/mail', () => ({
  setApiKey: jest.fn(),
  send: jest.fn(),
}));

describe('mailService', () => {
  describe('resend', () => {
    it('should throw 404 error if mail log does not exist', async () => {
      mailLogs.doc.mockReturnValue({
        get: jest.fn().mockResolvedValue({ exists: false })
      });

      await expect(resend('invalid-log-id')).rejects.toMatchObject({
        message: 'mail_log_not_found',
        status: 404
      });
    });
  });
});
