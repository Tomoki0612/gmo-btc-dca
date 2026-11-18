import { Amplify } from 'aws-amplify';
import { confirmSignIn, getCurrentUser, signIn } from 'aws-amplify/auth';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import QRCode from 'qrcode';
import App from './App';

vi.mock('aws-amplify/auth', async (importOriginal) => ({
  ...await importOriginal(),
  getCurrentUser: vi.fn(),
  signIn: vi.fn(),
  confirmSignIn: vi.fn(),
}));

// Keep QR generation local and deterministic; the secret is a test fixture.
vi.mock('qrcode', () => ({
  default: { toDataURL: vi.fn().mockResolvedValue('data:image/png;base64,AA==') },
}));

beforeAll(() => {
  Amplify.configure({
    Auth: {
      Cognito: {
        userPoolId: 'ap-northeast-1_testpool',
        userPoolClientId: 'testclientid',
        loginWith: { email: true },
      },
    },
  });
});

beforeEach(() => {
  vi.clearAllMocks();
  getCurrentUser.mockRejectedValue(new Error('Not signed in'));
  confirmSignIn.mockRejectedValue(Object.assign(
    new Error('確認コードが正しくありません'), { name: 'CodeMismatchException' },
  ));
  global.fetch = vi.fn();
});

test.each([
  'CONTINUE_SIGN_IN_WITH_TOTP_SETUP',
  'CONFIRM_SIGN_IN_WITH_TOTP_CODE',
])('%s requires the Bitwarden code before backend access', async (signInStep) => {
  signIn.mockResolvedValue({
    isSignedIn: false,
    nextStep: {
      signInStep,
      totpSetupDetails: { sharedSecret: 'JBSWY3DPEHPK3PXP' },
    },
  });
  render(<App />);

  fireEvent.change(await screen.findByLabelText('メールアドレス'), {
    target: { value: 'owner@example.com' },
  });
  const password = screen.getByLabelText('パスワード', { selector: 'input' });
  fireEvent.change(password, { target: { value: 'Test-only-password1!' } });
  fireEvent.submit(password.closest('form'));

  const code = await screen.findByPlaceholderText('Bitwardenの6桁のコード');
  expect(global.fetch).not.toHaveBeenCalled();
  if (signInStep === 'CONTINUE_SIGN_IN_WITH_TOTP_SETUP') {
    expect(screen.getByRole('heading', { name: '認証アプリの登録' })).toBeInTheDocument();
    await waitFor(() => expect(QRCode.toDataURL).toHaveBeenCalled());
    const uri = new URL(QRCode.toDataURL.mock.calls[0][0]);
    expect(uri.protocol).toBe('otpauth:');
    expect(uri.searchParams.get('issuer')).toBe('ツミビット');
    expect(uri.searchParams.get('secret')).toBe('JBSWY3DPEHPK3PXP');
  } else {
    expect(QRCode.toDataURL).not.toHaveBeenCalled();
  }

  fireEvent.change(code, { target: { value: '000000' } });
  fireEvent.submit(code.closest('form'));
  await screen.findByText('確認コードが正しくありません');
  expect(confirmSignIn).toHaveBeenCalledWith(expect.objectContaining({ challengeResponse: '000000' }));
  expect(global.fetch).not.toHaveBeenCalled();
  expect(code).toBeInTheDocument();
});
