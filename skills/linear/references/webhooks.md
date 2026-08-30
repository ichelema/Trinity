# Webhooks

> **Index** — [Why this matters](#why-this-matters) · [Resource types](#resource-types) · [Create](#create-a-webhook) · [List / Get / Update / Delete](#list-get-update-delete) · [Rotate the secret](#rotate-the-secret) · [Signature verification](#signature-verification) · [Delivery and retries](#delivery-and-retries) · [Common pitfalls](#common-pitfalls)

## Why this matters

The Linear MCP **cannot manage webhooks** — there is no `save_webhook`, no `delete_webhook`, no `list_webhooks`. The only way an agent can subscribe to Linear events programmatically today is through this skill. Without webhooks, every agent reduces to polling the API on a timer; that's slow, expensive in complexity, and misses the events you actually need to react to (issue moved to In Progress, comment added, project marked at-risk).

This file is the reason the skill exists.

## Resource types

`WebhookCreateInput.resourceTypes` is `[String!]!` — a required list of event-source type names. Pass strings like `"Issue"`, not enum literals. Common values:

| String | Fires when |
|---|---|
| `Issue` | An issue is created, updated, or removed (state change, assignment, etc.) |
| `Comment` | A comment is created, edited, or deleted |
| `IssueLabel` | An issue label is created or removed |
| `Reaction` | A reaction is added to an issue, comment, or project update |
| `Project` | A project is created, updated, or archived |
| `ProjectUpdate` | A project status update is posted |
| `Cycle` | A cycle is created or updated |
| `Initiative` | An initiative is created or updated |
| `IssueAttachment` | An attachment is added or removed |
| `IssueSLA` | An issue SLA is set, breached, or resolved |
| `Customer` | A customer record changes |
| `CustomerNeed` | A linked customer need is added / removed |
| `OauthApp` | OAuth app installed / uninstalled (workspace admin) |
| `AppUserNotification` | A notification is delivered to an authorising user |
| `AgentSessionEvent` | Agent-session lifecycle (for `actor=app` integrations) |

If a value isn't in this list, run `scripts/linear.py introspect Webhook` to see what your workspace actually accepts. Linear adds new resource types occasionally and documentation lags.

## Create a webhook

Required: `url` and `resourceTypes`. Everything else is optional.

```graphql
mutation CreateWebhook($input: WebhookCreateInput!) {
  webhookCreate(input: $input) {
    success
    webhook {
      id label url enabled
      resourceTypes
      team { key }
      allPublicTeams
      secret
    }
  }
}
```

```json
{"input": {
  "url": "https://your-app.example.com/linear-webhook",
  "label": "Triage agent — issue events",
  "resourceTypes": ["Issue", "Comment"],
  "teamId": "<team-uuid>",
  "enabled": true
}}
```

| Field | Notes |
|---|---|
| `url` | HTTPS only. Linear posts JSON via `POST` here. |
| `resourceTypes` | At least one. Order does not matter; deduped server-side. |
| `label` | Free-form. Show this in your management UI. |
| `teamId` | Scope to one team. Omit (or set `allPublicTeams: true`) for workspace-wide. |
| `allPublicTeams` | Workspace-wide subscription, but only public teams. |
| `secret` | Optional — if omitted, Linear generates one and returns it on create. **Capture it. The secret is shown in plaintext only at create time.** |
| `enabled` | Defaults to `true`. Set `false` to provision quietly. |

## List / Get / Update / Delete

```graphql
query ListWebhooks {
  webhooks(first: 50) {
    nodes {
      id label url enabled
      resourceTypes
      team { key }
      allPublicTeams
      creator { name }
      createdAt updatedAt
    }
  }
}

query GetWebhook($id: String!) {
  webhook(id: $id) {
    id label url enabled resourceTypes team { key } allPublicTeams
  }
}

mutation UpdateWebhook($id: String!, $input: WebhookUpdateInput!) {
  webhookUpdate(id: $id, input: $input) {
    success
    webhook { id label url enabled }
  }
}

mutation DeleteWebhook($id: String!) {
  webhookDelete(id: $id) { success }
}
```

`WebhookUpdateInput` only exposes `label`, `secret`, `enabled`, `url` — to change `resourceTypes` or `teamId`, delete and recreate. `webhookDelete` is a hard delete; the subscription stops immediately.

## Rotate the secret

```graphql
mutation RotateWebhookSecret($id: String!) {
  webhookRotateSecret(id: $id) {
    success
    webhook { id secret }
  }
}
```

The new secret is returned in the response payload — capture it before the response leaves memory. After rotation, deliveries are signed with the new secret immediately. **Invalidating the old secret is your problem**: roll the receiver to accept either secret for a brief overlap window if you can't take a delivery gap.

## Signature verification

Linear signs every payload with HMAC-SHA256 using the secret. The signature is in the `Linear-Signature` header.

Reference verification snippet (Python — adapt for your runtime):

```python
import hmac, hashlib

def verify(body: bytes, signature: str, secret: str) -> bool:
    """Body is the raw request body. Compare in constant time."""
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
```

Always verify before parsing. An unsigned or wrong-signed request must be rejected with `401` so retries don't pile up. The receiver should also check `Linear-Delivery` (a UUID) for idempotency and `Linear-Event` for the resource type that fired.

## Delivery and retries

- **Method:** HTTPS POST. Plain HTTP is rejected.
- **Body:** JSON. Always `Content-Type: application/json`.
- **Timeout:** Linear waits a few seconds for a 2xx response. Take longer than that and the delivery is treated as failed.
- **Retries:** failed deliveries retry with exponential back-off for several hours. After enough consecutive failures the webhook is auto-disabled — read the `Webhook.failures` field for the recent failure log.
- **Order:** not guaranteed. Use `Linear-Delivery` for idempotency and the entity's `updatedAt` for ordering when you need it.
- **At-least-once:** plan for duplicate deliveries. Make your handlers idempotent.

## Common pitfalls

- **Secret captured-once.** `webhookCreate` and `webhookRotateSecret` are the only places the secret is returned in plaintext. Get it into your secret store before the response is gone.
- **`resourceTypes` is case-sensitive** and uses singular type names ("Issue", not "issues" or "Issues"). Use the strings in the table above verbatim.
- **`teamId` is the team UUID**, not the team key. Resolve `key → id` first via the `teams(filter:)` query in `references/common-queries.md`.
- **HTTPS-only URLs.** Linear refuses plain HTTP. For local dev, tunnel via `ngrok` / `cloudflared`.
- **Don't try to update `resourceTypes` via `webhookUpdate`** — the update input doesn't accept it. Delete and recreate.
- **Webhook auto-disable on repeated failure.** If your receiver goes down, expect the webhook to flip to `enabled: false` and need re-enabling. Monitor `enabled` in your provisioning code.

For the receiver side (the HTTP endpoint that receives payloads), this skill is **not** in scope — bring your own. The skill manages subscriptions; you write the handler.

Source: <https://linear.app/developers/webhooks>
