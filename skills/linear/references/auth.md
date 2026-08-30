# Auth

> **Index** — [Personal API key](#personal-api-key) · [OAuth (user)](#oauth-user) · [OAuth actor=app](#oauth-actorapp) · [Header format](#header-format) · [Scope cheatsheet](#scope-cheatsheet) · [Revocation](#revocation)

Linear supports three auth flows. **Use a personal API key for everything until you have a concrete reason not to** — it's the simplest path and matches the workflow this skill is built for.

## Personal API key

| | |
|---|---|
| Acts as | The owning user (full perms of that account) |
| Get one | Linear UI → **Settings → API → Personal API keys → Create key** |
| Token format | `lin_api_…` (48 chars at time of writing) |
| Header | `Authorization: lin_api_…` (raw, **no `Bearer ` prefix**) |
| Rotation | UI-only. The API has no `apiKeyCreate` / `apiKeyRotate` mutation. |
| When to use | Internal scripts, single-user agents, dev / sandbox |
| When not to | Multi-user products, anything you'll ship to a customer |

Storage: drop the token into `.env` as `LINEAR_API_KEY=…`. The CLI loads it via `python-dotenv`. The `.env` file is gitignored; never commit a key.

## OAuth (user)

| | |
|---|---|
| Acts as | The user who completed the OAuth flow |
| Token format | `lin_oauth_…` (or a JWT-shaped access token) |
| Header | `Authorization: Bearer lin_oauth_…` |
| Rate limit | Lower default than personal keys (~1,200 req/hr per user) |
| When to use | A multi-user app where each user authorises against their own data |

The `auth_header()` helper in `scripts/linear.py` routes anything that doesn't start with `lin_api_` through `Bearer ` — covers `lin_oauth_…`, raw JWTs, and any future token shape Linear introduces.

For a multi-user product flow, you'll need to handle per-installer token storage and refresh. That's out of scope for this skill — it's built for the workspace-bot pattern below.

## App identity (bot) — `client_credentials` grant

**This is the recommended path** when you (the developer) want your own OAuth app to talk to Linear *as itself*. The app authenticates with just its `client_id` + `client_secret`, no user dance, no browser, and the resulting token represents the app — comments, issues, and webhook events are attributed to the bot's name in Linear's UI and audit log.

| | |
|---|---|
| Acts as | The app (its own bot user in the workspace) |
| Grant type | OAuth 2.0 `client_credentials` |
| Token format | `lin_oauth_…` |
| Header | `Authorization: Bearer lin_oauth_…` |
| Lifetime | ~30 days (re-mint at any time by re-running the script) |
| Rate limit | 5,000 req/hr (vs ~2,500 for a personal key) |
| Scopes | `read`, `write`. **Not** `admin` — bots can't manage users or org settings. |
| When to use | Your own bot in your own workspace. The vast majority of cases. |

### Step 1 — register the OAuth app in Linear

1. **Settings → API → OAuth applications → Create new application**.
2. **Application name**, **Developer name**, **Description** — what you'll see on every audit log entry from now on. Linear lets you rename later but historical entries don't update.
3. **Application icon** and **Developer URL** — optional.
4. **Callback URLs** — required by the form. Use `http://localhost:8765/callback` even if you only intend to use `client_credentials` (Linear validates the URL but the `client_credentials` flow doesn't actually use it).
5. **GitHub username** — optional, only relevant if you bridge Linear ↔ GitHub through this app.
6. **Public** — leave **off** for single-workspace use.
7. **Client credentials** — toggle **ON**. *This is the key step.* Without it the `client_credentials` POST returns `unsupported_grant_type`.
8. **Webhooks** — leave **off** (we manage webhooks via the GraphQL API; this toggle is for a different feature).
9. **Create**. Copy `Client ID` (public) and `Client Secret` (private — never commit).
10. Add to `.env`:

    ```bash
    LINEAR_OAUTH_CLIENT_ID=...
    LINEAR_OAUTH_CLIENT_SECRET=...
    ```

### Step 2 — mint the bot token

```bash
python scripts/client_credentials_token.py
```

The script POSTs `grant_type=client_credentials` to Linear, gets a 30-day token, and writes it to `.env` as `LINEAR_API_KEY`. No browser, no consent screen, no refresh dance — just a token.

### Step 3 — verify

```bash
python scripts/linear.py query 'query { viewer { id name displayName } }'
```

Should return the bot's identity (e.g. `name: "ClaudeBot"`, `displayName: "claudebot1"`), not yours. Rate-limit header should show `5000`.

### Token expiry & re-mint

Tokens last ~30 days. When the token expires, queries fail with auth errors; re-run `client_credentials_token.py` to get a fresh one. There's no refresh dance because there's no user state to preserve — minting is idempotent. For unattended use, schedule it via cron a few days before expiry:

```cron
# Every 25 days at 03:00, refresh the bot token
0 3 */25 * *  cd /path/to/linear && python scripts/client_credentials_token.py
```

### Sharing the repo

If you publish this skill to GitHub, only the code is shared. Each user who clones it registers their own OAuth app in their own workspace, toggles **Client credentials** on, and runs the mint script. There is no shared-app pattern — that would create a security headache and cross-workspace attribution mess.

`.env` is gitignored (and `.env.*` for any variant filename); credentials never enter git history.

---

## Multi-tenant OAuth — `authorization_code` + `actor=app`

The path for **distributing your app to other workspaces**, where end-users install ClaudeBot in their own workspace and the app should act on their behalf as itself. This is the standard browser-dance OAuth flow with `actor=app` set on the authorize URL.

| | |
|---|---|
| Acts as | The app, but installed per-user/per-workspace |
| Grant type | `authorization_code` with `actor=app` URL parameter |
| Token format | `lin_oauth_…` (with paired `refresh_token`) |
| Lifetime | ~24h access token; rolling refresh keeps it alive indefinitely |
| When to use | A skill / app you're shipping to other Linear workspaces |

### Setup

Same OAuth-app registration as Step 1 above, except **leave Client credentials OFF** (or leave it ON — both grant types can coexist). The browser dance is run by `scripts/oauth_dance.py`:

```bash
python scripts/oauth_dance.py --write-env
```

This opens the user's browser, captures consent, exchanges the code for an `access_token` + `refresh_token` pair, and writes both to `.env`. To keep the token alive without further browser interaction, run `scripts/oauth_refresh.py` periodically:

```bash
python scripts/oauth_refresh.py
```

Refresh exchanges the rotating refresh token for a fresh access token + new refresh token. Cron it before the 24h mark and authentication lasts indefinitely.

> **Caveat from live testing:** Linear's `actor=app` URL parameter sometimes does not honor the bot-actor request and falls back to user-scoped tokens. For your own workspace use the `client_credentials` path above instead — it reliably gives bot identity. The auth-code dance is for the multi-tenant install case where `client_credentials` doesn't apply.

### Linear's `prompt=consent` is silently ignored for already-installed apps

If a user has already installed your app in their workspace, hitting the authorize URL again shows a "Manage" page instead of the consent screen — the dance times out waiting for a callback. To re-consent, the user has to uninstall the app first via Linear's app-management UI.

References: <https://linear.app/developers/oauth-2-0-authentication> · <https://linear.app/developers/oauth-actor-authorization>

## Header format

```http
POST /graphql HTTP/1.1
Host: api.linear.app
Content-Type: application/json
Authorization: lin_api_xxxxxxxx                # personal key, raw
# OR
Authorization: Bearer lin_oauth_xxxxxxxx       # OAuth user token
# OR
Authorization: Bearer eyJhbGciOi…              # OAuth actor=app JWT
```

`scripts/linear.py auth_header()` handles all three. The unit tests cover each branch.

## Scope cheatsheet

OAuth flows let you request a subset of permissions. Personal keys are full-power and do not use scopes.

| Scope | Grants |
|---|---|
| `read` | Read access to all resources (issues, projects, comments, etc) |
| `write` | Read + create/update/delete on most resources |
| `issues:create` | Create issues only — useful for narrow integrations |
| `comments:create` | Create comments only |
| `admin` | Workspace admin surface (user roles, billing, integrations). **Not granted to actor=app.** |

## Revocation

- **Personal key:** delete it in the UI (Settings → API → Personal API keys → trash icon). Effective immediately.
- **OAuth token:** call `revokeUser` mutation (user-scoped) or have the user uninstall the app from Settings → Apps.
- **If a key leaks:** revoke first, then regenerate. There is no "rotate" endpoint — revoke + recreate is the only path.

If you suspect a key in this repo's history was committed by mistake, the answer is the same: revoke it in Linear, regenerate, then strip from git history with `git filter-repo` or BFG. Don't try to "fix it later."
