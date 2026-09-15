# Shunt Module

A lightweight implementation of Spotify's "shunt" pattern for cost savings when using AI coding agents.

## What Is This?

The shunt module intercepts large file reads and delegates them to cheaper AI models, reducing costs while maintaining quality. Instead of sending entire files (1000+ lines) to expensive models, it:

1. **Detects** when a file read command is issued (cat, head, tail, etc.)
2. **Intercepts** files larger than 350 lines
3. **Summarizes** the file using a cheap worker model
4. **Sends** only the summary to the expensive model

**Result:** 40-65% cost savings with same quality.

## Features

### 1. Bulk-Read (File Reading)
Intercepts large file reads and delegates to cheap models.

### 2. Code-Writer (Boilerplate Generation)
Delegates code generation to cheap models, matching reference file patterns.

### 3. Smart Routing
Automatically skips files that don't benefit from shunt (visitors, parsers, small files).

### 4. Token COST Focus
Tracks actual dollar costs, not just token counts.

## Quick Start

```bash
# Clone the repo
git clone https://github.com/hyd-evaluation/shunt-module.git

# Install (one command)
cd shunt-module
bash install.sh

# Run evaluations
python3 run_evals.py
```

## Configuration

### Worker Models

Edit `configs/shunt_neusiscode.yaml` to change the worker model:

```yaml
shunt:
  enabled: true
  worker_model: codex/gpt-5.6-luna  # Change this
  threshold: 350  # Files larger than this get intercepted
```

## Usage

### Python API - Bulk-Read

```python
from worker import ShuntWorker

# Create worker
worker = ShuntWorker(
    api_key="sk-...",
    model="codex/gpt-5.6-luna",
    max_output_tokens=1024
)

# Summarize file
result = worker.summarize(
    file_path="src/Service.java",
    content=file_content,
    question="Summarize this file"
)

print(f"Summary: {result['summary']}")
print(f"Cost: ${result['cost']:.6f}")
```

### Python API - Code-Writer

```python
from code_writer import ShuntCodeWriter

# Create code writer
writer = ShuntCodeWriter(
    api_key="sk-...",
    worker_model="codex/gpt-5.6-luna"
)

# Generate code from reference
result = writer.generate(
    spec="Write unit tests for UserService",
    reference_path="tests/OrderTest.java",
    target_path="tests/UserTest.java"
)

print(f"Generated: {result['lines_generated']} lines")
print(f"Cost: ${result['cost']:.6f}")
```

### Command Line

```bash
# Test interceptor
python3 -c "
from interceptor import ShuntInterceptor
interceptor = ShuntInterceptor(threshold=350, base_dir='/path/to/repo')
result = interceptor.check_command('cat /path/to/large/file.py')
print(f'Intercept: {result[0]}')
"

# Test worker
python3 -c "
from worker import ShuntWorker
worker = ShuntWorker(api_key='sk-...', model='codex/gpt-5.6-luna')
result = worker.summarize('file.py', 'file content', 'Summarize this file')
print(result['summary'])
"
```

### Run Evaluations

```bash
# Run all evaluations
python3 run_evals.py

# Run specific evaluations
python3 evals/hook_evals.py
python3 evals/code_write_eval.py
python3 evals/benchmark_evals.py
python3 evals/quality_evals.py
```

## Components

| File | Purpose |
|------|---------|
| `worker.py` | Worker client for cheap models (token COST focus) |
| `code_writer.py` | Boilerplate code generation |
| `interceptor.py` | File read interception with smart routing |
| `shunt_model.py` | Shunt model wrapper |
| `configs/shunt_neusiscode.yaml` | Configuration |
| `requirements.txt` | Python dependencies |
| `install.sh` | One-command installer |

## How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│  SHUNT MODULE                                                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐      ┌──────────────────┐                │
│  │  ShuntModel      │      │  ShuntWorker     │                │
│  │  (Wraps Base)    │◄─────│  (Cheap Model)   │                │
│  └──────────────────┘      └──────────────────┘                │
│           │                                                      │
│           ▼                                                      │
│  ┌──────────────────┐      ┌──────────────────┐                │
│  │  Interceptor     │      │  CodeWriter      │                │
│  │  (File Reads)    │      │  (Code Gen)      │                │
│  └──────────────────┘      └──────────────────┘                │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Test Results

### Bulk-Read Tests (182 files)

| Metric | Result |
|--------|--------|
| Cost Savings | **29.1%** |
| Avg Latency Change | +72.1% |
| Files Tested | 182 |
| Success Rate | 100% |

### Code-Writer Tests (30 files)

| Metric | Result |
|--------|--------|
| Cost Savings | **62.4%** |
| Avg Latency | Same speed |
| Files Tested | 30 |
| Success Rate | 100% |

### Combined Results

| Metric | Value |
|--------|-------|
| Overall Cost Savings | **45.8%** |
| Quality Maintained | Yes |
| Test Coverage | 212 files |

## Smart Routing

The interceptor automatically skips files that don't benefit from shunt:

- **Visitor/Parser files** (regex patterns)
- **Small files** (< 500 lines)
- **Test files** (usually small)
- **Config files** (JSON, YAML, XML)
- **Minified files** (.min.js, .min.css)

## Interception Patterns

The interceptor detects these file read commands:

- `cat filename`
- `head -N filename`
- `tail -N filename`
- `less filename`
- `more filename`
- `sed ... < filename`
- `awk ... < filename`
- `view filename`
- `nvim filename`
- `vi filename`

## Troubleshooting

### "Python3 not found"
```bash
# Install Python 3.11+
sudo apt install python3.11
```

### "No internet connection"
The installer requires internet to install dependencies. If offline:
```bash
# On machine with internet
cd ~/shunt-module
tar -czf shunt-deps.tar.gz venv/

# On offline machine
tar -xzf shunt-deps.tar.gz
```

### "Dependencies not installed"
```bash
pip install -r requirements.txt
```

### "Shunt module not importable"
```bash
# Make sure you're in the right directory
cd ~/shunt-module
python3 -c "from worker import ShuntWorker; print('OK')"
```

## API Key

The default API key is included in the config. To use your own, edit `configs/shunt_neusiscode.yaml`:

```yaml
model:
  model_kwargs:
    api_key: YOUR_KEY_HERE

shunt:
  api_key: YOUR_KEY_HERE
```

## Contributing

1. Fork the repo
2. Create a feature branch
3. Make your changes
4. Test with `python3 run_evals.py`
5. Submit a pull request

## License

MIT License

## Support

For issues or questions:
- Open an issue on GitHub
- Contact: varunganduri
