import React, { useState } from 'react';

// Chỉ hiển thị khi chạy `npm run dev`: giả lập vai trò vì dev không có Cognito.

export const LAYOUTS = { 'Cổ điển': 'sidebar', 'Trả lời trước': 'topbar', 'Không gian': 'rail' };
export const ACCENTS = { '#d0662f': ['#a64b1b', '#fbece2'], '#c2542f': ['#9a3d1d', '#f8e6df'], '#b8782a': ['#8a5717', '#f6ecdc'] };
const ROLES = ['Nhân viên', 'Quản trị viên'];

function Seg({ label, value, options, onChange }) {
  return <div className="set-row"><span className="set-l">{label}</span>
    <div className="chips">{options.map(o => <button key={o} className={'chip sm' + (value === o ? ' on' : '')} onClick={() => onChange(o)}>{o}</button>)}</div></div>;
}

export default function SettingsPanel({ s, setS }) {
  const [open, setOpen] = useState(false);
  return <div className="settings">
    {open && <div className="settings-pop">
      <Seg label="Bố cục" value={s.layout} options={Object.keys(LAYOUTS)} onChange={v => setS({ ...s, layout: v })} />
      <Seg label="Vai trò" value={s.role} options={ROLES} onChange={v => setS({ ...s, role: v })} />
      <div className="set-row"><span className="set-l">Màu nhấn</span>
        <div className="row">{Object.keys(ACCENTS).map(c => <button key={c} className={'swatch' + (s.accent === c ? ' on' : '')} style={{ background: c }} title={c} onClick={() => setS({ ...s, accent: c })} />)}</div></div>
    </div>}
    <button className="btn btn-dark settings-btn" onClick={() => setOpen(o => !o)}>Tuỳ chỉnh</button>
  </div>;
}
