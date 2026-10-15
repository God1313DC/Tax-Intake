<?php
namespace App\Http\Controllers;

use App\Services\TaxIntakeService;
use Illuminate\Http\Request;
use Illuminate\Support\Facades\Http;
use Illuminate\Support\Facades\Validator;
use Illuminate\Support\Str;
use Illuminate\Validation\Rule;

class TaxIntakeController extends Controller
{
    public function landing()
    {
        return response()->view('intake.landing')->header('Cache-Control','public, max-age=300');
    }

    public function form(Request $request, string $kind, TaxIntakeService $service)
    {
        $questions = $service->definition($kind)['questions'];
        if (!$request->session()->has('intake_owner')) $request->session()->put('intake_owner', Str::random(64));
        return response()->view('intake.form', ['kind'=>$kind, 'settings'=>[
            'kind'=>$kind,'questions'=>$questions,'csrf'=>csrf_token(),
            'submitUrl'=>url('/tax-intake/'.$kind.'/submit'), 'explainUrl'=>url('/tax-intake/explain')
        ]])->header('Cache-Control','no-store, private');
    }

    public function submit(Request $request, string $kind, TaxIntakeService $service)
    {
        abort_if(strlen($request->getContent()) > 65536, 413);
        $request->validate(['answers'=>'required|array|max:80', 'submission_id'=>'required|uuid']);
        $owner = $request->session()->get('intake_owner');
        abort_unless(is_string($owner), 419);
        $input = $request->input('answers'); $rules = []; $labels = [];
        foreach ($service->active($kind, $input) as $q) {
            $rules[$q['key']] = ['required','string','max:1500'];
            $labels[$q['key']] = $q['label'];
            if ($q['choices']) $rules[$q['key']][] = Rule::in($q['choices']);
        }
        $rules['email'] = ['required','email','max:254'];
        $rules['consent'] = ['required', Rule::in(['I agree'])];
        if (($input['filing_year'] ?? '') === 'Other') $rules['other_year'] = ['required','regex:/^(19|20)\d{2}$/'];
        $answers = Validator::make($input, $rules, [], $labels)->validate();
        // Ignore hidden fields when a previous answer changed.
        $answers = array_intersect_key($answers, $rules);
        $record = $service->save($request->input('submission_id'), hash('sha256',$owner), $kind, $answers);
        $notificationSent = $service->notify($record['id']);
        return response()->json(['id'=>$record['id'], 'analysis'=>$record['analysis'], 'notification_sent'=>$notificationSent])
            ->header('Cache-Control','no-store')->header('X-Robots-Tag','noindex, nofollow');
    }

    public function explain(Request $request, TaxIntakeService $service)
    {
        $data = $request->validate(['kind'=>['required',Rule::in(['individual','business'])], 'key'=>'required|string|max:60']);
        $question = collect($service->definition($data['kind'])['questions'])->firstWhere('key',$data['key']);
        abort_unless($question,404);
        $fallback = $question['help'] ?: 'This helps your preparer identify the records and follow-up information needed. If you are unsure, choose Not sure when offered. Do not enter tax IDs or bank details.';
        $endpoint = config('tax-intake.ollama_url'); $model = config('tax-intake.ollama_model');
        if ($endpoint && $model) {
            try {
                $response = Http::timeout(12)->post(rtrim($endpoint,'/').'/api/chat', [
                    'model'=>$model,'stream'=>false,'options'=>['num_predict'=>120],
                    'messages'=>[
                        ['role'=>'system','content'=>'Explain this predefined tax intake question in under 60 plain-English words. Do not provide eligibility, tax rates, deadlines or refund advice. Never request tax IDs, bank details or documents.'],
                        ['role'=>'user','content'=>$question['label']]
                    ]
                ]);
                $text = $response->successful() ? $response->json('message.content') : null;
                if (is_string($text) && trim($text)) return response()->json(['text'=>mb_substr($text,0,1500),'mode'=>'ai'])->header('Cache-Control','no-store');
            } catch (\Throwable $error) { /* Guided help remains available. */ }
        }
        return response()->json(['text'=>$fallback,'mode'=>'guided'])->header('Cache-Control','no-store');
    }

    public function team(TaxIntakeService $service)
    {
        return response()->view('intake.team',['items'=>$service->recent()])
            ->header('Cache-Control','no-store, private')->header('X-Robots-Tag','noindex, nofollow');
    }

    public function retry(Request $request, TaxIntakeService $service)
    {
        $data=$request->validate(['reference'=>'required|uuid']);
        $ok=$service->notify($data['reference']);
        return back()->with('intake_notice',$ok ? 'Notification accepted by the mail server.' : 'Notification was already sent or delivery still needs attention.');
    }
}
