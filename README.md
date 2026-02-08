# 🚀 Springboard - LinkedIn Job Application Automation

Springboard is an AI-powered multi-agent system that automates your LinkedIn job search, from discovery to application. Built with LangGraph for orchestration, Claude API for intelligence, and Streamlit for visualization.

## Features

- **Automated Job Discovery** — Scrapes LinkedIn jobs based on your criteria using Selenium
- **AI-Powered Matching** — Scores jobs against your profile using Claude API with weighted criteria
- **Resume Customization** — Generates tailored resumes and cover letters for each position
- **One-Click Applications** — Submits LinkedIn Easy Apply applications automatically
- **Real-Time Dashboard** — 8-page Streamlit dashboard for monitoring and analytics
- **Smart Rate Limiting** — Configurable delays and daily limits to avoid detection
- **Checkpoint Recovery** — Resumable workflows via LangGraph state management

## Architecture

```
┌──────────────┐    ┌──────────────┐    ┌──────────────┐    ┌──────────────┐
│   LinkedIn   │───▶│  Job Matcher │───▶│   Resume     │───▶│  Application │
│   Scraper    │    │  (Claude AI) │    │  Customizer  │    │  Submitter   │
└──────────────┘    └──────────────┘    └──────────────┘    └──────────────┘
        │                   │                   │                   │
        └───────────────────┴───────────────────┴───────────────────┘
                                    │
                          ┌─────────────────┐
                          │   Supervisor     │
                          │  (LangGraph)     │
                          └─────────────────┘
                                    │
                          ┌─────────────────┐
                          │   Streamlit      │
                          │   Dashboard      │
                          └─────────────────┘
```

## Quick Start

### Prerequisites
- Python 3.10+
- Chrome browser (for Selenium)
- LinkedIn account
- Anthropic API key

### Installation

```bash
# Clone the repository
git clone <repo-url>
cd springboard

# Run setup script
chmod +x run.sh
./run.sh

# Or manual setup:
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your credentials
python -m src.database.init_db
streamlit run src/dashboard/app.py
```

### Configuration

1. Copy `.env.example` to `.env` and fill in your credentials
2. Edit `config/config.yaml` to customize job search parameters
3. Set up your profile in the dashboard's Profile page

## Dashboard Pages

| Page | Description |
|------|-------------|
| 🏠 Home | Overview metrics, activity feed, quick actions |
| 🔍 Job Search | Configure and launch job searches |
| 📋 Jobs | Browse, filter, and manage job listings |
| 📄 Applications | Track application status and history |
| 👤 Profile | Manage skills, experience, and preferences |
| 🤖 Agent Monitor | Control workflow and monitor agents |
| 📈 Analytics | Charts, funnels, and success metrics |
| ⚙️ Settings | Credentials, automation, and system config |

## Tech Stack

- **Python 3.10+** — Core language
- **Streamlit** — Dashboard UI
- **LangGraph + LangChain** — Multi-agent orchestration
- **SQLAlchemy** — ORM (SQLite/PostgreSQL)
- **Selenium** — Browser automation
- **Anthropic Claude API** — AI matching and generation
- **Plotly** — Interactive charts

## Project Structure

```
springboard/
├── src/
│   ├── agents/           # AI agents (scraper, matcher, customizer, applier)
│   ├── database/         # Models, connection, repositories
│   ├── graph/            # LangGraph workflow definition
│   ├── dashboard/        # Streamlit app and pages
│   ├── state/            # State definitions
│   ├── tools/            # Helper utilities
│   └── utils/            # Config and logging
├── config/               # YAML configuration
├── data/                 # Runtime data (db, logs, screenshots)
├── tests/                # Test suite
├── docs/                 # Documentation
├── requirements.txt
├── run.sh
└── README.md
```

## Safety & Ethics

- Configurable daily application limits (default: 20/day)
- Random delays between actions to mimic human behavior
- Never stores passwords in code (uses .env)
- Screenshot proof of every application
- Full audit trail in database

## License

MIT License
