'use strict';
const cfg=JSON.parse(document.getElementById('config').textContent), answers={};
const $=id=>document.getElementById(id);
let index=0, selected='', sending=false;
const submissionId=crypto.randomUUID();
function active(){return cfg.questions.filter(q=>!q.when||(Array.isArray(q.when[1])?q.when[1]:[q.when[1]]).includes(answers[q.when[0]]));}
function draw(){
 const qs=active(),q=qs[index];
 $('status').textContent=''; $('progress').value=Math.round(index/qs.length*100);
 $('back').disabled=index===0; $('review').hidden=!!q; $('answer-form').hidden=!q;
 if(!q){$('review-list').replaceChildren();for(const item of qs){let dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=item.label;dd.textContent=answers[item.key];$('review-list').append(dt,dd);}return;}
 $('question').textContent=q.label;$('help').textContent=q.help||'';$('choices').replaceChildren();selected=answers[q.key]||'';
 $('answer').hidden=!!q.choices;$('answer').value=selected;$('answer').type=q.key==='email'?'email':'text';$('answer').required=!q.choices;
 $('transcript').replaceChildren();if(index){const prev=qs[index-1],b=document.createElement('div');b.className='bubble';b.textContent='You: '+answers[prev.key];$('transcript').append(b);}
 if(q.choices){for(const choice of q.choices){const b=document.createElement('button');b.type='button';b.className='choice';b.textContent=choice;b.setAttribute('aria-pressed',String(selected===choice));b.onclick=()=>{selected=choice;for(const child of $('choices').children)child.setAttribute('aria-pressed',String(child===b));};$('choices').append(b);}}else $('answer').focus();
}
$('answer-form').onsubmit=e=>{e.preventDefault();const q=active()[index],value=q.choices?selected:$('answer').value.trim();if(!value){$('status').textContent='Please enter or choose an answer.';return;}if(q.key==='consent'&&value!=='I agree'){$('status').textContent='Your answers have not been sent. You can close this tab or go back.';return;}answers[q.key]=value;index++;draw();};
$('review-back').onclick=()=>{index=Math.max(0,active().length-1);draw();};
$('back').onclick=()=>{index=Math.max(0,index-1);draw();};
$('why').onclick=async()=>{const q=active()[index];$('why').disabled=true;try{const res=await fetch('/api/intake/explain',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({csrf:cfg.csrf,kind:cfg.kind,key:q.key})});if(!res.ok)throw Error();const data=await res.json();if(active()[index]?.key===q.key){$('help').textContent=data.text;$('mode').textContent=data.mode==='ai'?'AI explanation · please verify':'Guided intake';}}catch{$('help').textContent='Your preparer can help clarify this question. Choose Not sure if available.';}finally{$('why').disabled=false;}};
$('submit').onclick=async()=>{if(sending)return;sending=true;$('submit').disabled=true;$('status').textContent='Saving your intake…';try{const res=await fetch('/api/intake/'+cfg.kind+'/submit',{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':submissionId},body:JSON.stringify({csrf:cfg.csrf,answers})});if(!res.ok)throw Error();const data=await res.json();$('review').replaceChildren();const h=document.createElement('h2');h.textContent='Thank you. Your intake is saved.';$('review').append(h);const p=document.createElement('p');p.textContent='Your team will review your answers. Here is your starting document checklist; arrange secure collection with your preparer.';$('review').append(p);for(const doc of data.analysis.documents){const title=document.createElement('h3'),reason=document.createElement('p');title.textContent=doc.title;reason.textContent=doc.reason;$('review').append(title,reason);}$('status').textContent='Reference: '+data.id;$('progress').value=100;$('transcript').replaceChildren();}catch{$('status').textContent='We could not confirm the save. Please try again; retrying will not create a duplicate.';$('submit').disabled=false;sending=false;}};
draw();
