import React,{useState,useEffect,useRef,useMemo} from 'react';

function Icon({n,s=18}){
  const p={width:s,height:s,viewBox:'0 0 24 24',fill:'none',stroke:'currentColor',strokeWidth:1.7,strokeLinecap:'round',strokeLinejoin:'round'};
  const m={
    search:<><circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/></>,
    chat:<><rect x="3.5" y="4.5" width="17" height="12" rx="3"/><path d="M8 16.5v3.5l4-3.5"/></>,
    lib:<><rect x="4" y="4" width="4" height="16" rx="1"/><rect x="10" y="4" width="4" height="16" rx="1"/><path d="M16.5 5l3.5 14.5"/></>,
    admin:<><circle cx="12" cy="12" r="3"/><circle cx="12" cy="12" r="8"/></>,
    hist:<><circle cx="12" cy="12" r="8"/><path d="M12 7.5V12l3 2"/></>,
    up:<><path d="M12 16V5"/><path d="M7.5 9.5L12 5l4.5 4.5"/><path d="M5 19h14"/></>,
    x:<><path d="M6 6l12 12M18 6L6 18"/></>,
    arr:<><path d="M5 12h14"/><path d="M13 6l6 6-6 6"/></>,
    spark:<><path d="M12 3l2.2 6.8L21 12l-6.8 2.2L12 21l-2.2-6.8L3 12l6.8-2.2z"/></>,
    file:<><path d="M6 3h8l4 4v14H6z"/><path d="M14 3v4h4"/></>,
    out:<><path d="M14 4h5v16h-5"/><path d="M10 8l-4 4 4 4"/><path d="M6 12h9"/></>,
    plus:<><path d="M12 5v14M5 12h14"/></>,
    check:<><path d="M5 12.5l4.5 4.5L19 7.5"/></>,
    down:<><path d="M12 5v11"/><path d="M7.5 11.5L12 16l4.5-4.5"/><path d="M5 20h14"/></>,
    send:<><path d="M5 12h13"/><path d="M12 6l6 6-6 6"/></>,
    lock:<><rect x="5" y="10.5" width="14" height="9.5" rx="2"/><path d="M8.5 10.5V7.5a3.5 3.5 0 017 0v3"/></>,
  };
  return <svg {...p}>{m[n]}</svg>;
}

function useStream(text,key,speed=14){
  const [n,setN]=useState(0);
  useEffect(()=>{ if(!text){setN(0);return;} setN(0); let i=0;
    const t=setInterval(()=>{ i+=3; setN(i); if(i>=text.length) clearInterval(t); },speed);
    return ()=>clearInterval(t); },[text,key]);
  return {out:text?text.slice(0,n):'',done:!text||n>=text.length};
}

function RichAnswer({text,docs,onCite,caret}){
  const parts=text.split(/(\*\*[^*]+\*\*|\[\d\])/g);
  return <p className="answer-text">{parts.map((p,i)=>{
    if(/^\*\*/.test(p)) return <strong key={i}>{p.replace(/\*\*/g,'')}</strong>;
    const m=p.match(/^\[(\d)\]$/);
    if(m){const d=docs&&docs[+m[1]-1];return <button key={i} className="cite" title={d?d.title:''} onClick={()=>d&&onCite&&onCite(d)}>{m[1]}</button>;}
    return <React.Fragment key={i}>{p.replace(/\*\*?[^*]*$/,s=>s.startsWith('**')?s.slice(2):s)}</React.Fragment>;
  })}{caret&&<span className="caret"></span>}</p>;
}

function TypeTag({t}){return <span className={'typetag t-'+t.toLowerCase()}>{t}</span>;}
function Btn({kind='ghost',icon,children,...r}){return <button className={'btn btn-'+kind} {...r}>{icon&&<Icon n={icon} s={16}/>}{children}</button>;}
function Placeholder({label,h=200}){return <div className="ph" style={{height:h}}><span>{label}</span></div>;}

