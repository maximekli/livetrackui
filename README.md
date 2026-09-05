# LiveTrackUI

A lightweight dashboard for displaying active Garmin LiveTrack sessions in a tiled layout.

The system monitors an IMAP mailbox for Garmin LiveTrack notification emails, extracts a LiveTrack URL from each message, verifies whether each session is still active, and exposes only active sessions to an Electron display client.

Electron loads Garmin's own LiveTrack interface directly and arranges multiple sessions in a tiled layout.

## Architecture

```text
                         ┌────────────────┐
                         │  IMAP mailbox  │
                         │                │
                         │ Garmin emails  │
                         └───────┬────────┘
                                 │
                                 │ IMAP
                                 ▼
┌────────────────────────────────────────────────────────┐
│                       Backend                          │
│                                                        │
│  ┌──────────────┐    ┌──────────────┐                 │
│  │ IMAP reader  │───▶│ Email parser │                 │
│  └──────────────┘    └──────┬───────┘                 │
│                             │                          │
│                             ▼                          │
│                    ┌─────────────────┐                 │
│                    │ Session state   │◀── state.json   │
│                    └────────┬────────┘                 │
│                             │                          │
│                             ▼                          │
│                    ┌─────────────────┐                 │
│                    │    Playwright   │                 │
│                    │                 │                 │
│                    │ Garmin page     │                 │
│                    │ active / retry / ended            │
│                    └────────┬────────┘                 │
│                             │                          │
│                             ▼                          │
│                    ┌─────────────────┐                 │
│                    │   HTTP API      │                 │
│                    │ active sessions │                 │
│                    └────────┬────────┘                 │
└─────────────────────────────┼──────────────────────────┘
                              │
                              │ HTTP
                              ▼
                    ┌────────────────────┐
                    │ Electron display   │
                    │                    │
                    │ ┌────────┬───────┐ │
                    │ │ Garmin │ Garmin│ │
                    │ │   A    │   B   │ │
                    │ ├────────┼───────┤ │
                    │ │ Garmin │ Garmin│ │
                    │ │   C    │   D   │ │
                    │ └────────┴───────┘ │
                    └────────────────────┘
```

## Components

### Backend

The backend runs as a Docker container.

Responsibilities:

* Connect to an IMAP mailbox.
* Process Garmin LiveTrack notification emails.
* Extract the LiveTrack URL.
* Maintain the current session state.
* Check LiveTrack URLs to determine whether sessions have ended.
* Expose only active sessions through an HTTP API.

The backend is the authority for session state.

### Electron display client

The Electron application runs on the machine connected to the display.

Responsibilities:

* Fetch the active session list from the backend.
* Create and remove LiveTrack views as the session list changes.
* Load Garmin LiveTrack URLs.
* Arrange sessions in a tiled/grid layout.
* Run in fullscreen/kiosk mode.

Electron does not determine whether a session is active or expired.

## Session model

The session representation is deliberately minimal.

The LiveTrack URL is the unique identifier for a session. The backend extracts only the URL from the Garmin notification email.

```json
{
  "sessions": [
    {
      "url": "https://livetrack.garmin.com/session/527787cb-3b82-8e5c-b615-604efbe0aa00/token/..."
    }
  ]
}
```

The backend does not attempt to extract or interpret any other Garmin data.

The API exposes the same minimal representation, containing only sessions that are currently active.

Internally, each session also has a lifecycle state:

* `active`: a visible Garmin map container is present and no visible ended-session marker is present.
* `unavailable`: validation failed for a temporary or ambiguous reason. The session is retained and retried, but is not exposed by the API.
* `ended`: Garmin explicitly reported that the session has ended. The session is removed and is not retried.

## Session lifecycle

```text
Garmin activity starts
        │
        ▼
Garmin notification email
        │
        ▼
IMAP reader
        │
        ▼
Extract URL
        │
        ▼
Session added to state
        │
        ▼
      Check LiveTrack page
            │
        ┌────┼─────────────┐
        │    │             │
      active unavailable  ended
        │    │             │
        ▼    ▼             ▼
      expose retry        remove
        │    │
        └────┘
            │
            ▼
      Expose active sessions through /sessions
        │
        ▼
Electron displays tile
```

Sessions are periodically checked against Garmin at a configurable interval. The current example configuration uses 60 seconds.

Validation continues for every session until Garmin explicitly reports that it has ended. A session that cannot be validated because of a timeout, network failure, browser failure, server error, or ambiguous page remains a retry candidate but is hidden from `/sessions`. Only an explicit ended state removes the session permanently.

## Garmin session validation

A plain HTTP request is not sufficient because the LiveTrack page is a JavaScript application.

The backend therefore uses **Playwright** with a headless Chromium browser to load the LiveTrack page.

Conceptually:

```python
page.goto(url, wait_until="domcontentloaded")

ended = page.locator(
  '[data-tid="session_complete_banner"], [class*="session-ended-view_container"]'
)
if await effectively_visible(ended):
    session_is_expired()

map_container = page.locator(".leaflet-container")
if await effectively_visible(map_container):
    session_is_active()
```

