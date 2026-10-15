'use strict';
(()=>{
 const el=id=>document.getElementById(id);
 const cfg=JSON.parse(el('config').textContent);
 const source=cfg.kind==='business'?'https://www.irs.gov/businesses/small-businesses-self-employed/what-kind-of-records-should-i-keep':'https://www.irs.gov/filing/gather-your-documents';
 const corpus=cfg.questions.filter(q=>q.help).map(q=>({key:q.key,question:q.label,answer:q.help,source}));
 corpus.push(
  {key:'w2',title:'Employee wage statements (W-2)',question:'W-2 employee employer wage statement paycheck withholding tax form',answer:'A W-2 reports employee wages and withholding. Keep each employer’s W-2 so your preparer can review the amounts reported.',source:'https://www.irs.gov/filing/gather-your-documents'},
  {key:'1095a',title:'Marketplace insurance (1095-A)',question:'1095-A Marketplace health insurance coverage healthcare insurance statement',answer:'Form 1095-A reports Marketplace health insurance coverage. Keep each Marketplace policy statement for your preparer to review coverage and reconcile advance premium tax credits when applicable.',source:'https://www.irs.gov/filing/gather-your-documents'},
  {key:'1098t',title:'College and education records',question:'1098-T college tuition education student scholarships grants books university statement',answer:'Gather Form 1098-T, tuition and required education expense records, plus scholarship and grant information. Your preparer checks how these amounts interact and whether a tax benefit applies.',source:'https://www.irs.gov/filing/gather-your-documents'},
  {key:'gig',title:'Freelance and delivery income',question:'DoorDash Uber rideshare delivery freelance gig self employed side job mileage receipts',answer:'Yes—report your DoorDash, Uber or other gig income, even if you do not receive a 1099. In this form, select self-employment or gig income. Gather your app earnings statements, any 1099s, business expense receipts and mileage log.',source:'https://www.irs.gov/filing/gather-your-documents'},
  {key:'books',title:'Business bookkeeping records',question:'Business bookkeeping profit loss balance sheet general ledger records reconciliation',answer:'Gather year-end profit and loss, balance sheet, general ledger and supporting income and expense records. Reconcile bank and card activity so your preparer can review the books.',source:'https://www.irs.gov/businesses/small-businesses-self-employed/what-kind-of-records-should-i-keep'},
  {key:'privacy',title:'Secure document collection',question:'upload documents SSN social security EIN bank details secure privacy identification',answer:'Do not enter tax IDs, bank numbers or document contents here. This questionnaire has no document upload. Your preparer will arrange a secure collection process.',source:'https://ustaxdeals.com/privacy-policy'}
 );
 let worker=null,ready=false,busy=false,requestId=0,loadingTimer=null,generationTimer=null;
 const status=text=>{el('ai-status').textContent=text;};
 const controls=disabled=>['ai-send','ai-summary','ai-explain-current'].forEach(id=>{el(id).disabled=disabled;});
 function reset(message){worker?.terminate();worker=null;ready=false;busy=false;clearTimeout(loadingTimer);clearTimeout(generationTimer);status('Chat ready · quick answers available');controls(false);}
 function show(text,sourceURL){
  const output=el('ai-output');output.replaceChildren();
  
  output.append(document.createTextNode(text));
  const inquiry=document.createElement('a');inquiry.textContent='Send an inquiry for a detailed review →';inquiry.href='/contact';inquiry.className='chat-inquiry';output.append(document.createElement('br'),inquiry);
  if(sourceURL){const link=document.createElement('a');link.textContent='Reference';link.href=sourceURL;link.target='_blank';link.rel='noopener noreferrer';output.append(document.createElement('br'),link);}
 }
 function startAI(){
  if(worker)return;status('Chat ready · enhancing question matching…');
  try{
   worker=new Worker('/intake-assets/intake-ai-worker.js?v=3',{type:'module'});
   worker.onerror=()=>reset('AI is unavailable on this device. Guided questions and help still work.');
   worker.onmessage=({data})=>{
    if(data.type==='progress'){return;}
    if(data.type==='ready'){clearTimeout(loadingTimer);ready=true;el('ai-panel').hidden=false;status('Chat ready');controls(false);return;}
    if(data.type==='error'){clearTimeout(generationTimer);if(!ready){reset(data.text);return;}busy=false;controls(false);show('Please send an inquiry so our team can review your question and give you a specific answer.');status('Chat ready');return;}
    if(data.type==='result'){clearTimeout(generationTimer);busy=false;controls(false);status('Chat ready');show(data.matched ? data.text : 'Please send an inquiry so our team can review your question and give you a specific answer.',data.source);}
   };
   loadingTimer=setTimeout(()=>reset('AI loading took too long. Retry or continue guided intake.'),180000);
   worker.postMessage({type:'load',id:++requestId,corpus});
  }catch{reset('AI is unavailable on this device. Guided intake is still available.');}
 }

 function query(prompt){
  if(busy)return;
  const normalized=prompt.toLowerCase().replace(/[^a-z0-9]+/g,' ');
  const topics=[['gig',/\b(door\s?dash|uber|lyft|instacart|grubhub|freelanc\w*|gig|delivery|self employ\w*|side hustle)\b/],['w2',/\b(w\s?2|wage statement|employer|paycheck)\b/],['1095a',/\b(1095\s?a|marketplace|health insurance)\b/],['1098t',/\b(1098\s?t|college|tuition|scholarship|university)\b/],['books',/\b(bookkeeping|balance sheet|profit and loss|general ledger)\b/],['privacy',/\b(upload|ssn|ein|bank details|social security number)\b/]];
  const topic=topics.find(([,pattern])=>pattern.test(normalized));
  if(topic){const card=corpus.find(c=>c.key===topic[0]);show(card.answer,card.source);return;}
  if(!ready){show('Please send an inquiry so our team can review your question and give you a specific answer.');return;}
  busy=true;controls(true);status('Matching your question to reviewed guidance…');
  generationTimer=setTimeout(()=>reset('AI was too slow on this device. Guided intake remains available.'),30000);
  worker.postMessage({id:++requestId,type:'query',prompt});
 }
 el('ai-explain-current').onclick=()=>{const q=window.taxIntakeBridge.currentQuestion();if(!q){show('Your questionnaire is ready to submit. You can build a summary instead.');return;}show(q.help || 'Send an inquiry if you need help answering this question.');};
 el('ai-send').onclick=()=>{
  const text=el('ai-message').value.trim();if(!text){show('Enter a question about your intake or documents.');return;}
  if(/\b\d{3}[- ]?\d{2}[- ]?\d{4}\b|\b\d{2}-\d{7}\b|\b\d{13,19}\b/.test(text)){show('Please remove tax IDs or account numbers and ask a general intake question instead.');return;}
  if(/qualif|eligib|refund|deadline|tax rate|how much|credit amount|deduction amount/i.test(text)){show('That needs a review of your tax year and details. Send an inquiry so our team can check your situation and give you a specific answer.');return;}
  query(text);
 };
 el('ai-message').addEventListener('keydown',event=>{if(event.key==='Enter'&&!event.shiftKey){event.preventDefault();el('ai-send').click();}});
 el('ai-summary').onclick=()=>{
  const facts=window.taxIntakeBridge.summaryFacts().split('\n').filter(s=>!s.endsWith('Not answered'));
  if(!facts.length){show('Answer a few intake questions first, then build your summary.');return;}
  el('ai-summary-box').hidden=false;el('ai-draft').value='Structured intake summary for preparer review:\n'+facts.map(s=>'• '+s).join('\n');
  show('Review these recorded facts before including them. This structured summary does not infer tax eligibility.');
 };
 el('ai-keep-draft').onclick=()=>{window.taxIntakeBridge.setSummary(el('ai-draft').value);show('Summary included. Review it before submitting your intake.');};
 el('ai-remove-draft').onclick=()=>{window.taxIntakeBridge.setSummary('');el('ai-draft').value='';el('ai-summary-box').hidden=true;show('Summary removed.');};
 show('Hi! Ask me about your tax documents or how to answer this form.');
 startAI();
})();
