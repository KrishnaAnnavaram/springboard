# API Reference

## Agents

### LinkedInScraperAgent
LinkedIn job scraping using Selenium WebDriver.

| Method | Parameters | Returns | Description |
|--------|-----------|---------|-------------|
| `login()` | — | `bool` | Authenticate with LinkedIn |
| `search_jobs(keywords, location, max_jobs)` | `list[str], str, int` | `list[dict]` | Search and scrape jobs |
| `save_jobs_to_db(jobs)` | `list[dict]` | `int` | Save scraped jobs to database |
| `run(keywords, location, max_jobs)` | `list[str], str, int` | `list[dict]` | Full scraping pipeline |

### JobMatcherAgent
AI-powered job matching using Claude API.

| Method | Parameters | Returns | Description |
|--------|-----------|---------|-------------|
| `analyze_job(job, user_profile)` | `dict, dict` | `dict` | Score a single job |
| `match_all_jobs(user_profile)` | `dict` | `list[dict]` | Score all unmatched jobs |
| `run(user_profile)` | `dict` | `list[dict]` | Full matching pipeline |

### ResumeCustomizerAgent
AI-powered resume and cover letter generation.

| Method | Parameters | Returns | Description |
|--------|-----------|---------|-------------|
| `customize_resume(base_resume, job)` | `str, dict` | `str` | Generate tailored resume |
| `generate_cover_letter(job, profile)` | `dict, dict` | `str` | Generate cover letter |
| `run(job_id)` | `int` | `dict` | Full customization pipeline |

### LinkedInApplicationAgent
Automated LinkedIn Easy Apply submission.

| Method | Parameters | Returns | Description |
|--------|-----------|---------|-------------|
| `navigate_to_job(job_url)` | `str` | `bool` | Navigate to job page |
| `fill_form(user_data)` | `dict` | `bool` | Fill application form |
| `submit_application()` | — | `bool` | Submit the application |
| `take_screenshot(job_id)` | `int` | `str` | Capture screenshot |
| `run(job_id, resume_text, cover_letter)` | `int, str, str` | `dict` | Full application pipeline |

### SupervisorAgent
Workflow routing and error recovery.

| Method | Parameters | Returns | Description |
|--------|-----------|---------|-------------|
| `route(state)` | `dict` | `str` | Determine next workflow step |
| `should_continue(state)` | `dict` | `bool` | Check if workflow should continue |
| `evaluate_results(state)` | `dict` | `dict` | Generate results summary |

## Repositories

### JobRepository
| Method | Description |
|--------|-------------|
| `create(**kwargs)` | Create a job record |
| `get_by_id(id)` | Get job by primary key |
| `get_by_linkedin_id(lid)` | Get job by LinkedIn ID |
| `get_all(limit, offset)` | Paginated job listing |
| `get_by_status(status)` | Filter by status |
| `get_matched_jobs(min_score)` | Get high-scoring jobs |
| `update_match_score(id, score, reasoning)` | Update match results |
| `search(query, status, min_score, location)` | Search with filters |
| `get_unmatched_jobs()` | Get unscored jobs |
| `get_top_companies(limit)` | Company ranking |

### ApplicationRepository
| Method | Description |
|--------|-------------|
| `create(**kwargs)` | Create application record |
| `get_by_id(id)` | Get by primary key |
| `get_by_status(status)` | Filter by status |
| `update_status(id, status)` | Update status |
| `add_note(id, note)` | Append timestamped note |
| `get_response_rate()` | Calculate response % |
| `get_daily_counts(days)` | Daily application counts |
| `get_status_breakdown()` | Status distribution |

### UserRepository
| Method | Description |
|--------|-------------|
| `create(**kwargs)` | Create user |
| `get_default_user()` | Get first user |
| `update_profile(id, **kwargs)` | Update user fields |
| `update_preferences(id, prefs)` | Update job preferences |
| `update_profile_data(id, data)` | Update skills/experience |

### ResumeRepository
| Method | Description |
|--------|-------------|
| `create(**kwargs)` | Create resume version |
| `get_primary(user_id)` | Get primary resume |
| `set_primary(id, user_id)` | Set as primary |
| `update_content(id, text)` | Update resume text |

## Configuration

See `config/config.yaml` for all available settings and `.env.example` for environment variables.
