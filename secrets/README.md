# Secrets of the public site

compose.yaml gives each of these files to one service as a Docker secret
(`/run/secrets/<name>`, read by the app's settings): the `findaline_*` files to `web`,
`opentopography_api_key` to `worker`; `deploy/monitoring/compose.yaml` gives
`grafana_admin_password` and `ntfy_url` to Grafana (docs/deployment.md, section 15). Put the value alone in the file, no
quotes, one line ending in LF (not CRLF: Grafana keeps the carriage return in its password); the files are git-ignored and never enter the image.

| File | Value |
| --- | --- |
| `findaline_session_secret` | A long random string that signs the sign-in cookie: `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `findaline_github_client_secret` | The client secret of the GitHub OAuth app |
| `findaline_google_client_secret` | The client secret of the Google OAuth client |
| `findaline_microsoft_client_secret` | The client secret (its *Value*) of the Microsoft Entra app; it expires (24 months at most): a new one before then |
| `grafana_admin_password` | The password of Grafana's user `admin` (the monitoring), used when Grafana's database is made: `deploy/vps.sh` writes a random one when the file is empty; changing it later needs `grafana cli admin reset-admin-password` in the container |
| `ntfy_url` | The whole URL of the secret [ntfy](https://ntfy.sh) topic Grafana sends its alerts to, one line, e.g. `https://ntfy.sh/<secret topic>`; pick a name nobody can guess |
| `opentopography_api_key` | The OpenTopography API key for `--source nasadem` (admins only on the public site; free at [opentopography.org](https://portal.opentopography.org/myopentopo)). OpenTopography allows one user per key: your own key only when you are the site's only administrator, otherwise empty |

`deploy/secrets.example/` holds the seven files empty: `cp -n deploy/secrets.example/* secrets/`,
then put the values in. Every file must exist (compose refuses to start without it): leave the file of a provider you do not
use empty (with its client id unset), and it is not offered; an empty `opentopography_api_key`
means no NASADEM. The session secret must have at least 32
characters. The container user (uid 10001) must be able to read it, e.g. `sudo chown 10001:10001 secrets/findaline_* secrets/opentopography_api_key && sudo chmod 400 secrets/findaline_* secrets/opentopography_api_key`;
Grafana's two files belong to Grafana's user (uid 472): `sudo chown 472:472 secrets/grafana_admin_password secrets/ntfy_url && sudo chmod 400 secrets/grafana_admin_password secrets/ntfy_url` (`deploy/vps.sh` does both).