The backend does not parse Garmin's map, statistics, or other LiveTrack information. It uses the rendered page only to distinguish an explicit ended state from a successfully rendered active state. Detection checks visibility, not merely element existence, because ended markers can be present but hidden in the DOM. Visibility includes ancestor styles (`opacity`, `display`, and `visibility`) and non-zero dimensions.

The validator does not depend on English wording. It uses Garmin's semantic `data-tid="session_complete_banner"` marker and the current `.session-ended-view_container` structure, so localized ended messages remain supported. The page is loaded with `domcontentloaded`, then given a short readiness window for an ended marker or map. An unavailable, malformed, or ambiguous page is treated as temporarily unavailable rather than ended.

Session validation runs periodically rather than requiring Electron to monitor the Garmin page.

## Persistence

The backend uses a small JSON file for persistent state.

Example:

```json
{
  "imap_uidvalidity": 123,
  "last_imap_uid": 12345,
  "sessions": [
    {
      "url": "https://livetrack.garmin.com/session/527787cb-3b82-8e5c-b615-604efbe0aa00/token/...",
      "state": "active"
    }
  ]
}
```

The state file is stored in the Compose bind mount `./livetrack_data/state.json`, allowing the backend to restart without reconstructing its state from the entire mailbox.

The IMAP `UID` of the last processed message and the mailbox `UIDVALIDITY` are persisted so that subsequent starts can continue processing only new messages. UIDs are valid only within one UID namespace. A provider may change `UIDVALIDITY` after mailbox recreation, migration, or restoration. When it changes, the backend resets the UID checkpoint and rescans the selected folder, deduplicating sessions by URL.

The IMAP reader searches the selected folder with `FROM <IMAP_SENDER>`, so it only fetches messages from the configured sender. It verifies the exact lowercased `From` address again after fetching and skips any mismatch before parsing. Fetches use `BODY.PEEK[]`, so they do not mark messages as read. Because some providers may ignore a UID range when combined with other search keys, returned UIDs are filtered locally before fetching. Messages are processed in increasing UID order, and each fetched UID is persisted before parsing or session handling so a callback failure cannot cause the message to be processed again. The checkpoint advances for malformed messages too, after logging and dropping them, so one bad message cannot block processing forever.

State files are written atomically using a temporary file followed by a rename. The state directory is created with permissions `0755` and `state.json` with permissions `0644`, so the file can be read from the host outside the container.

### Startup

On startup:

1. Load the persisted state.
2. Resume processing from the stored IMAP position.
3. Validate persisted sessions against Garmin.
4. Remove sessions that Garmin explicitly reports as ended.
5. Keep temporarily unavailable sessions for retry while hiding them from the API.
6. Continue monitoring the mailbox for new notifications.

The mailbox is therefore not treated as the application's database.

## When to use a database

A database is deliberately not used initially.

JSON is sufficient while the application only needs to maintain:

* The current LiveTrack sessions.
* The last processed IMAP position.

SQLite becomes appropriate if the application later needs persistent historical or queryable data, such as:

* Activity history.
* Historical statistics.
* Previous sessions.
* More complex relationships.
* Multiple independent configuration records.
* Transactional or concurrent state updates.

Until such requirements exist, SQLite would add complexity without providing a meaningful benefit.

## Email integration

The email provider is deliberately independent of the application.

Any provider offering IMAP access can be used.

The backend requires:

* IMAP server.
* IMAP port/security settings.
* Mailbox username.
* Mailbox password or application-specific credential.

The application only receives email. It does not send email.

Garmin-specific parsing is isolated from the generic IMAP handling.

The monitored folder and sender are configurable. The defaults are `INBOX` and the single case-insensitive sender address `noreply@garmin.com`.

## Garmin email parsing

Garmin LiveTrack notification emails contain a link similar to:

```text
https://livetrack.garmin.com/session/<session-id>/token/<token>
```

The email parser extracts:

* The LiveTrack URL.

No other Garmin information is parsed.

The parser supports multipart messages and uses the HTML and plain-text parts as available. A message is malformed when it does not contain a valid LiveTrack URL. It does not parse or store the athlete's name. Malformed messages are dropped and logged with their sender, subject, and date. The complete URL is not required in the log, but may be logged when useful because the deployment is intended for a trusted local network.

When the same URL appears more than once, the data from the newest message replaces the previous association. Newest means the greatest IMAP UID, which represents mailbox arrival order more reliably than the email `Date` header.

## API

### `GET /sessions`

Returns the currently active LiveTrack sessions.

Example:

```json
{
  "sessions": [
    {
      "url": "https://livetrack.garmin.com/session/abc123.../token/..."
    },
    {
      "url": "https://livetrack.garmin.com/session/efg456.../token/..."
    }
  ]
}
```

Expired sessions are not returned.

The URL is the session identifier. No separate ID is maintained.

The Electron client therefore has a deliberately simple contract:

```text
GET /sessions
       │
       ▼
active LiveTrack URLs
       │
       ▼
display them
```

