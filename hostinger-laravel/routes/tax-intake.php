<?php
use App\Http\Controllers\TaxIntakeController;
use Illuminate\Support\Facades\Route;

Route::get('/tax-intake', [TaxIntakeController::class,'landing'])->name('tax-intake');
Route::get('/tax-intake/team', [TaxIntakeController::class,'team'])->middleware(['auth','verified','role:Admin|Editor'])->name('tax-intake.team');
Route::post('/tax-intake/team/retry', [TaxIntakeController::class,'retry'])->middleware(['auth','verified','role:Admin|Editor','throttle:10,1']);
Route::post('/tax-intake/explain', [TaxIntakeController::class,'explain'])->middleware('throttle:20,1');
Route::get('/tax-intake/{kind}', [TaxIntakeController::class,'form'])->whereIn('kind',['individual','business'])->name('tax-intake.form');
Route::post('/tax-intake/{kind}/submit', [TaxIntakeController::class,'submit'])->whereIn('kind',['individual','business'])->middleware('throttle:5,1');
