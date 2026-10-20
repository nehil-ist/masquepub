# Masque

A social site where you wear a mask. Python (Flask) and SQLite, no email needed.

## Python migration
The site now runs entirely on Python (see `MIGRATION.md` for how it was moved from PHP). `python3 serve.py` creates the database tables, starts the background jobs and serves the site on `$PORT`.

## Files
- `serve.py`: starts everything (the database layout, the background jobs and the server)
- `masque/`: the Python server, one class per job (`app.py` front door, `actions/` one module per area, `background.py` timed jobs, `ogcard.py` link-preview cards, `pages.py` the HTML page)
- `assets/style.css`, `assets/app.js`: all styling and front-end code
- `tests/`: `test_*.py` (unit and parity tests) and `smoke.py` (end-to-end)

## Smaller files (rebuild after every change)
`assets/app.js` and `assets/style.css` are the source files you edit. For the live site they are shrunk into `assets/app.min.js` and `assets/style.min.css`, which load about 40% faster on phones.
1. Install Node.js once (nodejs.org, the LTS version).
2. In a terminal opened inside this folder run `sh build.sh` (on Windows without Git Bash, run the two `npx --yes esbuild ...` lines inside `build.sh` by hand).
3. Deploy the whole folder, including the two `.min` files.

The server uses the `.min` file only when it exists and is not older than its source, so if you edit `app.js` or `style.css` and forget to rebuild, the site quietly serves the normal (bigger) file instead of old code. To undo the shrinking, delete the two `.min` files. Check it is on by viewing the page source and looking for `app.min.js` and `style.min.css`.

The service worker cache name (`mq-shell-...`) is made from the served files' modified times, so there is nothing to bump by hand.

## Run locally
    pip install -r requirements.txt
    python3 serve.py
Needs Python 3.10+. Open http://127.0.0.1:8080 (set `PORT` to change it, `DATA_DIR` for where the database and photos go).

## Tests
    python3 -I tests/test_posts.py        # also test_users, test_account, test_files, test_pages, test_background, test_migration
    python3 tests/smoke.py                # starts a throwaway copy of the site, runs ~180 checks, stops it
The `test_*.py` files run offline (nothing else needs to be installed).

## Background jobs
Run by a timer inside `serve.py` (`masque/background.py`), not by visitors' requests: automatic database backups (`BACKUP_HOURS`, default 24, and `BACKUP_KEEP`, default 7, `0` = off; files in `DATA_DIR/backups`), deleting posts that have run out of time, tidying rows that point at deleted things, deleting unused sticker pictures, and the "your streak ends soon" push reminders (prompt streaks and chat streaks, last 3 hours of the UTC day, one push per person per day). `BACKGROUND=off` turns all of them off.

## Deploy on Railway
1. Push this folder to GitHub and create a Railway service from the repo (the `Dockerfile` is used).
2. Add a Volume (for example mounted at `/data`) and set the variable `DATA_DIR=/data`.
   The database, backups and every uploaded photo live there. Without a volume they are lost on each deploy.
3. Nothing else to set for the start command: the image runs `python3 serve.py` on `$PORT`.
   If you put nginx or another proxy in front, raise its body limit to at least 6 MB (nginx: `client_max_body_size 6m;`), otherwise it drops big uploads mid-way and phones show a network error.
4. Make sure the site is served over HTTPS (Railway does this by default).

## Optional recovery email (Brevo)
Off by default. When it is on, people can add a recovery email in Settings > Security and get a reset link if they forget their password. The recovery code keeps working either way.

