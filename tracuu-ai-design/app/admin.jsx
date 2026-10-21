function Admin(){
  const [tab,setTab]=useState('overview');
  const tabs=[['overview','Tổng quan'],['kb','Knowledge Base'],['groups','Phân quyền'],['jobs','Đồng bộ dữ liệu']];
  return <div className="page">
    <div className="page-h"><div><h2>Quản trị</h2><p className="muted">kb-tailieu-prod · ap-southeast-1</p></div></div>
    <div className="tabs">{tabs.map(([k,l])=><button key={k} className={tab===k?'on':''} onClick={()=>setTab(k)}>{l}</button>)}</div>
    {tab==='overview'&&<Overview/>}{tab==='kb'&&<KbConfig/>}{tab==='groups'&&<Groups/>}{tab==='jobs'&&<Jobs/>}
  </div>;
}
function Overview(){
  const max=Math.max(...USAGE);
  return <>
    <div className="stats">
      {[['Truy vấn · 30 ngày','1.842','+12% so với tháng trước'],['Tài liệu đã lập chỉ mục','2.316','8 đang chờ xử lý'],['Phản hồi hữu ích','87%','trên 412 đánh giá'],['Chi phí Bedrock · tháng này','$214','dự kiến $296 cuối tháng']].map(([l,v,s])=>
        <div key={l} className="stat"><div className="muted sm">{l}</div><div className="stat-v">{v}</div><div className="muted sm">{s}</div></div>)}
    </div>
    <div className="two">
      <div className="card"><div className="card-h"><b>Truy vấn theo ngày</b><span className="muted sm">28 ngày</span></div>
        <div className="bars">{USAGE.map((v,i)=><i key={i} title={v+' truy vấn'} style={{height:(v/max*100)+'%'}}></i>)}</div></div>
      <div className="card"><div className="card-h"><b>Câu hỏi chưa có câu trả lời</b><span className="muted sm">gợi ý bổ sung tài liệu</span></div>
        {['Chính sách xe công tác','Quy định làm thêm giờ cuối tuần','Mẫu biên bản bàn giao tài sản','Hạn mức thẻ tín dụng công ty'].map((q,i)=><div key={q} className="tr"><span className="grow1">{q}</span><span className="muted sm">{[23,17,11,8][i]} lần</span></div>)}</div>
    </div>
  </>;
}
function KbConfig(){
  const [c,setC]=useState({model:'Claude Sonnet',emb:'Cohere Embed Multilingual',chunk:'Theo ngữ nghĩa',size:512,overlap:15,topk:6,guard:true,rerank:true,pii:true});
  const [saved,setSaved]=useState(false);const [dirty,setDirty]=useState(false);
  const set=(k,v)=>{setC({...c,[k]:v});setDirty(true);setSaved(false)};
  const Tog=({k,l,d})=><div className="cfg-row"><div><b>{l}</b><div className="muted sm">{d}</div></div><button className={'toggle'+(c[k]?' on':'')} onClick={()=>set(k,!c[k])}><i></i></button></div>;
  return <div className="two">
    <div className="card">
      <div className="card-h"><b>Mô hình</b></div>
      <label className="field"><span>Mô hình sinh câu trả lời</span><select className="select" value={c.model} onChange={e=>set('model',e.target.value)}><option>Claude Sonnet</option><option>Claude Haiku</option><option>Claude Opus</option></select></label>
      <label className="field"><span>Mô hình embedding</span><select className="select" value={c.emb} onChange={e=>set('emb',e.target.value)}><option>Titan Text Embeddings V2</option><option>Cohere Embed Multilingual</option></select></label>
      <label className="field"><span>Số đoạn truy xuất (top-k): <b>{c.topk}</b></span><input type="range" min="2" max="20" value={c.topk} onChange={e=>set('topk',+e.target.value)}/></label>
      <Tog k="rerank" l="Xếp hạng lại (rerank)" d="Sắp xếp lại kết quả truy xuất trước khi sinh câu trả lời"/>
    </div>
    <div className="card">
      <div className="card-h"><b>Chia đoạn & an toàn</b></div>
      <label className="field"><span>Chiến lược chia đoạn</span><select className="select" value={c.chunk} onChange={e=>set('chunk',e.target.value)}><option>Theo ngữ nghĩa</option><option>Kích thước cố định</option><option>Phân cấp</option></select></label>
      <label className="field"><span>Kích thước đoạn: <b>{c.size} token</b></span><input type="range" min="128" max="1024" step="64" value={c.size} onChange={e=>set('size',+e.target.value)}/></label>
      <label className="field"><span>Chồng lấn: <b>{c.overlap}%</b></span><input type="range" min="0" max="30" value={c.overlap} onChange={e=>set('overlap',+e.target.value)}/></label>
      <Tog k="guard" l="Bedrock Guardrails" d="Chặn nội dung độc hại và câu hỏi ngoài phạm vi"/>
      <Tog k="pii" l="Ẩn thông tin cá nhân (PII)" d="Che số CCCD, số tài khoản trong câu trả lời"/>
    </div>
    <div className="save-bar">{saved?<span className="pill ok"><Icon n="check" s={12}/>Đã lưu · thay đổi chia đoạn sẽ áp dụng ở lần đồng bộ tiếp theo</span>:<span className="muted sm">{dirty?'Có thay đổi chưa lưu':'Không có thay đổi'}</span>}<span className="grow1"></span><Btn kind="primary" disabled={!dirty} onClick={()=>{setSaved(true);setDirty(false)}}>Lưu cấu hình</Btn></div>
  </div>;
}
function Groups(){
  return <div className="card">
    <div className="card-h"><b>Nhóm người dùng</b><span className="muted sm">Đồng bộ từ IdP qua Cognito · dùng làm bộ lọc metadata khi truy xuất</span></div>
    <div className="table flat">
      <div className="tr th"><span className="grow1">Nhóm</span><span className="w120">Thành viên</span><span className="w120">Bộ sưu tập</span><span className="w160 hide-sm">Nguồn</span></div>
      {GROUPS.map(g=><div key={g.name} className="tr"><span className="grow1"><b>{g.name}</b></span><span className="w120">{g.members.toLocaleString('vi-VN')}</span><span className="w120">{g.docs}</span><span className="w160 mono muted sm hide-sm">{g.src}</span></div>)}
    </div>
  </div>;
}
function Jobs(){
  const [jobs,setJobs]=useState(JOBS);
  function run(){const id='ing-'+Math.random().toString(16).slice(2,6);setJobs(j=>[{id,src:'s3://docs-prod/',started:'Vừa xong',docs:8,status:'IN_PROGRESS',dur:'…'},...j]);
    setTimeout(()=>setJobs(j=>j.map(x=>x.id===id?{...x,status:'COMPLETE',dur:'41 s'}:x)),3500);}
  return <div className="card">
    <div className="card-h"><b>Lần đồng bộ (ingestion job)</b><span className="grow1"></span><Btn kind="primary" icon="up" onClick={run}>Đồng bộ ngay</Btn></div>
    <div className="table flat">
      <div className="tr th"><span className="w120">Job</span><span className="grow1">Nguồn</span><span className="w120 hide-sm">Bắt đầu</span><span className="w120">Tài liệu</span><span className="w120 hide-sm">Thời gian</span><span className="w160">Trạng thái</span></div>
      {jobs.map(j=><div key={j.id} className="tr"><span className="w120 mono sm">{j.id}</span><span className="grow1 mono sm muted">{j.src}</span><span className="w120 muted hide-sm">{j.started}</span><span className="w120">{j.docs}</span><span className="w120 muted hide-sm">{j.dur}</span>
        <span className="w160">{j.status==='COMPLETE'?<span className="pill ok">Hoàn tất</span>:j.status==='FAILED'?<span className="pill bad">Lỗi · xem log</span>:<span className="pill acc"><span className="spin sm"></span>Đang chạy</span>}</span></div>)}
    </div>
  </div>;
}
Object.assign(window,{Admin});
