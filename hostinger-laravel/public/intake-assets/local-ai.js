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
  {key:'gig',title:'Freelance and delivery income',question:'DoorDash Uber rideshare delivery freelance gig self employed side job mileage receipts',answer:'Gather income records, any 1099-NEC or 1099-K forms received, business expense receipts and mileage logs. Report all business income to your preparer, including income not shown on a tax form.',source:'https://www.irs.gov/filing/gather-your-documents'},
  {key:'books',title:'Business bookkeeping records',question:'Business bookkeeping profit loss balance sheet general ledger records reconciliation',answer:'Gather year-end profit and loss, balance sheet, general ledger and supporting income and expense records. Reconcile bank and card activity so your preparer can review the books.',source:'https://www.irs.gov/businesses/small-businesses-self-employed/what-kind-of-records-should-i-keep'},
  {key:'privacy',title:'Secure document collection',question:'upload documents SSN social security EIN bank details secure privacy identification',answer:'Do not enter tax IDs, bank numbers or document contents here. This questionnaire has no document upload. Your preparer will arrange a secure collection process.',source:'https://ustaxdeals.com/privacy-policy'}
 );
 let worker=null,ready=false,busy=false,requestId=0,loadingTimer=null,generationTimer=null;
 const status=text=>{el('ai-status').textContent=text;};
 const controls=disabled=>['ai-send','ai-summary','ai-explain-current'].forEach(id=>{el(id).disabled=disabled;});
 function reset(message){worker?.terminate();worker=null;ready=false;busy=false;clearTimeout(loadingTimer);clearTimeout(generationTimer);el('ai-panel').hidden=true;el('ai-stop').hidden=true;el('ai-enable').disabled=false;status(message);}
 function show(text,sourceURL,matched){
  const output=el('ai-output');output.replaceChildren();
  if(matched){const label=document.createElement('strong');label.textContent='Matched guidance: '+matched;output.append(label,document.createElement('br'));}
  output.append(document.createTextNode(text));
  if(sourceURL){const link=document.createElement('a');link.textContent='Reference';link.href=sourceURL;link.target='_blank';link.rel='noopener noreferrer';output.append(document.createElement('br'),link);}
 }
 el('ai-enable').onclick=()=>{
  if(worker)return;el('ai-enable').disabled=true;el('ai-stop').hidden=false;status('Loading on-device AI. You can continue the form while it loads.');
  try{
   worker=new Worker('/intake-assets/intake-ai-worker.js?v=3',{type:'module'});
   worker.onerror=()=>reset('AI is unavailable on this device. Guided questions and help still work.');
   worker.onmessage=({data})=>{
    if(data.type==='progress'){status(data.text);return;}
    if(data.type==='ready'){clearTimeout(loadingTimer);ready=true;el('ai-panel').hidden=false;status('AI ready · on-device matching to reviewed guidance');controls(false);return;}
    if(data.type==='error'){clearTimeout(generationTimer);if(!ready){reset(data.text);return;}busy=false;controls(false);show(data.text);status('Guided help remains available.');return;}
    if(data.type==='result'){clearTimeout(generationTimer);busy=false;controls(false);status('AI ready · on-device matching to reviewed guidance');show(data.text,data.source,data.matched);}
   };
   loadingTimer=setTimeout(()=>reset('AI loading took too long. Retry or continue guided intake.'),180000);
   worker.postMessage({type:'load',id:++requestId,corpus});
  }catch{reset('AI is unavailable on this device. Guided intake is still available.');}
 };
 el('ai-stop').onclick=()=>reset('AI stopped. Your form answers are unchanged.');
 function query(prompt){
  if(!ready||busy)return;busy=true;controls(true);status('Matching your question to reviewed guidance…');
  generationTimer=setTimeout(()=>reset('AI was too slow on this device. Guided intake remains available.'),30000);
  worker.postMessage({id:++requestId,type:'query',prompt});
 }
 el('ai-explain-current').onclick=()=>{const q=window.taxIntakeBridge.currentQuestion();if(!q){show('Your questionnaire is ready to submit. You can build a summary instead.');return;}query(q.label);};
 el('ai-send').onclick=()=>{
  const text=el('ai-message').value.trim();if(!text){show('Enter a question about your intake or documents.');return;}
  if(/\b\d{3}[- ]?\d{2}[- ]?\d{4}\b|\b\d{2}-\d{7}\b|\b\d{13,19}\b/.test(text)){show('Please remove tax IDs or account numbers and ask a general intake question instead.');return;}
  if(/qualif|eligib|refund|deadline|tax rate|how much|credit amount|deduction amount/i.test(text)){show('Your preparer must verify that for your tax year and circumstances. This helper organizes intake and documents; it does not determine eligibility, amounts or deadlines.');return;}
  query(text);
 };
 el('ai-summary').onclick=()=>{
  const facts=window.taxIntakeBridge.summaryFacts().split('\n').filter(s=>!s.endsWith('Not answered'));
  if(!facts.length){show('Answer a few intake questions first, then build your summary.');return;}
  el('ai-summary-box').hidden=false;el('ai-draft').value='Structured intake summary for preparer review:\n'+facts.map(s=>'• '+s).join('\n');
  show('Review these recorded facts before including them. This structured summary does not infer tax eligibility.');
 };
 el('ai-keep-draft').onclick=()=>{window.taxIntakeBridge.setSummary(el('ai-draft').value);show('Summary included. Review it before submitting your intake.');};
 el('ai-remove-draft').onclick=()=>{window.taxIntakeBridge.setSummary('');el('ai-draft').value='';el('ai-summary-box').hidden=true;show('Summary removed.');};
})();
