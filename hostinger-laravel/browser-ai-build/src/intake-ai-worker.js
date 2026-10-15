import { pipeline, env } from '@huggingface/transformers';
env.allowLocalModels=false;
env.useBrowserCache=true;
env.backends.onnx.wasm.numThreads=1;
let extractor=null,corpus=[],vectors=[],busy=false;
const dot=(a,b)=>a.reduce((s,v,i)=>s+v*b[i],0);
self.onmessage=async({data})=>{
 if(busy){self.postMessage({id:data.id,type:'error',text:'The helper is finishing another request. Please try again shortly.'});return;}
 busy=true;
 try{
  if(data.type==='load'){
   if(!extractor)extractor=await pipeline('feature-extraction','Xenova/all-MiniLM-L6-v2',{
    revision:'751bff37182d3f1213fa05d7196b954e230abad9',device:'wasm',dtype:'q8',
    progress_callback:info=>{if(info.status==='progress')self.postMessage({id:data.id,type:'progress',text:'Downloading AI helper: '+Math.round(info.progress||0)+'%'});}
   });
   corpus=Array.isArray(data.corpus)?data.corpus:[];
   if(!corpus.length)throw Error('No reviewed guidance');
   const encoded=await extractor(corpus.map(c=>c.question+' '+c.answer),{pooling:'mean',normalize:true});
   vectors=encoded.tolist();
   self.postMessage({id:data.id,type:'ready'});
  }else if(data.type==='query'){
   if(!extractor||!vectors.length)throw Error('Helper not loaded');
   const encoded=await extractor(String(data.prompt||'').slice(0,500),{pooling:'mean',normalize:true});
   const query=encoded.tolist()[0];
   const ranked=corpus.map((c,i)=>({...c,score:dot(query,vectors[i])})).sort((a,b)=>b.score-a.score);
   const best=ranked[0];
   if(best.score<0.36){self.postMessage({id:data.id,type:'result',text:'I could not confidently match that to our intake guidance. Ask about a specific form or document, or check with your preparer.',source:null,matched:null});}
   else self.postMessage({id:data.id,type:'result',text:best.answer,source:best.source,matched:best.title||best.question,score:best.score});
  }
 }catch(error){self.postMessage({id:data.id,type:'error',text:'AI matching is unavailable. Guided questions and help still work.'});}
 finally{busy=false;}
};
