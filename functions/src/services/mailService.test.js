const { dispatch, resend } = require('./mailService');
const { mailLogs, mailTemplates } = require('./firestore');
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
  afterEach(() => {
    jest.clearAllMocks();
  });

  describe('dispatch', () => {
    it('should handle SendGrid errors correctly and update log status to failed', async () => {
      const mockLogRef = {
        id: 'mock-log-id',
        update: jest.fn().mockResolvedValue(),
      };
      mailLogs.add.mockResolvedValue(mockLogRef);

      mailTemplates.doc.mockReturnValue({
        get: jest.fn().mockResolvedValue({
          exists: true,
          data: () => ({
            templates: {
              ko: { title: 'Test Subject', body: 'Test Body' }
            }
          })
        })
      });

      const sgError = new Error('SendGrid rejection');
      sgError.response = {
        body: {
          errors: [{ message: 'Bad Request' }]
        }
      };
      sgMail.send.mockRejectedValue(sgError);

      const dispatchParams = {
        to: 'test@example.com',
        templateKey: 'test-template',
        location: 'ko',
        dynamicData: {},
        source: 'test-source'
      };

      await expect(dispatch(dispatchParams)).rejects.toMatchObject({
        message: expect.stringContaining('Bad Request'),
        status: 502
      });

      expect(mockLogRef.update).toHaveBeenCalledWith({
        status: 'failed',
        error: expect.stringContaining('Bad Request (sender:'),
        failedAt: expect.any(Date)
      });
    });
  });

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
