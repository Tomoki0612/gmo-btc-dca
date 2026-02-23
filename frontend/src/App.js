import { useEffect, useState } from 'react';
import { Authenticator, ThemeProvider, createTheme, AccountSettings } from '@aws-amplify/ui-react';
import '@aws-amplify/ui-react/styles.css';
import './App.css';
import { I18n } from 'aws-amplify/utils';

I18n.putVocabulariesForLanguage('ja', {
  'Sign In': 'ログイン',
  'Sign in': 'ログイン',
  'Forgot your password?': 'パスワードをお忘れですか？',
  'Reset Password': 'パスワードをリセット',
  'Email': 'メールアドレス',
  'Send code': 'コードを送信',
  'Back to Sign In': 'ログイン画面に戻る',
  'Code': '確認コード',
  'New Password': '新しいパスワード',
  'Submit': '送信',
});
I18n.setLanguage('ja');

const theme = createTheme({
  tokens: {
    colors: {
      brand: {
        primary: {
          '10': { value: '#fff3e0' },
          '20': { value: '#ffe0b2' },
          '40': { value: '#ffb74d' },
          '60': { value: '#f97316' },
          '80': { value: '#ea6a0a' },
          '90': { value: '#d45d00' },
          '100': { value: '#bf5000' },
        },
      },
    },
  },
});

const formFields = {
  signIn: {
    username: {
      label: 'メールアドレス',
      placeholder: 'メールアドレスを入力',
    },
    password: {
      label: 'パスワード',
      placeholder: 'パスワードを入力',
    },
  },
};

const API_URL = "https://5slu1ftn2g.execute-api.ap-northeast-1.amazonaws.com/prod/settings";

function MainApp({ signOut }) {
  const [page, setPage] = useState('main');
  const [amount, setAmount] = useState(10000);
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [frequency, setFrequency] = useState("");
  const [scheduleDay, setScheduleDay] = useState("");
  const [scheduleTime, setScheduleTime] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [showPasswordChange, setShowPasswordChange] = useState(false);

  const navigateTo = (newPage) => {
    setError("");
    setSuccess("");
    setPage(newPage);
  };

  const postSettings = async () => {
    const response = await fetch(API_URL, {
      method: "POST",
      body: JSON.stringify({ amount, frequency, scheduleDay: frequency === 'daily' ? null : Number(scheduleDay), scheduleTime: scheduleTime !== "" ? Number(scheduleTime) : null, apiKey, apiSecret })
    });
    if (response.ok) {
      setError("");
      setSuccess("保存しました");
    } else {
      setSuccess("");
      setError("API通信エラー");
    }
  };

  const handleMainSave = async () => {
    if (!amount || amount <= 0) { setSuccess(""); setError("金額が適切に入力されていません"); return; }
    if (!frequency) { setSuccess(""); setError("積立頻度を選択してください"); return; }
    if (frequency !== 'daily' && !scheduleDay) { setSuccess(""); setError("積立日を選択してください"); return; }
    if (scheduleTime === "") { setSuccess(""); setError("積立時間を選択してください"); return; }
    await postSettings();
  };

  const handleApiSave = async () => {
    if (!apiKey) { setSuccess(""); setError("APIキーを入力してください"); return; }
    if (!apiSecret) { setSuccess(""); setError("APIシークレットを入力してください"); return; }
    await postSettings();
  };

  useEffect(() => {
    const loadSettings = async () => {
      const response = await fetch(API_URL);
      const data = await response.json();
      if (response.ok) {
        setAmount(data.amount);
        setFrequency(data.frequency || "");
        setScheduleDay(data.scheduleDay ? String(data.scheduleDay) : "");
        setScheduleTime(data.scheduleTime != null ? String(data.scheduleTime) : "");
        setApiKey(data.apiKey);
        setApiSecret(data.apiSecret);
      }
    };
    loadSettings();
  }, []);

  if (page === 'api-settings') {
    return (
      <div className="App">
        <header className="App-header">
          <div className="card">
            <div className="page-header">
              <button className="back-button" onClick={() => navigateTo('main')}>← 戻る</button>
              <h1>API設定</h1>
            </div>
            <div className='form-group'>
              <label>APIキー</label>
              <input
                type="password"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
              />
            </div>
            <div className='form-group'>
              <label>APIシークレット</label>
              <input
                type="password"
                value={apiSecret}
                onChange={(e) => setApiSecret(e.target.value)}
              />
            </div>
            <button className="save-button" onClick={handleApiSave}>保存</button>
            <p className='error-message'>{error}</p>
            <p className='success-message'>{success}</p>
          </div>
        </header>
      </div>
    );
  }

  return (
    <div className="App">
      <header className="App-header">
        <div className="card">
          <h1>ツミビット</h1>
          <div className='form-group'>
            <label>積立金額（円）</label>
            <input
              type="number"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
          </div>
          <div className='form-group'>
            <label>積立頻度</label>
            <select value={frequency} onChange={(e) => { setFrequency(e.target.value); setScheduleDay(""); }}>
              <option value="">選択してください</option>
              <option value="daily">毎日</option>
              <option value="weekly">毎週</option>
              <option value="monthly">毎月</option>
            </select>
          </div>
          {frequency === 'weekly' && (
            <div className='form-group'>
              <label>曜日</label>
              <select value={scheduleDay} onChange={(e) => setScheduleDay(e.target.value)}>
                <option value="">選択してください</option>
                {['月曜日', '火曜日', '水曜日', '木曜日', '金曜日', '土曜日', '日曜日'].map((day, i) => (
                  <option key={i + 1} value={i + 1}>{day}</option>
                ))}
              </select>
            </div>
          )}
          {frequency === 'monthly' && (
            <div className='form-group'>
              <label>日付</label>
              <select value={scheduleDay} onChange={(e) => setScheduleDay(e.target.value)}>
                <option value="">選択してください</option>
                {Array.from({ length: 28 }, (_, i) => i + 1).map((day) => (
                  <option key={day} value={day}>{day}日</option>
                ))}
              </select>
            </div>
          )}
          <div className='form-group'>
            <label>積立時間</label>
            <select value={scheduleTime} onChange={(e) => setScheduleTime(e.target.value)}>
              <option value="">選択してください</option>
              {Array.from({ length: 24 }, (_, i) => (
                <option key={i} value={i}>{i}時</option>
              ))}
            </select>
          </div>
          <button className="save-button" onClick={handleMainSave}>保存</button>
          <p className='error-message'>{error}</p>
          <p className='success-message'>{success}</p>
        </div>

        <button className="api-settings-button" onClick={() => navigateTo('api-settings')}>
          API設定 →
        </button>

        {showPasswordChange ? (
          <div className="card password-card">
            <h2>パスワード変更</h2>
            <AccountSettings.ChangePassword
              onSuccess={() => setShowPasswordChange(false)}
            />
            <button className="cancel-button" onClick={() => setShowPasswordChange(false)}>キャンセル</button>
          </div>
        ) : (
          <button className="change-password-button" onClick={() => setShowPasswordChange(true)}>
            パスワードを変更する
          </button>
        )}

        <button className="signout-button" onClick={signOut}>サインアウト</button>
      </header>
    </div>
  );
}

const components = {
  Header() {
    return (
      <div className="auth-header">
        <h1>ツミビット</h1>
        <p>BTC自動積立サービス</p>
      </div>
    );
  },
};

function App() {
  return (
    <ThemeProvider theme={theme}>
      <Authenticator hideSignUp formFields={formFields} components={components}>
        {({ signOut }) => <MainApp signOut={signOut} />}
      </Authenticator>
    </ThemeProvider>
  );
}

export default App;
