import React,{useState,useEffect,useRef} from 'react';
import {SUGGESTIONS} from './data.js';
import {api,askStream,uploadFile,useApi} from './api.js';
import {Icon,RichAnswer,TypeTag} from './ui.jsx';
import {ErrorNote} from './search.jsx';

function fromServer(m){return m.role==='user'?{role:'u',text:m.text}:{role:'a',text:m.text,docs:m.docs,id:m.id,rating:m.rating,done:true}}

function Chat({seed,seedDoc,openDoc}){
  const sessions=useApi(()=>api('/api/chat/sessions'),[]);
  const docs=useApi(()=>api('/api/documents'),[]);
  const [sid,setSid]=useState(null);
  const [msgs,setMsgs]=useState([]);const [txt,setTxt]=useState('');const [busy,setBusy]=useState(false);
  const [scope,setScope]=useState(seedDoc?seedDoc.id:'all');
  const [err,setErr]=useState('');
  const end=useRef(null);const abort=useRef(null);const sidRef=useRef(null);
  useEffect(()=>{sidRef.current=sid},[sid]);

  useEffect(()=>{
    abort.current&&abort.current.abort();
    setMsgs([]);setSid(null);sidRef.current=null;setErr('');
    if(seed) ask(seed,seedDoc?seedDoc.id:undefined);
    return()=>abort.current&&abort.current.abort();
  },[seed]);
  useEffect(()=>{end.current&&end.current.parentElement.scrollTo({top:1e6,behavior:'smooth'})},[msgs]);

  function patchLast(fn){setMsgs(m=>[...m.slice(0,-1),fn(m[m.length-1])])}
  function ask(q,docId){
    setErr('');setBusy(true);
    setMsgs(m=>[...m,{role:'u',text:q},{role:'a',pending:true,text:'',docs:[]}]);
    const ac=new AbortController();abort.current=ac;
    askStream(q,{sessionId:sidRef.current,docId:docId||(scope==='all'?undefined:scope),signal:ac.signal,onEvent:ev=>{
      if(ev.type==='meta'){sidRef.current=ev.session_id;setSid(ev.session_id)}
      else if(ev.type==='delta') patchLast(a=>({...a,pending:false,text:a.text+ev.text}));
      else if(ev.type==='blocked') patchLast(a=>({...a,pending:false,text:ev.text}));
      else if(ev.type==='citations') patchLast(a=>({...a,docs:ev.docs}));
      else if(ev.type==='error'){patchLast(a=>({...a,pending:false,done:true,text:a.text||ev.message}));setErr(ev.message)}
      else if(ev.type==='done'){patchLast(a=>({...a,pending:false,done:true,id:ev.message_id}));sessions.reload()}
    }}).catch(e=>{if(!ac.signal.aborted){patchLast(a=>({...a,pending:false,done:true,text:a.text||'Không gửi được câu hỏi.'}));setErr(e.message)}})
      .finally(()=>setBusy(false));
  }
  function send(e){e.preventDefault();if(!txt.trim()||busy)return;ask(txt.trim());setTxt('');}
  function open(s){
    abort.current&&abort.current.abort();setBusy(false);setErr('');
    api('/api/chat/sessions/'+s.id).then(r=>{setSid(s.id);sidRef.current=s.id;setMsgs(r.messages.map(fromServer))},e=>setErr(e.message));
  }
  function newChat(){abort.current&&abort.current.abort();setBusy(false);setMsgs([]);setSid(null);sidRef.current=null;setErr('')}
  function rate(i,rating){
    const m=msgs[i];if(!m.id||!sid)return;
    setMsgs(ms=>ms.map((x,j)=>j===i?{...x,rating}:x));
    api('/api/feedback',{method:'POST',body:{session_id:sid,message_id:m.id,rating}}).catch(e=>setErr(e.message));
  }
  const last=[...msgs].reverse().find(m=>m.docs&&m.docs.length);
  return <div className="chat">
    <div className="chat-list">
      <button className="btn btn-soft w100" onClick={newChat}><Icon n="plus" s={16}/>Hội thoại mới</button>
      <div className="side-sec">Gần đây</div>
      {(sessions.data?.items||[]).map(s=><button key={s.id} className={'side-item sm'+(sid===s.id?' on':'')} onClick={()=>open(s)}><span className="grow1 ell">{s.title}</span><span className="muted sm">{s.when}</span></button>)}
    </div>
    <div className="chat-main">
      <div className="chat-scroll">
        {!msgs.length&&<div className="chat-empty"><span className="ai-badge lg"><Icon n="spark" s={16}/>Trợ lý tài liệu</span><h2>Hỏi bất cứ điều gì về tài liệu nội bộ</h2><p className="muted">Câu trả lời luôn kèm trích dẫn nguồn. Trợ lý chỉ dùng tài liệu bạn có quyền xem.</p>
          <div className="chips center">{SUGGESTIONS.map(s=><button key={s} className="chip" onClick={()=>ask(s)}>{s}</button>)}</div></div>}
        {msgs.map((m,i)=>m.role==='u'?<div key={i} className="msg u"><div className="bubble">{m.text}</div></div>:
          <div key={i} className="msg a"><span className="ai-dot"><Icon n="spark" s={14}/></span><div className="grow1">{m.pending?<div className="skel"><i></i><i style={{width:'70%'}}></i></div>:
            <><RichAnswer text={m.text} docs={m.docs} onCite={openDoc} caret={!m.done}/>
            {m.done&&<div className="msg-tools"><button className="chip sm" onClick={()=>navigator.clipboard&&navigator.clipboard.writeText(m.text)}>Sao chép</button>
              <button className="chip sm" disabled={busy} onClick={()=>ask(msgs[i-1].text)}>Tạo lại</button>
              {m.id&&<><button className={'chip sm'+(m.rating==='up'?' on':'')} onClick={()=>rate(i,'up')}>Hữu ích</button><button className={'chip sm'+(m.rating==='down'?' on':'')} onClick={()=>rate(i,'down')}>Chưa tốt</button></>}</div>}</>}</div></div>)}
        <div ref={end}></div>
      </div>
      {err&&<p className="sm" style={{color:'var(--bad)',margin:'0 max(32px,calc((100% - 760px)/2)) 8px'}}>{err}</p>}
      <form className="composer" onSubmit={send}>
        <textarea rows="2" value={txt} maxLength={2000} onChange={e=>setTxt(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey)send(e)}} placeholder="Nhập câu hỏi… (Enter để gửi, Shift+Enter xuống dòng)"></textarea>
        <div className="composer-f">
          <select className="select" value={scope} onChange={e=>setScope(e.target.value)}><option value="all">Phạm vi: Tất cả tài liệu</option>{(docs.data?.items||[]).filter(d=>d.status==='INDEXED').map(d=><option key={d.id} value={d.id}>{d.title}</option>)}</select>
          <span className="muted sm">Claude · Bedrock Knowledge Base</span><span className="grow1"></span>
          <button className="btn btn-primary" disabled={!txt.trim()||busy}>Gửi<Icon n="send" s={15}/></button>
        </div>
      </form>
    </div>
    <div className="chat-src">
      <div className="label">Nguồn được trích dẫn</div>
      {last?last.docs.map((d,i)=><button key={d.id+i} className="src-card" onClick={()=>openDoc(d)}><div className="row"><span className="cite static">{i+1}</span><TypeTag t={d.type}/></div><div className="src-t2">{d.title}</div><div className="muted sm clamp3">{(d.passage||'').split('\n').slice(-1)[0]}</div></button>):<p className="muted sm">Nguồn sẽ hiện ở đây khi trợ lý trả lời.</p>}
    </div>
  </div>;
}

