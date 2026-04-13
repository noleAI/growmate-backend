$ErrorActionPreference = 'Stop'

$root = Split-Path -Parent $PSScriptRoot
$paths = @{
  p2 = Join-Path $root 'data\diagnosis\diagnosis_scenarios.json'
  p3 = Join-Path $root 'data\interventions\intervention_catalog.json'
  p4 = Join-Path $root 'configs\runtime\runtime_decision_config.json'
  p5 = Join-Path $root 'data\dictionary\data_dictionary.md'
  p6 = Join-Path $root 'data\golden\golden_dataset.json'
}

$issues = New-Object System.Collections.Generic.List[string]

foreach ($name in $paths.Keys) {
  if (-not (Test-Path $paths[$name])) {
    $issues.Add("Missing file: $($paths[$name])")
  }
}

if ($issues.Count -gt 0) {
  $issues | ForEach-Object { Write-Host "[FAIL] $_" -ForegroundColor Red }
  exit 1
}

$p2 = Get-Content $paths.p2 -Raw | ConvertFrom-Json
$p3 = Get-Content $paths.p3 -Raw | ConvertFrom-Json
$p4 = Get-Content $paths.p4 -Raw | ConvertFrom-Json
$p5 = Get-Content $paths.p5 -Raw
$p6 = Get-Content $paths.p6 -Raw | ConvertFrom-Json

function Get-RiskBand([double]$u, $rt) {
  if ($u -ge $rt.low.minUncertainty -and $u -le $rt.low.maxUncertainty) { return 'low' }
  if ($u -ge $rt.medium.minUncertainty -and $u -le $rt.medium.maxUncertainty) { return 'medium' }
  if ($u -ge $rt.high.minUncertainty -and $u -le $rt.high.maxUncertainty) { return 'high' }
  return 'invalid'
}

function Get-ConfidenceBand([double]$c, $ct) {
  if ($c -ge $ct.low.min -and $c -le $ct.low.max) { return 'low' }
  if ($c -ge $ct.medium.min -and $c -le $ct.medium.max) { return 'medium' }
  if ($c -ge $ct.high.min -and $c -le $ct.high.max) { return 'high' }
  return 'invalid'
}

# P2 checks
$requiredP2 = @('diagnosisId','title','gapAnalysis','diagnosisReason','strengths','needsReview','confidence','riskLevel','mode','requiresHITL','nextSuggestedTopic','interventionPlan')
if (($p2 | Measure-Object).Count -ne 4) { $issues.Add('P2: number of scenarios must be 4') }
foreach ($s in $p2) {
  $keys = @($s.PSObject.Properties.Name)
  $missing = $requiredP2 | Where-Object { $_ -notin $keys }
  if ($missing.Count -gt 0) { $issues.Add("P2: missing fields [$($missing -join ',')] in $($s.diagnosisId)") }
  if ($s.riskLevel -notin @('low','medium','high')) { $issues.Add("P2: invalid riskLevel in $($s.diagnosisId)") }
  if ($s.mode -notin @('normal','recovery','hitl_pending')) { $issues.Add("P2: invalid mode in $($s.diagnosisId)") }
  if ([double]$s.confidence -lt 0 -or [double]$s.confidence -gt 1) { $issues.Add("P2: confidence out of range in $($s.diagnosisId)") }
}

# P3 checks
if (-not $p3.interventions) { $issues.Add('P3: missing interventions root') }
$requiredP3 = @('interventionId','type','title','description','duration','intensity','applicableRiskLevels','tags')
$idsP3 = @()
foreach ($i in $p3.interventions) {
  $keys = @($i.PSObject.Properties.Name)
  $missing = $requiredP3 | Where-Object { $_ -notin $keys }
  if ($missing.Count -gt 0) { $issues.Add("P3: missing fields [$($missing -join ',')] in $($i.interventionId)") }
  if ($i.type -notin @('review','practice','recovery','breath','grounding')) { $issues.Add("P3: invalid type in $($i.interventionId)") }
  foreach ($r in $i.applicableRiskLevels) {
    if ($r -notin @('low','medium','high')) { $issues.Add("P3: invalid applicableRiskLevels value '$r' in $($i.interventionId)") }
  }
  if ([int]$i.duration -le 0) { $issues.Add("P3: duration must be > 0 in $($i.interventionId)") }
  $idsP3 += $i.interventionId
}
$dupIds = $idsP3 | Group-Object | Where-Object { $_.Count -gt 1 }
if ($dupIds) { $issues.Add("P3: duplicate interventionId [$($dupIds.Name -join ',')]") }

