# Accounts, navigation and administration

The public site now has Home (`/`), About (`/about`) and Contact (`/contact`). Registration (`/register`) and login (`/login`) are public; leaf analysis is at `/portal` and requires an active account. Both the prediction upload and AI-readiness endpoint require authentication. Existing users can log in with their previous credentials.

Authenticated navigation includes My portal and a POST/CSRF-protected Logout action. Logout invalidates the session and clears previous prediction results. Passwords are hashed, sessions regenerate on authentication, credential failures use generic messages, and login/registration/contact requests are rate limited. Public registration cannot set admin or account-status flags. Suspended users are blocked at login and on subsequent protected requests from existing sessions. Protected responses are not cached.

## Administrator setup on Render Free

In the Render service's **Environment** section, set:

```dotenv
ADMIN_EMAIL=the-owners-real-email-address
ADMIN_PASSWORD=a-unique-secret-password-at-least-12-characters-long
ADMIN_NAME="Project administrator"
```

Replace both example values with the owner's chosen real email and unique password. Store the password only in Render's environment settings; do not commit it, send it in a URL or paste it into application logs. These are optional: omit both ADMIN_EMAIL and ADMIN_PASSWORD if no administrator is needed. Supplying only one, an invalid email or a password outside 12–128 characters causes startup to fail with a generic configuration error.

Deploy the feature branch. Startup runs additive migrations and `php artisan app:bootstrap-admin`. This creates or updates the configured administrator, makes it active, and hashes its password. It never prints the password. **Server configuration controls this account: each container startup reapplies its configured name and password.** Use the configured email/password at `/login`, then open **Admin** in the navigation. No shell or publicly accessible admin-creation route is needed.

Password provisioning also revokes older sessions for that account, so someone holding an earlier session cannot inherit newly granted administrator privileges. Administrator sessions need a fresh login after startup reapplies the configured password.

The accepted temporary SQLite setup still applies: replacing/spinning down the free container can reset ordinary accounts and contact messages. The configured administrator is recreated on startup. Persistent storage is needed if durable account/message retention becomes a requirement. Existing environment variables for SQLite and AI remain valid.

## Local setup

```powershell
php artisan migrate
```

Register a normal account in the browser. To promote a trusted existing active account:

```powershell
php artisan app:make-admin owner@example.com
```

Use that account's real email. The command fails if the account does not exist or is suspended. Alternatively, set the three ADMIN variables in the local `.env` and run `php artisan app:bootstrap-admin`. If local configuration was cached, clear/rebuild it after editing environment values.

## Dashboard and contact behavior

`/admin` is administrator-only. It shows paginated accounts, registered-account counts, unread-message counts and a contact inbox. Administrators can suspend/reactivate ordinary users and mark messages read. Administrator accounts are protected from suspension through this dashboard. It does not delete users, expose passwords or allow users to grant their own roles.

The contact form saves validated messages in SQLite for the administrator; it does not send email. Message text is escaped in the inbox. The site does not advertise invented contact addresses or promise emailed replies. There is no password-reset or email-verification delivery integration in this change; those would require a configured mail service and separate workflows.

The inference model, its preprocessing and its weights are unchanged. Registration does not train the model or save a diagnosis history. Public `/healthz` and `/up` remain available for deployment probes.

## Verification

27 Laravel tests passed (143 assertions), covering access control, registration, login, logout, rate limiting, administrator privileges, account suspension, escaped/private inbox messages, server provisioning and stale-session revocation. Production assets built and Blade views compiled successfully. Isolated Chrome checks exercised real forms/cookies, contact submission, admin controls and five mobile page layouts without page errors.

[Linux Docker verification](https://github.com/nahsir12390/crop-disease-detection/actions/runs/44147700690) passed for commit `71745f6`, including real registration, authenticated image submission through Laravel to MobileNetV2, and SQLite/key preservation using a test volume. Both the standard check and the separate 512 MiB/0.1 CPU check passed. The test volume does not imply persistence on the free Render configuration. This is container verification; deploy the updated branch and check the public HTTPS site separately.
