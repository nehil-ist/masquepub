# PHP to Python migration (finished)

Masque used to be one PHP file (`index.php`). It was moved to Python in steps with a *strangler* front door: Python answered every action it had taken over and forwarded the rest to PHP, sharing the same `app.db` and session files, so the site kept working after every step. All 171 actions, the file routes, the page shell, the link-preview cards, the background jobs and the database schema are now Python, and `index.php`, the PHP backend and the PHP parity tests have been removed.

## Layout
- `masque/config.py` `Config` (env vars), `masque/database.py` `Database`, `masque/php_session.py` `PhpSession` + `PhpSerial`
- `masque/security.py` `PasswordHasher` (bcrypt, `$2y$`, same hashes as PHP), `RecoveryCodes`, `RateLimiter` (`rl` table, `throttle`), `ClientIp`; `masque/names.py` `NameRules`; `masque/mailer.py` `Mailer` (Brevo), `MailTokens`; `masque/accounts.py` `Accounts` (sign-in, signup id, admin sync), `AccountEraser` (delacct); `masque/tidy.py` `Tidy`
- `masque/users.py` `Users` (`me()`, `need()`, `need_admin()`), `Admins`, `MailVault`, `Devices` (device tokens, `touch()` = PHP devtouch)
- `masque/gate.py` `MaintenanceGate` (runs before every migrated action that is not `maintenance_exempt`)
- `masque/actions/account.py` (me, signup, login, logout, recover, newrc, pw, delacct) and `masque/actions/mail.py` (mailset, mailverify, mailrm, mailreq, mailreset)
- `masque/actions/base.py` `Action`, `Context` (`ctx.users`, `ctx.action`), `Reply`, `Abort`, `ActionRegistry`; one module per area (`site.py`, ...)
- `masque/routes/` query-key routes that run before the actions (`base.py` `Route`, `RouteTable`, `FileBody`; `files.py` `UploadRoute` ?img=, `StickerRoute` ?stk=, `LinkThumbRoute` ?lpi=; `cards.py` `ProfileCardRoute` ?og=, `PostCardRoute` ?ogp=, `CardDiagnosticsRoute` ?ogdiag)
- `masque/linkpreview.py` (`AddressGuard`, `SafeFetcher`, `PagePreview`, `ThumbMaker`, `OwnLinks`, `LinkPreviews`), `masque/ogcard.py` (`CardAssets`, `Canvas`, `ProfileCard`, `PostCard`), `masque/actions/links.py` (`lpv`)
- `masque/assets.py` (`AssetFiles` min/plain choice and versions, `GzipAssets`, `AssetServer`), `masque/pages.py` (`PrettyLinks`, `ShellPage`, `LegalPages`, `ServiceWorker`), `masque/legal_content.py` (privacy and terms text), `masque/templates/shell.html` (the page, with `@@name@@` slots), `masque/routes/pages.py` (`ManifestRoute`, `LegalRoute`, `ServiceWorkerRoute`, `ShellRoute`)
- `masque/app.py` Flask front door (CSRF + upload-size gates, then the action), `masque/errors.py` `ErrorPages` (JSON crash and 404 answers), `masque/background.py` (timed jobs incl. `SessionGcJob`)
- `tests/`: `test_*.py` (including `test_users.py`, the user and session layer) run offline against the Python app (`python3 -I tests/test_posts.py`); `smoke.py` starts a throwaway `serve.py` and runs the end-to-end checks.

## Things that changed on purpose
- The feed returns image alt texts for every photo (PHP only filled them for the last photo row because of a missing brace).
- Files in `assets/` sub-folders (the saved fonts) are served too.
- Link-preview cards are drawn by Pillow instead of GD: close to, but not pixel for pixel, the old ones.
- Background work runs on a timer thread (`masque/background.py`) instead of after requests, so it also runs on a quiet site; tidy runs once an hour.
- Unknown actions answer `{"e":"Not found."}` (404) and crashes answer `{"e":"Server error. Please try again."}` (500) from Python (`masque/errors.py`).
- Old session files are deleted after 30 days of no use (`SessionGcJob`), as PHP's session garbage collection did.
- `masque/schema.py` creates and upgrades every table. It does not repeat PHP's one-time `user_version` 1 and 2 clean-ups, so a database must already have been opened by the PHP version once (any live site has been).
- The `Set-Cookie` PHP sent to a first-time visitor on the file routes is no longer sent.
