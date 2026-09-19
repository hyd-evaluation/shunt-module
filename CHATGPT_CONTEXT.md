# Shunt Module - Complete Project Summary for ChatGPT

## What Is This Project?

We built a **shunt module** - a system that routes I/O-heavy AI work (file reads, code generation) to **cheap AI models** to save money, while keeping expensive models for complex reasoning. This is inspired by Spotify's approach (https://github.com/spotify/portal-ai-plugins).

---

## What We Built

### Core Files

| File | Purpose |
|------|---------|
| `worker.py` | Calls cheap AI models (Luna) for summarization |
| `interceptor.py` | Detects large file reads and blocks them |
| `code_writer.py` | Generates boilerplate code using cheap AI |
| `shunt_model.py` | Wraps expensive model with shunt interception |
| `test_10files.py` | Quick 3-way comparison test |

### Testing Files

| File | Purpose |
|------|---------|
| `parallel_test.py` | Tests bulk file reads (async, 182 files) |
| `codewriter_eval.py` | Tests code generation (async, 3-way comparison) |
| `codewriter_eval_simple.py` | Simplified version for quick tests |
| `run_evals.py` | Runs all eval tests |
| `evals/hook_evals.py` | Tests interceptor behavior |
| `evals/quality_evals.py` | Tests summary quality |

---

## Models We Use

| Model | Role | Price (per 1M tokens) |
|-------|------|----------------------|
| `codex/gpt-5.6-sol` | Expensive (replacing Terra which is DOWN) | Input: $2.50, Output: $15.00 |
| `codex/gpt-5.6-luna` | Cheap worker | Input: $1.00, Output: $6.00 |
| `codex/gpt-5.6-terra` | Expensive (DOWN - empty responses) | Input: $2.50, Output: $15.00 |

### Price Ratio: Sol vs Luna = 2.5x
(Spotify uses 50x ratio with Claude vs Gemini Flash)

---

## What We Tested

### Test 1: Bulk-Read (File Summarization)

**Flow:**
```
Large file (350+ lines) → Luna summarizes → Summary → Expensive model reads summary
```

**Results (182 files from Apache ShardingSphere):**

| Metric | Value |
|--------|-------|
| Files tested | 182 |
| Total cost (Expensive only) | $6.54 |
| Total cost (Shunt: Luna + Expensive) | $4.63 |
| **Token savings** | **29.1%** |
| Latency increase | +72.1% |
| Failures | 0 |

**Key findings:**
- Best case: RootSQLParserTestCases.java (2,222 lines) → 53.6% savings
- Worst case: CallTimeRecordDataSource.java (356 lines) → -14.9% (cost INCREASED)
- Token bloat: ALL files use MORE tokens with shunt (1.3-1.6x), savings come from PRICE difference
- Some files have high latency outliers (Visitor/Parser files: +600%)

---

### Test 2: Code-Writer (Code Generation)

**Flow:**
```
Option A (Terra alone): Full file + spec → Terra → Code
Option B (Luna alone): Full file + spec → Luna → Code  
Option C (Terra+Luna): Full file → Luna → Summary + spec → Terra → Code
```

**Results (9 files tested):**

| Metric | Terra Alone | Luna Alone | Terra+Luna |
|--------|-------------|------------|------------|
| Total Cost | $0.25 | $0.10 | $0.33 |
| Cost Per File | $0.028 | $0.011 | $0.037 |
| Savings vs Terra | -- | **60.7%** | **-31.5%** (MORE!) |
| Avg Latency | 64.1s | 53.7s | 81.5s |
| Summary Keyword Coverage | -- | -- | 33% |

**Critical Discovery:**
- **Luna alone: GOOD** - 60.7% cheaper than Terra
- **Terra+Luna: BAD** - 31.5% MORE EXPENSIVE than Terra alone
- Why: Extra Luna summary call adds cost, Terra still generates full code

---

### Test 3: Quality Evaluation

**What we measured:**
- Keyword coverage: Does Luna's summary mention all key class/method names?
- LLM-as-judge: Does Sol rate Luna's generated code as good quality?

**Results:**
- Bulk-read keyword coverage: ~94% (good)
- Code-writer summary coverage: 33% (poor)
- Quality scores: 4.0-4.2/5 (good)

---

## How Spotify's Shunt Works (From Their Code)

```bash
# Spotify's hook (plugins/shunt/hooks/check-file-size):
if file has offset/limit: ALLOW (targeted read)
if file doesn't exist: ALLOW
if file < 350 lines: ALLOW
if file >= 350 lines: BLOCK (redirect to bulk-reader)
```

**Spotify does NOT check for "reasoning complexity"** - they only check file size.

---

## What's Working vs Not Working

### Working:
1. **Bulk-read shunt** - Luna summarizes large files, saves 29% tokens
2. **Luna code generation** - Luna generates code, saves 60% vs Terra
3. **Interceptor** - Pure Python, no AI calls, FREE
4. **Smart routing** - Skips Visitor/Parser/Test files, piped commands

### Not Working:
1. **Terra is DOWN** - Returns "upstream empty response"
2. **Terra+Luna for code generation** - Costs MORE than Terra alone
3. **Summary quality for code-writer** - Only 33% keyword coverage
4. **Async scripts** - Keep getting killed (too many files)

---

## Key Learnings

### 1. Token Bulk-Read Saves Money, Not Tokens
- Shunt uses 1.3-1.6x MORE tokens
- But Luna is 2.5x cheaper than Sol
- Net result: 29% cost savings

### 2. Code Generation: Luna Alone Wins
- Luna alone: 60% cheaper
- Terra+Luna: 31% MORE expensive (extra summary call)
- For code generation, skip the summary step

### 3. Price Ratio Matters
- Our ratio: 2.5x (Sol vs Luna)
- Spotify's ratio: 50x (Claude vs Gemini Flash)
- With 50x ratio, our savings would approach 90%

### 4. Summary Quality Varies by Task
- Bulk-read summaries: 94% keyword coverage (good)
- Code-writer summaries: 33% keyword coverage (poor)
- Code generation needs more detail than file reading

---

## Environment

- **Repo tested:** Apache ShardingSphere (199K Java lines)
- **GitHub:** https://github.com/hyd-evaluation/shunt-module
- **API:** Neusis Router at https://pbtest.neusis.ai/router/v1
- **API Key:** sk-55100efb9fb4a726-62bfab-89db8b81

---

## What ChatGPT Should Help With Next

1. **Improving summary quality** for code generation (currently 33%)
2. **Adding complexity detection** - route complex files to expensive model
3. **Testing on 200+ files** (scripts keep timing out)
4. **Comparing with other cheap models** (Gemini Flash, Qwen, Nemotron)
5. **Adding human review step** for quality validation

---

## Prompt Template for ChatGPT

When asking ChatGPT for help, use this context:

```
I'm working on a shunt module that routes AI work to cheap models to save money.

Current state:
- Bulk-read: 29% token savings (Luna summarizes large files)
- Code-writer: Luna alone saves 60%, but Terra+Luna costs MORE
- Summary quality: 94% for reading, 33% for code generation

Models:
- Expensive: codex/gpt-5.6-sol ($2.50/$15.00 per 1M tokens)
- Cheap: codex/gpt-5.6-luna ($1.00/$6.00 per 1M tokens)
- Price ratio: 2.5x

I need help with: [YOUR QUESTION HERE]
```
