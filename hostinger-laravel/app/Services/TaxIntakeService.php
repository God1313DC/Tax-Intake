<?php
namespace App\Services;

use Illuminate\Support\Facades\Crypt;
use Illuminate\Support\Facades\Mail;
use Illuminate\Support\Facades\Log;
use Illuminate\Support\Str;

class TaxIntakeService
{
    public function definition(string $kind): array
    {
        abort_unless(in_array($kind, ['individual', 'business'], true), 404);
        $all = json_decode(file_get_contents(__DIR__.'/tax-intake-rules.json'), true, 512, JSON_THROW_ON_ERROR);
        return $all[$kind];
    }

    public function active(string $kind, array $answers): array
    {
        return array_values(array_filter($this->definition($kind)['questions'], function ($q) use ($answers) {
            if (!$q['when']) return true;
            [$key, $allowed] = $q['when'];
            return in_array($answers[$key] ?? null, is_array($allowed) ? $allowed : [$allowed], true);
        }));
    }

    public function analysis(string $kind, array $answers): array
    {
        $definition = $this->definition($kind);
        $documents = $definition['baseline'];
        foreach ($definition['rules'] as $key => $items) {
            if (($answers[$key] ?? null) === 'Yes') $documents = array_merge($documents, $items);
        }
        $review = [];
        if ($kind === 'individual' && ($answers['residency'] ?? '') !== 'Resident all year') {
            $review[] = 'Confirm U.S. tax residency, relevant treaties and return type before assessing deductions or credits.';
        }
        if ($kind === 'individual' && ($answers['dependents'] ?? '') === 'Yes') {
            $review[] = 'Check each dependent separately: age, relationship, residency, support, student status and competing claims.';
        }
        if ($kind === 'business') {
            $review[] = 'Confirm entity classification, elections, fiscal year-end and ownership before choosing the return and due date.';
            if (($answers['books'] ?? '') !== 'Yes') $review[] = 'Bookkeeping completion or reconciliation is needed before return preparation.';
        }
        if (($answers['foreign'] ?? '') === 'Yes') $review[] = 'International income, account or ownership reporting requires specialist review.';
        foreach ($this->active($kind, $answers) as $q) {
            if (($answers[$q['key']] ?? '') === 'Not sure') $review[] = 'Follow up: '.$q['label'];
        }
        $year = ($answers['filing_year'] ?? '') === 'Other' ? ($answers['other_year'] ?? '') : ($answers['filing_year'] ?? '');
        $review[] = 'Verify federal and state guidance for tax year '.$year.'. No refund, filing status or credit eligibility is determined by this questionnaire.';
        return ['documents' => $documents, 'review' => $review,
            'guidance_reviewed' => '2026-10-15',
            'scope' => 'Document collection guidance only. Your preparer verifies tax-year and state-specific requirements.'];
    }

    private function directory(): string
    {
        $dir = storage_path('app/private/tax-intakes');
        if (!is_dir($dir) && !@mkdir($dir, 0700, true) && !is_dir($dir)) {
            throw new \RuntimeException('Intake storage unavailable');
        }
        return $dir;
    }

    // One exclusive lock covers each read/modify/write. Names contain only random IDs.
    public function transaction(string $id, callable $callback): array
    {
        if (!Str::isUuid($id)) throw new \InvalidArgumentException('Invalid reference');
        $path = $this->directory().'/'.$id.'.enc';
        $handle = fopen($path.'.lock', 'c+');
        if (!$handle) throw new \RuntimeException('Intake storage unavailable');
        @chmod($path.'.lock', 0600);
        try {
            if (!flock($handle, LOCK_EX)) throw new \RuntimeException('Intake storage busy');
            $raw = is_file($path) ? file_get_contents($path) : ''; 
            $record = $raw ? json_decode(Crypt::decryptString($raw), true, 512, JSON_THROW_ON_ERROR) : [];
            $updated = $callback($record);
            if ($updated !== $record) {
                // Atomic rename leaves the old complete record intact if the process dies.
                $temp = tempnam($this->directory(), '.write-');
                try {
                    $encrypted = Crypt::encryptString(json_encode($updated, JSON_THROW_ON_ERROR));
                    if (file_put_contents($temp, $encrypted, LOCK_EX) !== strlen($encrypted)) throw new \RuntimeException('Intake save failed');
                    @chmod($temp, 0600);
                    if (!rename($temp, $path)) throw new \RuntimeException('Intake save failed');
                } finally { if (file_exists($temp)) @unlink($temp); }
            }
            return $updated;
        } finally { flock($handle, LOCK_UN); fclose($handle); }
    }

