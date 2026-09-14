(function(){
  const form=document.getElementById('loginForm');
  const err=document.getElementById('loginError');
  form.addEventListener('submit',async e=>{
    e.preventDefault();
    err.hidden=true;
    const username=document.getElementById('loginUser').value;
    const password=document.getElementById('loginPass').value;
    try{
      const resp=await fetch('/api/auth/login',{
        method:'POST',
        headers:{'Content-Type':'application/json','X-CSRF-Token':window.__LOGIN_CSRF||''},
        body:JSON.stringify({username,password})
      });
      const body=await resp.json().catch(()=>({ok:false,error:'Sunucu yanıtı okunamadı'}));
      if(!resp.ok||!body.ok){
        err.textContent=body.error||'Giriş başarısız';
        err.hidden=false;
        return;
      }
      if(body.csrfToken){try{sessionStorage.setItem('nexgen_csrf',body.csrfToken)}catch(e){}}
      window.location.replace(body.redirect||'/');
    }catch(ex){
      err.textContent=ex.message||'Bağlantı hatası';
      err.hidden=false;
    }
  });
})();
