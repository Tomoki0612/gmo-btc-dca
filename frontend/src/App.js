import { useEffect, useRef, useState } from 'react';
import './App.css';

const API_BASE = '/api';
const API_URL = `${API_BASE}/settings`;
const BALANCE_URL = `${API_BASE}/balance`;
const HISTORY_URL = `${API_BASE}/history`;

const FREQ_LABEL = { daily: '毎日', weekly: '毎週', monthly: '毎月' };
const WEEKDAYS = ['月', '火', '水', '木', '金', '土', '日'];

const fmtYen = (n) => `¥${Number(n).toLocaleString('ja-JP')}`;
const fmtSchedule = (freq, day) => {
  if (freq === 'daily') return '毎日';
  if (freq === 'weekly') return day ? `毎週 ${WEEKDAYS[day - 1]}曜日` : '毎週';
  if (freq === 'monthly') return day ? `毎月 ${day}日` : '毎月';
  return '—';
};
const fmtTime = (h) => (h == null ? '—' : `${String(h).padStart(2, '0')}:00`);

function nextRun(freq, day, hour) {
  const now = new Date();
  const target = new Date(now);
  target.setMinutes(0, 0, 0);
  target.setHours(hour);
  if (freq === 'daily') {
    if (target <= now) target.setDate(target.getDate() + 1);
  } else if (freq === 'weekly') {
    const jsDow = target.getDay() === 0 ? 7 : target.getDay();
    let diff = day - jsDow;
    if (diff < 0 || (diff === 0 && target <= now)) diff += 7;
    target.setDate(target.getDate() + diff);
  } else {
    target.setDate(day);
    if (target <= now) target.setMonth(target.getMonth() + 1);
  }
  const m = target.getMonth() + 1;
  const d = target.getDate();
  const h = String(target.getHours()).padStart(2, '0');
  const wd = ['日', '月', '火', '水', '木', '金', '土'][target.getDay()];
  return `${m}/${d}(${wd}) ${h}:00`;
}

function FieldCard({ label, icon, changed, currentDisplay, children, footer, onClick, linkLike, rightAdornment }) {
  return (
    <section
      className={`field-card ${linkLike ? 'field-card--link' : ''}`}
      data-changed={changed ? 'true' : 'false'}
      onClick={onClick}
      role={onClick ? 'button' : undefined}
      tabIndex={onClick ? 0 : undefined}
      onKeyDown={onClick ? (e) => { if (e.key === 'Enter' || e.key === ' ') onClick(); } : undefined}
    >
      <header className="field-card__head">
        <div className="field-card__label">
          <span className="field-card__icon" aria-hidden>{icon}</span>
          <span>{label}</span>
        </div>
        {changed && <span className="badge badge--changed">変更</span>}
        {rightAdornment}
      </header>
      <div className="field-card__current" aria-live="polite">{currentDisplay}</div>
      {children && <div className="field-card__body">{children}</div>}
      {footer && <div className="field-card__footer">{footer}</div>}
    </section>
  );
}

function DiffValue({ before, after, changed, big }) {
  return (
    <div className={`diff ${big ? 'diff--big' : ''}`} data-changed={changed}>
      {changed && <span className="diff__before">{before}</span>}
      {changed && <span className="diff__arrow" aria-hidden>→</span>}
      <span className="diff__after">{after}</span>
    </div>
  );
}

const AMOUNT_MIN = 1000;
const AMOUNT_MAX = 500000;
const toSlider = (v) => Math.log(v / AMOUNT_MIN) / Math.log(AMOUNT_MAX / AMOUNT_MIN);
const fromSlider = (t) => {
  const raw = AMOUNT_MIN * Math.pow(AMOUNT_MAX / AMOUNT_MIN, t);
  return Math.round(raw / 1000) * 1000;
};

