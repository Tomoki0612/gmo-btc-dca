import { useState } from 'react';
import './App.css';
import logo from './logo.svg';

function App() {
  const title = "tubitoko 設定画面"
  const [amount, setAmount] = useState(10000);
  const [apiKey, setApiKey] = useState("");
  const [apiSecret, setApiSecret] = useState("");
  const [schedule, setSchedule] = useState("");
  const [error, setError] = useState("");
  const handleSave = () => {
    if (amount === null || amount <= 0) {
      setError("金額が適切に入力されていません")
      return ;
    }
    if (schedule === '') {
      setError("積立日が入力されていません")
      return ;
    }
    if (apiKey === '') {
      setError("APIキーを入力してください")
      return ;
    } 
    if (apiSecret === '') {
      setError("APIシークレットを入力してください")
      return ;
    }
    setError("")
    console.log(amount,schedule, apiKey, apiSecret);
    };



  return (
    <div className="App">
      <header className="App-header">
        <img src={logo} className="App-logo" alt="logo" />
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
            <input
              type="text"
              value={schedule}
              onChange={(e) => setSchedule(e.target.value)}
            />
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
        </div>
        <a
          className="App-link"
          href="https://reactjs.org"
          target="_blank"
          rel="noopener noreferrer"
        >
          Learn React
        </a>
      </header>
    </div>
  );
}

export default App;
