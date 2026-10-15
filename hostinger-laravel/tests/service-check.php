<?php
namespace Illuminate\Support { class Str { public static function isUuid($id) { return preg_match('/^[0-9a-f-]{36}$/',$id); } } }
namespace Illuminate\Support\Facades {
    // Framework seams only: these tests don't validate Laravel's encryption/SMTP implementations.
    class Crypt { public static function encryptString($s){return base64_encode($s);} public static function decryptString($s){return base64_decode($s);} }
    class Log { public static function warning(...$args){} }
    class Mail { public static function mailer($name){throw new \RuntimeException('Simulated mail outage');} }
}
namespace {
    function abort_unless($test,$status){if(!$test)throw new \RuntimeException((string)$status);}
    function storage_path($suffix){return sys_get_temp_dir().'/intake-test-'.getmypid().'/'.$suffix;}
    function now(){return new class {function toIso8601String(){return date('c');}};}
    function config($key){return null;}
    require __DIR__.'/../app/Services/TaxIntakeService.php';
    $s = new \App\Services\TaxIntakeService;
    $count=0;
    function check($condition,$message){global $count;if(!$condition)throw new \RuntimeException($message);$count++;}
    foreach(['individual','business'] as $kind){
        $a=['filing_year'=>'2025','residency'=>'Resident all year','books'=>'Yes','dependents'=>'No','self_employed'=>'Yes'];
        $questions=$s->active($kind,$a);
        check(count($questions)>15,'Questionnaire incomplete');
        $report=$s->analysis($kind,$a);
        check(count($report['documents'])>0,'Checklist missing');
        check(count($report['review'])>0,'Review missing');
        if($kind==='individual'){
            $keys=array_column($questions,'key');
            check(in_array('gig_details',$keys),'Gig follow-up missing');
            check(!in_array('dependent_facts',$keys),'Hidden dependent field retained');
            check(str_contains(json_encode($report['documents']),'mileage'),'Business mileage records missing');
        }
    }
    $id='1e19785f-d4b1-418e-bd99-b82c48c13173';
    $a=['full_name'=>'Sample','email'=>'sample@example.com','filing_year'=>'2025'];
    $record=$s->save($id,'owner','individual',$a);
    check($record['answers']===$a,'Save failed');
    check($s->save($id,'owner','individual',['full_name'=>'Changed'])['answers']===$a,'Duplicate submission changed record');
    try{$s->save($id,'different','individual',$a);check(false,'Cross-session conflict accepted');}catch(\RuntimeException $e){check($e->getMessage()==='409','Wrong conflict response');}
    check(!$s->notify($id),'Mail failure not handled');
    check($s->recent()[0]['notification']==='failed','Notification failure not retained');
    $unknown=$s->analysis('business',['books'=>'Not sure','foreign'=>'Yes','filing_year'=>'Other','other_year'=>'2022']);
    check(str_contains(json_encode($unknown),'2022'),'Other year missing');
    check(str_contains(json_encode($unknown),'specialist'),'International review missing');
    echo "PASS: {$count} service checks\n";
}
