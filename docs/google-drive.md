# Google Drive delivery

After each publication (manual, "run now" or scheduled) Feed Studio uploads the
published XML to Google Drive. It always **updates the same Drive file**, so its
sharing link never changes.

Permissions: OAuth 2.0 with the scope `https://www.googleapis.com/auth/drive.file`
(classified by Google as *non-sensitive*). Feed Studio can only see and modify
the files it creates; it cannot read the rest of the user's Drive. Refresh tokens
are stored encrypted (Fernet) with `FEEDSTUDIO_SECRET_KEY`.

## 1. Create a Google Cloud OAuth client (once)

1. Open https://console.cloud.google.com/ and create (or select) a project.
2. **APIs & Services → Library**: enable **Google Drive API**.
3. **Google Auth Platform → Branding / Audience** (OAuth consent screen):
   - User type: **External** (or Internal for a Workspace organization).
   - App name, support email and developer contact.
   - Scopes: add `.../auth/drive.file`, `openid` and `email`.
4. **Clients → Create client**:
   - Application type: **Web application**.
   - Authorized redirect URI: exactly
     - Docker: `http://localhost:8080/api/integrations/google/callback`
     - Local development: `http://localhost:8000/api/integrations/google/callback`
     - A deployed server: `https://YOUR-DOMAIN/api/integrations/google/callback`
5. Copy the **Client ID** and **Client secret**.

> **7-day limit while in Testing.** Google issues refresh tokens that expire after
> 7 days for External apps whose publishing status is *Testing*. Before relying
> on scheduled uploads, set the publishing status to **In production**
> (Audience → Publish app). With only non-sensitive scopes this requires no
> Google review. While in Testing, add your account under *Test users*.

## 2. Configure Feed Studio

Generate an encryption key:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Add to `.env` (Docker reads it from the repository root):

```
FEEDSTUDIO_SECRET_KEY=<generated key>
FEEDSTUDIO_GOOGLE_CLIENT_ID=<client id>
FEEDSTUDIO_GOOGLE_CLIENT_SECRET=<client secret>
```

Restart: `docker compose up -d`. Keep the key safe: if it changes, connected
accounts must be reconnected.

## 3. Connect and add a destination

1. **Canales de exportación** → a channel → **Google Drive → Conectar Google Drive**,
   and accept the permissions.
2. Choose the file name (e.g. `google-merchant.xml`) and, optionally, a Drive
   folder (paste the folder URL or its ID). Without a folder the file goes to
   *My Drive*.
3. Publish a version (or **Subir ahora**). The destination shows the upload
   time and an **abrir en Drive** link.

For scheduled uploads, enable **Publicar automáticamente** on the channel and a
schedule on the source (**Fuentes XML → Actualización automática**).

## Troubleshooting

| Message | Cause and fix |
|---|---|
| "Google Drive no está configurado en el servidor" | One of the three variables is missing; restart after setting them. |
| `redirect_uri_mismatch` on Google's page | The redirect URI registered in Google Cloud must match exactly (scheme, host, port, path). |
| "Google ha revocado o caducado el acceso" | The 7-day Testing limit, a revoked grant or a changed password. Reconnect the account; publish the app to *In production*. |
| "no devolvió un token de acceso permanente" | Revoke Feed Studio at https://myaccount.google.com/permissions and connect again. |
| Upload creates a new file | The previous file was deleted in Drive or the folder was changed; the new id is kept from then on. |
