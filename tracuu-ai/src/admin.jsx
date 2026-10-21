import React,{useState,useEffect} from 'react';
import {api,useApi} from './api.js';
import {Icon,Btn} from './ui.jsx';
import {ErrorNote} from './search.jsx';

function Admin({region}){
  const [tab,setTab]=useState('overview');
  const tabs=[['overview','Tổng quan'],['kb','Knowledge Base'],['groups','Phân quyền'],['jobs','Đồng bộ dữ liệu']];
  return <div className="page">
    <div className="page-h"><div><h2>Quản trị</h2><p className="muted">Amazon Bedrock Knowledge Bases{region?' · '+region:''}</p></div></div>
    <div className="tabs">{tabs.map(([k,l])=><button key={k} className={tab===k?'on':''} onClick={()=>setTab(k)}>{l}</button>)}</div>
    {tab==='overview'&&<Overview/>}{tab==='kb'&&<KbConfig/>}{tab==='groups'&&<Groups/>}{tab==='jobs'&&<Jobs/>}
  </div>;
}

const fmt=n=>n.toLocaleString('vi-VN');

function Overview(){
  const {data:o,error,reload}=useApi(()=>api('/api/admin/overview'),[]);
  if(error) return <ErrorNote error={error} onRetry={reload}/>;
  if(!o) return <div className="skel"><i></i><i></i></div>;
  const max=Math.max(1,...o.queries_by_day);
  const tiles=[['Truy vấn · 28 ngày',fmt(o.queries_28d),'trên toàn hệ thống'],
    ['Tài liệu đã lập chỉ mục',fmt(o.docs_indexed),`${o.docs_pending} đang chờ xử lý · ${o.docs_failed} lỗi`],
    ['Phản hồi hữu ích',o.helpful_pct==null?'—':o.helpful_pct+'%',`trên ${fmt(o.ratings)} đánh giá`],
    ['Chưa có câu trả lời',fmt(o.unanswered_28d),'câu hỏi không tìm thấy nguồn']];
  return <>
    <div className="stats">{tiles.map(([l,v,s])=><div key={l} className="stat"><div className="muted sm">{l}</div><div className="stat-v">{v}</div><div className="muted sm">{s}</div></div>)}</div>
    <div className="card"><div className="card-h"><b>Truy vấn theo ngày</b><span className="muted sm">28 ngày</span></div>
      <div className="bars">{o.queries_by_day.map((v,i)=><i key={i} title={v+' truy vấn'} style={{height:(v/max*100)+'%'}}></i>)}</div></div>
  </>;
}

const SELECTS={model:['Claude Sonnet','Claude Haiku','Claude Opus'],emb:['Titan Text Embeddings V2','Cohere Embed Multilingual'],chunk:['Theo ngữ nghĩa','Kích thước cố định','Phân cấp']};

function KbConfig(){
  const {data,error,reload}=useApi(()=>api('/api/admin/kb-config'),[]);
  const [c,setC]=useState(null);
  const [saved,setSaved]=useState(false);const [dirty,setDirty]=useState(false);const [err,setErr]=useState('');
  useEffect(()=>{if(data)setC(data)},[data]);
  if(error) return <ErrorNote error={error} onRetry={reload}/>;
  if(!c) return <div className="skel"><i></i><i></i></div>;
  const set=(k,v)=>{setC({...c,[k]:v});setDirty(true);setSaved(false)};
  const save=()=>api('/api/admin/kb-config',{method:'PUT',body:c}).then(r=>{setC(r);setSaved(true);setDirty(false);setErr('')},e=>setErr(e.message));
  const Tog=({k,l,d})=><div className="cfg-row"><div><b>{l}</b><div className="muted sm">{d}</div></div><button className={'toggle'+(c[k]?' on':'')} onClick={()=>set(k,!c[k])}><i></i></button></div>;
  const Sel=({k,l})=><label className="field"><span>{l}</span><select className="select" value={c[k]} onChange={e=>set(k,e.target.value)}>{SELECTS[k].map(o=><option key={o}>{o}</option>)}</select></label>;
  return <div className="two">
    <div className="card">
      <div className="card-h"><b>Mô hình</b></div>
      <Sel k="model" l="Mô hình sinh câu trả lời"/>
      <Sel k="emb" l="Mô hình embedding"/>
      <label className="field"><span>Số đoạn truy xuất (top-k): <b>{c.topk}</b></span><input type="range" min="2" max="20" value={c.topk} onChange={e=>set('topk',+e.target.value)}/></label>
      <Tog k="rerank" l="Xếp hạng lại (rerank)" d="Sắp xếp lại kết quả truy xuất trước khi sinh câu trả lời"/>
    </div>
    <div className="card">
      <div className="card-h"><b>Chia đoạn & an toàn</b></div>
      <Sel k="chunk" l="Chiến lược chia đoạn"/>
      <label className="field"><span>Kích thước đoạn: <b>{c.size} token</b></span><input type="range" min="128" max="1024" step="64" value={c.size} onChange={e=>set('size',+e.target.value)}/></label>
      <label className="field"><span>Chồng lấn: <b>{c.overlap}%</b></span><input type="range" min="0" max="30" value={c.overlap} onChange={e=>set('overlap',+e.target.value)}/></label>
      <Tog k="guard" l="Bedrock Guardrails" d="Chặn nội dung độc hại và câu hỏi ngoài phạm vi"/>
      <Tog k="pii" l="Ẩn thông tin cá nhân (PII)" d="Che số CCCD, số tài khoản trong câu trả lời"/>
    </div>
    <div className="save-bar">{saved?<span className="pill ok"><Icon n="check" s={12}/>Đã lưu · thay đổi chia đoạn sẽ áp dụng ở lần đồng bộ tiếp theo</span>:<span className="muted sm" style={err?{color:'var(--bad)'}:undefined}>{err||(dirty?'Có thay đổi chưa lưu':'Không có thay đổi')}</span>}<span className="grow1"></span><Btn kind="primary" disabled={!dirty} onClick={save}>Lưu cấu hình</Btn></div>
  </div>;
}

