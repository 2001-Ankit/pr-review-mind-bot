# ReviewMindBot

An intelligent pull request code review tool powered by LLM providers that automatically analyzes diffs and provides actionable feedback on code changes.

## Features

- **Automated PR Review**: Analyzes pull request diffs using AI-powered code review
- **Multi-LLM Support**: Integrates with multiple LLM providers (Gemini, OpenAI)
- **Smart Diff Parsing**: Parses unified diff format with support for hunks, added/removed lines, and context
- **GitHub Integration**: Fetch and review diffs directly from GitHub PRs
- **Intelligent Chunking**: Breaks large diffs into manageable chunks for better analysis
- **Categorized Findings**: Issues categorized by severity (low/medium/high) and type (bug/refactor/test/security)
- **Modular Architecture**: Extensible design with separate components for parsing, reviewing, routing, and aggregation

## Project Structure

```
reviewmindbot/
├── app/
│   ├── cli.py                 # Command-line interface
│   ├── core/
│   │   └── diff_parser.py     # Unified diff format parser
│   ├── engine/
│   │   ├── orchestrator.py    # Coordinates review workflow
│   │   ├── reviewer.py        # Performs code review analysis
│   │   ├── router.py          # Routes files/hunks to appropriate handlers
│   │   ├── aggregator.py      # Aggregates review findings
│   │   ├── file_router.py     # File-specific routing logic
│   │   └── models.py          # Data models for review results
│   ├── llm/
│   │   ├── base.py            # Abstract LLM provider base class
│   │   ├── gemini.py          # Google Gemini implementation
│   │   └── openai.py          # OpenAI API implementation
│   ├── integration/
│   │   └── github.py          # GitHub PR integration
│   └── examples/
│       └── simple_change.diff # Example diff file
├── main.py                    # Entry point
├── pyproject.toml             # Project configuration
└── README.md                  # This file
```

## Installation

### Prerequisites

- Python >=3.12
- pip or uv package manager

### Setup

```bash
# Clone the repository
git clone https://github.com/2001-Ankit/pr-review-mind-bot.git
cd reviewmindbot

# Install dependencies
pip install -e .
```

## Configuration

### LLM Provider Setup

Before using ReviewMindBot, configure your preferred LLM provider:

#### Google Gemini

```bash
# Set your API key as an environment variable
export GEMINI_API_KEY="your-api-key-here"
```

#### OpenAI

```bash
# Set your API key as an environment variable
export OPENAI_API_KEY="your-api-key-here"
```

## Usage

### Command-Line Interface

#### Review a Local Diff File

```bash
python -m app.cli path/to/your/diff/file.diff
```

#### Review a GitHub Pull Request

```bash
python -m app.cli --pr https://github.com/owner/repo/pull/123
```

### Example

```bash
# Review the included example diff
python -m app.cli app/examples/simple_change.diff
```

### Output

The tool outputs review findings in the following format:

```
=== Review Results ===

[HIGH] bug - Variable 'x' used before definition on line 5
[MEDIUM] refactor - Consider extracting this function for better readability
[LOW] test - Missing unit test for edge case
[HIGH] security - SQL injection vulnerability detected in query string
```

## How It Works

1. **Diff Parsing**: Reads unified diff format and extracts file changes, hunks, and line information
2. **Chunking**: Splits large diffs into smaller chunks using recursive character splitting (500 chars, 50 char overlap)
3. **LLM Analysis**: Sends chunks to the LLM with a system prompt asking for structured code review feedback
4. **JSON Parsing**: Parses LLM responses into structured finding objects
5. **Aggregation**: Combines findings from all chunks and returns categorized results
6. **Reporting**: Displays findings sorted by severity

## API Components

### DiffParser

Parses unified diff format into structured FileChange objects with hunks and line information.

```python
from app.core.diff_parser import DiffParser

parser = DiffParser()
files = parser.parse(diff_text)
```

### Reviewer

Analyzes code chunks using an LLM provider.

```python
from app.engine.reviewer import Reviewer
from app.llm.gemini import GeminiProvider

llm = GeminiProvider()
reviewer = Reviewer(llm)
findings = reviewer.review_chunk(code_chunk)
```

### LLM Providers

All providers implement the `LLMProvider` base class:

```python
from app.llm.base import LLMProvider

provider = GeminiProvider()  # or OpenAIProvider()
response = provider.generate(system_prompt, user_prompt)
```

## Data Models

### Hunk

Represents a single diff hunk:

- `header`: Hunk header line
- `raw_lines`: Original diff lines
- `added_lines`: Lines added in this hunk
- `removed_lines`: Lines removed in this hunk
- `context_lines`: Unchanged context lines

### FileChange

Represents changes to a single file:

- `file_name`: Path to the file
- `hunks`: List of Hunk objects
- `total_added`: Total lines added
- `total_removed`: Total lines removed
- `is_new`: Whether this is a new file
- `is_deleted`: Whether this file was deleted

### ReviewFinding

Represents a single review issue:

- `severity`: low | medium | high
- `category`: bug | refactor | test | security
- `message`: Actionable feedback

## Architecture

ReviewMindBot uses a modular, extensible architecture:

- **Separations of Concerns**: Parsing, reviewing, routing, and aggregation are independent
- **Provider Pattern**: LLM implementations are pluggable via the provider interface
- **Orchestrator Pattern**: The Orchestrator coordinates the review workflow
- **Router Pattern**: FileRouter determines how to handle different files/hunks

## Contributing

Contributions are welcome! The modular design makes it easy to:

- Add new LLM providers (extend `LLMProvider`)
- Improve diff parsing (enhance `DiffParser`)
- Add file-specific logic (enhance `FileRouter`)
- Implement new aggregation strategies (extend `Aggregator`)

## Technologies Used

- **Python 3.12+**: Core language
- **LangChain**: Text splitting and LLM abstraction
- **Google Gemini API**: LLM provider
- **OpenAI API**: LLM provider
- **GitHub API**: PR integration

## Requirements

```toml
[project]
name = "reviewmindbot"
version = "0.1.0"
description = "Intelligent PR review bot powered by LLMs"
requires-python = ">=3.12"
dependencies = [
    "langchain",
    "langchain-text-splitters",
    "google-generativeai",  # For Gemini
    "openai",              # For OpenAI
    "requests"             # For GitHub integration
]
```

## Roadmap

- [ ] Add support for more LLM providers (Claude, Llama)
- [ ] Implement caching for repeated reviews
- [ ] Add webhook integration for automatic PR reviews
- [ ] Create GitHub Action for CI/CD integration
- [ ] Add support for custom review rules and policies
- [ ] Add metrics and reporting

## License

MIT License - See LICENSE file for details

## Author

[2001-Ankit](https://github.com/2001-Ankit)

## Support

For issues, questions, or contributions, please open an issue on [GitHub](https://github.com/2001-Ankit/pr-review-mind-bot).

---

**Made with ❤️ for better code reviews**
