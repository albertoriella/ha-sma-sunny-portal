# Manual authentication for v0.1

Version 0.1 uses an experimental bootstrap because this project does not have
an SMA-authorized OAuth client and redirect URI. These instructions apply only
to Sunny Portal powered by ennexOS and can stop working if SMA changes its web
application.

## Before you begin

You need:

- access to your own Sunny Portal account;
- a desktop browser with developer tools;
- the Home Assistant integration setup form ready in another local tab.

Treat the refresh token like a password. Work on a trusted computer, do not save
a HAR file, do not take screenshots of response bodies, and do not paste the
token into a terminal, chat, issue, or password manager browser extension.

Use a new private/incognito browser window dedicated to this setup. A dedicated
session makes it less likely that the portal and Home Assistant will later try
to rotate the same refresh-token chain.

## 1. Capture the newest refresh token

1. In the private window, open the browser developer tools and select the
   **Network** panel.
2. Enable **Preserve log** before signing in.
3. Open [Sunny Portal powered by ennexOS](https://ennexos.sunnyportal.com/) and
   complete the normal SMA login.
4. Filter the network list for `token`. Select the successful `POST` request to:

   ```text
   https://login.sma.energy/auth/realms/SMA/protocol/openid-connect/token
   ```

5. In that request's JSON response, copy only the value of `refresh_token` and
   paste it directly into the Home Assistant setup form. Use the response from
   the newest successful token request if more than one is present.

Do not copy `access_token`, `id_token`, cookies, request headers, or the complete
response. The integration needs only `refresh_token`.

## 2. Find the plant ID

1. In Sunny Portal, open the plant that Home Assistant should use.
2. Keep the **Network** panel open and filter for `consumerbalance`.
3. Select a successful request whose path has this shape:

   ```text
   /api/v1/measurements/PLANT_ID/consumerbalance/consumption
   ```

4. Copy only the numeric `PLANT_ID` segment between `measurements/` and
   `/consumerbalance` into the Home Assistant setup form.

The plant ID is private metadata even though it is not a login credential. Do
not publish it. The config flow verifies that the captured account can access
the selected plant before saving anything.

## 3. Hand the token chain to Home Assistant

1. Submit the Home Assistant setup form once both fields are present.
2. Wait for the integration to validate the plant and complete setup.
3. Stop interacting with the dedicated Sunny Portal session and close the whole
   private window. Do not press **Sign out**, because a server-side logout may
   invalidate the session that Home Assistant has just adopted.

Do not reopen or automate that captured browser session. Sunny Portal refresh
tokens rotate: if the browser and Home Assistant both consume the same chain,
one of them can invalidate the token expected by the other.

The integration immediately rotates the submitted token, persists the newest
token atomically in a private Home Assistant store, and removes the bootstrap
value from config-entry data.

## Reauthentication

If Home Assistant reports that reauthentication is required, repeat the process
in a new private browser window and enter only the newly captured refresh token
in the reauthentication form. The configured plant ID stays unchanged.

If a token was accidentally shared, assume it is compromised. End the affected
SMA sessions, establish a fresh login, reauthenticate Home Assistant, and remove
the secret from every location where it was copied. Deleting it from a public
Git commit is not sufficient; credentials exposed in Git history must be
rotated.
