import { useEffect, useRef, useState } from 'react';

export default function OverviewExplanation({ overviewId, chartType, title }) {
  const [status, setStatus] = useState('idle');
  const [explanation, setExplanation] = useState('');
  const [error, setError] = useState('');
  const active = useRef(null);

  useEffect(() => () => active.current?.abort(), []);

  async function explain() {
    if (status === 'loading') return;
    const controller = new AbortController();
    active.current = controller;
    setStatus('loading');
    setError('');
    try {
      const response = await fetch('/api/overview/explain', {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, signal: controller.signal,
        body: JSON.stringify({ overview_id: overviewId, chart_type: chartType }),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.error === 'string' ? data.error : data.error?.message || 'The explanation is unavailable. Try again.');
      setExplanation(data.explanation);
      setStatus('complete');
    } catch (failure) {
      if (controller.signal.aborted) return;
      setError(failure.message);
      setStatus('failed');
    }
  }

  return <div className="overview-explanation" aria-busy={status === 'loading'}>
    <button className="secondary-button" type="button" disabled={!overviewId || status === 'loading' || status === 'complete'}
      aria-label={`Explain ${title}`} onClick={explain}>
      {status === 'loading' ? 'Explaining…' : status === 'complete' ? 'Explanation' : 'Explain with AI'}
    </button>
    <div aria-live="polite">
      {explanation && <p className="overview-explanation-text">{explanation}</p>}
      {error && <p className="error-text" role="alert">{error}</p>}
    </div>
  </div>;
}
