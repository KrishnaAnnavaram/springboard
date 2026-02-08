# Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         STREAMLIT DASHBOARD                            │
│  ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──────┐ ┌──┐│
│  │ Home │ │Search│ │ Jobs │ │ Apps │ │Profile│ │Monitor│ │Stats │ │⚙️││
│  └──────┘ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘ └──────┘ └──┘│
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────────┐
│                       LANGGRAPH WORKFLOW ENGINE                         │
│                                                                         │
│   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐           │
│   │  Scrape  │──▶│  Match   │──▶│Customize │──▶│  Apply   │           │
│   │  Node    │   │  Node    │   │  Node    │   │  Node    │           │
│   └──────────┘   └──────────┘   └──────────┘   └──────────┘           │
│        │              │              │              │                   │
│        └──────────────┴──────────────┴──────────────┘                   │
│                              │                                          │
│                    ┌─────────▼──────────┐                               │
│                    │   Supervisor Node  │                               │
│                    │   (Routing Logic)  │                               │
│                    └────────────────────┘                               │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────────┐
│                          AGENT LAYER                                    │
│                                                                         │
│  ┌─────────────────┐  ┌─────────────────┐  ┌──────────────────────┐   │
│  │ LinkedIn Scraper │  │  Job Matcher    │  │ Resume Customizer    │   │
│  │ (Selenium)       │  │  (Claude API)   │  │ (Claude API)         │   │
│  └─────────────────┘  └─────────────────┘  └──────────────────────┘   │
│                                                                         │
│  ┌─────────────────┐  ┌─────────────────┐                              │
│  │ LinkedIn Applier │  │  Supervisor     │                              │
│  │ (Selenium)       │  │  (Routing)      │                              │
│  └─────────────────┘  └─────────────────┘                              │
└───────────────────────────────┬─────────────────────────────────────────┘
                                │
┌───────────────────────────────▼─────────────────────────────────────────┐
│                        DATA LAYER                                       │
│                                                                         │
│  ┌────────────────┐  ┌──────────────────────────────────────────────┐  │
│  │  SQLAlchemy ORM │  │           Repositories                      │  │
│  │                 │  │  JobRepo | AppRepo | UserRepo | ResumeRepo  │  │
│  └────────┬───────┘  └──────────────────────────────────────────────┘  │
│           │                                                             │
│  ┌────────▼───────┐                                                     │
│  │ SQLite / Postgres│                                                   │
│  └────────────────┘                                                     │
└─────────────────────────────────────────────────────────────────────────┘
```

## Data Flow

1. **Scrape**: Selenium scrapes LinkedIn → jobs saved to database
2. **Match**: Claude API scores each job → scores saved to database
3. **Supervisor**: Evaluates state → routes to next step or ends
4. **Customize**: Claude API generates tailored resume + cover letter
5. **Apply**: Selenium submits Easy Apply → application recorded

## Key Design Decisions

- **SQLAlchemy ORM** — Database-agnostic (SQLite dev, PostgreSQL prod)
- **Repository Pattern** — Clean separation of data access from business logic
- **LangGraph** — Declarative workflow with conditional routing and checkpointing
- **Singleton Config** — Single source of truth for all settings
- **Scoped Sessions** — Thread-safe database access via context managers