Electron polls this endpoint at a configurable interval, defaulting to 60 seconds in code. It displays sessions in the order returned by the API and tiles them without reordering. It keeps existing Garmin views when the session URL list is unchanged, so polling does not reload already displayed pages. When the list is empty, it shows `No active sessions`. Electron does not validate session state or interpret Garmin's ended page.

### `GET /electron/download`

Returns the packaged Electron application as a file download. This endpoint is intended for clients on the trusted local network that need to install or update the display application.

The Electron application is built and packaged for Linux while the Docker image is built. The resulting artifact is included in the image and served by the backend from the path configured by `ELECTRON_ARTIFACT_PATH`. The response uses the artifact filename in `Content-Disposition` and its detected content type. If the artifact is not available, the endpoint returns an error rather than an incomplete download.

The endpoint has no authentication. The application is intended for local use only and does not provide application-level security controls.

## Configuration

Deployment configuration is supplied through environment variables in `compose.yaml`. The application is intended for local use only; it does not provide authentication, authorization, encryption, or other application-level security controls. Keep the backend and display client on a trusted local network.

Backend variables:

```text
IMAP_HOST
IMAP_PORT=993
IMAP_USE_SSL=true
IMAP_USERNAME
IMAP_PASSWORD
IMAP_FOLDER=INBOX
IMAP_SENDER=noreply@garmin.com
IMAP_POLL_INTERVAL_SECONDS=60
VALIDATION_INTERVAL_SECONDS=60
PLAYWRIGHT_TIMEOUT_SECONDS=30
STATE_FILE=/data/state.json
ELECTRON_ARTIFACT_PATH=/opt/livetrackui/electron/dist/LiveTrackUI.AppImage
```

Electron variables can be supplied through the environment of the display process:

```text
BACKEND_URL=http://localhost:8000
SESSIONS_POLL_INTERVAL_SECONDS=60
```

Intervals are independent: the backend can discover emails and validate sessions at different rates, while Electron independently refreshes the displayed active list.

The Linux AppImage can be downloaded and started with:

```bash
curl -fL http://localhost:8000/electron/download -o LiveTrackUI.AppImage
chmod +x LiveTrackUI.AppImage
./LiveTrackUI.AppImage
```

Electron forces the X11 and GTK3 backends for compatibility with some Wayland/GNOME environments. The display client also hides Garmin/TrustArc cookie-consent overlays in each LiveTrack view.

## Technology choices

### Backend

**Python + FastAPI**

Chosen for:

* Small implementation footprint.
* Simple HTTP API.
* Good IMAP/email parsing ecosystem.
* Straightforward background processing.
* Easy Docker deployment.

### Email

**IMAP**

The application uses a generic IMAP-compatible mailbox and does not depend on a particular email provider.

### Garmin validation

**Playwright + Chromium**

Used by the backend to render LiveTrack pages and determine whether a session has ended.

The browser is headless and is not used to display the application.

### Display

**Electron**

Electron provides the Chromium environment required to display multiple independent Garmin LiveTrack pages.

Each session is represented by a `WebContentsView`.

### Persistence

**JSON file**

Used for minimal persistent state.

No database is required initially.

### Deployment

**Docker**

The backend runs as a Docker container. Building the image also installs the Electron dependencies and packages the Linux Electron application. The packaged artifact is copied into the final image and is available through `/electron/download`.

The runtime volume contains configuration and `state.json`; it does not contain the Electron artifact. Publishing a new Electron version therefore requires rebuilding and redeploying the Docker image.

The Electron application runs separately on the display machine.

## Security and intended use

This project is intended for local use only. Nothing is implemented specifically to secure the application: there is no authentication, authorization, TLS configuration, access control, or network isolation provided by the application itself.

Deploy it only on a trusted local network and do not expose the backend or its download endpoint directly to the internet. The operator is responsible for the network, host, Docker, and credential configuration.

LiveTrack URLs are not treated as secrets by this application. They identify shared LiveTrack pages, but the pages expose location and activity information. Avoid publishing URLs, logs, screenshots, or API responses outside the intended audience, and keep IMAP credentials outside source control.

## Project structure

```text
livetrackui/
├── server/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
│       ├── main.py
│       ├── imap_reader.py
│       ├── parser.py
│       ├── garmin.py
│       ├── models.py
│       ├── state.py
│       └── config.py
│
├── electron/
│   ├── package.json
│   ├── package-lock.json
│   └── main.js
│
├── livetrack_data/              # Docker bind-mounted state directory
│   └── state.json
│
├── compose.yaml
└── README.md
```

## Design principles

1. **Keep the system small.**
2. **Use IMAP as the source of incoming LiveTrack events.**
3. **Parse only the LiveTrack URL from emails.**
4. **Use the Garmin page only to determine whether a session has ended.**
5. **Keep session state in the backend.**
6. **Expose only active sessions to Electron.**
7. **Keep Electron focused exclusively on display.**
8. **Do not reimplement Garmin's UI.**
9. **Use a JSON state file instead of a database.**
10. **Treat LiveTrack URLs as location-sharing data and protect IMAP credentials.**
