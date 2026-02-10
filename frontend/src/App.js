import { useState } from 'react';
import './App.css';
import logo from './logo.svg';

function App() {
  const title = "BTC自動積立 設定画面"
  const [amount, setAmount] = useState(5000);

  return (
    <div className="App">
      <header className="App-header">
        <img src={logo} className="App-logo" alt="logo" />
        <div>
          <h1>{ title }</h1>
          <label>積立金額（円）</label>
          <input
            type="number"
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
          />
          <p>現在の設定：{amount}</p>
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
