# The writing standard: ASD-STE100 Simplified Technical English

Use these rules for every README and for `docs/ste-style-guide.md` in each repository. Copy this file
into the repository as `docs/ste-style-guide.md` and add a **project vocabulary** section (Section 3)
with the technical names and technical verbs of that project.

## 1. The writing rules

### Words

1. Use one word for one meaning, and one meaning for one word. Do not use synonyms for variety.
2. Use a word only as one part of speech. For example, `test` is a noun or a verb, `check` is a verb.
3. Do not use phrasal verbs (`set up`, `carry out`, `find out`, `pick up`, `look up`, `come up with`).
   Use one verb: `prepare`, `do`, `find`, `get`, `make`.
4. Do not use an `-ing` form as a noun or an adjective (`the running job`, `after indexing`).
   Exception: a technical name, a file name, a command or a status value.
5. Do not use contractions (`don't`, `it's`, `can't`). Do not use slang or idioms
   (`out of the box`, `under the hood`, `at a glance`, `gotcha`, `bells and whistles`).
6. Do not use `and/or`. Write `A, B or both`.
7. Do not use `should`, `could`, `would` or `may` for instructions. Use `must` for a rule, the
   imperative for a step and `can` for a possibility.
8. Keep the articles `a`, `an` and `the` in sentences.
9. Do not make a noun cluster of more than three words. A technical name is one word.

### Sentences

1. A procedural sentence (an instruction) has a maximum of **20 words**.
2. A descriptive sentence has a maximum of **25 words**.
3. Write one instruction in one sentence.
4. Use the imperative for an instruction: `Run the tests.` Not `The tests should be run.`
5. Use the active voice. Use the passive voice only when the agent of the action is not important.
6. Use only the simple present, the simple past and the simple future.
7. Put a condition before the instruction: `If the index is stale, build it again.`
8. Do not use semicolons in sentences. Write two sentences.

### Paragraphs, notes and warnings

1. A paragraph has one topic and a maximum of **6 sentences**. Start with the topic sentence.
2. A warning or a caution starts with a clear command. Then it gives the reason.
3. A note gives information. It does not give an instruction.
4. Use a vertical list for a sequence or a set of conditions. Each item of a numbered procedure is one step.

### Tables, headings and diagrams

1. A table cell can be a short phrase. If a cell has a sentence, the sentence obeys the rules.
2. A heading is a noun phrase (`The cost model`) or an imperative (`Run the demo`).
   Do not start a heading with an `-ing` form.
3. A diagram label is a short phrase. Use the same terms as the text.

### What STE does not change

Code, commands, file names, paths, field names, environment variables, status values, enum values,
product names and URLs stay exactly as they are. They are technical names. Put them in backticks.

## 2. General words to replace

| Do not use | Use |
|---|---|
| utilize, leverage | use |
| in order to | to |
| set up | prepare, install, configure |
| carry out, perform | do |
| make sure, ensure | make sure (allowed), or `check that` |
| a lot of, lots of | many, much |
| e.g., i.e. | for example, that is |
| should (instruction) | must (rule) / imperative (step) |
| might, may (possibility) | can |
| very, really, just, simply, easily | (delete) |
| seamless, robust, powerful, blazing | (delete or give a measured fact) |

## 3. Project vocabulary

This section gives the technical names and the technical verbs of Springboard. The README uses each term with only this meaning.

### 3.1 Technical names (nouns)

| Term | Meaning | Do not use |
|---|---|---|
| **job** | One job advertisement, one row of the `linkedin_jobs` table, from any platform | listing, vacancy, opening, position (except in a quoted title) |
| **platform** | One job source with a scraper: `linkedin`, `linkedin_feed`, `dice`, `indeed`, `monster`, `handshake` | site, board, portal, provider |
| **scraper** | A class that extends `BaseJobScraperAgent` and collects jobs from one platform | crawler, spider, bot |
| **platform registry** | The `_SCRAPER_REGISTRY` map from a platform name to a scraper class | factory, catalog |
| **feed post** | A LinkedIn post that contains a hiring keyword | hiring post (except the page name), update |
| **agent** | One Python class that does one step: orchestrator, supervisor, scraper, matcher, customizer or applier | worker, bot, service |
| **orchestrator** | The `OrchestratorAgent` that runs the scrapers and the other agents | coordinator, manager |
| **supervisor** | The `SupervisorAgent` that selects the next graph node | router, controller |
| **matcher** | The `JobMatcherAgent` that scores a job with Claude | ranker, scorer |
| **customizer** | The `ResumeCustomizerAgent` that writes a tailored resume and a cover letter | tailor, rewriter |
| **applier** | The `LinkedInApplicationAgent` that fills and submits the Easy Apply form | submitter, bot |
| **workflow** | The compiled LangGraph `StateGraph` of six nodes | pipeline (except `run_full_pipeline`), DAG |
| **node** | One function of the workflow: `feed_scrape`, `scrape`, `match`, `supervisor`, `customize`, `apply` | step (except the state field `current_step`), stage |
| **state** | The `AppState` dictionary that the nodes read and update | context, memory |
| **match score** | The weighted score from 0 to 100 that the matcher stores in `match_score` | fit, rating, rank |
| **category score** | One of the five scores: skills, experience, location, salary, company | sub-score, dimension |
| **weight** | The fraction of one category score in the match score | factor, coefficient |
| **minimum match score** | `min_match_score`, the lowest match score of a matched job | cutoff, floor |
| **auto-apply threshold** | `auto_apply_threshold`, the lowest match score of a pending application | apply bar, trigger |
| **primary resume** | The `Resume` row with `is_primary=True`, the base for each tailored resume | master CV, main resume |
| **tailored resume** | A `Resume` row that the customizer writes for one job | custom CV, variant |
| **application** | One row of the `applications` table | submission, apply record |
| **daily cap** | `MAX_APPLICATIONS_PER_DAY`, the maximum number of applications in one day | quota, budget |
| **status** | The value of the `status` column of a job, an application or a feed post | state (for a row), stage |
| **profile** | The default `User` row with `profile_data` and `preferences` | account, CV |
| **dashboard** | The Streamlit app in `src/dashboard/` | UI, front end, console |

### 3.2 Technical verbs

| Verb | Meaning |
|---|---|
| **scrape** | Open a platform in Chrome and read jobs from its search pages |
| **register** | Add a scraper class to the platform registry |
| **save** | Write new jobs to the database and skip the jobs that exist |
| **score** | Send a job and the profile to Claude and calculate the match score |
| **route** | Select the next node from the state |
| **retry** | Run a failed call or node again, with a delay that grows each time |
| **customize** | Write a tailored resume and a cover letter for one job |
| **apply** | Fill and submit the LinkedIn Easy Apply form of one job |
| **record** | Write an application row, a screenshot path and a note |
