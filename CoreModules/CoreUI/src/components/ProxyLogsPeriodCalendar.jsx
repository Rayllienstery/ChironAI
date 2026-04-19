import { useState } from 'react';

const WEEKDAY_HEADERS = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'];

function getDaysInMonth(year, month) {
  const first = new Date(year, month, 1);
  const last = new Date(year, month + 1, 0);
  const days = [];
  const startPad = first.getDay();
  for (let i = 0; i < startPad; i++) {
    days.push(null);
  }
  for (let d = 1; d <= last.getDate(); d++) {
    days.push(new Date(year, month, d));
  }
  return days;
}

function ProxyLogsPeriodCalendar({ selectedDate, onDateSelect, onDateReset }) {
  const now = new Date();
  const [viewDate, setViewDate] = useState(() => selectedDate || new Date(now.getFullYear(), now.getMonth(), 1));
  const year = viewDate.getFullYear();
  const month = viewDate.getMonth();
  const days = getDaysInMonth(year, month);
  const monthLabel = viewDate.toLocaleDateString(undefined, { month: 'long', year: 'numeric' });

  const isSelected = (d) => {
    if (!d || !selectedDate) return false;
    return d.getFullYear() === selectedDate.getFullYear() &&
      d.getMonth() === selectedDate.getMonth() &&
      d.getDate() === selectedDate.getDate();
  };

  const isToday = (d) => {
    if (!d) return false;
    return d.getFullYear() === now.getFullYear() &&
      d.getMonth() === now.getMonth() &&
      d.getDate() === now.getDate();
  };

  const goPrevMonth = () => setViewDate(new Date(year, month - 1, 1));
  const goNextMonth = () => setViewDate(new Date(year, month + 1, 1));

  return (
    <div className="proxy-logs-calendar" role="application" aria-label="Calendar to select a day for proxy logs">
      <div className="proxy-logs-calendar-header">
        <button
          type="button"
          className="proxy-logs-calendar-nav"
          onClick={goPrevMonth}
          aria-label="Previous month"
        >
          ‹
        </button>
        <span className="proxy-logs-calendar-month">{monthLabel}</span>
        <button
          type="button"
          className="proxy-logs-calendar-nav"
          onClick={goNextMonth}
          aria-label="Next month"
        >
          ›
        </button>
      </div>
      <div className="proxy-logs-calendar-weekdays">
        {WEEKDAY_HEADERS.map((w) => (
          <span key={w} className="proxy-logs-calendar-weekday">{w}</span>
        ))}
      </div>
      <div className="proxy-logs-calendar-grid">
        {days.map((d, idx) => (
          <button
            key={d ? d.toISOString() : `empty-${idx}`}
            type="button"
            className={`proxy-logs-calendar-day ${!d ? 'empty' : ''} ${isSelected(d) ? 'selected' : ''} ${isToday(d) ? 'today' : ''}`}
            disabled={!d}
            onClick={() => d && onDateSelect(d)}
            aria-label={d ? d.toLocaleDateString() : ''}
            aria-pressed={d ? isSelected(d) : undefined}
          >
            {d ? d.getDate() : ''}
          </button>
        ))}
      </div>
      {selectedDate && (
        <button
          type="button"
          className="proxy-logs-calendar-reset"
          onClick={onDateReset}
          aria-label="Reset day selection and show period range"
        >
          Reset day
        </button>
      )}
    </div>
  );
}

export default ProxyLogsPeriodCalendar;
