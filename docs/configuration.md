# Configure (`.env`)

**English** · [Türkçe](configuration.tr.md)

Nothing is required. When something is missing, only the matching section says "not measured" and explains why. The **Settings › Connections** page shows what is ready and lets you test each key with a **Test** button.

| Variable | What it enables | Where to get it |
|---|---|---|
| `ANTHROPIC_API_KEY` | Summary, advice, E-E-A-T commentary and **Chat** | [console.anthropic.com](https://console.anthropic.com/) |
| `SEOA_GOOGLE_API_KEY` | Real-user speed data (CrUX) and PageSpeed | Google Cloud › Credentials › API key (see below) |
| `SEOA_OPENPAGERANK_KEY` | Domain authority estimate | [keywordseverywhere.com/account/openpagerank](https://keywordseverywhere.com/account/openpagerank) (a free key is tied to one IP address) |
| `SEOA_LLM_MODEL` | Model to use (default `claude-haiku-5-5`) | |
| `SEOA_LLM_BUDGET_USD` | Hard cap on all AI spending of this installation (default 8) | |
| `SEOA_MAX_PAGES` | Sample size of a site audit (default 25) | |
| `SEOA_RENDER` | Set `0` to turn headless rendering off | |
| `SEOA_DATA_DIR` | Where the database and files live (default `./data`) | |

`.env` and the `data/` folder are in `.gitignore`: your keys and Google tokens never enter the repository.

## Google connection

There are two separate things:

1. **A single API key** (for CrUX and PageSpeed; no site ownership needed). In Google Cloud, create a project, enable the *Chrome UX Report API* and the *PageSpeed Insights API*, create a key under **Credentials › Create credentials › API key**, restrict it to those two APIs and put it in `.env` as `SEOA_GOOGLE_API_KEY`.
2. **Search Console** (indexing, queries and rankings of your own sites), connected with read-only OAuth:
   1. Enable the *Google Search Console API* in the same project.
   2. Set up the OAuth consent screen as **External / Testing** and add your own e-mail under *Test users*.
   3. Create an OAuth client of type **Desktop app** and save its JSON as `data/google_client.json`.
   4. Start the app and press **Settings › Connections › Connect with Google**.
   5. The site must have a verified Search Console property in your account (a *Domain* property is easiest).

Details and common errors: [`docs/google-setup.md`](google-setup.md). To see the status from the command line: `python scripts/google_setup_check.py`.
