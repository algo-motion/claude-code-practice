import React,{useState,useEffect,useMemo} from 'react';
import {SUGGESTIONS} from './data.js';
import {api,askStream,useApi} from './api.js';
import {Icon,useStream,RichAnswer,TypeTag,Btn,Placeholder} from './ui.jsx';

function ErrorNote({error,onRetry}){
  return <div className="empty-note">{error.status===403?'Bạn không có quyền xem nội dung này.':'Không tải được dữ liệu. '+(error.message||'')}{onRetry&&<> <button className="link" onClick={onRetry}>Thử lại</button></>}</div>;
}

// Tô sáng từ khoá bằng phần tử React, không dùng dangerouslySetInnerHTML nên nội dung tài liệu không thể chèn HTML.
function Highlight({text,query}){
  const words=[...new Set((query||'').toLowerCase().match(/[\p{L}\p{N}]{2,}/gu)||[])];
  if(!words.length) return text;
  const re=new RegExp('('+words.map(w=>w.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('|')+')','giu');
  return text.split(re).map((p,i)=>i%2?<mark key={i}>{p}</mark>:p);
}

function SearchBox({value,onChange,onSubmit,big,autoFocus}){
  return <form className={'sbox'+(big?' big':'')} onSubmit={e=>{e.preventDefault();value.trim()&&onSubmit(value.trim())}}>
    <Icon n="search" s={big?22:18}/>
    <input autoFocus={autoFocus} value={value} onChange={e=>onChange(e.target.value)} maxLength={2000} placeholder="Hỏi bằng ngôn ngữ tự nhiên hoặc nhập từ khoá…"/>
    {value&&<button type="button" className="icon-btn" onClick={()=>onChange('')}><Icon n="x" s={15}/></button>}
    <button className="btn btn-primary" disabled={!value.trim()}>Tìm<Icon n="arr" s={15}/></button>
  </form>;
}

function SearchHome({user,onSearch,openDoc}){
  const [q,setQ]=useState('');
  const hist=useApi(()=>api('/api/history'),[]);
  const docs=useApi(()=>api('/api/documents'),[]);
  return <div className="page home">
    <div className="home-hero">
      <div className="eyebrow">Xin chào, {user.name.split(' ').pop()}</div>
      <h1>Bạn cần tìm gì trong kho tài liệu?</h1>
      <SearchBox big value={q} onChange={setQ} onSubmit={onSearch} autoFocus/>
      <div className="chips">{SUGGESTIONS.map(s=><button key={s} className="chip" onClick={()=>onSearch(s)}>{s}</button>)}</div>
    </div>
    <div className="home-cols">
      <section><h3 className="sec-h">Tìm kiếm gần đây</h3>
        <div className="list-plain">{(hist.data?.items||[]).slice(0,4).map(h=><button key={h.id} className="row-link" onClick={()=>onSearch(h.q)}><Icon n="hist" s={16}/><span className="grow1">{h.q}</span><span className="muted sm">{h.when}</span></button>)}
          {!hist.loading&&!hist.error&&!hist.data?.items.length&&<p className="muted sm">Chưa có tìm kiếm nào.</p>}</div></section>
      <section><h3 className="sec-h">Mới cập nhật</h3>
        <div className="list-plain">{(docs.data?.items||[]).slice(0,4).map(d=><button key={d.id} className="row-link" onClick={()=>openDoc(d)}><TypeTag t={d.type}/><span className="grow1">{d.title}</span><span className="muted sm">{d.updated}</span></button>)}</div></section>
    </div>
  </div>;
}

/** Câu trả lời AI cho trang tìm kiếm: stream từ /api/ask (save=false nên không tạo phiên chat). */
function AnswerCard({query,onCite,onChat,hero}){
  const [st,setSt]=useState({thinking:true,text:'',docs:[],done:false,error:null});
  const [fb,setFb]=useState(null);
  useEffect(()=>{
    const ac=new AbortController();let text='';
    setSt({thinking:true,text:'',docs:[],done:false,error:null});setFb(null);
    askStream(query,{save:false,signal:ac.signal,onEvent:ev=>{
      if(ev.type==='delta'){text+=ev.text;setSt(s=>({...s,thinking:false,text}));}
      else if(ev.type==='blocked'){text=ev.text;setSt(s=>({...s,thinking:false,text}));}
      else if(ev.type==='citations') setSt(s=>({...s,docs:ev.docs}));
      else if(ev.type==='error') setSt(s=>({...s,thinking:false,error:ev.message}));
      else if(ev.type==='done') setSt(s=>({...s,thinking:false,done:true}));
    }}).catch(e=>{if(!ac.signal.aborted)setSt(s=>({...s,thinking:false,done:true,error:e.message}))});
    return()=>ac.abort();
  },[query]);
  const {thinking,text,docs,done,error}=st;
  return <div className={'answer'+(hero?' hero':'')}>
    <div className="answer-h"><span className="ai-badge"><Icon n="spark" s={13}/>Trả lời từ AI</span>{done&&!error&&<span className="muted sm">Dựa trên {docs.length} tài liệu bạn có quyền truy cập</span>}</div>
    {thinking?<div className="skel"><i></i><i></i><i style={{width:'60%'}}></i></div>:
      error?<p className="answer-text">{error}</p>:<RichAnswer text={text} docs={docs} onCite={onCite} caret={!done}/>}
    {done&&!error&&<>
      <div className="sources">{docs.map((d,i)=><button key={d.id+i} className="source" onClick={()=>onCite(d)}><span className="cite static">{i+1}</span><span className="src-t">{d.title}</span>{d.page>0&&<span className="muted sm">tr. {d.page}</span>}</button>)}</div>
      <div className="answer-f"><Btn kind="soft" icon="chat" onClick={()=>onChat(query)}>Hỏi tiếp trong chat</Btn>
        <div className="grow1"></div>
        <span className="muted sm">{fb?'Cảm ơn phản hồi của bạn':'Câu trả lời có hữu ích?'}</span>
        {!fb&&<><button className="chip sm" onClick={()=>{setFb('y');api('/api/feedback',{method:'POST',body:{rating:'up'}}).catch(()=>{})}}>Có</button><button className="chip sm" onClick={()=>{setFb('n');api('/api/feedback',{method:'POST',body:{rating:'down'}}).catch(()=>{})}}>Không</button></>}
      </div></>}
  </div>;
}

function ResultItem({d,query,active,onClick,card}){
  return <button className={'result'+(active?' on':'')+(card?' card':'')} onClick={onClick}>
    <div className="result-top"><TypeTag t={d.type}/><span className="muted sm">{d.dept} · {d.updated}{d.pages>0&&' · '+d.pages+' trang'}</span><span className="grow1"></span><span className="score" title="Độ liên quan"><i style={{width:Math.round((d.score||0)*100)+'%'}}></i></span></div>
    <div className="result-t">{d.title}</div>
    <div className="result-s"><Highlight text={d.snippet||''} query={query}/></div>
    {!d.groups.includes('Toàn công ty')&&<div className="lock"><Icon n="lock" s={12}/>{d.group}</div>}
  </button>;
}

function Filters({f,setF,count}){
  const depts=['Nhân sự','Tài chính','Mua sắm','Pháp chế','CNTT'];const types=['PDF','DOCX','XLSX'];
  const tog=(k,v)=>setF({...f,[k]:f[k]===v?null:v});
  return <div className="filters">
    <span className="muted sm">{count} kết quả</span><span className="sep"></span>
    {types.map(t=><button key={t} className={'chip sm'+(f.type===t?' on':'')} onClick={()=>tog('type',t)}>{t}</button>)}<span className="sep"></span>
    {depts.map(t=><button key={t} className={'chip sm'+(f.dept===t?' on':'')} onClick={()=>tog('dept',t)}>{t}</button>)}
  </div>;
}

function Preview({d,onClose,onChat,mode}){
  const [summary,setSummary]=useState(null);const [loading,setLoading]=useState(false);const [err,setErr]=useState('');
  useEffect(()=>{setSummary(null);setLoading(false);setErr('')},[d&&d.id]);
  const text=summary?summary.map(s=>'• '+s).join('\n'):'';
  const {out,done}=useStream(text,d&&d.id+String(!!summary),10);
  if(!d) return <div className="preview empty"><Icon n="file" s={28}/><p>Chọn một kết quả để xem trước</p></div>;
  const indexed=d.status==='INDEXED';
  function summarize(){
    setLoading(true);setErr('');
    api(`/api/documents/${d.id}/summarize`,{method:'POST'}).then(r=>setSummary(r.summary),e=>setErr(e.message)).finally(()=>setLoading(false));
  }
  function download(){api(`/api/documents/${d.id}/download`).then(r=>window.open(r.url,'_blank','noopener'),e=>setErr(e.message))}
  return <div className={'preview '+(mode||'')}>
    <div className="pv-h"><TypeTag t={d.type}/><div className="grow1"><div className="pv-t">{d.title}</div><div className="muted sm">{d.dept} · {d.owner} · cập nhật {d.updated}</div></div>{onClose&&<button className="icon-btn" onClick={onClose}><Icon n="x"/></button>}</div>
    <div className="pv-actions">
      <Btn kind="soft" icon="spark" disabled={!!summary||loading||!indexed} onClick={summarize}>{loading?'Đang tóm tắt…':'Tóm tắt bằng AI'}</Btn>
      <Btn icon="chat" onClick={()=>onChat('Tài liệu "'+d.title+'" nói gì?',d)}>Hỏi về tài liệu</Btn>
      <Btn icon="down" onClick={download}>Tải xuống</Btn>
    </div>
    {err&&<p className="sm" style={{color:'var(--bad)',marginTop:10}}>{err}</p>}
    {(summary||loading)&&<div className="pv-sum"><div className="label">Tóm tắt</div>{loading?<div className="skel"><i></i><i style={{width:'75%'}}></i></div>:<div className="sum-text">{out}{!done&&<span className="caret"></span>}</div>}</div>}
    {d.passage&&<><div className="label">Đoạn được truy xuất {d.page>0&&<span className="mono muted">trang {d.page}</span>}</div>
    <div className="pv-passage">{d.passage.split('\n').map((l,i)=><p key={i} className={i===0?'b':''}>{l}</p>)}</div></>}
    <div className="pv-meta">
      <div><span>Quyền truy cập</span><b>{d.group}</b></div><div><span>Dung lượng</span><b>{d.size||'—'}</b></div><div><span>Số trang</span><b>{d.pages>0?d.pages:'—'}</b></div><div><span>Trạng thái</span><b className={indexed?'ok':''}>{indexed?'Đã lập chỉ mục':d.status==='FAILED'?'Lỗi lập chỉ mục':'Đang xử lý'}</b></div>
    </div>
    <Placeholder label={'trang tài liệu · '+d.type.toLowerCase()+' viewer'} h={260}/>
  </div>;
}

function Results({layout,query,onSearch,onChat}){
  const [q,setQ]=useState(query);const [f,setF]=useState({});
  const res=useApi(()=>api('/api/search',{method:'POST',body:{query}}),[query]);
  const all=res.data?.results||[];
  const list=all.filter(d=>(!f.type||d.type===f.type)&&(!f.dept||d.dept===f.dept));
  const [sel,setSel]=useState(null);
  useEffect(()=>{setQ(query)},[query]);
  useEffect(()=>{setSel(layout==='topbar'?null:all[0]||null)},[res.data,layout]);
  const head=<div className="res-head"><SearchBox value={q} onChange={setQ} onSubmit={onSearch}/></div>;
  const items=(card)=>res.loading?<div className="skel" style={{padding:16}}><i></i><i></i><i style={{width:'60%'}}></i></div>:
    res.error?<ErrorNote error={res.error} onRetry={res.reload}/>:
    list.length?list.map(d=><ResultItem card={card} key={d.id} d={d} query={query} active={!card&&sel&&sel.id===d.id} onClick={()=>setSel(d)}/>):<div className="empty-note">Không tìm thấy tài liệu phù hợp.</div>;

  if(layout==='topbar') return <div className="page res-b">
    {head}
    <AnswerCard hero query={query} onCite={setSel} onChat={onChat}/>
    <Filters f={f} setF={setF} count={list.length}/>
    <div className="grid2">{items(true)}</div>
    {sel&&<div className="drawer-bg" onClick={()=>setSel(null)}><div className="drawer" onClick={e=>e.stopPropagation()}><Preview d={sel} onClose={()=>setSel(null)} onChat={onChat}/></div></div>}
  </div>;

  if(layout==='rail') return <div className="res-c">
    <div className="pane pane-list">{head}<Filters f={f} setF={setF} count={list.length}/>{items(false)}</div>
    <div className="pane pane-pv"><Preview d={sel} onChat={onChat}/></div>
    <div className="pane pane-ai"><AnswerCard query={query} onCite={setSel} onChat={onChat}/></div>
  </div>;

  return <div className="res-a">
    <div className="pane pane-main">{head}<AnswerCard query={query} onCite={setSel} onChat={onChat}/><Filters f={f} setF={setF} count={list.length}/>
      <div className="rlist">{items(false)}</div></div>
    <div className="pane pane-pv"><Preview d={sel} onChat={onChat}/></div>
  </div>;
}

function History({onSearch}){
  const {data,loading,error,reload,setData}=useApi(()=>api('/api/history'),[]);
  const [f,setF]=useState('');
  const items=data?.items||[];
  const shown=items.filter(h=>h.q.toLowerCase().includes(f.toLowerCase()));
  const remove=h=>{setData({items:items.filter(x=>x!==h)});api('/api/history/'+h.id,{method:'DELETE'}).catch(reload)};
  const clear=()=>{setData({items:[]});api('/api/history',{method:'DELETE'}).catch(reload)};
  return <div className="page narrow">
    <div className="page-h"><div><h2>Lịch sử tìm kiếm</h2><p className="muted">Lưu 90 ngày, chỉ bạn nhìn thấy.</p></div><Btn onClick={clear} disabled={!items.length}>Xoá tất cả</Btn></div>
    <input className="input" placeholder="Lọc lịch sử…" value={f} onChange={e=>setF(e.target.value)}/>
    <div className="table">{shown.map(h=><div key={h.id} className="tr hov">
      <button className="row-link grow1" onClick={()=>onSearch(h.q)}><Icon n="search" s={16}/><span className="grow1">{h.q}</span></button>
      <span className="muted sm hide-sm">{h.n} nguồn</span><span className="muted sm w120">{h.when}</span>
      <button className="icon-btn" onClick={()=>remove(h)}><Icon n="x" s={15}/></button></div>)}
      {error?<ErrorNote error={error} onRetry={reload}/>:!loading&&!shown.length&&<div className="empty-note">Không có mục nào.</div>}</div>
  </div>;
}

export {SearchHome,Results,Preview,History,SearchBox,ErrorNote};
