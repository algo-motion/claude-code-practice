function SearchBox({value,onChange,onSubmit,big,autoFocus}){
  return <form className={'sbox'+(big?' big':'')} onSubmit={e=>{e.preventDefault();value.trim()&&onSubmit(value.trim())}}>
    <Icon n="search" s={big?22:18}/>
    <input autoFocus={autoFocus} value={value} onChange={e=>onChange(e.target.value)} placeholder="Hỏi bằng ngôn ngữ tự nhiên hoặc nhập từ khoá…"/>
    {value&&<button type="button" className="icon-btn" onClick={()=>onChange('')}><Icon n="x" s={15}/></button>}
    <button className="btn btn-primary" disabled={!value.trim()}>Tìm<Icon n="arr" s={15}/></button>
  </form>;
}

function SearchHome({user,onSearch,openDoc}){
  const [q,setQ]=useState('');
  return <div className="page home">
    <div className="home-hero">
      <div className="eyebrow">Xin chào, {user.name.split(' ').pop()}</div>
      <h1>Bạn cần tìm gì trong kho tài liệu?</h1>
      <SearchBox big value={q} onChange={setQ} onSubmit={onSearch} autoFocus/>
      <div className="chips">{SUGGESTIONS.map(s=><button key={s} className="chip" onClick={()=>onSearch(s)}>{s}</button>)}</div>
    </div>
    <div className="home-cols">
      <section><h3 className="sec-h">Tìm kiếm gần đây</h3>
        <div className="list-plain">{HISTORY.slice(0,4).map(h=><button key={h.q} className="row-link" onClick={()=>onSearch(h.q)}><Icon n="hist" s={16}/><span className="grow1">{h.q}</span><span className="muted sm">{h.when}</span></button>)}</div></section>
      <section><h3 className="sec-h">Mới cập nhật</h3>
        <div className="list-plain">{DOCS.slice(0,4).map(d=><button key={d.id} className="row-link" onClick={()=>openDoc(d)}><TypeTag t={d.type}/><span className="grow1">{d.title}</span><span className="muted sm">{d.updated}</span></button>)}</div></section>
    </div>
  </div>;
}

function AnswerCard({query,onCite,onChat,hero}){
  const a=useMemo(()=>answerFor(query),[query]);
  const [thinking,setThinking]=useState(true);
  useEffect(()=>{setThinking(true);const t=setTimeout(()=>setThinking(false),700);return()=>clearTimeout(t)},[query]);
  const {out,done}=useStream(thinking?'':a.text,query);
  const [fb,setFb]=useState(null);
  return <div className={'answer'+(hero?' hero':'')}>
    <div className="answer-h"><span className="ai-badge"><Icon n="spark" s={13}/>Trả lời từ AI</span><span className="muted sm">Dựa trên {a.docs.length} tài liệu bạn có quyền truy cập</span></div>
    {thinking?<div className="skel"><i></i><i></i><i style={{width:'60%'}}></i></div>:<RichAnswer text={out} docs={a.docs} onCite={onCite} caret={!done}/>}
    {done&&!thinking&&<>
      <div className="sources">{a.docs.map((d,i)=><button key={d.id} className="source" onClick={()=>onCite(d)}><span className="cite static">{i+1}</span><span className="src-t">{d.title}</span><span className="muted sm">tr. {3+i*5}</span></button>)}</div>
      <div className="answer-f"><Btn kind="soft" icon="chat" onClick={()=>onChat(query)}>Hỏi tiếp trong chat</Btn>
        <div className="grow1"></div>
        <span className="muted sm">{fb?'Cảm ơn phản hồi của bạn':'Câu trả lời có hữu ích?'}</span>
        {!fb&&<><button className="chip sm" onClick={()=>setFb('y')}>Có</button><button className="chip sm" onClick={()=>setFb('n')}>Không</button></>}
      </div></>}
  </div>;
}