function Groups(){
  const {data,error,reload}=useApi(()=>api('/api/admin/groups'),[]);
  if(error) return <ErrorNote error={error} onRetry={reload}/>;
  return <div className="card">
    <div className="card-h"><b>Nhóm người dùng</b><span className="muted sm">Đồng bộ từ IdP qua Cognito · dùng làm bộ lọc metadata khi truy xuất</span></div>
    <div className="table flat">
      <div className="tr th"><span className="grow1">Nhóm</span><span className="w120">Thành viên</span><span className="w120">Bộ sưu tập</span><span className="w160 hide-sm">Nguồn</span></div>
      {(data?.items||[]).map(g=><div key={g.name} className="tr"><span className="grow1"><b>{g.name}</b></span><span className="w120">{g.members==null?'—':fmt(g.members)}</span><span className="w120">{g.docs}</span><span className="w160 mono muted sm hide-sm">{g.src||'—'}</span></div>)}
    </div>
  </div>;
}

function Jobs(){
  const {data,error,reload,setData}=useApi(()=>api('/api/admin/jobs'),[]);
  const jobs=data?.items||[];
  const running=jobs.some(j=>j.status==='IN_PROGRESS');
  const [err,setErr]=useState('');
  useEffect(()=>{
    if(!running) return;
    const t=setInterval(()=>api('/api/admin/jobs').then(setData,()=>{}),3000);
    return()=>clearInterval(t);
  },[running]);
  const run=()=>api('/api/admin/jobs',{method:'POST'}).then(()=>{setErr('');reload()},e=>setErr(e.message));
  return <div className="card">
    <div className="card-h"><b>Lần đồng bộ (ingestion job)</b><span className="grow1"></span><Btn kind="primary" icon="up" onClick={run} disabled={running}>Đồng bộ ngay</Btn></div>
    {err&&<p className="sm" style={{color:'var(--bad)'}}>{err}</p>}
    <div className="table flat">
      <div className="tr th"><span className="w120">Job</span><span className="grow1">Nguồn</span><span className="w120 hide-sm">Bắt đầu</span><span className="w120">Tài liệu</span><span className="w120 hide-sm">Thời gian</span><span className="w160">Trạng thái</span></div>
      {jobs.map(j=><div key={j.id} className="tr"><span className="w120 mono sm">{j.id}</span><span className="grow1 mono sm muted">{j.source}</span><span className="w120 muted hide-sm">{j.started}</span><span className="w120">{j.docs}</span><span className="w120 muted hide-sm">{j.duration}</span>
        <span className="w160">{j.status==='COMPLETE'?<span className="pill ok">Hoàn tất</span>:j.status==='FAILED'?<span className="pill bad">Lỗi · xem log</span>:<span className="pill acc"><span className="spin sm"></span>Đang chạy</span>}</span></div>)}
      {error&&<ErrorNote error={error} onRetry={reload}/>}
    </div>
  </div>;
}
export {Admin};
