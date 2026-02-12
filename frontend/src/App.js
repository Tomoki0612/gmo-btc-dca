import { useState } from 'react';
import './App.css';

function App() {
  const title = "tubitoko 設定画面"
  const [amount, setAmount] = useState(10000);
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [schedule, setSchedule] = useState("");
  const [error, setError] = useState("");
  const [success, setSuccess] = useState("")
  const handleSave = () => {
    if (amount === null || amount <= 0) {
      setSuccess("")
      setError("金額が適切に入力されていません")
      return ;
    }
    if (schedule === '') {
      setSuccess("")
      setError("積立日が入力されていません")
      return ;
    }
    if (apiKey === '') {
      setSuccess("")
      setError("APIキーを入力してください")
      return ;
    } 
    if (apiSecret === '') {
      setSuccess("")
      setError("APIシークレットを入力してください")
      return ;
    }
    setError("")
    setSuccess("保存しました")
    console.log(amount,schedule, apiKey, apiSecret);
    };



  return (
    <div className="App">
      <header className="App-header">
        <div>
          <h1>{ title }</h1>
          <div className='form-group'>
            <label>積立金額（円）</label>
            <input
              type="number"
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
            />
          </div>
          <div className='form-group'>
            <label>積立日</label>
            <select value={schedule} onChange={(e) => setSchedule(e.target.value)}>
              <option value="">選択してください</option>
              {Array.from({ length: 28 }, (_, i) => i + 1).map((day) => (
                <option key = {day} value={day}>{day}日</option>
              ))}
            </select>
          </div>
          <div className='form-group'>
            <label>apiKey</label>
            <input
              type="password"
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
            />
          </div>
          <div className='form-group'>
            <label>apiSecret</label>
            <input
              type="password"
              value={apiSecret}
              onChange={(e) => setApiSecret(e.target.value)}
            />
          </div>
          <button className = "save-button" onClick={handleSave}>保存</button>
          <p className='error-message'>{error}</p>
          <p className='success-message'>{success}</p>
        </div>
      </header>
    </div>
  );
}

export default App;
