# Shunt Module

A lightweight implementation of Spotify's "shunt" pattern for cost savings when using AI coding agents.

## What Is This?

The shunt module intercepts large file reads and delegates them to cheaper AI models, reducing costs while maintaining quality. Instead of sending entire files (1000+ lines) to expensive models, it:

1. **Detects** when a file read command is issued (cat, head, tail, etc.)
2. **Intercepts** files larger than 350 lines
3. **Summarizes** the file using a cheap worker model
4. **Sends** only the summary to the expensive model

**Result:** 40-50% cost savings with same quality.

## Quick Start

### Option 1: One-Command Setup (Recommended)

```bash
# Clone the repo
git clone https://github.com/hyd-evaluation/shunt-module.git

# Run setup
cd shunt-module
bash setup.sh --force
```

### Option 2: Manual Setup

```bash
# Create directories
mkdir -p ~/shunt-module/configs
mkdir -p ~/pb-harness-v2

# Create virtual environment
cd ~/pb-harness-v2
python3 -m venv venv
source venv/bin/activate
pip install mini-swe-agent pyyaml jinja2 requests

# Test shunt module
cd ~/shunt-module
PYTHONPATH=~ python3 -c "from shunt_module import ShuntInterceptor; print('OK')"
```

## Setup Script Options

```bash
bash setup.sh --help        # Show all options
bash setup.sh --force       # Auto-install without prompts
bash setup.sh --check       # Verify existing setup
bash setup.sh --dry-run     # Preview without changes
bash setup.sh --verbose     # Detailed output
bash setup.sh --uninstall   # Remove everything
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

### Available Worker Models

| Model | Input Cost | Output Cost | Speed | Quality |
|-------|------------|-------------|-------|---------|
| codex/gpt-5.6-luna | $1.00/1M | $6.00/1M | Fast | Good |
| openrouter/google/gemini-3.6-flash | $0.00 | $0.00 | Fast | Good |
| openrouter/nvidia/nemotron-3.5-lightning:free | $0.00 | $0.00 | Fast | OK |
| openrouter/qwen/qwen3-coder | $0.50/1M | $2.00/1M | Medium | Good |

### Pricing Comparison

| Model | Input | Output |
|-------|-------|--------|
| Terra (expensive) | $2.50/1M | $15.00/1M |
| Luna (cheap worker) | $1.00/1M | $6.00/1M |

**Luna is 2.5x cheaper than Terra**

## Usage

### Python API

```python
from shunt_module import ShuntModel, ShuntWorkerFactory

# Create base model (from harness)
base_model = NeusisRouterModel(...)

# Create shunt model
shunt_model = ShuntModel(
    base_model=base_model,
    worker_model="codex/gpt-5.6-luna",
    api_key="sk-...",
    threshold=350
)

# Use it (same interface as base model)
result = shunt_model.query(messages)
```

### Command Line

```bash
# Test interceptor
PYTHONPATH=~ python3 -c "
from shunt_module import ShuntInterceptor
interceptor = ShuntInterceptor(threshold=350, base_dir='/path/to/repo')
result = interceptor.check_command('cat /path/to/large/file.py')
print(f'Intercept: {result[0]}')
"

# Test worker
PYTHONPATH=~ python3 -c "
from shunt_module import ShuntWorker
worker = ShuntWorker(api_key='sk-...', model='codex/gpt-5.6-luna')
result = worker.summarize('file.py', 'file content', 'Summarize this file')
print(result['summary'])
"
```

## Components

| File | Purpose |
|------|---------|
| `worker.py` | Worker client for cheap models |
| `interceptor.py` | File read interception |
| `shunt_model.py` | Shunt model wrapper |
| `configs/shunt_neusiscode.yaml` | Configuration |

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
│  ┌──────────────────┐                                           │
│  │  Interceptor     │                                           │
│  │  (File Reads)    │                                           │
│  └──────────────────┘                                           │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Test Results

### Document Reading Tests

| Metric | Result |
|--------|--------|
| Cost Savings | 49.6% |
| Speed Improvement | 31% |
| Quality Delta | +0.25 (improved) |

### Bug Resolution Tests

| Metric | Result |
|--------|--------|
| Cost Change | -9.6% (small files) |
| Quality Delta | +0.92 (improved) |
| Speed Improvement | 53% |

### Combined Results

| Metric | Value |
|--------|-------|
| Overall Cost Savings | 41.2% |
| Overall Speed Improvement | 38.8% |
| Quality Maintained | Yes |

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
The setup script requires internet to install dependencies. If offline:
```bash
# On machine with internet
cd ~/pb-harness-v2
tar -czf pb-harness-deps.tar.gz venv/

# On offline machine
tar -xzf pb-harness-deps.tar.gz
```

### "Dependencies not installed"
```bash
cd ~/pb-harness-v2
source venv/bin/activate
pip install mini-swe-agent pyyaml jinja2 requests
```

### "Shunt module not importable"
```bash
# Make sure you're in the right directory
cd ~/shunt-module
PYTHONPATH=~ python3 -c "from shunt_module import ShuntInterceptor; print('OK')"
```

## API Key

The default API key is included in the config. To use your own:

```bash
bash setup.sh --api-key YOUR_KEY_HERE
```

Or edit `configs/shunt_neusiscode.yaml`:

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
4. Test with `bash setup.sh --check`
5. Submit a pull request

## License

MIT License

## Support

For issues or questions:
- Open an issue on GitHub
- Contact: varunganduri