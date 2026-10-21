import { useCallback, useEffect, useState } from 'react';

export class ApiError extends Error {
  constructor(status, message) {
    super(message);
    this.status = status;
  }
}

// Ở chế độ dev backend không có ALB/Cognito; vai trò giả lập lấy từ panel "Tuỳ chỉnh".
function devHeaders() {
  if (!import.meta.env.DEV) return {};
  try {
    const role = JSON.parse(localStorage.getItem('tracuu-settings') || '{}').role;
    return { 'X-Dev-Role': role === 'Nhân viên' ? 'staff' : 'admin' };
  } catch {
    return {};
  }
}

async function request(path, { method = 'GET', body, signal } = {}) {
  const res = await fetch(path, {
    method, signal,
    headers: { ...(body !== undefined ? { 'Content-Type': 'application/json' } : {}), ...devHeaders() },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (!res.ok) {
    let msg = res.statusText;
    try { msg = (await res.json()).error || msg; } catch { /* không phải JSON */ }
    throw new ApiError(res.status, msg);
  }
  return res;
}

export async function api(path, opts) {
  const res = await request(path, opts);
  return res.status === 204 ? null : res.json();
}

/** POST /api/ask và đọc luồng SSE; gọi onEvent cho từng sự kiện {type, ...}. */
export async function askStream(question, { sessionId, docId, save = true, signal, onEvent }) {
  const res = await request('/api/ask', { method: 'POST', signal, body: { question, session_id: sessionId, doc_id: docId, save } });
  const reader = res.body.getReader();
  const dec = new TextDecoder();
  let buf = '';
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf('\n\n')) >= 0) {
      const block = buf.slice(0, i);
      buf = buf.slice(i + 2);
      const data = block.split('\n').find(l => l.startsWith('data: '));
      if (data) onEvent(JSON.parse(data.slice(6)));
    }
  }
}

/** Tải tài liệu lên S3 qua presigned URL (trình duyệt PUT thẳng, không qua container). */
export async function uploadFile(file, { groups, dept }) {
  const ticket = await api('/api/uploads', { method: 'POST', body: { filename: file.name, size: file.size, groups, dept } });
  const put = await fetch(ticket.upload_url, {
    method: 'PUT', body: file, headers: { 'Content-Type': ticket.content_type, ...devHeaders() },
  });
  if (!put.ok) throw new ApiError(put.status, 'Tải tệp lên thất bại');
  return ticket.doc;
}

/** Gọi fn khi deps đổi; trả về {data, error, loading, reload, setData}. */
export function useApi(fn, deps) {
  const [state, setState] = useState({ data: null, error: null, loading: true });
  const run = useCallback(() => {
    let live = true;
    setState(s => ({ ...s, loading: true, error: null }));
    fn().then(data => live && setState({ data, error: null, loading: false }),
              error => live && setState({ data: null, error, loading: false }));
    return () => { live = false; };
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(run, [run]);
  return { ...state, reload: run, setData: data => setState(s => ({ ...s, data })) };
}