function AmountField({ value, saved, onChange }) {
  const changed = value !== saved;
  const preset = [3000, 5000, 10000, 30000, 50000, 100000];
  const clamped = Math.max(AMOUNT_MIN, Math.min(AMOUNT_MAX, value || AMOUNT_MIN));

  return (
    <FieldCard
      label="積立金額"
      icon="¥"
      changed={changed}
      currentDisplay={
        <DiffValue big changed={changed} before={fmtYen(saved ?? 0)} after={fmtYen(value ?? 0)} />
      }
      footer={
        <div className="field-card__hint">
          <span>1回あたり ¥1,000 〜 ¥500,000 / 最低 ¥3,000 推奨</span>
        </div>
      }
    >
      <div className="amount-input-row">
        <div className="numeric-input">
          <button
            type="button"
            className="numeric-input__btn"
            aria-label="減らす"
            onClick={() => onChange(Math.max(AMOUNT_MIN, Math.round(((value || 0) - 1000) / 1000) * 1000))}
          >−</button>
          <div className="numeric-input__display">
            <span className="numeric-input__currency">¥</span>
            <input
              type="text"
              inputMode="numeric"
              value={(value || 0).toLocaleString('ja-JP')}
              onChange={(e) => {
                const n = parseInt(e.target.value.replace(/[^0-9]/g, ''), 10);
                if (!isNaN(n)) onChange(Math.min(AMOUNT_MAX, Math.max(0, n)));
                else if (e.target.value === '') onChange(0);
              }}
              aria-label="積立金額"
            />
          </div>
          <button
            type="button"
            className="numeric-input__btn"
            aria-label="増やす"
            onClick={() => onChange(Math.min(AMOUNT_MAX, Math.round(((value || 0) + 1000) / 1000) * 1000))}
          >+</button>
        </div>
      </div>

      <div className="slider-wrap">
        <input
          type="range"
          min="0"
          max="1"
          step="0.001"
          value={toSlider(clamped)}
          onChange={(e) => onChange(fromSlider(parseFloat(e.target.value)))}
          style={{ '--t': `${toSlider(clamped) * 100}%` }}
          aria-label="金額スライダー"
        />
        <div className="slider-ticks" aria-hidden>
          <span>¥1千</span><span>¥1万</span><span>¥10万</span><span>¥50万</span>
        </div>
      </div>

      <div className="preset-row">
        {preset.map((p) => (
          <button
            key={p}
            type="button"
            className="chip"
            data-active={value === p}
            onClick={() => onChange(p)}
          >
            {p >= 10000 ? `${p / 10000}万` : `${p / 1000}千`}
          </button>
        ))}
      </div>
    </FieldCard>
  );
}

