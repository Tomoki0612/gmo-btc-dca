import { useEffect, useRef, useState } from 'react';
import { Authenticator, ThemeProvider, createTheme } from '@aws-amplify/ui-react';
import { updatePassword } from 'aws-amplify/auth';
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
  const headingRef = useRef(null);

  useEffect(() => {
    headingRef.current?.focus();
  }, [page]);
  const [savedSettings, setSavedSettings] = useState(null);
  const [amount, setAmount] = useState(10000);
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [frequency, setFrequency] = useState("");
  const [scheduleDay, setScheduleDay] = useState("");
  const [scheduleTime, setScheduleTime] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("");
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [passwordSuccess, setPasswordSuccess] = useState("");

  const handlePasswordChange = async () => {
    setPasswordError("");
    setPasswordSuccess("");
    if (!oldPassword) { setPasswordError("現在のパスワードを入力してください"); return; }
    if (!newPassword) { setPasswordError("新しいパスワードを入力してください"); return; }
    if (newPassword !== confirmPassword) { setPasswordError("新しいパスワードが一致しません"); return; }
    try {
      await updatePassword({ oldPassword, newPassword });
      setPasswordSuccess("パスワードを変更しました");
      setOldPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (e) {
      if (e.name === 'NotAuthorizedException') {
        setPasswordError("現在のパスワードが正しくありません");
      } else if (e.name === 'InvalidPasswordException') {
        setPasswordError("パスワードの形式が正しくありません（8文字以上・大文字・小文字・数字・記号をすべて含めてください）");
      } else {
        setPasswordError("エラーが発生しました: " + e.message);
      }
    }
  };

  const navigateTo = (newPage) => {
    setError("");
    setSuccess("");
    setOldPassword(""); setNewPassword(""); setConfirmPassword("");
    setPasswordError(""); setPasswordSuccess("");
    setPage(newPage);
  };

  const postSettings = async () => {
    const response = await fetch(API_URL, {
      method: "POST",
      body: JSON.stringify({ amount: Number(amount), frequency, scheduleDay: frequency === 'daily' ? null : Number(scheduleDay), scheduleTime: scheduleTime !== "" ? Number(scheduleTime) : null, apiKey, apiSecret })
    });
    if (response.ok) {
      setError("");
      setSuccess("保存しました");
      setSavedSettings({ amount: Number(amount), frequency, scheduleDay: frequency === 'daily' ? null : Number(scheduleDay), scheduleTime: scheduleTime !== "" ? Number(scheduleTime) : null, apiKey, apiSecret });
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
    if (!savedSettings) { setSuccess(""); setError("設定の読み込みが完了していません。再読み込みしてください"); return; }
    const response = await fetch(API_URL, {
      method: "POST",
      body: JSON.stringify({ ...savedSettings, apiKey, apiSecret })
    });
    if (response.ok) {
      setError("");
      setSuccess("保存しました");
      setSavedSettings(prev => ({ ...prev, apiKey, apiSecret }));
    } else {
      setSuccess("");
      setError("API通信エラー");
    }
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
        setSavedSettings(data);
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
              <h1 ref={headingRef} tabIndex={-1}>API設定</h1>
              <div className="page-header-spacer"></div>
            </div>
            <div className='form-group'>
              <label htmlFor="apiKey">APIキー</label>
              <input
                id="apiKey"
                type="password"
                autoComplete="off"
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
              />
            </div>
            <div className='form-group'>
              <label htmlFor="apiSecret">APIシークレット</label>
              <input
                id="apiSecret"
                type="password"
                autoComplete="off"
                value={apiSecret}
                onChange={(e) => setApiSecret(e.target.value)}
              />
            </div>
            <button className="save-button" onClick={handleApiSave}>保存</button>
            <p className='error-message' role="alert">{error}</p>
            <p className='success-message' role="status">{success}</p>
          </div>
        </header>
      </div>
    );
  }

  if (page === 'password') {
    return (
      <div className="App">
        <header className="App-header">
          <div className="card">
            <div className="page-header">
              <button className="back-button" onClick={() => navigateTo('main')}>← 戻る</button>
              <h1 ref={headingRef} tabIndex={-1}>パスワード変更</h1>
              <div className="page-header-spacer"></div>
            </div>
            <div className="form-fields">
              <div className="form-group">
                <label htmlFor="oldPassword">現在のパスワード</label>
                <input id="oldPassword" type="password" autoComplete="current-password" value={oldPassword} onChange={(e) => setOldPassword(e.target.value)} />
              </div>
              <div className="form-group">
                <label htmlFor="newPassword">新しいパスワード</label>
                <div>
                  <input id="newPassword" type="password" autoComplete="new-password" value={newPassword} onChange={(e) => setNewPassword(e.target.value)} />
                  <p className="input-hint">8文字以上・大文字・小文字・数字・記号を含む</p>
                </div>
              </div>
              <div className="form-group">
                <label htmlFor="confirmPassword">新しいパスワード（確認）</label>
                <input id="confirmPassword" type="password" autoComplete="new-password" value={confirmPassword} onChange={(e) => setConfirmPassword(e.target.value)} />
              </div>
            </div>
            <p className="error-message" role="alert">{passwordError}</p>
            <p className="success-message" role="status">{passwordSuccess}</p>
            <div className="password-buttons">
              <button className="save-button" onClick={handlePasswordChange}>変更する</button>
              <button className="cancel-button" onClick={() => navigateTo('main')}>キャンセル</button>
            </div>
          </div>
        </header>
      </div>
    );
  }

  const WEEKDAYS = ['月曜日', '火曜日', '水曜日', '木曜日', '金曜日', '土曜日', '日曜日'];
  const scheduleLabel = (s) => {
    if (!s?.frequency) return '—';
    if (s.frequency === 'daily') return '毎日';
    if (s.frequency === 'weekly') return s.scheduleDay ? `毎週 ${WEEKDAYS[Number(s.scheduleDay) - 1]}` : '毎週';
    if (s.frequency === 'monthly') return s.scheduleDay ? `毎月 ${s.scheduleDay}日` : '毎月';
    return '—';
  };

  return (
    <div className="App">
      <header className="App-header">
        <h1 ref={headingRef} tabIndex={-1} className="page-title">ツミビット</h1>
        <div className="split-layout">
          <div className="card summary-card">
            <h2>現在の設定</h2>
            <div className="summary-row">
              <span className="summary-label">積立金額</span>
              <span className="summary-value">{savedSettings?.amount ? `${Number(savedSettings.amount).toLocaleString()}円` : '—'}</span>
            </div>
            <div className="summary-row">
              <span className="summary-label">積立スケジュール</span>
              <span className="summary-value">{scheduleLabel(savedSettings)}</span>
            </div>
            <div className="summary-row">
              <span className="summary-label">積立時間</span>
              <span className="summary-value">{savedSettings?.scheduleTime != null ? `${savedSettings.scheduleTime}時` : '—'}</span>
            </div>
            <div className="summary-row">
              <span className="summary-label">APIキー</span>
              <span className="summary-value">{savedSettings?.apiKey ? '設定済み' : '未設定'}</span>
            </div>
            <div className="summary-row">
              <span className="summary-label">APIシークレット</span>
              <span className="summary-value">{savedSettings?.apiSecret ? '設定済み' : '未設定'}</span>
            </div>
          </div>
        <div className="card">
          <div className='form-group'>
            <label htmlFor="amount">積立金額（円）</label>
            <input
              id="amount"
              type="number"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
          </div>
          <div className='form-group'>
            <label htmlFor="frequency">積立頻度</label>
            <select id="frequency" value={frequency} onChange={(e) => { setFrequency(e.target.value); setScheduleDay(""); }}>
              <option value="">選択してください</option>
              <option value="daily">毎日</option>
              <option value="weekly">毎週</option>
              <option value="monthly">毎月</option>
            </select>
          </div>
          {frequency === 'weekly' && (
            <div className='form-group'>
              <label htmlFor="scheduleWeekday">曜日</label>
              <select id="scheduleWeekday" value={scheduleDay} onChange={(e) => setScheduleDay(e.target.value)}>
                <option value="">選択してください</option>
                {['月曜日', '火曜日', '水曜日', '木曜日', '金曜日', '土曜日', '日曜日'].map((day, i) => (
                  <option key={i + 1} value={i + 1}>{day}</option>
                ))}
              </select>
            </div>
          )}
          {frequency === 'monthly' && (
            <div className='form-group'>
              <label htmlFor="scheduleMonthDay">日付</label>
              <select id="scheduleMonthDay" value={scheduleDay} onChange={(e) => setScheduleDay(e.target.value)}>
                <option value="">選択してください</option>
                {Array.from({ length: 28 }, (_, i) => i + 1).map((day) => (
                  <option key={day} value={day}>{day}日</option>
                ))}
              </select>
            </div>
          )}
          <div className='form-group'>
            <label htmlFor="scheduleTime">積立時間</label>
            <select id="scheduleTime" value={scheduleTime} onChange={(e) => setScheduleTime(e.target.value)}>
              <option value="">選択してください</option>
              {Array.from({ length: 24 }, (_, i) => (
                <option key={i} value={i}>{i}時</option>
              ))}
            </select>
          </div>
          <button className="save-button" onClick={handleMainSave}>保存</button>
          <p className='error-message' role="alert">{error}</p>
          <p className='success-message' role="status">{success}</p>
        </div>
        </div>

        <div className="bottom-buttons">
          <button className="api-settings-button" onClick={() => navigateTo('api-settings')}>
            API設定 →
          </button>

          <button className="change-password-button" onClick={() => navigateTo('password')}>
            パスワードを変更する
          </button>

          <button className="signout-button" onClick={signOut}>サインアウト</button>
        </div>
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
