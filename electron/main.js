const { app, BrowserWindow, WebContentsView } = require('electron');

app.commandLine.appendSwitch('ozone-platform', 'x11');
app.commandLine.appendSwitch('gtk-version', '3');

const backendUrl = process.env.BACKEND_URL || 'http://localhost:8000';
const pollIntervalMs = Number(process.env.SESSIONS_POLL_INTERVAL_SECONDS || 60) * 1000;

let window;
let views = [];
let emptyView;
let renderedSessionKey = null;

function tileEmptyView() {
  if (!emptyView) return;
  const { width, height } = window.getBounds();
  emptyView.setBounds({ x: 0, y: 0, width, height });
}

function dismissCookiePopup(view) {
  view.webContents.executeJavaScript(`
    (() => {
      const selectors = [
        '#consent_blackbar',
        '.truste_overlay',
        '.truste_box_overlay',
        '.truste_cm_outerdiv',
        '.truste_popframe'
      ];
      const hide = () => selectors.forEach((selector) => {
        document.querySelectorAll(selector).forEach((element) => {
          element.style.setProperty('display', 'none', 'important');
          element.style.setProperty('visibility', 'hidden', 'important');
        });
      });
      hide();
      new MutationObserver(hide).observe(document.documentElement, {
        childList: true,
        subtree: true,
        attributes: true,
        attributeFilter: ['class', 'style']
      });
    })();
  `).catch((error) => console.error('Unable to dismiss cookie popup', error));
}

function tileViews() {
  const { width, height } = window.getBounds();
  const columns = Math.max(1, Math.ceil(Math.sqrt(views.length)));
  const rows = Math.max(1, Math.ceil(views.length / columns));
  const tileWidth = Math.floor(width / columns);
  const tileHeight = Math.floor(height / rows);

  views.forEach((view, index) => {
    const column = index % columns;
    const row = Math.floor(index / columns);
    view.setBounds({
      x: column * tileWidth,
      y: row * tileHeight,
      width: column === columns - 1 ? width - column * tileWidth : tileWidth,
      height: row === rows - 1 ? height - row * tileHeight : tileHeight,
    });
  });
}

async function refreshSessions() {
  const response = await fetch(`${backendUrl}/sessions`);
  if (!response.ok) throw new Error(`Session API returned ${response.status}`);
  const payload = await response.json();
  const sessions = payload.sessions || [];
  const sessionKey = JSON.stringify(
    sessions
      .map((session) => session.url)
      .sort((left, right) => left.localeCompare(right))
  );
  if (sessionKey === renderedSessionKey) return;
  renderedSessionKey = sessionKey;

  views.forEach((view) => window.contentView.removeChildView(view));
  views = [];
  if (emptyView) {
    window.contentView.removeChildView(emptyView);
    emptyView = undefined;
  }

  if (sessions.length === 0) {
    emptyView = new WebContentsView();
    window.contentView.addChildView(emptyView);
    emptyView.webContents.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent(`
      <!doctype html>
      <html>
        <body style="margin:0;display:grid;place-items:center;height:100vh;background:#111827;color:#f9fafb;font:32px sans-serif">
          No active sessions
        </body>
      </html>
    `)}`);
    tileEmptyView();
    return;
  }

  views = sessions.map((session) => {
    const view = new WebContentsView();
    window.contentView.addChildView(view);
    view.webContents.on('did-finish-load', () => dismissCookiePopup(view));
    view.webContents.loadURL(session.url);
    return view;
  });
  tileViews();
}

async function createWindow() {
  window = new BrowserWindow({
    fullscreen: true,
    kiosk: true,
    webPreferences: { sandbox: true },
  });
  await refreshSessions().catch((error) => console.error(error));
  setInterval(() => refreshSessions().catch((error) => console.error(error)), pollIntervalMs);
}

app.whenReady().then(createWindow);
app.on('window-all-closed', () => app.quit());