function ScheduleField({ frequency, day, savedFrequency, savedDay, onChangeFreq, onChangeDay }) {
  const freqChanged = frequency !== savedFrequency;
  const dayChanged = frequency === savedFrequency && frequency !== 'daily' && day !== savedDay;
  const changed = freqChanged || dayChanged;
  const beforeText = fmtSchedule(savedFrequency, savedDay);
  const afterText = fmtSchedule(frequency, day);

  return (
    <FieldCard
      label="積立スケジュール"
      icon="◷"
      changed={changed}
      currentDisplay={<DiffValue big changed={changed} before={beforeText} after={afterText} />}
    >
      <div className="segmented" role="tablist" aria-label="積立頻度">
        {['daily', 'weekly', 'monthly'].map((f) => (
          <button
            key={f}
            type="button"
            role="tab"
            aria-selected={frequency === f}
            className="segmented__item"
            data-active={frequency === f}
            onClick={() => onChangeFreq(f)}
          >
            {FREQ_LABEL[f]}
          </button>
        ))}
      </div>

      {frequency === 'weekly' && (
        <div className="sub-section">
          <div className="sub-label">曜日</div>
          <div className="weekday-row">
            {WEEKDAYS.map((w, idx) => {
              const v = idx + 1;
              return (
                <button
                  key={v}
                  type="button"
                  className="pill"
                  data-active={day === v}
                  onClick={() => onChangeDay(v)}
                  aria-pressed={day === v}
                >
                  {w}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {frequency === 'monthly' && (
        <div className="sub-section">
          <div className="sub-label">日付（月末ズレ回避のため1〜28日）</div>
          <div className="date-grid">
            {Array.from({ length: 28 }, (_, i) => i + 1).map((d) => (
              <button
                key={d}
                type="button"
                className="date-cell"
                data-active={day === d}
                onClick={() => onChangeDay(d)}
                aria-pressed={day === d}
              >
                {d}
              </button>
            ))}
          </div>
        </div>
      )}

      {frequency === 'daily' && (
        <div className="sub-section sub-section--hint">
          毎日、指定した時刻に実行されます。
        </div>
      )}
    </FieldCard>
  );
}

function TimeField({ value, saved, onChange }) {
  const changed = value !== saved;
  return (
    <FieldCard
      label="積立時間"
      icon="✦"
      changed={changed}
      currentDisplay={
        <DiffValue big changed={changed} before={fmtTime(saved)} after={fmtTime(value)} />
      }
      footer={<div className="field-card__hint"><span>日本時間 (JST) </span></div>}
    >
      <div className="time-slider-wrap">
        <div className="time-rail">
          <div className="time-rail__markers" aria-hidden>
            {[0, 6, 12, 18, 23].map((h) => (
              <span key={h} style={{ left: `${(h / 23) * 100}%` }}>{h}時</span>
            ))}
          </div>
          <input
            type="range"
            min="0"
            max="23"
            step="1"
            value={value ?? 0}
            onChange={(e) => onChange(parseInt(e.target.value, 10))}
            style={{ '--t': `${((value ?? 0) / 23) * 100}%` }}
            aria-label="時刻スライダー"
          />
        </div>
        <div className="day-night" aria-hidden>
          <span className={value >= 5 && value < 11 ? 'on' : ''}>☀︎ 朝</span>
          <span className={value >= 11 && value < 17 ? 'on' : ''}>◎ 昼</span>
          <span className={value >= 17 && value < 21 ? 'on' : ''}>◐ 夕</span>
          <span className={value >= 21 || value < 5 ? 'on' : ''}>☾ 夜</span>
        </div>
      </div>
    </FieldCard>
  );
}

function TopBar({ title, onBack, onMenu, center }) {
  return (
    <header className="top-bar">
      <div className="top-bar__inner">
        {onBack ? (
          <button type="button" className="text-btn" onClick={onBack}>‹ 戻る</button>
        ) : (
          <div className="brand">
            <span className="brand__mark" aria-hidden>₿</span>
            <span className="brand__name">ツミビット</span>
          </div>
        )}
        {center && <div className="brand brand--center"><span className="brand__name">{title}</span></div>}
        {onMenu ? (
          <button type="button" className="icon-btn" aria-label="メニュー" onClick={onMenu}>
            <span className="icon-btn__dot" />
            <span className="icon-btn__dot" />
            <span className="icon-btn__dot" />
          </button>
        ) : (
          <div style={{ width: 48 }} />
        )}
      </div>
    </header>
  );
}

function maskApiKey(key) {
  if (!key) return '';
  const head = key.slice(0, 4);
  return `${head}••••••••••••`;
}

function BalanceCard({ apiConfigured }) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [data, setData] = useState(null);
  const [updated, setUpdated] = useState(null);

  const load = async () => {
    if (!apiConfigured) return;
    setLoading(true);
    setError('');
    try {
      const res = await fetch(BALANCE_URL);
      const body = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(body.message || '残高取得に失敗しました');
      if (body.configured === false) {
        setData(null);
      } else {
        setData(body);
        setUpdated(new Date());
      }
    } catch (e) {
      setError(e.message || '残高取得に失敗しました');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (apiConfigured) load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [apiConfigured]);

  const fmtUpd = (d) => (d
    ? `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}:${String(d.getSeconds()).padStart(2, '0')}`
    : '--:--:--');

  if (!apiConfigured) {
    return (
      <section className="field-card balance-card">
        <header className="field-card__head">
          <div className="field-card__label">
            <span className="field-card__icon" aria-hidden>$</span>
            <span>取引所残高</span>
          </div>
        </header>
        <div className="field-card__current">
          <div className="api-status">
            <span className="api-dot" />
            APIキー未設定
          </div>
        </div>
        <div className="field-card__footer">
          <div className="field-card__hint">APIキーを設定すると残高が表示されます</div>
        </div>
      </section>
    );
  }

  const btcInJpy = data ? Math.round(data.btc * data.btcJpyRate) : 0;
  const total = data ? Math.round(data.jpy + btcInJpy) : 0;

  return (
    <section className="field-card balance-card">
      <header className="field-card__head">
        <div className="field-card__label">
          <span className="field-card__icon" aria-hidden>$</span>
          <span>取引所残高</span>
        </div>
        <button type="button" className="refresh-btn" onClick={load} aria-label="残高を更新" data-loading={loading} disabled={loading}>
          <span aria-hidden>↻</span>
          <span className="refresh-btn__txt">{fmtUpd(updated)}</span>
        </button>
      </header>

      <div className="balance-total">
        <span className="balance-total__label">評価額合計</span>
        <span className="balance-total__value">{data ? fmtYen(total) : '—'}</span>
      </div>

      <div className="balance-rows">
        <div className="balance-row">
          <div className="balance-row__left">
            <span className="asset-mark asset-mark--jpy" aria-hidden>¥</span>
            <div>
              <div className="balance-row__ticker">JPY</div>
              <div className="balance-row__name">日本円</div>
            </div>
          </div>
          <div className="balance-row__right">
            <div className="balance-row__amount mono">{data ? Math.floor(data.jpy).toLocaleString('ja-JP') : '—'}</div>
            <div className="balance-row__sub">円</div>
          </div>
        </div>

        <div className="balance-row">
          <div className="balance-row__left">
            <span className="asset-mark asset-mark--btc" aria-hidden>₿</span>
            <div>
              <div className="balance-row__ticker">BTC</div>
              <div className="balance-row__name">ビットコイン</div>
            </div>
          </div>
          <div className="balance-row__right">
            <div className="balance-row__amount mono">{data ? data.btc.toFixed(5) : '—'}</div>
            <div className="balance-row__sub">{data ? `${btcInJpy.toLocaleString('ja-JP')}円` : '—'}</div>
          </div>
        </div>
      </div>

      <div className="field-card__footer">
        <div className="field-card__hint">
          {data ? (
            <>1 BTC = <span className="mono">{fmtYen(data.btcJpyRate)}</span> ・ GMOコイン</>
          ) : (
            <>GMOコイン</>
          )}
          {error && <span className="balance-error"> ・ {error}</span>}
        </div>
      </div>
    </section>
  );
}

function SettingsPage({ savedSettings, onNavigate, headingRef }) {
  const hasSaved = !!savedSettings;
  const savedAmount = savedSettings?.amount ?? 0;
  const savedFrequency = savedSettings?.frequency || 'monthly';
  const savedDay = savedSettings?.scheduleDay ?? (savedFrequency === 'monthly' ? 1 : 1);
  const savedTime = savedSettings?.scheduleTime ?? 0;

  const [amount, setAmount] = useState(savedAmount);
  const [frequency, setFrequency] = useState(savedFrequency);
  const [scheduleDay, setScheduleDay] = useState(savedDay);
  const [scheduleTime, setScheduleTime] = useState(savedTime);
  const [toast, setToast] = useState(null);
  const [error, setError] = useState('');
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!savedSettings) return;
    setAmount(savedSettings.amount ?? 0);
    setFrequency(savedSettings.frequency || 'monthly');
    setScheduleDay(savedSettings.scheduleDay ?? 1);
    setScheduleTime(savedSettings.scheduleTime ?? 0);
  }, [savedSettings]);

  const handleFreqChange = (f) => {
    setFrequency(f);
    if (f === 'weekly') setScheduleDay(savedFrequency === 'weekly' ? savedDay : 1);
    else if (f === 'monthly') setScheduleDay(savedFrequency === 'monthly' ? savedDay : 1);
  };

  const changes = [];
  if (amount !== savedAmount) {
    changes.push({ k: 'amount', label: '積立金額', before: fmtYen(savedAmount), after: fmtYen(amount) });
  }
  if (frequency !== savedFrequency || (frequency !== 'daily' && scheduleDay !== savedDay)) {
    changes.push({
      k: 'schedule',
      label: 'スケジュール',
      before: fmtSchedule(savedFrequency, savedDay),
      after: fmtSchedule(frequency, scheduleDay),
    });
  }
  if (scheduleTime !== savedTime) {
    changes.push({ k: 'time', label: '積立時間', before: fmtTime(savedTime), after: fmtTime(scheduleTime) });
  }
  const hasChanges = changes.length > 0;
  const amountValid = amount >= AMOUNT_MIN;
  const canSave = hasSaved && hasChanges && amountValid && !saving;

  const discard = () => {
    setAmount(savedAmount);
    setFrequency(savedFrequency);
    setScheduleDay(savedDay);
    setScheduleTime(savedTime);
    setError('');
  };

  const save = async () => {
    if (!canSave) return;
    setSaving(true);
    setError('');
    try {
      const body = {
        amount: Number(amount),
        frequency,
        scheduleDay: frequency === 'daily' ? null : Number(scheduleDay),
        scheduleTime: Number(scheduleTime),
        apiKey: savedSettings?.apiKey || '',
        apiSecret: savedSettings?.apiSecret || '',
      };
      const res = await fetch(API_URL, { method: 'POST', body: JSON.stringify(body) });
      if (!res.ok) throw new Error('API通信エラー');
      onNavigate('settings', { ...savedSettings, ...body });
      setToast(`${changes.length}件の変更を保存しました`);
      setTimeout(() => setToast(null), 2600);
    } catch (e) {
      setError(e.message || '保存に失敗しました');
    } finally {
      setSaving(false);
    }
  };

  const apiConfigured = !!(savedSettings?.apiKey && savedSettings?.apiSecret);

  return (
    <>
      <section className="hero-preview">
        <div className="hero-preview__label">次回の積立</div>
        <h1 ref={headingRef} tabIndex={-1} className="hero-preview__value">
          {hasSaved ? nextRun(frequency, frequency === 'daily' ? 1 : scheduleDay, scheduleTime) : '—'}
        </h1>
        <div className="hero-preview__meta">
          <span>BTC</span>
          <span className="dot-sep">•</span>
          <span>{fmtYen(amount)}</span>
          <span className="dot-sep">•</span>
          <span>{fmtSchedule(frequency, scheduleDay)} {fmtTime(scheduleTime)}</span>
        </div>
      </section>

      <main className="settings-grid">
        <AmountField value={amount} saved={savedAmount} onChange={setAmount} />
        <ScheduleField
          frequency={frequency}
          day={scheduleDay}
          savedFrequency={savedFrequency}
          savedDay={savedDay}
          onChangeFreq={handleFreqChange}
          onChangeDay={setScheduleDay}
        />
        <TimeField value={scheduleTime} saved={savedTime} onChange={setScheduleTime} />

        <BalanceCard apiConfigured={apiConfigured} />

        <FieldCard
          label="GMOコイン API"
          icon="⚙"
          linkLike
          onClick={() => onNavigate('api')}
          rightAdornment={<span className="chev" aria-hidden>›</span>}
          currentDisplay={
            <div className="api-status">
              <span className={`api-dot ${apiConfigured ? 'api-dot--ok' : ''}`} />
              {apiConfigured ? '接続済み' : '未設定'}
            </div>
          }
        >
          <div className="kv-row">
            <span>APIキー</span>
            <span className="kv-row__val">{savedSettings?.apiKey ? maskApiKey(savedSettings.apiKey) : '未設定'}</span>
          </div>
          <div className="kv-row">
            <span>APIシークレット</span>
            <span className="kv-row__val">{savedSettings?.apiSecret ? '設定済み' : '未設定'}</span>
          </div>
        </FieldCard>
      </main>

      <div className="spacer-bottom" />

      {error && <p className="error-message" role="alert" style={{ textAlign: 'center' }}>{error}</p>}

      <div className={`save-bar ${hasChanges ? 'save-bar--visible' : ''}`} role="region" aria-label="変更の保存">
        <div className="save-bar__inner">
          <div className="save-bar__summary">
            <div className="save-bar__count">
              <span className="save-bar__num">{changes.length}</span>
              <span className="save-bar__countLabel">件の変更</span>
            </div>
            <ul className="save-bar__list">
              {changes.slice(0, 3).map((c) => (
                <li key={c.k}>
                  <span className="save-bar__listLabel">{c.label}</span>
                  <span className="save-bar__before">{c.before}</span>
                  <span className="save-bar__arrow" aria-hidden>→</span>
                  <span className="save-bar__after">{c.after}</span>
                </li>
              ))}
            </ul>
          </div>
          <div className="save-bar__actions">
            <button type="button" className="btn btn--ghost" onClick={discard} disabled={saving}>破棄</button>
            <button type="button" className="btn btn--primary" onClick={save} disabled={!canSave}>
              {saving ? '保存中…' : '保存する'}
            </button>
          </div>
        </div>
      </div>

      {toast && (
        <div className="toast" role="status">
          <span className="toast__check" aria-hidden>✓</span>
          {toast}
        </div>
      )}
    </>
  );
}

const FIELD_LABEL = { time: '積立時間', amount: '積立金額', schedule: 'スケジュール', api: 'API設定' };

function fmtHistDate(iso) {
  const d = new Date(iso);
  const m = d.getMonth() + 1;
  const day = d.getDate();
  const h = String(d.getHours()).padStart(2, '0');
  const min = String(d.getMinutes()).padStart(2, '0');
  const wd = ['日', '月', '火', '水', '木', '金', '土'][d.getDay()];
  return `${d.getFullYear()}/${m}/${day}(${wd}) ${h}:${min}`;
}
function fmtDateShort(iso) {
  const d = new Date(iso);
  const day = d.getDate();
  const wd = ['日', '月', '火', '水', '木', '金', '土'][d.getDay()];
  return { day, wd };
}
function fmtTimeShort(iso) {
  const d = new Date(iso);
  const h = String(d.getHours()).padStart(2, '0');
  const min = String(d.getMinutes()).padStart(2, '0');
  return `${h}:${min}`;
}
function ymKey(iso) {
  const d = new Date(iso);
  return `${d.getFullYear()}年${d.getMonth() + 1}月`;
}

function HistoryItem({ item }) {
  const { day, wd } = fmtDateShort(item.at);
  const time = fmtTimeShort(item.at);

  if (item.type === 'purchase') {
    const ok = item.status === 'ok';
    return (
      <article className={`tl-row tl-row--purchase ${ok ? '' : 'tl-row--failed'}`}>
        <div className="tl-date" aria-label={fmtHistDate(item.at)}>
          <span className="tl-date__day mono">{day}</span>
          <span className="tl-date__wd">{wd}</span>
        </div>
        <div className="tl-rail" aria-hidden>
          <span className="tl-rail__dot"></span>
        </div>
        <div className="tl-body">
          {ok ? (
            <>
              <div className="tl-line">
                <span className="tl-amount mono">¥{Number(item.amount).toLocaleString('ja-JP')}</span>
                <span className="tl-arrow" aria-hidden>→</span>
                <span className="tl-btc mono">{Number(item.btc).toFixed(5)}<em>BTC</em></span>
              </div>
              <div className="tl-meta">
                <span className="tl-meta__time mono">{time}</span>
                {item.rate && (
                  <>
                    <span className="tl-meta__sep">·</span>
                    <span className="tl-meta__rate">1BTC = <span className="mono">¥{Math.round(item.rate).toLocaleString('ja-JP')}</span></span>
                  </>
                )}
              </div>
            </>
          ) : (
            <>
              <div className="tl-line">
                <span className="tl-fail-badge">失敗</span>
                <span className="tl-fail-reason">{item.reason || 'エラー'}</span>
              </div>
              <div className="tl-meta">
                <span className="tl-meta__time mono">{time}</span>
                {item.amount != null && (
                  <>
                    <span className="tl-meta__sep">·</span>
                    <span>¥{Number(item.amount).toLocaleString('ja-JP')} 予定</span>
                  </>
                )}
              </div>
            </>
          )}
        </div>
      </article>
    );
  }

  return (
    <article className="tl-row tl-row--change">
      <div className="tl-date" aria-label={fmtHistDate(item.at)}>
        <span className="tl-date__day mono">{day}</span>
        <span className="tl-date__wd">{wd}</span>
      </div>
      <div className="tl-rail" aria-hidden>
        <span className="tl-rail__dot tl-rail__dot--change"></span>
      </div>
      <div className="tl-body">
        <div className="tl-line tl-line--change">
          <span className="tl-change-label">{FIELD_LABEL[item.field] || item.field}</span>
          <span className="tl-change-diff">
            <span className="tl-change-before">{item.before}</span>
            <span className="tl-arrow" aria-hidden>→</span>
            <span className="tl-change-after">{item.after}</span>
          </span>
        </div>
        <div className="tl-meta">
          <span className="tl-meta__time mono">{time}</span>
        </div>
      </div>
    </article>
  );
}

function HistoryPage({ headingRef }) {
  const [filter, setFilter] = useState('all');
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const res = await fetch(HISTORY_URL);
        if (!res.ok) throw new Error('履歴取得エラー');
        const body = await res.json();
        if (!cancelled) setItems(Array.isArray(body.items) ? body.items : []);
      } catch (e) {
        if (!cancelled) setError(e.message || '履歴取得エラー');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const counts = {
    all: items.length,
    purchase: items.filter((i) => i.type === 'purchase').length,
    change: items.filter((i) => i.type === 'change').length,
  };

  const filtered = items.filter((it) => (filter === 'all' ? true : it.type === filter));

  const groups = [];
  for (const it of filtered) {
    const k = ymKey(it.at);
    let g = groups.find((x) => x.key === k);
    if (!g) { g = { key: k, items: [] }; groups.push(g); }
    g.items.push(it);
  }

  const stats = items.reduce((acc, it) => {
    if (it.type === 'purchase' && it.status === 'ok') {
      acc.count += 1;
      acc.totalJpy += Number(it.amount) || 0;
      acc.totalBtc += Number(it.btc) || 0;
    }
    return acc;
  }, { count: 0, totalJpy: 0, totalBtc: 0 });

  return (
    <main className="hist-main">
      <h1 ref={headingRef} tabIndex={-1} className="visually-hidden">履歴</h1>

      <section className="hist-stats">
        <div className="hist-stats__primary">
          <span className="hist-stats__label">累計</span>
          <span className="hist-stats__btc">
            <span className="mono">{stats.totalBtc.toFixed(5)}</span>
            <em>BTC</em>
          </span>
        </div>
        <div className="hist-stats__divider" aria-hidden></div>
        <div className="hist-stats__secondary">
          <div className="hist-stats__kv">
            <span className="hist-stats__l">投入額</span>
            <span className="hist-stats__r mono">¥{stats.totalJpy.toLocaleString('ja-JP')}</span>
          </div>
          <div className="hist-stats__kv">
            <span className="hist-stats__l">実行</span>
            <span className="hist-stats__r mono">{stats.count}<em>回</em></span>
          </div>
        </div>
      </section>

      <div className="hist-filter" role="tablist" aria-label="履歴フィルタ">
        {[
          { k: 'all', label: 'すべて' },
          { k: 'purchase', label: '積立' },
          { k: 'change', label: '設定変更' },
        ].map((f) => (
          <button
            key={f.k}
            type="button"
            role="tab"
            aria-selected={filter === f.k}
            className="hist-filter__item"
            data-active={filter === f.k}
            onClick={() => setFilter(f.k)}
          >
            <span>{f.label}</span>
            <span className="hist-filter__count">{counts[f.k]}</span>
          </button>
        ))}
      </div>

      {loading && <div className="hist-empty">読み込み中…</div>}
      {!loading && error && <div className="hist-empty">{error}</div>}
      {!loading && !error && groups.length === 0 && (
        <div className="hist-empty">該当する履歴がありません</div>
      )}

      {groups.map((g) => (
        <section key={g.key} className="hist-month">
          <h2 className="hist-month__title">{g.key}</h2>
          <div className="hist-timeline">
            {g.items.map((it) => (
              <HistoryItem key={it.id} item={it} />
            ))}
          </div>
        </section>
      ))}
    </main>
  );
}

function HomePage({ savedSettings, onNavigate, headingRef }) {
  const [tab, setTab] = useState('settings');

  return (
    <div className="app">
      <header className="top-bar">
        <div className="top-bar__inner">
          <div className="brand">
            <span className="brand__mark" aria-hidden>₿</span>
            <span className="brand__name">ツミビット</span>
          </div>
          <button
            type="button"
            className="icon-btn"
            aria-label="メニュー"
            onClick={() => onNavigate('menu')}
          >
            <span className="icon-btn__dot" />
            <span className="icon-btn__dot" />
            <span className="icon-btn__dot" />
          </button>
        </div>
        <nav className="home-tabs" role="tablist" aria-label="画面切替">
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'settings'}
            className="home-tab"
            data-active={tab === 'settings'}
            onClick={() => setTab('settings')}
          >
            <span className="home-tab__icon" aria-hidden>◷</span>
            <span>積立設定</span>
          </button>
          <button
            type="button"
            role="tab"
            aria-selected={tab === 'history'}
            className="home-tab"
            data-active={tab === 'history'}
            onClick={() => setTab('history')}
          >
            <span className="home-tab__icon" aria-hidden>⧗</span>
            <span>履歴</span>
          </button>
        </nav>
      </header>

      {tab === 'settings' && (
        <SettingsPage
          savedSettings={savedSettings}
          onNavigate={onNavigate}
          headingRef={headingRef}
        />
      )}
      {tab === 'history' && <HistoryPage headingRef={headingRef} />}
    </div>
  );
}

function MenuPage({ onNavigate, headingRef }) {
  return (
    <div className="app">
      <TopBar title="アカウント" center onBack={() => onNavigate('home')} />
      <h1 ref={headingRef} tabIndex={-1} className="visually-hidden">アカウント</h1>
      <div className="menu-list">
        <button className="menu-item" onClick={() => onNavigate('api')}>
          <span className="menu-item__icon">⚙</span>
          <span className="menu-item__body">
            <span className="menu-item__title">GMOコイン API設定</span>
            <span className="menu-item__sub">取引APIキー / シークレット</span>
          </span>
          <span className="chev" aria-hidden>›</span>
        </button>
      </div>
    </div>
  );
}

function ApiPage({ savedSettings, onNavigate, onSaved, headingRef }) {
  const [key, setKey] = useState(savedSettings?.apiKey || '');
  const [secret, setSecret] = useState(savedSettings?.apiSecret || '');
  const [showKey, setShowKey] = useState(false);
  const [showSecret, setShowSecret] = useState(false);
  const [saved, setSaved] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  const handleSave = async () => {
    if (!key || !secret) return;
    if (!savedSettings) { setError('設定の読み込みが完了していません'); return; }
    setBusy(true);
    setError('');
    try {
      const body = { ...savedSettings, apiKey: key, apiSecret: secret };
      const res = await fetch(API_URL, { method: 'POST', body: JSON.stringify(body) });
      if (!res.ok) throw new Error('API通信エラー');
      setSaved(true);
      onSaved(body);
      setTimeout(() => onNavigate('home'), 800);
    } catch (e) {
      setError(e.message || '保存に失敗しました');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="app">
      <TopBar title="API設定" center onBack={() => onNavigate('menu')} />
      <h1 ref={headingRef} tabIndex={-1} className="visually-hidden">API設定</h1>
      <main className="form-page">
        <div className="callout">
          <div className="callout__title">GMOコイン 取引API</div>
          <div className="callout__body">取引権限を有効にしたAPIキーを発行して入力してください。暗号化して保存されます。</div>
        </div>

        <label className="input-block">
          <span className="input-block__label">APIキー</span>
          <div className="input-affix">
            <input
              type={showKey ? 'text' : 'password'}
              value={key}
              onChange={(e) => setKey(e.target.value)}
              placeholder="••••••••••••••••"
              autoComplete="off"
            />
            <button type="button" className="affix-btn" onClick={() => setShowKey(!showKey)}>
              {showKey ? '隠す' : '表示'}
            </button>
          </div>
        </label>

        <label className="input-block">
          <span className="input-block__label">APIシークレット</span>
          <div className="input-affix">
            <input
              type={showSecret ? 'text' : 'password'}
              value={secret}
              onChange={(e) => setSecret(e.target.value)}
              placeholder="••••••••••••••••"
              autoComplete="off"
            />
            <button type="button" className="affix-btn" onClick={() => setShowSecret(!showSecret)}>
              {showSecret ? '隠す' : '表示'}
            </button>
          </div>
        </label>

        <button
          type="button"
          className="btn btn--primary btn--block"
          disabled={!key || !secret || busy}
          onClick={handleSave}
        >
          {busy ? '保存中…' : '保存する'}
        </button>
        {error && <p className="error-message" role="alert">{error}</p>}
        {saved && (
          <div className="toast toast--inline">
            <span className="toast__check">✓</span>API設定を保存しました
          </div>
        )}
      </main>
    </div>
  );
}

function MainApp() {
  const [page, setPage] = useState('home');
  const [savedSettings, setSavedSettings] = useState(null);
  const headingRef = useRef(null);

  useEffect(() => {
    headingRef.current?.focus();
  }, [page]);

  useEffect(() => {
    const load = async () => {
      try {
        const res = await fetch(API_URL);
        if (!res.ok) return;
        const data = await res.json();
        setSavedSettings({
          amount: data.amount ?? 10000,
          frequency: data.frequency || 'monthly',
          scheduleDay: data.scheduleDay ?? 1,
          scheduleTime: data.scheduleTime ?? 0,
          apiKey: data.apiKey || '',
          apiSecret: data.apiSecret || '',
        });
      } catch {
        /* noop */
      }
    };
    load();
  }, []);

  const navigate = (next, updated) => {
    if (updated) setSavedSettings(updated);
    setPage(next);
  };

  const navigateAfterSave = (target, updated) => {
    if (updated) setSavedSettings(updated);
    setPage(target === 'settings' ? 'home' : target);
  };

  return (
    <div className="root">
      {page === 'home' && (
        <HomePage
          savedSettings={savedSettings}
          onNavigate={navigateAfterSave}
          headingRef={headingRef}
        />
      )}
      {page === 'menu' && (
        <MenuPage onNavigate={navigate} headingRef={headingRef} />
      )}
      {page === 'api' && (
        <ApiPage
          savedSettings={savedSettings}
          onNavigate={navigate}
          onSaved={(next) => setSavedSettings(next)}
          headingRef={headingRef}
        />
      )}
    </div>
  );
}

export default MainApp;