const NAV=[
  {id:'search',label:'Tìm kiếm',icon:'search'},
  {id:'chat',label:'Hỏi đáp AI',icon:'chat'},
  {id:'library',label:'Thư viện',icon:'lib'},
  {id:'history',label:'Lịch sử',icon:'hist'},
  {id:'admin',label:'Quản trị',icon:'admin',admin:true},
];

function Brand({compact}){return <div className="brand"><span className="brand-mark"></span>{!compact&&<span>Tra Cứu<b>AI</b></span>}</div>;}

function Shell({layout,screen,go,user,onLogout,children}){
  const active=screen==='results'?'search':screen;
  const items=NAV.filter(n=>!n.admin||user.role==='admin');
  if(layout==='topbar') return <div className="shell shell-top">
    <header className="topbar"><Brand/><nav className="topnav">{items.map(n=><button key={n.id} className={active===n.id?'on':''} onClick={()=>go(n.id)}>{n.label}</button>)}</nav>
      <div className="me"><span className="avatar">{user.initials}</span><button className="icon-btn" title="Đăng xuất" onClick={onLogout}><Icon n="out" s={17}/></button></div></header>
    <main className="main">{children}</main></div>;
  if(layout==='rail') return <div className="shell shell-rail">
    <aside className="rail"><Brand compact/>{items.map(n=><button key={n.id} className={'rail-item'+(active===n.id?' on':'')} title={n.label} onClick={()=>go(n.id)}><Icon n={n.icon} s={20}/><span>{n.label.split(' ')[0]}</span></button>)}
      <div className="grow"></div><button className="rail-item" title="Đăng xuất" onClick={onLogout}><span className="avatar">{user.initials}</span></button></aside>
    <main className="main">{children}</main></div>;
  return <div className="shell shell-side">
    <aside className="side"><Brand/>
      <button className="btn btn-primary side-new" onClick={()=>go('chat',{newChat:true})}><Icon n="plus" s={16}/>Cuộc hội thoại mới</button>
      <nav>{items.map(n=><button key={n.id} className={'side-item'+(active===n.id?' on':'')} onClick={()=>go(n.id)}><Icon n={n.icon}/>{n.label}</button>)}</nav>
      <div className="side-sec">Bộ sưu tập</div>
      {['Nhân sự','Tài chính','Mua sắm','Pháp chế','CNTT'].map(d=><button key={d} className="side-item sm" onClick={()=>go('library',{dept:d})}><span className="dot"></span>{d}</button>)}
      <div className="grow"></div>
      <div className="side-user"><span className="avatar">{user.initials}</span><div><div className="u-name">{user.name}</div><div className="u-sub">{user.groups.join(' · ')}</div></div><button className="icon-btn" title="Đăng xuất" onClick={onLogout}><Icon n="out" s={17}/></button></div>
    </aside>
    <main className="main">{children}</main></div>;
}

function Login({onSso}){
  const [busy,setBusy]=useState(false);
  return <div className="login">
    <div className="login-card">
      <Brand/>
      <h1>Đăng nhập</h1>
      <p className="muted">Tìm kiếm và hỏi đáp trên kho tài liệu nội bộ. Bạn chỉ thấy tài liệu thuộc nhóm của mình.</p>
      <button className="btn btn-primary btn-lg w100" onClick={()=>{setBusy(true);onSso()}} disabled={busy}>{busy?<><span className="spin"></span>Đang chuyển hướng tới SSO…</>:<><Icon n="lock" s={16}/>Đăng nhập bằng SSO công ty</>}</button>
      <p className="fine">Xác thực bởi Amazon Cognito liên kết với IdP công ty · MFA bắt buộc</p>
    </div>
    <div className="login-side"><Placeholder label="ảnh thương hiệu / văn phòng" h="100%"/></div>
  </div>;
}

export {Icon,useStream,RichAnswer,TypeTag,Btn,Placeholder,Shell,Login,Brand};
