function Chat({seed,seedDoc,openDoc}){
  const [sessions,setSessions]=useState([{id:1,title:'Chính sách công tác phí',when:'Hôm nay'},{id:2,title:'Quy trình mua sắm thiết bị',when:'Hôm qua'},{id:3,title:'Onboarding cho team mới',when:'14/10'}]);
  const [cur,setCur]=useState(0);
  const [msgs,setMsgs]=useState([]);const [txt,setTxt]=useState('');const [busy,setBusy]=useState(false);
  const [scope,setScope]=useState(seedDoc?seedDoc.id:'all');
  const end=useRef(null);
  useEffect(()=>{ if(seed){setMsgs([]);ask(seed);} else setMsgs([]); },[seed]);
  useEffect(()=>{end.current&&end.current.parentElement.scrollTo({top:1e6,behavior:'smooth'})},[msgs]);
  function ask(q){
    setMsgs(m=>[...m,{role:'u',text:q},{role:'a',pending:true}]);setBusy(true);
    setTimeout(()=>{const a=answerFor(q);setMsgs(m=>[...m.slice(0,-1),{role:'a',text:a.text,docs:a.docs,k:Date.now()}]);setBusy(false);},900);
  }
  function send(e){e.preventDefault();if(!txt.trim()||busy)return;ask(txt.trim());setTxt('');}
  const last=[...msgs].reverse().find(m=>m.docs);
  return <div className="chat">
    <div className="chat-list">
      <button className="btn btn-soft w100" onClick={()=>{setMsgs([]);setCur(null)}}><Icon n="plus" s={16}/>Hội thoại mới</button>
      <div className="side-sec">Gần đây</div>
      {sessions.map((s,i)=><button key={s.id} className={'side-item sm'+(cur===i?' on':'')} onClick={()=>{setCur(i);setMsgs([]);ask(s.title)}}><span className="grow1 ell">{s.title}</span><span className="muted sm">{s.when}</span></button>)}
    </div>
    <div className="chat-main">
      <div className="chat-scroll">
        {!msgs.length&&<div className="chat-empty"><span className="ai-badge lg"><Icon n="spark" s={16}/>Trợ lý tài liệu</span><h2>Hỏi bất cứ điều gì về tài liệu nội bộ</h2><p className="muted">Câu trả lời luôn kèm trích dẫn nguồn. Trợ lý chỉ dùng tài liệu bạn có quyền xem.</p>
          <div className="chips center">{SUGGESTIONS.map(s=><button key={s} className="chip" onClick={()=>ask(s)}>{s}</button>)}</div></div>}
        {msgs.map((m,i)=>m.role==='u'?<div key={i} className="msg u"><div className="bubble">{m.text}</div></div>:
          <div key={i} className="msg a"><span className="ai-dot"><Icon n="spark" s={14}/></span><div className="grow1">{m.pending?<div className="skel"><i></i><i style={{width:'70%'}}></i></div>:<StreamMsg m={m} openDoc={openDoc}/>}</div></div>)}
        <div ref={end}></div>
      </div>
      <form className="composer" onSubmit={send}>
        <textarea rows="2" value={txt} onChange={e=>setTxt(e.target.value)} onKeyDown={e=>{if(e.key==='Enter'&&!e.shiftKey)send(e)}} placeholder="Nhập câu hỏi… (Enter để gửi, Shift+Enter xuống dòng)"></textarea>
        <div className="composer-f">
          <select className="select" value={scope} onChange={e=>setScope(e.target.value)}><option value="all">Phạm vi: Tất cả tài liệu</option>{DOCS.map(d=><option key={d.id} value={d.id}>{d.title}</option>)}</select>
          <span className="muted sm">Claude · Bedrock Knowledge Base</span><span className="grow1"></span>
          <button className="btn btn-primary" disabled={!txt.trim()||busy}>Gửi<Icon n="send" s={15}/></button>
        </div>
      </form>
    </div>
    <div className="chat-src">
      <div className="label">Nguồn được trích dẫn</div>
      {last?last.docs.map((d,i)=><button key={d.id} className="src-card" onClick={()=>openDoc(d)}><div className="row"><span className="cite static">{i+1}</span><TypeTag t={d.type}/></div><div className="src-t2">{d.title}</div><div className="muted sm clamp3">{d.passage.split('\n')[1]}</div></button>):<p className="muted sm">Nguồn sẽ hiện ở đây khi trợ lý trả lời.</p>}
    </div>
  </div>;
}
function StreamMsg({m,openDoc}){const {out,done}=useStream(m.text,m.k);
  return <><RichAnswer text={out} docs={m.docs} onCite={openDoc} caret={!done}/>{done&&<div className="msg-tools"><button className="chip sm">Sao chép</button><button className="chip sm">Tạo lại</button></div>}</>;}