function ResultItem({d,active,onClick,card}){
  return <button className={'result'+(active?' on':'')+(card?' card':'')} onClick={onClick}>
    <div className="result-top"><TypeTag t={d.type}/><span className="muted sm">{d.dept} · {d.updated} · {d.pages} trang</span><span className="grow1"></span><span className="score" title="Độ liên quan"><i style={{width:Math.round(d.score*100)+'%'}}></i></span></div>
    <div className="result-t">{d.title}</div>
    <div className="result-s" dangerouslySetInnerHTML={{__html:d.snippet}}></div>
    {d.group!=='Toàn công ty'&&<div className="lock"><Icon n="lock" s={12}/>{d.group}</div>}
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
  const [sum,setSum]=useState(false);const [loading,setLoading]=useState(false);
  useEffect(()=>{setSum(false);setLoading(false)},[d&&d.id]);
  const text=sum?d.summary.map(s=>'• '+s).join('\n'):'';
  const {out,done}=useStream(text,d&&d.id+String(sum),10);
  if(!d) return <div className="preview empty"><Icon n="file" s={28}/><p>Chọn một kết quả để xem trước</p></div>;
  return <div className={'preview '+(mode||'')}>
    <div className="pv-h"><TypeTag t={d.type}/><div className="grow1"><div className="pv-t">{d.title}</div><div className="muted sm">{d.dept} · {d.owner} · cập nhật {d.updated}</div></div>{onClose&&<button className="icon-btn" onClick={onClose}><Icon n="x"/></button>}</div>
    <div className="pv-actions">
      <Btn kind="soft" icon="spark" disabled={sum} onClick={()=>{setLoading(true);setTimeout(()=>{setLoading(false);setSum(true)},800)}}>{loading?'Đang tóm tắt…':'Tóm tắt bằng AI'}</Btn>
      <Btn icon="chat" onClick={()=>onChat('Tài liệu "'+d.title+'" nói gì?',d)}>Hỏi về tài liệu</Btn>
      <Btn icon="down">Tải xuống</Btn>
    </div>
    {(sum||loading)&&<div className="pv-sum"><div className="label">Tóm tắt</div>{loading?<div className="skel"><i></i><i style={{width:'75%'}}></i></div>:<div className="sum-text">{out}{!done&&<span className="caret"></span>}</div>}</div>}
    <div className="label">Đoạn được truy xuất <span className="mono muted">chunk #{d.id.slice(1)}-07 · trang 3</span></div>
    <div className="pv-passage">{d.passage.split('\n').map((l,i)=><p key={i} className={i===0?'b':''}>{l}</p>)}</div>
    <div className="pv-meta">
      <div><span>Quyền truy cập</span><b>{d.group}</b></div><div><span>Dung lượng</span><b>{d.size}</b></div><div><span>Số trang</span><b>{d.pages}</b></div><div><span>Trạng thái</span><b className="ok">Đã lập chỉ mục</b></div>
    </div>
    <Placeholder label={'trang tài liệu · '+d.type.toLowerCase()+' viewer'} h={260}/>
  </div>;
}

function Results({layout,query,onSearch,onChat,initialDoc}){
  const [q,setQ]=useState(query);const [f,setF]=useState({});
  const all=useMemo(()=>resultsFor(query),[query]);
  const list=all.filter(d=>(!f.type||d.type===f.type)&&(!f.dept||d.dept===f.dept));
  const [sel,setSel]=useState(initialDoc||(layout==='topbar'?null:all[0]));
  useEffect(()=>{setQ(query);setSel(layout==='topbar'?null:all[0])},[query,layout]);
  const head=<div className="res-head"><SearchBox value={q} onChange={setQ} onSubmit={onSearch}/></div>;

  if(layout==='topbar') return <div className="page res-b">
    {head}
    <AnswerCard hero query={query} onCite={setSel} onChat={onChat}/>
    <Filters f={f} setF={setF} count={list.length}/>
    <div className="grid2">{list.map(d=><ResultItem card key={d.id} d={d} onClick={()=>setSel(d)}/>)}</div>
    {sel&&<div className="drawer-bg" onClick={()=>setSel(null)}><div className="drawer" onClick={e=>e.stopPropagation()}><Preview d={sel} onClose={()=>setSel(null)} onChat={onChat}/></div></div>}
  </div>;

  if(layout==='rail') return <div className="res-c">
    <div className="pane pane-list">{head}<Filters f={f} setF={setF} count={list.length}/>{list.map(d=><ResultItem key={d.id} d={d} active={sel&&sel.id===d.id} onClick={()=>setSel(d)}/>)}</div>
    <div className="pane pane-pv"><Preview d={sel} onChat={onChat}/></div>
    <div className="pane pane-ai"><AnswerCard query={query} onCite={setSel} onChat={onChat}/></div>
  </div>;

  return <div className="res-a">
    <div className="pane pane-main">{head}<AnswerCard query={query} onCite={setSel} onChat={onChat}/><Filters f={f} setF={setF} count={list.length}/>
      <div className="rlist">{list.map(d=><ResultItem key={d.id} d={d} active={sel&&sel.id===d.id} onClick={()=>setSel(d)}/>)}</div></div>
    <div className="pane pane-pv"><Preview d={sel} onChat={onChat}/></div>
  </div>;
}

function History({onSearch}){
  const [items,setItems]=useState(HISTORY);const [f,setF]=useState('');
  const shown=items.filter(h=>h.q.toLowerCase().includes(f.toLowerCase()));
  return <div className="page narrow">
    <div className="page-h"><div><h2>Lịch sử tìm kiếm</h2><p className="muted">Lưu 90 ngày, chỉ bạn nhìn thấy.</p></div><Btn onClick={()=>setItems([])} disabled={!items.length}>Xoá tất cả</Btn></div>
    <input className="input" placeholder="Lọc lịch sử…" value={f} onChange={e=>setF(e.target.value)}/>
    <div className="table">{shown.map(h=><div key={h.q} className="tr hov">
      <button className="row-link grow1" onClick={()=>onSearch(h.q)}><Icon n="search" s={16}/><span className="grow1">{h.q}</span></button>
      <span className="muted sm hide-sm">{h.n} nguồn</span><span className="muted sm w120">{h.when}</span>
      <button className="icon-btn" onClick={()=>setItems(items.filter(x=>x!==h))}><Icon n="x" s={15}/></button></div>)}
      {!shown.length&&<div className="empty-note">Không có mục nào.</div>}</div>
  </div>;
}

Object.assign(window,{SearchHome,Results,Preview,History,SearchBox});
