<?php
namespace App\Services;
use Illuminate\Support\Facades\Http;

class TaxIntakeSources
{
    public const SOURCES = [
        'individual'=>'https://www.irs.gov/filing/gather-your-documents',
        'business'=>'https://www.irs.gov/businesses/small-businesses-self-employed/what-kind-of-records-should-i-keep',
    ];
    private function path(): string
    {
        $directory=storage_path('app/private/tax-guidance');
        if(!is_dir($directory) && !@mkdir($directory,0700,true) && !is_dir($directory)) throw new \RuntimeException('Guidance storage unavailable');
        return $directory.'/sources.json';
    }
    public function status(): array
    {
        $path=$this->path();
        return is_file($path) ? (json_decode(file_get_contents($path),true) ?: []) : [];
    }
    public function refreshIfDue(bool $force=false): array
    {
        $path=$this->path();$handle=fopen($path.'.lock','c+');
        if(!$handle || !flock($handle,LOCK_EX|LOCK_NB)) {if($handle)fclose($handle);return $this->status();}
        try{
            $state=$this->status();
            if(!$force && isset($state['checked_at']) && strtotime($state['checked_at'])>time()-86400)return $state;
            foreach(self::SOURCES as $kind=>$url){
                $old=$state['sources'][$kind] ?? [];
                try{
                    $response=Http::connectTimeout(5)->timeout(15)->withHeaders(['User-Agent'=>'US Tax Deals source freshness checker; ustaxdeals.com'])->get($url);
                    if(!$response->successful())throw new \RuntimeException('Source unavailable');
                    $html=$response->body();
                    if(strlen($html)>2000000)throw new \RuntimeException('Source too large');
                    $doc=new \DOMDocument();$before=libxml_use_internal_errors(true);$doc->loadHTML('<?xml encoding="UTF-8">'.$html);libxml_clear_errors();libxml_use_internal_errors($before);
                    $xpath=new \DOMXPath($doc);$main=$xpath->query('//main')->item(0) ?: $xpath->query('//*[@id="main-content"]')->item(0);
                    if(!$main)throw new \RuntimeException('Source format changed');
                    foreach($xpath->query('.//nav|.//header|.//footer|.//script|.//style',$main) as $node){$node->parentNode->removeChild($node);}
                    $text=trim(preg_replace('/\s+/u',' ',$main->textContent));
                    if(mb_strlen($text)<300)throw new \RuntimeException('Source incomplete');
                    $hash=hash('sha256',$text);
                    $state['sources'][$kind]=['url'=>$url,'fetched_at'=>now()->toIso8601String(),'text'=>mb_substr($text,0,20000),'hash'=>$hash,
                        'changed'=>isset($old['hash']) && $old['hash']!==$hash,'review_required'=>($old['review_required']??false)||(isset($old['hash'])&&$old['hash']!==$hash),'error'=>false];
                }catch(\Throwable $e){$state['sources'][$kind]=array_merge($old,['url'=>$url,'error'=>true]);}
            }
            $state['checked_at']=now()->toIso8601String();
            $temp=tempnam(dirname($path),'.source-');
            try{file_put_contents($temp,json_encode($state,JSON_THROW_ON_ERROR),LOCK_EX);@chmod($temp,0600);if(!rename($temp,$path))throw new \RuntimeException('Source status save failed');}finally{if(is_file($temp))@unlink($temp);}
            return $state;
        }finally{flock($handle,LOCK_UN);fclose($handle);}
    }
}