const STAGES=['Đang tải lên S3','Trích xuất nội dung','Tạo embedding','Đã lập chỉ mục'];
function Library({openDoc,dept}){
  const [docs,setDocs]=useState(DOCS.map(d=>({...d,stage:3})));
  const [drag,setDrag]=useState(false);const [grp,setGrp]=useState('Toàn công ty');
  const [fd,setFd]=useState(dept||'');const [q,setQ]=useState('');
  const inp=useRef(null);
  useEffect(()=>setFd(dept||''),[dept]);
  function add(files){
    const arr=[...files].slice(0,5);if(!arr.length)return;
    const nw=arr.map((f,i)=>{const ext=(f.name.split('.').pop()||'pdf').toUpperCase();return {...DOCS[0],id:'n'+Date.now()+i,title:f.name.replace(/\.[^.]+$/,''),type:['PDF','DOCX','XLSX'].includes(ext)?ext:'PDF',size:(f.size/1048576).toFixed(1).replace('.',',')+' MB',updated:'Vừa xong',owner:'Bạn',group:grp,dept:'—',stage:0}});
    setDocs(d=>[...nw,...d]);
    nw.forEach(n=>[1,2,3].forEach(s=>setTimeout(()=>setDocs(d=>d.map(x=>x.id===n.id?{...x,stage:s}:x)),s*1400+Math.random()*500)));
  }
  const shown=docs.filter(d=>(!fd||d.dept===fd)&&d.title.toLowerCase().includes(q.toLowerCase()));
  return <div className="page">
    <div className="page-h"><div><h2>Thư viện tài liệu</h2><p className="muted">{docs.length} tài liệu · đồng bộ vào Knowledge Base tự động</p></div></div>
    <div className={'drop'+(drag?' on':'')} onDragOver={e=>{e.preventDefault();setDrag(true)}} onDragLeave={()=>setDrag(false)} onDrop={e=>{e.preventDefault();setDrag(false);add(e.dataTransfer.files)}} onClick={()=>inp.current.click()}>
      <input ref={inp} type="file" multiple hidden onChange={e=>add(e.target.files)}/>
      <span className="drop-ic"><Icon n="up" s={22}/></span>
      <div><b>Kéo thả tệp vào đây</b> hoặc <span className="link">chọn từ máy</span><div className="muted sm">PDF, DOCX, XLSX, ảnh scan · tối đa 50 MB/tệp</div></div>
      <div className="grow1"></div>
      <label className="field inline" onClick={e=>e.stopPropagation()}><span>Chia sẻ với nhóm</span><select className="select" value={grp} onChange={e=>setGrp(e.target.value)}>{GROUPS.map(g=><option key={g.name}>{g.name}</option>)}</select></label>
    </div>
    <div className="toolbar"><input className="input" placeholder="Lọc theo tên…" value={q} onChange={e=>setQ(e.target.value)}/>
      <div className="chips">{['','Nhân sự','Tài chính','Mua sắm','Pháp chế','CNTT'].map(x=><button key={x} className={'chip sm'+(fd===x?' on':'')} onClick={()=>setFd(x)}>{x||'Tất cả'}</button>)}</div></div>
    <div className="table">
      <div className="tr th"><span className="grow1">Tên tài liệu</span><span className="w120 hide-sm">Phòng ban</span><span className="w160">Quyền truy cập</span><span className="w120 hide-sm">Cập nhật</span><span className="w160">Trạng thái</span></div>
      {shown.map(d=><div key={d.id} className="tr hov" onClick={()=>d.stage===3&&openDoc(d)}>
        <span className="grow1 row"><TypeTag t={d.type}/><span className="ell">{d.title}</span></span>
        <span className="w120 muted hide-sm">{d.dept}</span><span className="w160 muted ell">{d.group}</span><span className="w120 muted hide-sm">{d.updated}</span>
        <span className="w160">{d.stage===3?<span className="pill ok"><Icon n="check" s={12}/>Đã lập chỉ mục</span>:<span className="stage"><span className="pill acc"><span className="spin sm"></span>{STAGES[d.stage]}</span><span className="bar"><i style={{width:((d.stage+1)/4*100)+'%'}}></i></span></span>}</span>
      </div>)}
      {!shown.length&&<div className="empty-note">Không có tài liệu phù hợp.</div>}
    </div>
  </div>;
}
Object.assign(window,{Chat,Library});
