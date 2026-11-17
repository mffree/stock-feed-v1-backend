# Stock Feed API — Auth & Users

Contract between the iOS app and the backend for Sign in with Apple. Existing
endpoints (`GET /feed`, `GET /health`) are unchanged and need no auth.

## Conventions

- JSON request and response bodies, `Content-Type: application/json`.
- Timestamps are ISO 8601 UTC strings, e.g. `"2026-11-17T21:03:39Z"`.
- IDs are UUID strings.
- Authenticated endpoints need `Authorization: Bearer <access_token>`.
- Nullable fields are always present in responses, with value `null` when unknown.

### Error format

Every error response, including request-validation errors, has this shape:

```json
{
  "error": "invalid_session",
  "message": "Human-readable explanation for logs; do not show to users."
}
```

The client branches on `error` (a stable code), never on `message`.

| HTTP | `error` | Meaning | Client action |
|---|---|---|---|
| 400 | `invalid_request` | Body missing, not JSON, or fields missing or wrong type | Bug; log it |
| 401 | `invalid_apple_token` | Apple identity token failed verification | Show "Sign in failed, try again" |
| 401 | `not_authenticated` | No `Authorization: Bearer` header | Treat as signed out |
| 401 | `invalid_session` | Session token malformed, bad signature, expired, or its user no longer exists | Delete token from Keychain; treat as signed out |
| 503 | `apple_unavailable` | Backend couldn't fetch Apple's signing keys | Show "try again later" |
| 500 | `internal_error` | Unexpected server error | Show "try again later" |

### User object

Returned by sign-in and `GET /users/me`.

| Field | Type | Notes |
|---|---|---|
| `id` | string (UUID) | Stable user ID |
| `email` | string \| null | May be an Apple private-relay address (`…@privaterelay.appleid.com`). `null` if Apple didn't provide one |
| `display_name` | string \| null | Built from the name sent on first sign-in. `null` if never provided |
| `created_at` | string (timestamp) | |

```json
{
  "id": "3f6c2a9e-8b1d-4c57-9e0a-2d7f4b1c8a10",
  "email": "abc123@privaterelay.appleid.com",
  "display_name": "Jane Appleseed",
  "created_at": "2026-11-17T21:03:39Z"
}
```

---

## 1. Sign in with Apple

`POST /auth/apple` (no auth header)

Verifies an Apple identity token, finds or creates the user, and returns a
60-day session token. The same endpoint handles both first sign-up and later sign-ins.

### Request

| Field | Type | Required | Notes |
|---|---|---|---|
| `identity_token` | string | yes | `ASAuthorizationAppleIDCredential.identityToken`, UTF-8 decoded (a JWT) |
| `nonce` | string | yes | The **raw** nonce the app generated. The app passed `SHA256(nonce)` (lowercase hex) to Apple. The backend checks the token's `nonce` claim equals `SHA256(nonce)` |
| `given_name` | string \| null | no | From `credential.fullName`. Apple supplies it only on the very first authorization. Send it whenever present |
| `family_name` | string \| null | no | Same as above |

```json
{
  "identity_token": "eyJraWQiOiJXNldjT0tC...",
  "nonce": "q8Zt3v0rX1mJk2pN7aBcD4eF",
  "given_name": "Jane",
  "family_name": "Appleseed"
}
```

### Server behavior
1. Verify `identity_token`: RS256 signature against Apple's JWKS,
   `iss == "https://appleid.apple.com"`, `aud == APPLE_BUNDLE_ID`, not
   expired, `nonce` claim matches `SHA256(request.nonce)`.
2. Look up `auth_identities` by `(provider="apple", provider_subject=sub)`.
   - **Found:** update `last_used_at`. If the token carries an `email`, update the identity's email. Fill in
     `users.display_name` only if it is currently `null` and a name was sent.
   - **Not found:** create a `users` row (email from the token, `display_name`
     = trimmed `"given_name family_name"`, or `null` if both are empty) and an
     `auth_identities` row.
3. Issue a session JWT (`sub` = user id, `exp` = now + 60 days).

### Response: `200 OK`

| Field | Type | Notes |
|---|---|---|
| `access_token` | string | Session JWT. Store in Keychain |
| `token_type` | string | Always `"Bearer"` |
| `expires_at` | string (timestamp) | 60 days after issue. No refresh. Sign in again after this |
| `is_new_user` | boolean | `true` if this request created the account |
| `user` | User | |

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "Bearer",
  "expires_at": "2027-01-16T21:03:39Z",
  "is_new_user": true,
  "user": {
    "id": "3f6c2a9e-8b1d-4c57-9e0a-2d7f4b1c8a10",
    "email": "abc123@privaterelay.appleid.com",
    "display_name": "Jane Appleseed",
    "created_at": "2026-11-17T21:03:39Z"
  }
}
```

### Errors

| HTTP | `error` | When |
|---|---|---|
| 400 | `invalid_request` | `identity_token` or `nonce` missing/empty/not a string; names not string or null |
| 401 | `invalid_apple_token` | Not a JWT, unknown `kid`, bad signature, wrong `iss`/`aud`, expired, missing `sub`, or nonce mismatch |
| 503 | `apple_unavailable` | Apple JWKS fetch failed and no cached keys are usable |
| 500 | `internal_error` | Database or other unexpected failure |

---

## 2. Get current user

`GET /users/me` (requires `Authorization: Bearer <access_token>`)

Used on app launch to restore the signed-in state and to fill the Profile screen.

### Request
No body, no query params.

### Response: `200 OK`
A User object (see above), not wrapped.

### Errors

| HTTP | `error` | When |
|---|---|---|
| 401 | `not_authenticated` | `Authorization` header missing or not `Bearer <token>` |
| 401 | `invalid_session` | Token malformed, bad signature, expired, or user deleted |
| 500 | `internal_error` | Unexpected failure |

---

## 3. Delete current user

`DELETE /users/me` (requires `Authorization: Bearer <access_token>`)

Permanently deletes the user and all their `auth_identities` (cascade).
After this, the token returns `invalid_session` everywhere. If the same
Apple ID signs in again, a brand-new user is created (`is_new_user: true`).

### Request
No body, no query params.

### Response: `204 No Content`
Empty body. The client deletes the token from the Keychain and returns to the signed-out state.

### Errors

| HTTP | `error` | When |
|---|---|---|
| 401 | `not_authenticated` | `Authorization` header missing or not `Bearer <token>` |
| 401 | `invalid_session` | Token malformed, bad signature, expired, or user already deleted |
| 500 | `internal_error` | Unexpected failure; nothing was deleted |

---

## Open questions

- **Apple token revocation on delete.** Apple expects apps to revoke the
  user's Apple tokens when an account is deleted (`POST
  https://appleid.apple.com/auth/revoke`). That requires exchanging the
  `authorization_code` at sign-in, which needs extra secrets: Team ID, Key ID,
  and a `.p8` private key. This is out of scope for v1 under the agreed env vars. If
  added later, `POST /auth/apple` gains an optional `authorization_code` field
  and the backend gains three env vars.
- **Server-side sign-out / token revocation.** The tokens are stateless, so a
  leaked token stays valid until it expires or the user is deleted. Rotating
  `JWT_SECRET` invalidates every session.
