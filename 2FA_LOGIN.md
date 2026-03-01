# Garmin Two-Factor Authentication (2FA/MFA) Login

## Overview

This application fully supports Garmin accounts with Two-Factor Authentication (2FA/MFA) enabled. You can log in directly from the web UI -- no command-line token generation required.

## Logging In via the Web UI (Recommended)

1. Open the application in your browser (e.g. `http://localhost:5000`)
2. Open the **Settings** panel (gear icon on mobile, or scroll down on desktop)
3. In the **Garmin Connect** section, you will see the current login status
4. Enter your Garmin **email** and **password**, then click **Log in**
5. If your account has 2FA enabled, you will be prompted to enter your **MFA code** from your authenticator app or SMS
6. After successful login, the status will show a green dot and your display name
7. To disconnect, click **Log out**

Once logged in, the OAuth tokens are cached for approximately **one year**. The application will use these tokens for all automated syncs without requiring your credentials again.

## How It Works

The application uses [`python-garminconnect`](https://github.com/cyberjunky/python-garminconnect) + [`garth`](https://github.com/matin/garth) for Garmin SSO authentication:

1. **Token-first**: On every sync, the app tries cached OAuth tokens at `/garmin/.garminconnect`
2. **Credential fallback**: If no tokens exist, it falls back to `GARMIN_EMAIL` / `GARMIN_PASSWORD` environment variables (if set)
3. **Interactive login**: If neither works, the user logs in via the Settings page in the web UI (supports 2FA/MFA)

**Token lifecycle:**
- **OAuth1 token**: Valid for approximately **1 year**
- **OAuth2 token**: Short-lived, but **auto-refreshed** using the OAuth1 token
- You only need to log in again once per year or if you revoke sessions in your Garmin account

## Environment Variables (Optional)

`GARMIN_EMAIL` and `GARMIN_PASSWORD` are **no longer required**. You can omit them entirely and use the web UI login instead.

If you do set them, they serve as a fallback for automated credential login (only works without 2FA):

```yaml
environment:
  # Optional -- only needed if you want env-var based login (no 2FA)
  GARMIN_EMAIL: "your_garmin_email@example.com"
  GARMIN_PASSWORD: "your_garmin_password"
```

## Alternative: Pre-generate Tokens via CLI

If you prefer to generate tokens outside the container (e.g. for fully automated setups), you can still do so:

### Using the `garth` CLI

```bash
pip install garth

python3 -c "
import garth
from getpass import getpass

email = input('Garmin email: ')
password = getpass('Garmin password: ')

garth.login(email, password)
garth.save('./garmin-to-dawarich-sync/.garminconnect')
print('Tokens saved successfully.')
"
```

Ensure your docker-compose volume maps the token directory:

```yaml
volumes:
  - ./garmin-to-dawarich-sync:/garmin
```

### Using `uvx garth login`

```bash
uvx garth login
cp -r ~/.garth ./garmin-to-dawarich-sync/.garminconnect
```

## Token Storage

| Path (inside container) | Description |
|---|---|
| `/garmin/.garminconnect/` | garth token directory (`oauth1_token.json`, `oauth2_token.json`) |
| `/garmin/.garminconnect_base64` | Base64-encoded token backup (auto-generated) |

## Troubleshooting

### Status shows "Not connected"
No valid tokens exist. Log in via the Settings page or pre-generate tokens.

### "MFA is required for this Garmin account"
This error appears when the scheduled job or quick check tries to use env-var credentials on a 2FA account without cached tokens. Log in via the Settings page to cache tokens.

### Login fails with "Invalid email or password"
Double-check your credentials. Note that Garmin may lock your account after too many failed attempts.

### "Too many login attempts"
Garmin rate-limits login requests. Wait a few minutes before trying again.

### Tokens exist but syncs still fail
Tokens may have expired (~1 year) or been revoked. Click **Log out** in Settings, then log in again.

## Can I Disable 2FA Instead?

Yes, but it is not recommended. If you disable 2FA on your Garmin account:
1. Log in to [Garmin Connect](https://connect.garmin.com/)
2. Go to **Account Settings** > **Security** > **Two-Factor Authentication**
3. Disable 2FA

With 2FA disabled, the `GARMIN_EMAIL` and `GARMIN_PASSWORD` environment variables work directly. However, this reduces the security of your Garmin account, and the web UI login is a better alternative.