const STAGES=['Đang tải lên S3','Trích xuất nội dung','Tạo embedding','Đã lập chỉ mục'];
const STAGE={UPLOADING:0,UPLOADED:1,INGESTING:2,INDEXED:3};

function Library({user,openDoc,dept}){
  const {data,loading,error,reload,setData}=useApi(()=>api('/api/documents'),[]);
  const docs=data?.items||[];
  const [drag,setDrag]=useState(false);const [grp,setGrp]=useState('Toàn công ty');
  const [fd,setFd]=useState(dept||'');const [q,setQ]=useState('');const [msg,setMsg]=useState('');
  const inp=useRef(null);
  useEffect(()=>setFd(dept||''),[dept]);

  // Theo dõi tiến trình lập chỉ mục: hỏi lại danh sách mỗi 3 giây khi còn tài liệu đang xử lý.
  const pending=docs.some(d=>d.status in STAGE&&d.status!=='INDEXED');
  useEffect(()=>{
    if(!pending) return;
    const t=setInterval(()=>api('/api/documents').then(setData,()=>{}),3000);
    return()=>clearInterval(t);
  },[pending]);

  async function add(files){
    const arr=[...files].slice(0,5);if(!arr.length)return;
    setMsg('');
    for(const f of arr){
      try{await uploadFile(f,{groups:[grp],dept:fd||undefined})}
      catch(e){setMsg(`${f.name}: ${e.message}`)}
    }
    reload();
  }
  const retry=id=>api('/api/admin/documents/'+id+'/retry',{method:'POST'}).then(reload,e=>setMsg(e.message));
  const shown=docs.filter(d=>(!fd||d.dept===fd)&&d.title.toLowerCase().includes(q.toLowerCase()));
  return <div className="page">
    <div className="page-h"><div><h2>Thư viện tài liệu</h2><p className="muted">{docs.length} tài liệu · đồng bộ vào Knowledge Base tự động</p></div></div>
    <div className={'drop'+(drag?' on':'')} onDragOver={e=>{e.preventDefault();setDrag(true)}} onDragLeave={()=>setDrag(false)} onDrop={e=>{e.preventDefault();setDrag(false);add(e.dataTransfer.files)}} onClick={()=>inp.current.click()}>
      <input ref={inp} type="file" multiple hidden accept=".pdf,.docx,.xlsx,.png,.jpg,.jpeg" onChange={e=>{add(e.target.files);e.target.value=''}}/>
      <span className="drop-ic"><Icon n="up" s={22}/></span>
      <div><b>Kéo thả tệp vào đây</b> hoặc <span className="link">chọn từ máy</span><div className="muted sm">PDF, DOCX, XLSX, ảnh scan · tối đa 50 MB/tệp</div></div>
      <div className="grow1"></div>
      <label className="field inline" onClick={e=>e.stopPropagation()}><span>Chia sẻ với nhóm</span><select className="select" value={grp} onChange={e=>setGrp(e.target.value)}>{user.groups.map(g=><option key={g}>{g}</option>)}</select></label>
    </div>
    {msg&&<p className="sm" style={{color:'var(--bad)',marginTop:10}}>{msg}</p>}
    <div className="toolbar"><input className="input" placeholder="Lọc theo tên…" value={q} onChange={e=>setQ(e.target.value)}/>
      <div className="chips">{['','Nhân sự','Tài chính','Mua sắm','Pháp chế','CNTT'].map(x=><button key={x} className={'chip sm'+(fd===x?' on':'')} onClick={()=>setFd(x)}>{x||'Tất cả'}</button>)}</div></div>
    <div className="table">
      <div className="tr th"><span className="grow1">Tên tài liệu</span><span className="w120 hide-sm">Phòng ban</span><span className="w160">Quyền truy cập</span><span className="w120 hide-sm">Cập nhật</span><span className="w160">Trạng thái</span></div>
      {shown.map(d=>{const stage=STAGE[d.status];return <div key={d.id} className="tr hov" onClick={()=>d.status==='INDEXED'&&openDoc(d)}>
        <span className="grow1 row"><TypeTag t={d.type}/><span className="ell">{d.title}</span></span>
        <span className="w120 muted hide-sm">{d.dept}</span><span className="w160 muted ell">{d.group}</span><span className="w120 muted hide-sm">{d.updated}</span>
        <span className="w160">{d.status==='INDEXED'?<span className="pill ok"><Icon n="check" s={12}/>Đã lập chỉ mục</span>
          :d.status==='FAILED'?<span className="row"><span className="pill bad">Lỗi lập chỉ mục</span>{user.role==='admin'&&<button className="link sm" onClick={e=>{e.stopPropagation();retry(d.id)}}>Thử lại</button>}</span>
          :<span className="stage"><span className="pill acc"><span className="spin sm"></span>{STAGES[stage]||d.status}</span><span className="bar"><i style={{width:(((stage||0)+1)/4*100)+'%'}}></i></span></span>}</span>
      </div>})}
      {error?<ErrorNote error={error} onRetry={reload}/>:!loading&&!shown.length&&<div className="empty-note">Không có tài liệu phù hợp.</div>}
    </div>
  </div>;
}
export {Chat,Library};
