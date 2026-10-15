'use strict';
const cfg=JSON.parse(document.getElementById('config').textContent), answers={};
const $=id=>document.getElementById(id);
let index=0, selected='', sending=false;
const submissionId=crypto.randomUUID();
function active(){return cfg.questions.filter(q=>!q.when||(Array.isArray(q.when[1])?q.when[1]:[q.when[1]]).includes(answers[q.when[0]]));}
function draw(){
 const qs=active(),q=qs[index];
 $('status').textContent=''; $('progress').value=Math.round(index/qs.length*100);
 $('step-count').textContent=q?'Question '+(index+1)+' of '+qs.length:'Ready to submit';$('back').disabled=index===0; $('review').hidden=!!q; $('answer-form').hidden=!q;
 if(!q){$('review-list').replaceChildren();for(const item of qs){let dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=item.label;dd.textContent=answers[item.key];$('review-list').append(dt,dd);}return;}
 $('question').textContent=q.label;$('help').textContent=q.help||'';$('choices').replaceChildren();selected=answers[q.key]||'';
 $('answer').hidden=!!q.choices;$('answer').value=selected;$('answer').type=q.key==='email'?'email':'text';$('answer').required=!q.choices;
 $('transcript').replaceChildren();if(index){const prev=qs[index-1],b=document.createElement('div');b.className='bubble';b.textContent='You: '+answers[prev.key];$('transcript').append(b);}
 if(q.choices){for(const choice of q.choices){const b=document.createElement('button');b.type='button';b.className='choice';b.textContent=choice;b.setAttribute('aria-pressed',String(selected===choice));b.onclick=()=>{selected=choice;for(const child of $('choices').children)child.setAttribute('aria-pressed',String(child===b));};$('choices').append(b);}}else $('answer').focus();
}
$('answer-form').onsubmit=e=>{e.preventDefault();const q=active()[index],value=q.choices?selected:$('answer').value.trim();if(!value){$('status').textContent='Please enter or choose an answer.';return;}if(q.key==='consent'&&value!=='I agree'){$('status').textContent='Your answers have not been sent. You can close this tab or go back.';return;}answers[q.key]=value;index++;draw();};
$('review-back').onclick=()=>{index=0;draw();};
$('back').onclick=()=>{index=Math.max(0,index-1);draw();};
$('why').onclick=async()=>{const q=active()[index];$('why').disabled=true;try{const res=await fetch(cfg.explainUrl,{method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json','X-CSRF-TOKEN':cfg.csrf},body:JSON.stringify({csrf:cfg.csrf,kind:cfg.kind,key:q.key})});if(!res.ok)throw Error();const data=await res.json();if(active()[index]?.key===q.key){$('help').textContent=data.text;$('mode').textContent=data.mode==='ai'?'AI explanation · please verify':'Guided intake';}}catch{$('help').textContent='Your preparer can help clarify this question. Choose Not sure if available.';}finally{$('why').disabled=false;}};
$('submit').onclick=async()=>{if(sending)return;sending=true;$('submit').disabled=true;$('status').textContent='Saving your intake…';try{const res=await fetch(cfg.submitUrl,{method:'POST',headers:{'Content-Type':'application/json','Accept':'application/json','X-CSRF-TOKEN':cfg.csrf,'Idempotency-Key':submissionId},body:JSON.stringify({answers,submission_id:submissionId})});if(!res.ok){if(res.status===419)throw Error('Your session expired. Reload this page to start again.');if(res.status===429)throw Error('Please wait a minute before trying again.');if(res.status===422){const error=await res.json();throw Error(Object.values(error.errors||{}).flat()[0]||'Please review your answers.');}throw Error('We could not confirm the save. Please try again; retrying will not create a duplicate.');}const data=await res.json();$('review').replaceChildren();const h=document.createElement('h2');h.textContent='Thank you. Your intake is saved.';$('review').append(h);const p=document.createElement('p');p.textContent='Your team will review your answers. Here is your starting document checklist; arrange secure collection with your preparer.';$('review').append(p);for(const doc of data.analysis.documents){const title=document.createElement('h3'),reason=document.createElement('p');title.textContent=doc.title;reason.textContent=doc.reason;$('review').append(title,reason);}const printButton=document.createElement('button');printButton.type='button';printButton.textContent='Print your checklist';printButton.onclick=()=>window.print();$('review').append(printButton);$('status').textContent='Reference: '+data.id+(data.notification_sent?' · Email notification sent to our team.':' · Saved for team review.');$('progress').value=100;$('transcript').replaceChildren();}catch(error){$('status').textContent=error.message||'Connection interrupted. Please try again.';$('submit').disabled=false;sending=false;}};
draw();

// The optional local helper receives only the current question and selected structured facts.
window.taxIntakeBridge={
 currentQuestion:()=>{const q=active()[index];return q?{label:q.label,help:q.help||''}:null;},
 summaryFacts:()=>active().filter(q=>q.choices&&q.key!=='consent').map(q=>q.label+' '+(answers[q.key]||'Not answered')).join('\n'),
 setSummary:text=>{if(text)answers._ai_summary=String(text).slice(0,2500);else delete answers._ai_summary;}
};