# P2 -> P3 linkage
$p2PlanIds = $p2 | ForEach-Object { $_.interventionPlan } | ForEach-Object { $_ } | Sort-Object -Unique
$missingInP3 = $p2PlanIds | Where-Object { $_ -notin $idsP3 }
if ($missingInP3.Count -gt 0) { $issues.Add("Link P2->P3: missing interventionId [$($missingInP3 -join ',')]") }

# P4 checks
foreach ($k in @('version','created_at','thresholds','fallbackRules','hitlConditions')) {
  if ($k -notin @($p4.PSObject.Properties.Name)) { $issues.Add("P4: missing root field '$k'") }
}
foreach ($fk in @('normal','recovery','hitl_pending','missingInterventionPlan')) {
  if (-not $p4.fallbackRules.$fk) {
    $issues.Add("P4: missing fallbackRules.$fk")
  } elseif ($p4.fallbackRules.$fk -notin $idsP3) {
    $issues.Add("P4: fallbackRules.$fk references unknown interventionId")
  }
}
if ($p4.hitlConditions.mode -ne 'hitl_pending') { $issues.Add('P4: hitlConditions.mode must be hitl_pending') }
if (-not [bool]$p4.hitlConditions.requiresHITL) { $issues.Add('P4: hitlConditions.requiresHITL must be true') }

# P5 checks
foreach ($col in @('Field description','Data type','Enum values','Required','Example value')) {
  if ($p5 -notmatch [regex]::Escape($col)) { $issues.Add("P5: missing column '$col'") }
}
foreach ($field in @('diagnosisId','interventionId','riskThresholds','confidenceThresholds','fallbackRules','hitlConditions')) {
  if ($p5 -notmatch [regex]::Escape($field)) { $issues.Add("P5: missing documented field '$field'") }
}

# P6 checks
if (-not [bool]$p6.deterministic) { $issues.Add('P6: deterministic must be true') }
if (($p6.testCases | Measure-Object).Count -ne 4) { $issues.Add('P6: number of testCases must be 4') }
$requiredTypes = @('normal_flow','high_risk','low_confidence','fallback_scenario')
$actualTypes = $p6.testCases | ForEach-Object { $_.caseType }
$missingTypes = $requiredTypes | Where-Object { $_ -notin $actualTypes }
if ($missingTypes.Count -gt 0) { $issues.Add("P6: missing caseType [$($missingTypes -join ',')]") }

foreach ($tc in $p6.testCases) {
  $diag = $p2 | Where-Object { $_.diagnosisId -eq $tc.expectedDiagnosisOutput.diagnosisId } | Select-Object -First 1
  if (-not $diag) {
    $issues.Add("P6: unknown expectedDiagnosisOutput.diagnosisId in $($tc.caseId)")
  }
  $inv = $p3.interventions | Where-Object { $_.interventionId -eq $tc.expectedIntervention.interventionId } | Select-Object -First 1
  if (-not $inv) {
    $issues.Add("P6: unknown expectedIntervention.interventionId in $($tc.caseId)")
  }

  $u = [double]$tc.input.uncertainty
  $c = [double]$tc.input.confidence
  $rb = Get-RiskBand $u $p4.thresholds.riskThresholds
  $cb = Get-ConfidenceBand $c $p4.thresholds.confidenceThresholds
  if ($tc.expectedSystemBehavior.riskBandFromThresholds -ne $rb) { $issues.Add("P6: wrong riskBandFromThresholds in $($tc.caseId)") }
  if ($tc.expectedSystemBehavior.confidenceBandFromThresholds -ne $cb) { $issues.Add("P6: wrong confidenceBandFromThresholds in $($tc.caseId)") }

  $hitlExpected = ($u -ge [double]$p4.hitlConditions.uncertaintyHitlThreshold) -or ($c -le [double]$p4.hitlConditions.confidenceHitlThreshold)
  if ([bool]$tc.expectedSystemBehavior.hitlTriggered -ne $hitlExpected) { $issues.Add("P6: wrong hitlTriggered in $($tc.caseId)") }
}

if ($issues.Count -eq 0) {
  Write-Host '[PASS] All package data checks passed.' -ForegroundColor Green
  exit 0
}

Write-Host "[FAIL] Found $($issues.Count) issue(s):" -ForegroundColor Red
$issues | ForEach-Object { Write-Host " - $_" -ForegroundColor Yellow }
exit 1
