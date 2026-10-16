# SYNTHETIC POLICY — Larkspur Health Plan (fictional payer)

Policy ID: SYN-LARKSPUR-SPINE-01
Policy version: SYN-LARKSPUR-SPINE-01 v2026.1
Payer ID: SYN-PAYER-LARKSPUR
Procedure: CPT 63030 — lumbar decompression with disc removal at one level (our own short description)
Diagnosis: ICD-10-CM M51.16 (intervertebral disc disorders with radiculopathy, lumbar region)

This policy is synthetic and written for this repository. It is not clinical guidance.

## 2. Criteria

All criteria must be met before the procedure is approved without clinician review.

2.1 C1: At least six weeks of conservative therapy, documented as completed visits.
```rule
{"doc_kinds": ["physical therapy notes"], "pattern": "(?i:\\b(?P<visits>\\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty) visits over (?P<weeks>\\d+|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty) weeks\\b)", "minimums": {"visits": 1, "weeks": 6}}
```

2.2 C2: Imaging confirms the diagnosis: disc herniation with nerve root compression.
```rule
{"doc_kinds": ["radiology report"], "pattern": "\\bdisc herniation with nerve root compression\\b", "minimums": {}}
```

2.3 C3: Functional limitation documented with an Oswestry Disability Index of at least 40 percent.
```rule
{"doc_kinds": ["clinic note"], "pattern": "\\bOswestry Disability Index (?P<odi>\\d+) percent\\b", "minimums": {"odi": 40}}
```
