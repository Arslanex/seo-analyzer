# Connecting Google Search Console: setup guide

**English** · [Türkçe](google-setup.tr.md)

The app reads Search Console data with **read-only** access (`webmasters.readonly`). You create an OAuth client in Google Cloud once; after that you connect with your own Google account. It only works on the local machine (localhost).

## 1. Google Cloud project

1. Create a new project at <https://console.cloud.google.com/> (for example `seo-analyzer`).
2. Under **APIs & Services → Library**, find the **Google Search Console API** and press **Enable**.

## 2. OAuth consent screen (testing mode)

1. **APIs & Services → OAuth consent screen** (called *Google Auth Platform* in the new interface).
2. User type: **External**. Fill in the app name and e-mail fields.
3. Leave the publishing status as **Testing** (you do not need to publish).
4. Add **your own Google e-mail** to the **Test users** list. An account that is not on the list cannot connect (`access_denied`).

## 3. OAuth client ("Desktop app")

1. **Credentials → Create credentials → OAuth client ID**.
2. Application type: **Desktop app**. The name is free.
3. Download the JSON with **Download JSON** and save it as:

   ```
   data/google_client.json
   ```

   (For another path use `SEOA_GOOGLE_CLIENT_FILE`; instead of a file you can also set the `GOOGLE_OAUTH_CLIENT_ID` and `GOOGLE_OAUTH_CLIENT_SECRET` environment variables.)

Do not share this file or add it to git; the app never prints it anywhere.

## 4. Connect

1. Start the app and open `http://127.0.0.1:<port>/connect/google` in the browser (or use **Connect with Google** under Settings › Connections).
2. Pick your account in Google. The "This app isn't verified by Google" warning is normal (testing mode): choose **Advanced → go to (app name)** and approve the permission.
3. On success you return to the home page with `?google=connected`.

To see the status: `.venv/bin/python scripts/google_setup_check.py`

To disconnect, use the **Disconnect** button in the interface (it also revokes the permission at Google).

## 5. Property and site verification

The site you audit must have a property **verified in your account** in Search Console.

- **Recommended: a Domain property** (`sc-domain:example.com`). It covers every subdomain and both http and https. It is verified with a DNS TXT record.
- A URL-prefix property (`https://www.example.com/`) also works, but is valid only for that exact prefix.
- Verification: Search Console → *Add property* → follow the instructions (DNS, HTML file or tag).

The app does **not guess** a property for you: if no property matches the audited domain it says "property not found" and never shows another site's data. A `siteUnverifiedUser` permission does not count.

## 6. Common errors

| Symptom | Cause / fix |
|---|---|
| `redirect_uri_mismatch` | The client type is not "Desktop app" (for example "Web application" was chosen). Create a desktop client and refresh the JSON. |
| `access_denied` | Your account is not on the **Test users** list on the OAuth screen, or you declined the permission screen. |
| `invalid_grant` | Access was revoked at Google, or the 7-day period in testing mode ended. The app deletes the stored key; reconnect with **Connect with Google**. |
| "App not verified" warning | Expected in testing mode; Advanced → continue. |
| No refresh key was issued | Remove the app's access at `myaccount.google.com/permissions` and connect again. |
| "Property not found" in the report | The site has no verified property in your account (section 5). |
| "No permission" in the report | The property exists but is unverified, or your account's permission is not enough. |
| `rate-limited` | Google quota limit; URL Inspection allows 2000 queries per day per property. Try again later. |

Notes: Search Console data lags by 2-3 days, so the audit end date is 3 days before today. The refresh key is kept in `data/google_tokens.json` (permission 0600); a product would need encrypted storage.

## 7. Optional: a single API key (CrUX / PageSpeed)

Real-user data (CrUX) and PageSpeed need no OAuth; **a single API key** is enough:

1. In the same project: **Credentials → Create credentials → API key**.
2. Enable the **Chrome UX Report API** and the **PageSpeed Insights API**; restrict the key to these two APIs.
3. Add it to the `.env` file:

   ```
   SEOA_GOOGLE_API_KEY=...
   ```

You can test it from **Settings › Connections** with the **Test** button.
