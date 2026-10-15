<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow"><title>Tax Intake Workspace | US Tax Deals</title><link rel="stylesheet" href="/intake-assets/intake.css?v=20261015b"></head><body><header><a href="/dashboard" class="brand">US TAX DEALS <span>Team workspace</span></a><a href="/tax-intake">Open intake</a></header><main><h1>Tax intake workspace</h1><p>Latest 100 submissions · <a href="/dashboard">Back to dashboard</a></p>
@if(session('intake_notice'))<p role="status">{{ session('intake_notice') }}</p>
@endif <section class="conversation"><h2>IRS source freshness</h2><p class="muted">Sources are checked daily. A changed page requires preparer review; this does not automatically update eligibility rules.</p>
@foreach(($sources['sources'] ?? []) as $kind=>$source)<p><b>{{ ucfirst($kind) }}</b> · {{ ($source['error'] ?? true) ? 'Refresh needs attention' : 'Source available' }} · Last fetched: {{ $source['fetched_at'] ?? 'Not yet fetched' }} @if($source['review_required'] ?? false)<strong>· Preparer review required</strong>
@endif <a href="{{ $source['url'] }}" target="_blank" rel="noopener noreferrer">View IRS page</a></p>
@endforeach @if(auth()->user()->hasRole('Admin'))<form action="/tax-intake/team/refresh-sources" method="post">
@csrf<button>Refresh IRS sources</button></form>
@endif
</section>
@foreach($items as $item)<section class="conversation team-record"><p class="eyebrow">{{ $item['kind'] }} · {{ $item['created_at'] }}</p><h2>{{ $item['answers']['full_name'] }}</h2><p>{{ $item['answers']['email'] }} · Reference: {{ $item['id'] }}</p><p>Notification: {{ $item['notification'] }} · Attempts: {{ $item['attempts'] }}</p>
@if($item['notification'] !== 'sent')<form method="post" action="/tax-intake/team/retry">
@csrf<input type="hidden" name="reference" value="{{ $item['id'] }}"><button>Retry notification</button></form>
@endif
@if(!empty($item['answers']['_ai_summary']))<h3>Client-supplied helper summary · verify</h3><p style="white-space:pre-wrap">{{ $item['answers']['_ai_summary'] }}</p>
@endif
<h3>Preparer review</h3><ul>
@foreach($item['analysis']['review'] as $flag)<li>{{ $flag }}</li>
@endforeach
</ul><h3>Documents to request</h3>
@foreach($item['analysis']['documents'] as $doc)<p><b>{{ $doc['title'] }}</b><br>{{ $doc['reason'] }} <a href="{{ $doc['source'] }}" target="_blank" rel="noopener noreferrer">IRS reference</a></p>
@endforeach
<details><summary>All client answers</summary><dl>
@foreach($item['answers'] as $key=>$value)<dt>{{ str_replace('_',' ',$key) }}</dt><dd>{{ $value }}</dd>
@endforeach
</dl></details><p class="muted">Guidance reviewed {{ $item['analysis']['guidance_reviewed'] }}. {{ $item['analysis']['scope'] }}</p></section>
@endforeach @if(!$items)<p>No submissions yet.</p>
@endif
</main></body></html>