1. Make a free account at brevo.com and add a sender address (the "from" address). Brevo emails it a confirmation link.
2. In Brevo create an API key (SMTP & API > API keys).
3. Add these variables on the server (Railway > Variables):
   - `BREVO_API_KEY`: the API key from step 2.
   - `MAIL_FROM`: the sender address you confirmed in step 1.
   - `MAIL_KEY`: a long random secret (20+ characters) that encrypts saved emails. Do not change it later, or saved emails become unreadable.
   - `SITE_URL`: the public address of the site, for example `https://masque.example.com` (no slash at the end). It is required on purpose: links in emails are never built from the visitor's Host header.
   - Optional: `MAIL_NAME` (sender name, default Masque) and `MAIL_DAILY_MAX` (emails per day, default 250; Brevo's free plan allows 300).
4. Redeploy. The Recovery email card appears in Settings > Security once all four required variables are set.

How it works: the email is saved only after the person opens the confirmation link (valid 1 hour). A reset link is valid 30 minutes, works once, and signs every other device out. Only a hash of each link is stored. Asking for a reset always gives the same answer and takes the same time, whether or not the account exists or has an email. Password changes, resets and email changes also send a notice to the saved address.
Brevo is called over HTTPS (Railway blocks plain SMTP on most plans). If sends fail with an "unrecognised IP" error, turn off Brevo's authorised-IP restriction for the key. Mail from a Gmail or other free sender address often lands in spam; sending from your own domain with Brevo's SPF/DKIM records fixes most of that.

## Things to know
- The group creator can set a group picture and rename the group from the pencil in the chat header (Edit group). Group pictures are only served to members of that group.
- Chats (direct and group) support replying to a specific message, one emoji reaction per person per message (double-tap a bubble for a heart), and pinned messages (up to 5 per chat, any participant can pin or unpin). Open the ⋯ menu under a message.
- Hold a reaction under a message (or right-click it, or choose **See who reacted** in the message menu) to see who left each emoji; tap your own row to remove your reaction. Group lists come from the `rxwho` action; a member who is only in the group as their Masque is shown as that Masque, and people who left show as Former member. Direct chats are drawn in the browser.
- Prompt streak look (Home → Prompt of the day): a flame that grows with the streak (Spark 1+, Kindled 3+, Blazing 7+, Wildfire 14+, Blue flame 30+, Eternal 100+), a 7-day row, a live countdown while the streak is at risk (the day ends at 00:00 UTC, when the prompt changes), progress to the next goal and best streak. A small flame chip with the number sits on the collapsed button, and a kept new day pops the flame and rolls the number up once. The `prompt` action sends `wk` (last 7 days, oldest first) and `best`; the look is `strBlock` / `strInfo` in `assets/app.js` and the `sk0`..`sk6` colours at the end of `style.css`.
- Keep `DATA_DIR` outside the public web root. On Apache the folder gets a `.htaccess` that blocks access; on Nginx add your own deny rule.
- The site copies the database into `DATA_DIR/backups` by itself, but those copies sit on the same volume: also copy `DATA_DIR` (`app.db` plus `up/`) somewhere else regularly.
- Without a recovery code or a recovery email, a forgotten password cannot be recovered.
- Users can block and report. Set `ADMIN_USERS` (comma-separated usernames, e.g. `ADMIN_USERS=you,friend`) to let those accounts open the Reports page from their profile. Admins can delete reported posts and comments or dismiss reports. Users can delete their own account from Edit profile (this removes their posts, photos, comments, likes, messages and friendships).
- Admin status follows the username, so an admin who renames their account loses it until the variable is updated. Register every `ADMIN_USERS` account right after you first deploy: until a name is registered, anyone could sign up with it. The safest way is the pair of variables below. Non-admins cannot rename themselves to an admin name.
- Renamed usernames: when someone changes their username the old one stays reserved for them (table `oldnames`), so nobody else can register it or take over the old @mentions. Usernames and display names can be changed once every 7 days (one shared timer), after a confirmation. Names released by renames made before this was added are not reserved.
- Comments: `comments` (GET, `pid`) and `comment` (POST, `pid`, `txt`, optional `par`) in `masque/actions/posts.py`. Replies are one level deep, a user can post 10 comments per minute, and blocked users' comments are hidden both ways. Mutes (`mutes`, `mutec`, `muteword`, `unmute`, table `mutes`) hide comments from chosen people or containing chosen words, only on your own posts and only for you; muted commenters send you no notifications and are not told. On an anonymous post the author's own comments stay anonymous to others and send no notifications.
- Blocking and Masques: blocking a person (account block) never changes what you see of Masque posts, comments, Room messages or notifications, because that would let you test whether a Masque belongs to someone (block them, see if it disappears). To hide a Masque, use Block on its profile page or "Block this Masque" in the chat menu (table `mblocks`; a blocked Masque's profile still opens so you can unblock it): you stop seeing its posts, comments, Room messages and notifications, and it can't message you. Account blocks still hide that person's normal posts and comments as before. The same rule holds in chats: an account block only applies between two plain accounts. If a Masque is on either side of a direct chat, or a message in a group was sent as a Masque, only blocking the Masque counts (messages, typing indicators, reactions, pins, unread counts and push notifications all follow it).
- Masque times: to other people, a Masque's posts, comments and edits show their time rounded down to the hour (`mqts()` in `masque/access.py`), so an exact minute can't be matched against someone's main account. The owner still sees the real time. Order in feeds is by post id, so it is unchanged. Room messages keep exact times because rooms delete themselves.
- Private accounts: in Edit profile a user can make their account private. Their posts (and the photos, comments and likes on them) are then visible only to the owner and accepted friends. The profile page, name, bio and counts stay visible. Masque posts (and old anonymous posts) are the exception: they ignore the owner's private account and are shown like any public post, because showing them only to the owner's friends would reveal whose Masque it is.

- Photos: the picker accepts up to 50 MB, but the browser shrinks every photo to about 1.2 MB (max 1600px, JPEG) before sending, so uploads stay small on mobile data. The browser redraws every upload through a canvas (max 1600px, JPEG) which also drops EXIF/GPS data, and the server strips metadata from JPEG, PNG and WebP again as a second layer.
- Login rate limit: 10 failed attempts per IP and 100 per username in 15 minutes (the username limit is high on purpose, so a stranger can't lock someone out of their own account). Unknown usernames take as long to reject as real ones. The IP comes from `X-Real-IP` (Railway overwrites it) and never from `X-Forwarded-For`.

- Accent color: gray. It lives in the `--sigil`, `--btn`, `--tint` and `--tint2` variables at the top of `assets/style.css` (light) and in the two dark-mode blocks near line 100.

## Motion
- All animation lives at the bottom of `assets/style.css` (stage 1 to 4 sections) and respects `prefers-reduced-motion`.
- `big(title)` in `app.js` makes the giant wiping page titles, `kin(text)` splits text into rising letters, and `slam(text)` stamps giant text over a post or the screen.
- Page-load animations only play when the URL hash changes, so refreshing a page after an action (like accepting a friend) does not replay them.

- Mentions and tags: `@name` in a caption or comment notifies that user (up to 5 per text, only if they can see the post). On a `#tag` page the Follow button subscribes you (max 30 tags); you get a notification when someone posts with it. Private accounts' posts only notify accepted friends.

## Install as an app (PWA)
- `?manifest=1` and `?sw=1` are served by `masque/routes/pages.py` from `assets/manifest.json` and `assets/sw.js`, so the service worker can control the whole site. Needs HTTPS (Railway has it).
- The service worker only keeps the page shell (HTML, CSS, JS) for offline start-up. It never caches API calls (`?a=`) or photos (`?img=`), so private content is not stored by it.
- Icons are in `assets/icon-*.png`. Settings has an Install card (Android/desktop button, iPhone instructions).
- After changing `assets/sw.js`, bump `V` at its top so old caches are cleared.

- Group chats: the creator can add friends to a group and remove members from the Members sheet (up to 31 people). New members start with no unread backlog.
- Leaving a group: anyone can leave from the Members sheet. If the creator leaves, the longest-standing member becomes the creator; if the last member leaves, the group and its photos are deleted.
- Renaming: the group creator can rename the group with the pencil button in the chat header; other members see the new name within a few seconds.
- Seen receipts: under your latest message in a group chat it shows who has read it ("Seen by Ana, Ben", or a count for bigger groups). People added after a message was sent are not counted as having seen it.

- Deleted usernames are reserved forever (stored as a SHA-256 hash in the `gone` table), so nobody can re-register a deleted account's name, including a deleted admin's. User ids are never reused either. Deleting an account also removes its group messages and memberships; groups it owned pass to the longest-standing member, or are removed if empty.

- Display names: optional, up to 24 characters, set in Edit profile. They are shown instead of the username on posts, profiles, chats, notifications and friend lists, and people search also matches them. The unique `@username` is still what you log in with and what mentions and profile links use. Display names must not look like anyone else's username or display name (see below); names that already clashed before this rule are left alone until changed. Control, invisible and bidi-override characters are stripped, and a display name cannot equal someone else's username, a deleted user's name or an `ADMIN_USERS` name. Anonymous posts hide the display name along with the username. The admin Reports page always shows real usernames.

- Group chat photos can only be opened by current members of that group (never cached publicly). Someone who leaves or is removed can no longer open them or edit their old messages (they can still delete them).
- Blocking inside groups: blocked people can't be added to a group where the person who blocked them is a member. If two people in the same group block each other, they don't see each other's messages (or count them as unread), but the group itself is untouched. Blocked people also can't like, comment on or be notified about each other's posts.

- Rate limits (table `rl`, per account unless noted): sign-up 5 per hour per IP, posts 20 per 10 min, photo uploads 40 per 10 min, DMs and group messages 40 per minute, friend requests 30 per hour, new groups 10 per hour, comments 10 per minute, wrong current-password guesses (change password / delete account) 10 per 15 min. The numbers are in the `throttle(...)` calls in `masque/actions/` (via `masque/limits.py`).
- Look-alike names: when someone signs up, renames, or sets a display name, it is compared with every other username and display name after lowercasing, folding common Cyrillic/Greek look-alike letters to Latin and dropping spaces, punctuation and symbols (`John_Doe`, `john doe` and `jоhn doe` with a Cyrillic о all match). Display names also can't look like an admin name.
- Sessions: changing your password signs out every other device (this one stays signed in). Passwords are limited to 72 characters because longer ones were silently cut off.
- Errors: crashes are logged, never shown to visitors, and any crash returns a plain "Server error" message (`masque/errors.py`). An unknown action answers "Not found." with status 404. Odd inputs such as `name[]=x` are treated as empty text.

- Database mode: SQLite runs in WAL mode (with a 5 s busy timeout), so several workers can read while one writes. Next to `app.db` you will now see `app.db-wal` and `app.db-shm`; they belong to the database. When you back up, copy all of them together (or stop the app first), otherwise the latest changes can be missing from the copy.
- Content-Security-Policy: scripts only run from this site (the one inline script uses a per-request nonce), fonts come from this site (saved at build time by `tools/fetch-fonts.sh`; if that step fails, the site falls back to Google Fonts and the policy allows it), everything else is blocked. If something ever looks broken after a deploy, set the variable `CSP=off`, redeploy, and check the browser console for the blocked item.
- Deleting a post, comment or account also removes reports and notifications that pointed at it. API answers are sent with `Cache-Control: no-store`.

- Admin account from variables (recommended): set `ADMIN_USER` (3 to 20 letters, numbers or _) and `ADMIN_PASSWORD` (8 or more characters) in Railway. Open the site and log in with them: the account is created on that first login, nobody can sign up with that name (or a look-alike) before it exists, and it counts as an admin automatically (no need to add it to `ADMIN_USERS`). You can change the password inside the app as usual. If you ever forget it, log in with the `ADMIN_PASSWORD` value and the account's password goes back to that value. This account can't be renamed or deleted from the app: to use another admin name, set a new `ADMIN_USER`. Anyone who can read your Railway variables can read the password, so only give out access you trust; for more admins keep using `ADMIN_USERS` (those accounts still have to be registered by hand).

## Recovery codes, suspensions, backups
- Recovery code: at sign-up (and whenever someone makes a new one in Settings, which needs their current password) the app shows a code like `ABCD-EFGH-JKLM-NPQR` once. Only a hash is stored. On the sign-in page, "Forgot password?" takes username + code + a new password, signs out every other device and issues a fresh code (each code works once). Accounts that existed before this update, and the `ADMIN_USER` account, have no code until they make one in Settings. Rate limits: 10 attempts per IP and 30 per username per 15 minutes.
- Suspend / ban: on the Reports page an admin can suspend a reported user for 7 days or ban them until lifted. Suspended and banned users can still read, sign out, change their password, make a recovery code and delete their account, but every other action that writes (posting, commenting, messaging, liking, profile edits, friend requests) is refused, and they see a banner explaining why. Admins cannot be suspended. Each report card also shows how many reports that user has in total.
- Admin log: the Reports page lists the last 30 admin actions (deleted, dismissed, suspended, banned, lifted, backup downloaded). Entries are kept 90 days.
- Backups: once per 24 hours (by a timer job) the app saves a consistent copy of the database to `DATA_DIR/backups/app-YYYYMMDD-HHMMSS.db` and keeps the newest 7. Change with `BACKUP_KEEP` (0 turns it off) and `BACKUP_HOURS`. Admins can also download a fresh copy from Settings, Admin, Download backup. Photos are NOT in these files: they live in `DATA_DIR/up/`, so also snapshot the Railway volume or copy that folder. Backup files contain password hashes and private messages, so keep them private. Needs SQLite 3.27+ (any current Python build).

## Report safety, auto-hide, unmask, tests
- Reports: you can't report your own content, a person can send at most 5 reports per 10 minutes and 20 per day, and reporting the same item twice counts once.
- Auto-hide: a post reported by 5 different accounts (`AUTOHIDE`, 0 turns it off) that are at least a day old (`AUTOHIDE_AGE` in seconds) disappears from feeds, profiles and search for everyone except its author and admins. Brand-new throwaway accounts therefore can't hide someone's post. On the Reports page the card says "Auto-hidden". Dismiss clears ALL reports on that item (so the post comes back); Delete removes it. Comments and profiles are not auto-hidden.
- Unmask: on one of your own anonymous posts, Post options has "Reveal myself" (with confirmation). It can't be undone, the post then shows your name, appears on your profile, and your comments on it stop being anonymous. Mentions and tag alerts that were skipped while it was anonymous are not sent retroactively.
- Tests: `tests/smoke.py` is a standard-library Python script that runs through sign-up, recovery codes, unmask, reports, auto-hide, suspension and backups against a throwaway server. The start command is in the file's header. Use a fresh `DATA_DIR`: it creates 4 accounts and the sign-up limit is 5 per hour per IP.

## Anonymous questions
- Every profile (except your own, private accounts you are not friends with, and people you have blocked) has an "Ask anonymously" box. Questions are up to 200 characters, 10 per hour per person and 3 per day to the same person, and a person can hold at most 100 unanswered questions (table `asks`).
- The owner opens **Questions** on their own profile (or taps the notification) and can answer, delete or report each one. Answering makes a normal public post (300 characters, never anonymous) with the question shown above it (`posts.aq`), and the asker gets an "answered your question" notification. Answers are posted under the owner's name; the question is never linked to the asker on screen.
- The sender is stored (`asks.frm`) only for rate limits, blocking and reports. The owner never sees it. Reporting a question hides it from the owner and shows the sender's real username to admins on the Reports page, where they can delete it or suspend the sender. Dismissing or deleting the report removes the question. Blocking someone removes their unanswered questions, and deleting an account removes the questions it sent or received. Answered posts stay.
- Owners can switch questions off in Settings, Privacy. It is on by default (including for existing accounts). To make it off by default, change `askon INT DEFAULT 1` to `DEFAULT 0` in the `users` table in `masque/schema.py` before the first deploy (existing accounts keep their value).

## Prompt of the day
- Home shows one question a day (a built-in list of 35 in `masque/prompts.py` `DailyPrompt`, rotating by UTC day). To use your own for today, set `PROMPT_TODAY` in Railway; remove it to go back to the list.
- Tapping Answer opens the New post sheet with the question above it. Photos and the "Masque" chip both work. Each person can answer once per day. The question text is saved on the post (`posts.aq`, with `posts.pd` = the day number), so old answers keep their question even when the list changes. "See answers" opens the day's answers (`#/d/<day>`); private accounts' answers show only to friends.

## Masks (second persona)
- Each account can make one extra mask (Settings, Second mask) with its own name, photo and bio (table `masks`). The name can't be changed; to get another, delete the mask and make a new one. Deleting a mask deletes its posts, comments, photos and alerts, and its name stays reserved forever (table `gone`).
- A post gets "Post as <mask>" in the New post sheet. In every comment and reply box your profile picture sits on the left; hold it to switch to your mask (the picture changes and gets a ring, and the box says "Comment as <mask>"), hold it again to switch back. A quick tap shows a hint, and with a keyboard Enter or Space switches. It stays on the persona you picked until you switch back. If you comment on one of your own mask's posts you always comment as the mask, so the two are never shown together.
- Mask names must not look like any username, display name, admin name or other mask (same look-alike check as usernames, both ways). Mask posts and comments appear everywhere with the mask's name and photo and link to the mask page `#/k/<name>`. They are left out of your real profile and its post count, and alerts they cause (comment, reply, mention, tag) show the mask.
- Not hidden: the mask page and mask posts follow your account's privacy and blocks (a private account's mask posts are visible only to its friends; people you blocked can't see them). Likes follow the same persona as comments: hold a like button (on a post or a comment) to switch between you and your mask; while it acts as the mask it has a dashed ring and the alert the other person gets shows the mask's name, not yours (the server refuses a mask like if the mask no longer exists, rather than falling back to your name). Other people can't @mention a mask. Admins always see the real owner (Reports page; reporting a mask shows its owner), and suspending the owner also stops the mask.

## Sensitive photo blur
- When posting (and in Edit post) a photo post has a "Sensitive photo" chip. The photos stay blurred, and can't be opened or double-tapped, until the viewer taps "Tap to view". Nothing is remembered: it blurs again on the next visit. Stored in `posts.sens` (0 normal, 1 set by the author, 2 set by an admin). It is ignored on posts without a photo.
- Admins: each reported post with a photo has "View post" and "Blur photo" on the Reports page. An admin's blur (2) can't be removed by the author, only by an admin ("Remove blur"). Blurring is logged in the admin log and does not dismiss the report.
- The photo file itself is not changed: the blur is drawn by the browser, so it protects against surprise, not against someone who really wants to see it.

## Blocked-word filter
- Admins open Settings, Admin, **Blocked words** and add words or phrases (up to 200, 2 to 40 characters, stored in lowercase in table `badwords`). Each one is either **Flag for review** or **Hold back until approved**.
- Matching is on whole words or phrases and ignores capitalization and invisible characters, so `ass` does not match `class`. It does not catch creative spellings (`a.s.s`, look-alike letters), so treat it as a time saver, not a wall.
- It checks new posts (including prompt answers and answers to anonymous questions), new comments, and edited posts and comments whose text changed. Admins are never filtered. Words added later do not re-check old content. Profiles, bios, display names, messages and anonymous questions are not checked.
- **Flag**: the post or comment stays visible and shows up on the Reports page as "caught by the word filter".
- **Hold back**: `posts.hold` / `comments.hold` is set to 1. Everyone except the author and admins stops seeing it (feeds, search, tags, profile counts, comment counts), and the author sees "Waiting for review". No mention, tag or comment alerts are sent while it is held and they are not sent afterwards either. On the Reports page the button says **Approve** (it releases the item and clears the entry) or **Delete**. If the author edits a held item so it no longer matches, it is released automatically.
- Automatic entries are rows in `reports` with `uid = 0`. They do not count in a user's "reports in total" and cannot be auto-hide votes. Adding and removing words is written to the admin log.

## Masked DMs
- Open any conversation and tap **As mask** in the header to write as your mask (`#/m/<name>/k`). The other person sees only the mask's name and photo, in their own inbox, as a separate conversation (`messages.fm` = sent from a mask, `messages.tm` = addressed to a mask).
- A mask can start a chat with a real person, but not with someone who only accepts messages from friends (a mask never looks at friendships, because that would tell the other person who it is). The other person can reply. Anyone can start a chat with a mask from its profile (**Message** button); friendships are never checked, so nothing reveals who owns it. First messages land in the owner's **Message requests** (top of the Masque tab in Messages: Accept or Ignore, and replying accepts too; table `mreq`), and they don't count as unread or pop up until accepted. The owner can also turn new messages off for the mask (`masks.inb`). Real blocks and the DM rate limit still apply.
- The person receiving mask messages gets **Block** (this mask only: `mblocks`, it never touches the real account or friendships) and **Report** in the chat header. Reports show the owner to admins as usual.
- Deleting a mask deletes its chats and photos. Real blocks and the "you can't message this person" rules still apply to the owner account.

## Tell a friend your mask is you
- On your own mask page, **Tell a friend** lists your accepted friends. Choosing one (after a confirmation) saves a row in `mreveals`, sends them a "told you their mask is them" notification, and shows them a private line on the mask page saying whose it is. Nobody else sees anything.
- You can tap a friend again to stop showing your name on the mask page for them, but they still remember what they were told. Deleting the mask removes all of this.

## Disappearing posts
- The New post sheet has an **Expires: Never / 24 hours / 7 days** chip (tap to cycle; `posts.exp`, a unix time). The post shows a "Gone in ..." tag. Expired posts are deleted, with their photos, likes, comments, reports and alerts, on the next request after they expire (up to 50 at a time). It can't be changed after posting.

## Anonymous polls
- In New post, the **Poll** chip takes 2 to 4 options (up to 40 characters each); the caption is the question. Polls can't have photos and can't be a prompt answer. Everyone who can see the post can vote once and can't change it.
- Votes are anonymous by construction: `pollvoted` only records that a person voted (to stop double votes) and `polls.n` holds the count per option. No table links a person to an option. Results show after you vote (the author always sees them). If someone deletes their account their "voted" row goes, the counts stay.

## Prompt streaks and highlights
- The Home prompt card shows "You've answered N days in a row" (or "Answer today to keep your N-day streak" if you haven't yet today). A streak survives until a whole UTC day passes with no answer. Days are stored in `pstreak`, so deleting or expiring an answer never breaks it; accounts that existed before get their past answers counted automatically.
- **Worth reading** (`#/h/1`) shows yesterday's most-liked prompt answers and **This week** (`#/h/7`) the last 7 days (up to 5 each, at least one like, private accounts only to friends as usual).

## Pinned post
- In Post options on one of your own posts, **Pin to profile** (or **Unpin**) puts it first on your profile with a "Pinned" tag (`users.pin`). One pinned post at a time. Anonymous posts, mask posts and posts waiting for review can't be pinned, because they must never show on your real profile.

## Mask reputation
- A mask's page shows a level badge: Stranger (0 points), Whisper (10), Regular (40), Familiar (120), Legend (300). Points are 3 per post, 1 per comment and 1 per mark (like) received on its posts and comments, counted live (`maskuser` in `masque/actions/masques.py`, thresholds in `MasqueRep.THRESHOLDS`). It follows the same privacy as the mask's posts: for a private account's mask only the owner and friends see it. Deleted or expired posts stop counting.

## Mask comments tab
- Names and pictures in comments link to the commenter's page (a mask goes to `#/k/<name>`, a real person to their profile; anonymous comments stay unlinked).
- A mask page has **Posts** and **Comments** tabs. Each comment shows the post it was on and opens that post when tapped (`mcomments` in `masque/actions/masques.py`, 30 per page with Load more). Comments on posts you can't see, held comments, and a mask owner's comments on their own anonymous posts are left out. For a private account's mask only the owner and friends see the Comments tab.

## New post layout
- Post options (Masque, Poll, Sensitive photo, As mask, Expires) are small toggle chips. Tapping one shows its explanation in a single line under the chips, so the sheet fits a phone without scrolling. The live text preview has a minimum height and never gets squeezed.

## Masque mode indicator
- Holding a like button, the comment-box picture, or the Profile button in the nav (phone dock and desktop side rail) switches between you and your mask. While acting as the mask, a "Masque mode" pill slides in at the top and `<html>` gets class `mm`. The old dashed rings on likes and the ring on the comment picture are gone.
- While `<html>` has class `mm`, the border colors (`--line`, `--edge`, `--ol`, `--sh`) are darker in light theme and lighter and stronger in dark theme, with a short fade.
- In mask mode the nav Profile button shows your mask's picture and name and opens the mask profile (`#/k/name`). Each switch also pops the profile you are switching to in the middle of the screen for about a second and a half (skipped when the device asks for reduced motion).

## Masque posts
- Anonymous posts are now called Masque posts. The composer chip is "Masque". Other people see a laughing-mask picture and the name "Masque" on the post, and on that author's comments on it. The author sees their own name with a small laughing-mask badge on the picture and a "Masque to others" tag. Nothing changed on the server. This is separate from your second mask ("As [mask name]").
- Masque posts, header update: the laughing mask is no longer the profile picture. It now sits in the post header as a small stamp next to the time, and it laughs (hops, squints, mouth pulses, a little "ha ha" floats off) when you like the post, double-tap the photo, open the comments, send a comment or copy the link. Other people see a plain default avatar and the name "Masque". On your own Masque post you see your mask's name and photo (or your own name if you have no mask) with the "Masque to others" tag. Comments by the author are unchanged. Nothing changed on the server.
- Slight vibrations: the nav profile button (the one you hold to switch between you and your mask) shakes a little while you hover it, building up gently. The like button shakes and settles when you like a post, and phones that support it give a tiny buzz. Both are skipped with reduced motion on. Also fixed: holding the nav profile button while one of your own profiles is open now jumps straight to the other profile (you or your mask), so you no longer have to tap it a second time.
- Naming: everywhere the app showed the word "mask" for your second identity (buttons, labels, hints, alerts, error messages, the app description), it now says "Masque" (for example "Create your Masque", "As Masque", "Masque name"). The laughing-mask picture is still described as a laughing mask, and nothing underneath changed: the database table, API names, CSS classes and file names are the same.
- Prompt of the day page (`#/d/<day>`): it now counts as Home (Home is highlighted) and its back button says "← Home" instead of ← Explore. Tapping Home (the nav button or the logo) while you are already on Home refreshes the feed and scrolls back to the top.
- Masque mode pill: the pulsing dot is now a small laughing mask that giggles every few seconds (skipped with reduced motion).
- New post sheet: the separate "As [name]" option is gone. There is one **Masque** chip. If you have a second profile, posting with it on publishes the post under that profile's name and photo (visible to everyone, linking to its page) with the laughing-mask stamp in the header, and the post stays out of your real profile. If you have no second profile it is the anonymous Masque post as before. Nothing changed on the server.
- Expiration picker: the **Expires** chip in the New post sheet now opens a bottom sheet instead of cycling. Drag the slider (Never, then 1 minute up to 30 days) or tap +1 min, +5 min, +1 h or +1 day (they add up), or Never to clear it. The server (`post` in `masque/actions/posts.py`) takes `exp` as a number of seconds (clamped to 1 minute to 30 days) and still accepts the old `24h` and `7d`.
- Masque profile page: a laughing-mask badge sits on the picture. It laughs once when the page opens and every time you tap the picture.
- Anonymous posting is removed. The only options are posting as yourself or as your Masque (the **Masque** chip in the New post sheet; if you have no Masque yet, tapping it opens the create-Masque sheet). The server now ignores the `anon` field on `post`. Old anonymous posts are kept: they still show as "Masque" with the default picture and the laughing-mask stamp, and their authors can still use "Reveal myself". Comments now match posts: everyone gets their own picture (the default one for old anonymous comments) and Masque comments get a small laughing mask next to the name. `tests/smoke.py` was updated to match (the unmask checks now confirm it is refused, because no new anonymous post can be made).

## Downvotes and negative reputation
- Masque posts and comments (not your own) get a small down-arrow button next to the sigil. Tapping it takes 1 point off that Masque; tapping again undoes it. A downvote and a mark from the same person cancel each other (choosing one removes the other). Only Masque content can be downvoted, never real profiles.
- Downvotes are never shown as a count and never send an alert, and the Masque's owner can't see who did it. Routes: `dislike` (post, `id`) and `cdislike` (comment, `id`) in `masque/actions/posts.py`, stored in `dislikes` / `cdislikes`. Limit: 60 downvotes per hour per account. Suspended and banned users can't downvote (same as every other write).
- Score is now `3 per post + 1 per comment + 1 per mark - 1 per downvote` and can go below zero. Below 0 the badge reads **Shunned** (red) and the progress bar fills from -100 up to Stranger at 0. The Masque page also shows a downvote total, to the same people who can see its points.

## Live updates, banners, typing, status
- The page polls `?a=live` while the tab is visible, at a pace that follows how the page is being used (`liveDelay()` in `app.js`): every 2 s with a chat open or 4 s otherwise while you are active; double that after 30 s without touching the page; up to 1.5x and 2.25x slower still when several checks in a row show nothing new (capped at 6 s with a chat open, 12 s otherwise); and every 20 s after 5 minutes untouched. The first touch after a quiet spell checks immediately. A hidden tab does not check at all. The cap stays under the 45 s "online" window, so presence is unaffected. It returns badge counts and change signatures only; the page then fetches what changed. No long-lived connections, so server threads are never tied up.
- Pop-up banners for new DMs and group messages come from the same call (`af` / `gaf` = highest message ids the page has seen). A Masque sender is only ever shown as the Masque.
- Typing: table `typing` (rows live 5 s), written by `?a=typing`, read by `live`.
- Status: `users.la` (last check-in), `users.idl` (quiet for 5 min), `users.pst` (chosen: auto, online, idle, off). Online means a check-in in the last 45 s. Masque chats (either side) never show a status; they show the laughing mask instead.
- Private per-chat settings (`dmpref`): nickname for the other person and chat background.
- Chat search: `?a=msearch` (DMs, scoped to that exact pair and mask side) and `?a=gsearch` (groups). Plain-text match, 2+ letters, 40 results, newest first. Jumping to an old result opens the chat window around it (`thread` / `gthread` accept `around=<message id>`) and pauses live refresh until "Jump to latest" or you send something. The DM header's three dots menu holds Nickname, Chat background and Search.

- New post drafts: the caption, background, poll options, Masque toggle and expiry are saved in the browser's localStorage (`mq-draft-<username>`) as you type and restored when New post is opened again; photos are not kept. Closing the sheet with only a draft to keep no longer asks to discard. The draft is cleared when the post is shared.

- Signed-in devices: table `devices` (one row per browser, token kept in the session file, label from the User-Agent, no IP stored). `devices` (GET), `devout` (POST `id`) and `devoutall` (POST) in `masque/actions/notifs.py`; deleting a row signs that browser out on its next request. Sessions that existed before this was added are adopted on their next request. Changing the password or recovering the account still signs out every other device, and their rows are removed.

- Visitor IP behind a proxy (`IP_HEADER`, `IP_HOPS`): the sign-up limit (5 per hour) and the password-recovery limit use the visitor's IP. Behind a host's proxy (Render, Railway, ...) the app may only see the proxy's address, which would make everyone look like one visitor. Sign in as an admin and open `/?a=ipdiag` to see what your host sends, then set `IP_HEADER` to the header that carries the real IP (for example `True-Client-IP`). If that header is a list (`X-Forwarded-For`), set `IP_HOPS` to the entry to use counting from the right (1 = last). Unset, the app uses `X-Real-IP` if present, else the connection address. Only set a header your host fills in itself: one that visitors can send themselves can be faked.
- Chat attachments: a person can add 10 attachments a minute and 60 an hour (4 and 20 for new accounts) and 300 MB per 24 hours (100 MB for new accounts); admins are exempt. Attachments are refused when the data disk has less than `MIN_FREE_MB` free (default 500; `0` turns the check off), so the database and sign-ins keep working.
- New-account limits: for the first 24 hours (set `NEWACCT_SECS`, in seconds, to change it; `0` turns it off) an account gets tighter limits: posts 5/hour, comments 5/min and 30/hour, friend requests 10/hour, messages 15/min, anonymous questions 3/hour, new group chats 2/hour and adding people to groups 5/hour. For the first hour it also cannot put links in posts, comments or edits. Admins are exempt. Photos per post stay at 10. The smoke test makes brand-new accounts, so start the throwaway server with `NEWACCT_SECS=0`.

- Post visibility: `posts.vis` is 0 (everyone, the default), 1 (friends only) or 2 (only the author). `post` and `edit` accept `vis`. It is enforced in `canpost()` (comments, likes, saves, votes), in the feed query (profiles, tags, search, saved, single post), when serving photos, and in the trending tags and prompt counts. Friends-only is refused for Masque posts (it would reveal whose Masque it is). Posts that are not public send no mention or tag-follow notifications. The Private account setting still applies on top of this.

- Suspension appeals: table `appeals` (st 0 waiting, 1 approved, 2 denied). A suspended or banned user can still call `appeal` (POST `txt`, 20 to 1000 characters; one waiting at a time, 7 days after a denial, 3 per day) and `appealst` (GET); the banner shows an Appeal button. Admins see waiting appeals at the top of Reports and answer with `appealres` (POST `id`, `ok`, optional `note`): approving lifts the suspension, denying shows the note to the user. Lifting a suspension by hand also closes the user's waiting appeal. Decisions go in the admin log.

## Report feedback
- When an admin dismisses or deletes a reported item (Reports page), everyone who reported it gets a notification: "A report you sent was reviewed by the team." (`notifs.kind = 'rview'`, written by `masque/notify.py`). It never says what was decided and never names the person or the content. Word-filter entries (`uid = 0`) send nothing. These notifications are not tied to a mute group, and are cleared after 30 days like all notifications.

## Ban + delete all content (spam waves)
- On a report card (for any user that is not an admin) the **Ban + delete all content** button calls `purge` (POST `name`, admin only, 10 per hour). In one transaction it bans the account (until lifted) and deletes the user's posts and their photos, comments (and all comments on their posts), likes and downvotes they gave or received on them, direct and group messages they sent, anonymous questions they sent, pending friend requests they sent, upload leftovers, and any reports about them or filed by them. Reporters of the removed items get the usual "was reviewed" notice. Posts made as their Masque go too, because they belong to the same account.
- Kept on purpose: the account itself (so the name stays reserved and the user can still appeal), accepted friendships, the profile picture, bio and Masque profile (use the existing Suspend/Ban and delete tools if those are the problem), and messages other people sent to them. It is logged in the admin log as "banned + deleted content of". It cannot be undone, and there is no restore from the in-app log, so use a backup if you ever need the data back.

## Profile themes
- Edit profile has a **Theme** card: background (14 tinted or gradient colors, plus a pattern: Grid, Graph paper, Dots, Fading dots or Fading grid; the page background fades in when you open a profile and out when you leave), card style (Classic, Flat, Glass, Outlined) and font (6 presets). Stored as preset ids in `users.tbg` / `tbp` / `tcd` / `tfn`; the `profile` action in `masque/actions/profile.py` only accepts ids from its whitelist, so nothing typed by a user reaches the page.
- Everyone who opens that profile sees the theme: `app.js` (`setPT`) sets `data-pbg`, `data-pcd`, `data-pfn` on `<html>` while a profile is open and clears them when you leave. Rules are at the bottom of `assets/style.css`. Backgrounds are mixed into the normal page color, so they stay soft in dark mode.
- Adding a preset: add its id to the whitelist in `masque/actions/profile.py`, to `PBG` / `PCD` / `PFN` in `app.js`, and a `[data-pbg=...]` / `[data-pfn=...]` rule in `style.css`.
- Avatar style (Edit profile): shape (Circle, Squircle, Hexagon) and frame (None, Ring, Rainbow, Dashed, Glow), stored in `users.tas` / `taf` with the same whitelist check and the same `data-pas` / `data-paf` mechanism. They apply to the avatar on the profile page.
- Post layout (Edit profile): List (the normal cards), Grid (3-column tiles, `tile()` in `app.js`; tapping one opens the post page, and sensitive photos stay hidden in tiles) or Big card (`.pbc`, larger photos and text). Stored in `users.tpl`, same whitelist check. It only changes how that person's own profile page lists their posts, not feeds, tags or search.

- Staying signed in across updates: Sessions are stored in `DATA_DIR/sessions` (the persistent volume) instead of the server's temp folder, and last 30 days, so redeploying does not sign anyone out. This only works if `DATA_DIR` is on a volume (see Deploy).
- Maintenance mode: admins turn it on from Settings → Admin → Maintenance mode, with a message (300 characters). While it is on, everyone except admins sees a "Down for maintenance" screen with that message; admins keep full access and see a banner. Nobody is signed out, and the screen checks every 15 seconds and returns to the site by itself. Non-admins can't sign in or sign up meanwhile. Stored in the `site` table (`mt`, `mtmsg`); the toggle is in the admin action log.
- Admin way in during maintenance: the maintenance screen has no sign-in button. Admins tap the Masque logo 5 times quickly (works in the installed app too) or add `#/admin` to the address. Non-admins who try get the maintenance message instead of a session.
- Prompt-of-the-day threads: answers to the daily prompt no longer fill the Everyone / Friends feeds one by one. The `feed` endpoint leaves `pd>0` posts out of the home feeds and instead returns `threads` (the last 3 days that have answers you can see: day, prompt, count, up to 3 faces, whether you answered). The page drops one thread card per day among the first posts (steady spot per day and user); it opens `#/d/<day>` which lists every answer. Answers still show on the author's profile, Saved, search and tags.
- Avatar shapes and frames (Edit profile > Profile picture): shapes Circle, Squircle, Hexagon, Octagon, Diamond, Shield, Pixel; frames Ring, Rainbow, Dashed, Glow plus game-style Gold, Royal, Emerald, Ruby, Neon, Pixel, Prism (color-cycling) and Ember (pulsing glow). Stored in `users.tas` / `users.taf`, ids whitelisted in `masque/actions/profile.py`, drawn in the "Avatar shape and frame" and "More avatar shapes" sections of `assets/style.css`. Prism and Ember stop animating with reduced-motion.

- Audio in chats: in a direct or group chat the attach button also takes an audio file (MP3, M4A, AAC, OGG/Opus, WAV, FLAC, up to 25 MB). It is recognised by its first bytes, not its name, stored in `DATA_DIR/up/` and shown as a player in the message. It follows the same access rules as chat photos (only the people in the chat can open it) and is deleted with the message. If uploads over a few MB fail, raise `upload_max_filesize` and `post_max_size` (the start commands above use 5M and 6M).
- Group picture: tapping the picture at the top of a group chat opens it full size.

## Link previews
- Site link: `assets/og.png` (1200x630, the zine look with the laughing mask). The `?v=` on its URL changes whenever the file changes, so chat apps fetch the new one.
- Profile links (`/u/name`, older `/?u=name` still works) get a card drawn per person by `?og=<name>` (`masque/routes/cards.py`, drawn in `masque/ogcard.py`): photo (or the default laughing-mask avatar), display name in Pirata One, @username, bio (private accounts show "Private account" instead of the bio), and an "Open on Masque" button. It is drawn with Pillow (needs FreeType; `?ogdiag` as admin reports it). If the route fails for any reason it redirects to `assets/og.png`.
- Cards are cached as PNGs in `DATA_DIR/og/` (one per person, replaced when their name, bio, photo or privacy changes, old ones pruned after 30 days). Fonts are in `assets/fonts/`. If text looks too big or small on your server, change the scale constant at the top of `masque/ogcard.py`.

## Pretty links
- `/u/<name>` and `/p/<id>` are handled by `masque/routes/pages.py` (the preview tags and cards work exactly as for `?u=` / `?p=`). The page gets a `<base href>` so `?a=`, `?img=` and `assets/` still resolve from the app root; `BASE` in `app.js` reads it.
- `serve.py` sends every unknown path to the page, so no rewrite rules are needed. Behind nginx or Apache, proxy everything to `serve.py`.
- Bumped service worker cache to `mq-shell-70`.

## Post link previews
- **Copy link** on a post copies `/p/<id>` (older `/?p=<id>` and `#/p/<id>` links still work). The page turns the link into the normal `#/p/<id>` view on load, and the server gives chat apps a preview card for it.
- Only posts a stranger could already see get a card: public account, visible to everyone, not held by the word filter, not expired, not auto-hidden by reports (`PostAccess.public_post()` in `masque/access.py`, the same rules as the feed). Anything else (friends-only, private account, held, hidden, deleted, missing) previews as the plain site card, so a preview never confirms that such a post exists.
- The card (`?ogp=<id>`, drawn in `masque/ogcard.py`, cached in `DATA_DIR/og/`) shows the author, the caption (short text of up to 4 words becomes big Pirata One poster text), the prompt question if there is one, the first photo, marks and comments counts, and the laughing-mask stamp on Masque posts. Masque and old anonymous posts show only the Masque name and picture, never the real account. Photos marked sensitive are not drawn (the card says "Sensitive photo hidden"). The card is redrawn when the caption, counts or photo change.

## Emoji and stickers in chat
- The smiley button on the right of the message box opens a panel with two tabs: Emoji (tap to insert into your message) and Stickers (tap to send at once). Works in direct and group chats.
- Stickers are not files. A sticker message is stored as the text `:stk:ID:` (about 10 bytes) and each browser draws the artwork itself, so stickers use no upload storage. The list is `STK` in `assets/app.js`; add a row `[id, emoji, caption, colour]` to add one, and never remove or rename old ids. Each sticker is a little drawn mask character (inline SVG made in the browser, nothing stored): its look is the matching entry in `SKD` (eyes `e`, mouth `m`, things behind `b` or in front `x` of the mask, optional mask colour `c`), built from the small parts in `skEyes`, `skMouth`, `skX` and `skBack`. A row with no `SKD` entry falls back to its emoji. Masque-only stickers: WHO?, REVEAL, SHHH, TWINS, PSST, SPOTLIGHT.
- Spam limits: the normal 40 messages per minute still applies, plus at most 10 stickers per 30 seconds per person (server side), and the picker waits 0.7 s after each sticker.

## Picture stickers and favorites
- In a chat, the smiley panel has three tabs: Emoji, Stickers and **★ Mine**. In Mine, **+ Add picture** takes any image. The browser shrinks it first (long side at most 256 px, WebP, 50 KB or less; Safari falls back to JPEG, or PNG for pictures with see-through parts, because it cannot write WebP), shows a preview with its size, and offers **Add to favorites** or **Add and send**. A **GIF** becomes an animated sticker: the browser decodes it itself (`gifRead` / `gifPaint` in `app.js`), keeps at most 3 seconds and 24 frames at about 160 px, encodes each frame as WebP and joins them into one animated WebP (`webpAnim`) of 150 KB or less. Browsers that cannot write WebP (Safari) and GIFs with one frame get a still picture, and the preview says so. Everyone can *see* animated stickers, whatever their browser.
- Every sticker tile (built-in or picture) has a ☆ button that adds or removes it from your favorites. Holding a sticker message in a chat opens **Add to my stickers** / **Remove from my stickers**, so you can keep one someone else sent. Favorites are stored on the server per account (table `stkfav`, refs `b:ID` for built-in and `i:ID` for picture, up to 100 with at most 60 pictures), so they appear in every chat and on every device.
- Storage: a picture is stored once as `DATA_DIR/stk/<id>.<ext>` and recorded in `stkimg` with its SHA-256, so uploading the same picture again (by anyone) reuses the file. A chat message stores only the text `:sti:<16 hex>:`, so sending a sticker a thousand times adds no files. Once a day (`StickerGcJob` in `masque/background.py`) files that nobody has as a favorite and that no message uses any more are deleted. Deleting an account removes its favorites; its pictures go in the next sweep if nothing else uses them.
- Server checks (`stkup`): picture bytes only (JPEG, PNG or WebP, detected from the first bytes), at most 80 KB (150 KB and 2 to 30 frames for an animated WebP) and 512x512 px, metadata stripped (same `clean_img` as photos). Limits: 10 uploads per hour (4 for new accounts), plus the 10 stickers per 30 seconds send limit that built-in stickers already had. Uploads pause when the disk has less than `MIN_FREE_MB` free, like chat attachments.
- Serving: `?stk=<id>` needs a signed-in session, is cached privately by the browser and is never cached by the service worker. The id is random, so only people who have seen the sticker (or saved it) can load it. Sticker pictures are not tied to who uploaded them.
- Not covered: stickers are not reportable on their own (report the person or the chat as usual); admins can remove a file by deleting its row in `stkimg` and the file in `DATA_DIR/stk/`.
- Service worker cache bumped to `mq-shell-72`.
- Photos and GIFs already in a chat: hold one (or right-click it) and choose **Save as sticker**. The picture is fetched, shrunk (a GIF stays animated where the browser can write WebP) and added to your favorites through the same preview as **+ Add picture**. Nothing new is stored when someone saves a picture that is already a sticker.
- Admin testing exceptions: admins are not held to the 7-day username / display name timer (the Edit profile fields are never locked for them, and the server already skipped the check), and the low-disk guard (`MIN_FREE_MB`) does not block their photo, audio or sticker uploads. Because admin status follows the username, renaming an admin account only keeps admin access if the new name is in `ADMIN_USERS`; the `ADMIN_USER` account still cannot be renamed.

- Smaller photos: photos in posts, chats and prompt answers are now shrunk in the browser to a WebP of about 500 KB (long side 1600 px), about a third smaller than the old ~1.2 MB JPEG. Browsers that cannot write WebP (Safari) send a JPEG of about 900 KB. Avatars and covers stay JPEG. Only one copy of each photo is kept: extra resized copies would use more disk, not less. Photos that are already stored are not changed.

## Unlockables
- Most avatar frames, avatar shapes, banner frames, background colors, patterns, the Glass card style and two fonts have to be earned. The single list is the catalogue in `masque/unlockables.py`: `[setting][id] = [stat, amount]`. Anything not listed is free (None, Circle, Squircle, Ring, Dashed, Glow, Match avatar, Line, seven colors, Grid, Dots, Notebook, Flat, Outlined and the other fonts).
- Stats (`unl_stats()`): posts, comments written, likes on your posts, accepted friends, best daily-prompt streak, days on Masque. The same list is sent to the app by `?a=unl`, which shows lock icons and what each option needs.
- Saving a theme (`profile`) runs `unl_gate()`: a locked option is refused with a message. Whatever a person already has equipped stays (grandfathered); they only need to unlock it to pick it again after switching away.
- Admins (ADMIN_USER / ADMIN_USERS) have everything unlocked, both in the picker and on the server.
- To change a requirement, edit the number in `unl_cat()` (the app reads it from the server, so nothing else needs changing).

## Limited-time theme: Castle Night
Nightfall background + Castle pattern + Bats avatar and banner frames. Anyone can pick it until `CASTLE_END` (Unix time, server variable; default 3 Nov 2026 00:00 UTC). Afterwards it cannot be picked any more, but people who already have it equipped keep it.


## Edit history on posts

When you edit a post and the text changes, the old text is kept (with the time that version went live) in the `pedits` table: newest 20 per post, text only, no photos. "(edited)" on a post is a button; tapping it opens an "Edit history" sheet with the current version and earlier ones, newest first (`?a=pedhist&id=`). Anyone who is allowed to see the post can open it (same check as comments, and held posts stay hidden). The author, or an admin, can remove all earlier versions with "Remove earlier versions" (`?a=pedclear`, admin use is written to the admin log), for example when something private was posted by mistake. Posts edited before this existed have no history, and an edit that only changed photos or settings adds none. Deleting a post deletes its history.

## "New posts" pill

On Home, a small pill ("3 new posts") appears under the top bar when people have posted since the feed you are looking at was loaded. The page asks every 30 s while the tab is visible, when you come back to the tab, and when you switch between Everyone / Friends / Following (`?a=feed&cnt=1&after=<newest id>`, which counts through the same privacy filters as the feed itself; capped at "20+"; your own posts are not counted). Tapping it scrolls to the top and reloads like pull-to-refresh, and the new posts slide in. Prompt answers are not counted, because Home does not list them one by one.

## Explore search

People, tags and a few matching posts show together as you type (`?a=find&tg=1`). People come first; start with `#` to put tags first. Tags match anywhere in the tag, with tags that start with your text first. A leading `@` is ignored, so `@sam` finds Sam. "Recent searches" remembers what you opened (a person, a tag) or searched for, on this device only (`mq_xrec:<name>` in localStorage, newest 8). Tap the x on a chip to forget just that one, or Clear for all. Older plain-text history is picked up until the first change.

## Push notifications

Settings, then Notifications, then "Push notifications" turns on alerts for that browser. They use the Web Push standard, so there is nothing to sign up for: the server makes its own signing key the first time it is needed and keeps it in the `site` table of the database (keep your data folder/volume, or people have to turn notifications on again). `SITE_URL` should be your https address, because some push services (Apple) want a real contact address in the signature. The text is always generic ("Someone commented on your post"), never a name. Mutes and quiet hours are respected. On iPhone it only works after Add to Home Screen.

Streak reminders: in the last 3 hours of a UTC day (21:00 to 24:00 UTC, when the daily prompt and streak day roll over), anyone with push on and a streak of 2 or more days who has not answered yet gets one generic push, "Your N-day streak ends in about 3 hours" (the hours count down if it is sent later). Quiet hours are respected: someone who is quiet is not marked as reminded, so they get it as soon as quiet hours end if the day is not over. People turn it off with "Streak reminders" in Settings, Notifications. The check (`StreakReminder` jobs in `masque/background.py`) runs on a timer inside `serve.py` at most once every 5 minutes, even on a quiet site, and `streakping` remembers who was already reminded that day.

## Mentions
Type `@` in a group chat, DM, post caption or comment to pick someone. In groups, `@name` (a member's name or their Masque's name) and `@everyone` send a notification (`@everyone` is limited to once per 5 minutes per person per group and skips people who muted the group).

## For you feed and post views

- Home has a new first tab, **For you**, and the old Everyone tab is now **Latest** (still newest first). Friends and Following are unchanged.
- **How For you is ordered** (`FeedRanker` in `masque/feed.py`): the 300 newest posts the person may see are scored. The score rewards what viewers did with a post (marks, comments, saves) compared with how many people saw it, and it fades with age (roughly halving every 8 to 10 hours). Ordinary public posts also get a boost for friends, people you follow and people whose posts you marked or commented on in the last 30 days. Posts you have already seen sink to a fifth of their score, your own posts sit a little lower, and the same author is spaced out. After the first 300 the list continues newest first. Time is rounded to 10 minutes so the order holds still while you scroll, and the app skips any post it has already shown.
- **Anonymity:** anonymous and Masque posts never get a friend, follow or favourite boost and are never spaced by author, so the order can not be used to work out who wrote one.
- If ranking ever fails on the server the tab falls back to newest first.
- **Views:** `postviews(pid, uid, ts)` holds one row per person per post (never your own posts). A feed card counts once about 60% of it has been on screen for a second, the live view counts after it has stayed open for about a second. The app sends sightings in small batches to `?a=view`. Only the number is shown (an eye and a count on the post bar and in the live view), never who looked. Guests are not counted.


## Design scale (keep new CSS on these)
After the v151 cleanup `assets/style.css` uses a small set of sizes. When you add or change styles, pick from these instead of inventing a new value:
- Small text sizes (rem): .6, .68, .72, .78, .85, .9, .95, 1, 1.05, 1.1. Bigger sizes are for headings and display text.
- Corner roundness (px): 2, 4, 6, 8, 10, 12, 14, 16, 20, 24, plus 999px for pills and 50% for circles.
- Main animation curve: `cubic-bezier(.16,1,.3,1)` (the `--ease` variable).


## Roles and management (added after the Python migration)
Three roles: **user**, **moderator** (users table `role=1`, set by an admin) and **admin** (`ADMIN_USER` / `ADMIN_USERS` on the server).

| Page (hash)        | Who            | What it does |
| ------------------ | -------------- | ------------ |
| `#/dash`           | everyone       | Your own numbers; moderators also see the queue and their recent actions; admins also see site totals |
| `#/r`              | staff          | Reports and appeals (moderators: suspend up to 30 days, no bans) |
| `#/aposts`         | staff          | List, search, edit, delete any post |
| `#/acomments`      | staff          | List, search, edit, delete any comment |
| `#/ausers`         | admins         | List with roles, search, filter, add, edit (nick, bio, privacy, role, password), delete accounts |

Actions (all in `masque/actions/manage.py`, prefixed `mg_`): `mg_dash`, `mg_ulist`, `mg_uget`, `mg_uadd`, `mg_uedit`, `mg_udel`, `mg_mposts`, `mg_mpedit`, `mg_mpdel`, `mg_mcomments`, `mg_mcedit`, `mg_mcdel`. Role actions in `masque/actions/admin.py`: `staff`, `setrole`.
Masques stay hidden: content written as a Masque is listed as "Masque", never counted toward a person, and the admin log names no owner for it.
`assets/app.min.js` is not shipped; run `./build.sh` to make it (the site serves `assets/app.js` until then).
