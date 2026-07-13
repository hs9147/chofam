const { dispatch, resend, renderTemplate } = require('./mailService');
const { mailLogs, mailTemplates } = require('./firestore');
const nodemailer = require('nodemailer');

jest.mock('./firestore', () => ({
  mailLogs: {
    doc: jest.fn(),
    add: jest.fn(),
  },
  mailTemplates: {
    doc: jest.fn(),
  }
}));

const mockSendMail = jest.fn();
jest.mock('nodemailer', () => ({
  createTransport: jest.fn(() => ({ sendMail: (...args) => mockSendMail(...args) })),
}));

describe('mailService', () => {
  describe('renderTemplate', () => {
    it('should return an empty string when text is falsy', () => {
      expect(renderTemplate(null, {})).toBe('');
      expect(renderTemplate(undefined, {})).toBe('');
      expect(renderTemplate('', {})).toBe('');
    });

    it('should return the original text when no placeholders are present', () => {
      const text = 'Hello world, this is a plain text.';
      expect(renderTemplate(text, {})).toBe(text);
      expect(renderTemplate(text, { name: 'Jules' })).toBe(text);
    });

    it('should replace a single placeholder', () => {
      const text = 'Hello {{ name }}!';
      expect(renderTemplate(text, { name: 'Jules' })).toBe('Hello Jules!');
    });

    it('should replace multiple placeholders', () => {
      const text = 'Hello {{ name }}, welcome to {{ place }}!';
      expect(renderTemplate(text, { name: 'Jules', place: 'Earth' })).toBe('Hello Jules, welcome to Earth!');
    });

    it('should handle different spacing within placeholders', () => {
      const text1 = 'Hello {{name}}!';
      const text2 = 'Hello {{  name  }}!';
      const text3 = 'Hello {{ name}}!';
      expect(renderTemplate(text1, { name: 'Jules' })).toBe('Hello Jules!');
      expect(renderTemplate(text2, { name: 'Jules' })).toBe('Hello Jules!');
      expect(renderTemplate(text3, { name: 'Jules' })).toBe('Hello Jules!');
    });

    it('should leave placeholder unmodified when corresponding key is missing from data', () => {
      const text = 'Hello {{ name }} and {{ friend }}!';
      expect(renderTemplate(text, { name: 'Jules' })).toBe('Hello Jules and {{ friend }}!');
    });
  });

  describe('dispatch (nodemailer SMTP)', () => {
    beforeEach(() => {
      mockSendMail.mockReset();
      mailLogs.add.mockReset();
      mailLogs.add.mockResolvedValue({ id: 'log-1' });
      mailTemplates.doc.mockReturnValue({
        get: jest.fn().mockResolvedValue({
          exists: true,
          data: () => ({
            templates: {
              ko: { title: '인증 코드 {{ code }}', body: '<p>코드: {{ code }}</p>' },
            },
          }),
        }),
      });
    });

    it('템플릿을 렌더링해 SMTP로 발송하고 sent 로그를 남긴다', async () => {
      mockSendMail.mockResolvedValue({ accepted: ['user@example.com'] });

      const result = await dispatch({
        to: 'user@example.com',
        templateKey: `verify_ok_${Date.now()}`, // 템플릿 캐시 회피용 고유 키
        location: 'ko',
        dynamicData: { code: '123456' },
        source: 'liv-ay',
      });

      expect(nodemailer.createTransport).toHaveBeenCalled();
      expect(mockSendMail).toHaveBeenCalledWith(expect.objectContaining({
        to: 'user@example.com',
        subject: '인증 코드 123456',
        html: '<p>코드: 123456</p>',
      }));
      expect(mailLogs.add).toHaveBeenCalledWith(expect.objectContaining({ status: 'sent' }));
      expect(result).toEqual({ id: 'log-1', status: 'sent' });
    });

    it('SMTP 발송 실패 시 failed 로그를 남기고 502 에러를 던진다', async () => {
      mockSendMail.mockRejectedValue(new Error('550 relay denied'));

      await expect(dispatch({
        to: 'user@example.com',
        templateKey: `verify_fail_${Date.now()}`,
        source: 'liv-ay',
      })).rejects.toMatchObject({ status: 502 });

      expect(mailLogs.add).toHaveBeenCalledWith(expect.objectContaining({
        status: 'failed',
        error: expect.stringContaining('550 relay denied'),
      }));
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