    public function save(string $id, string $owner, string $kind, array $answers): array
    {
        return $this->transaction($id, function ($record) use ($id, $owner, $kind, $answers) {
            if ($record) {
                abort_unless(hash_equals($record['owner'], $owner), 409);
                return $record;
            }
            return ['id'=>$id, 'owner'=>$owner, 'kind'=>$kind, 'created_at'=>now()->toIso8601String(),
                'answers'=>$answers, 'analysis'=>$this->analysis($kind, $answers), 'notification'=>'pending', 'attempts'=>0];
        });
    }

    public function notify(string $id): bool
    {
        // Lock the entire delivery to avoid two workers mailing the same reference.
        $sent = false;
        $this->transaction($id, function ($record) use ($id, &$sent) {
            if (!$record || ($record['notification'] ?? '') === 'sent') return $record;
            $record['attempts']++;
            try {
                // Only a real SMTP transport counts as delivery, never log/array/failover.
                if (config('mail.mailers.smtp.transport') !== 'smtp' || !config('mail.mailers.smtp.host')) {
                    throw new \RuntimeException('SMTP not configured');
                }
                $to = config('tax-intake.notify_to');
                if (!filter_var($to, FILTER_VALIDATE_EMAIL)) throw new \RuntimeException('Recipient not configured');
                $url = url('/tax-intake/team');
                config(['mail.mailers.smtp.timeout'=>10]);
                Mail::mailer('smtp')->raw("A client completed a US Tax Deals intake.\nReference: {$id}\nSign in to view the answers and checklist:\n{$url}\n", function ($message) use ($to) {
                    $message->to($to)->subject('New US Tax Deals tax intake');
                });
                $record['notification'] = 'sent'; $sent = true;
            } catch (\Throwable $error) {
                $record['notification'] = 'failed';
                Log::warning('Intake email notification failed', ['reference'=>$id]);
            }
            return $record;
        });
        return $sent;
    }

    public function retryPending(): int
    {
        $lock = fopen($this->directory().'/.retry.lock', 'c+');
        if (!$lock) throw new \RuntimeException('Retry lock unavailable');
        if (!flock($lock, LOCK_EX|LOCK_NB)) { fclose($lock); return 0; }
        $attempted = 0;
        try {
            foreach ($this->recent(PHP_INT_MAX) as $record) {
                if (($record['notification'] ?? '') !== 'sent' && ($record['attempts'] ?? 0) < 10) {
                    $this->notify($record['id']); $attempted++;
                    if ($attempted >= 25) break;
                }
            }
        } finally { flock($lock, LOCK_UN); fclose($lock); }
        return $attempted;
    }

    public function recent(int $limit = 100): array
    {
        $paths = glob($this->directory().'/*.enc') ?: [];
        usort($paths, fn($a, $b) => filemtime($b) <=> filemtime($a));
        $out = [];
        foreach (array_slice($paths, 0, $limit) as $path) {
            try {
                $record = json_decode(Crypt::decryptString(file_get_contents($path)), true, 512, JSON_THROW_ON_ERROR);
                if ($record) $out[] = $record;
            } catch (\Throwable $error) { Log::warning('Intake record could not be read'); }
        }
        usort($out, fn($a, $b) => strcmp($b['created_at'], $a['created_at']));
        return $out;
    }
}
