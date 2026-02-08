# Springboard User Guide

## Installation

### Prerequisites
- Python 3.10 or higher
- Google Chrome browser
- A LinkedIn account
- An Anthropic API key ([get one here](https://console.anthropic.com/))

### Setup Steps

1. **Clone and install:**
   ```bash
   git clone <repo-url>
   cd springboard
   python -m venv venv
   source venv/bin/activate  # Linux/Mac
   # or: venv\Scripts\activate  # Windows
   pip install -r requirements.txt
   ```

2. **Configure credentials:**
   ```bash
   cp .env.example .env
   ```
   Edit `.env` with your LinkedIn credentials and Anthropic API key.

3. **Initialize database:**
   ```bash
   python -m src.database.init_db
   ```

4. **Launch dashboard:**
   ```bash
   streamlit run src/dashboard/app.py
   ```

## First-Time Setup

### 1. Set Up Your Profile
Navigate to the **👤 Profile** page and fill in:
- Personal information (name, email, phone)
- Work experience (add all relevant positions)
- Skills with proficiency levels
- Education history
- Job preferences (target roles, locations, salary range)
- Upload your base resume

### 2. Configure Search
Go to **🔍 Job Search** page:
- Enter target job titles
- Set location preferences
- Choose experience level
- Set salary range
- Enable Easy Apply filter (recommended)
- Set match threshold (60% recommended to start)

### 3. Verify Settings
Check **⚙️ Settings** page:
- Test LinkedIn connection
- Test Anthropic API connection
- Set daily application limits
- Configure delays between actions

## Daily Workflow

1. **Start a search** from the Job Search page
2. **Review matches** on the Jobs page, sorted by match score
3. **Monitor progress** on the Agent Monitor page
4. **Track applications** on the Applications page
5. **Analyze results** on the Analytics page

## Troubleshooting

### LinkedIn Login Issues
- Ensure credentials in `.env` are correct
- LinkedIn may require CAPTCHA verification — try logging in manually first
- If blocked, wait 24 hours before retrying

### API Errors
- Verify your Anthropic API key is valid
- Check rate limits on your API plan
- The system retries automatically up to 3 times

### Database Issues
- Run `python -m src.database.init_db` to recreate tables
- Use the Settings page to create a backup before troubleshooting
- Check `data/logs/springboard.log` for detailed errors

### Browser Issues
- Ensure Chrome is installed and up to date
- Try toggling headless mode in Settings
- Check that chromedriver is compatible with your Chrome version

## FAQ

**Q: How many applications per day is safe?**
A: We recommend 15-20 per day maximum to avoid LinkedIn detection.

**Q: Does this work with LinkedIn Premium?**
A: Yes, it works with both free and Premium accounts.

**Q: Can I customize which jobs to auto-apply to?**
A: Yes, set the auto-apply threshold in Job Search settings. Only jobs scoring above that threshold will be auto-applied.

**Q: Where are my applications tracked?**
A: All applications are stored in the SQLite database and visible on the Applications page.

**Q: Can I export my data?**
A: Yes, use the Export buttons on the Analytics and Applications pages to download CSV files.
