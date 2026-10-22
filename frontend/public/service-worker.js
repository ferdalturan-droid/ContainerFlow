// v4 (2026-10-22): Ingen falske "OK"-svar længere. Når serveren ikke svarer,
// får appen en rigtig fejl (503), så login, start af ture osv. kan sige
// "Ingen forbindelse" - og appens egen kø (tourOpQueue) gemmer chaufførens
// handlinger. Før svarede vi 200 {offline: true}, og login brød sammen med
// "Cannot read properties of undefined (reading 'name')".
const CACHE_NAME = 'containerflow-pwa-v4';
const STATIC_CACHE = 'containerflow-static-v4';
const DATA_CACHE = 'containerflow-data-v4';
const OFFLINE_DETAIL = 'Ingen forbindelse til serveren. Prøv igen om lidt.';

const offlineResponse = () => new Response(JSON.stringify({ offline: true, detail: OFFLINE_DETAIL }), {
  status: 503,
  headers: { 'Content-Type': 'application/json' }
});

// Core static assets to precache
const PRECACHE_URLS = [
  '/',
  '/index.html',
  '/manifest.json',
  '/icon-192.png',
  '/icon-512.png'
];

// Install: precache core assets
self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(STATIC_CACHE).then((cache) => {
      return cache.addAll(PRECACHE_URLS);
    }).then(() => self.skipWaiting())
  );
});

// Activate: clean old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((cacheNames) => {
      return Promise.all(
        cacheNames
          .filter((name) => name !== STATIC_CACHE && name !== DATA_CACHE && name !== CACHE_NAME)
          .map((name) => caches.delete(name))
      );
    }).then(() => self.clients.claim())
  );
});

// Fetch strategy
self.addEventListener('fetch', (event) => {
  const { request } = event;
  const url = new URL(request.url);

  // POST/PUT/DELETE går altid direkte til serveren. Uden forbindelse: en rigtig
  // fejl (503) - aldrig et falsk "OK".
  if (request.method !== 'GET') {
    if (url.pathname.startsWith('/api/')) {
      event.respondWith(fetch(request).catch(() => offlineResponse()));
    }
    return;
  }

  // Login/bruger må aldrig komme fra cachen (en anden bruger kan have været
  // logget ind på samme enhed).
  if (url.pathname.startsWith('/api/auth/')) {
    event.respondWith(fetch(request).catch(() => offlineResponse()));
    return;
  }

  // API requests: Network-first, fallback to cache
  if (url.pathname.startsWith('/api/')) {
    event.respondWith(
      fetch(request)
        .then((response) => {
          // Clone and cache successful API responses
          if (response.ok) {
            const responseClone = response.clone();
            caches.open(DATA_CACHE).then((cache) => {
              cache.put(request, responseClone);
            });
          }
          return response;
        })
        .catch(() => {
          // Network failed, try cache
          return caches.match(request).then((cached) => cached || offlineResponse());
        })
    );
    return;
  }

  // Static assets: Network-first for JS/CSS (avoid stale code), cache-first for images/fonts
  if (
    url.pathname.match(/\.(js|css)$/)
  ) {
    event.respondWith(
      fetch(request).then((response) => {
        if (response.ok) {
          const responseClone = response.clone();
          caches.open(STATIC_CACHE).then((cache) => {
            cache.put(request, responseClone);
          });
        }
        return response;
      }).catch(() => {
        return caches.match(request).then((cached) => {
          if (cached) return cached;
          return new Response('Offline', { status: 503 });
        });
      })
    );
    return;
  }

  if (
    url.pathname.match(/\.(png|jpg|jpeg|svg|ico|woff|woff2|ttf)$/) ||
    url.hostname === 'fonts.googleapis.com' ||
    url.hostname === 'fonts.gstatic.com'
  ) {
    event.respondWith(
      caches.match(request).then((cached) => {
        if (cached) return cached;
        return fetch(request).then((response) => {
          if (response.ok) {
            const responseClone = response.clone();
            caches.open(STATIC_CACHE).then((cache) => {
              cache.put(request, responseClone);
            });
          }
          return response;
        });
      })
    );
    return;
  }

  // HTML pages: Network-first, fallback to cache, then offline page
  event.respondWith(
    fetch(request)
      .then((response) => {
        if (response.ok) {
          const responseClone = response.clone();
          caches.open(STATIC_CACHE).then((cache) => {
            cache.put(request, responseClone);
          });
        }
        return response;
      })
      .catch(() => {
        return caches.match(request).then((cached) => {
          return cached || caches.match('/');
        });
      })
  );
});

// Background Sync
self.addEventListener('sync', (event) => {
  if (event.tag === 'sync-offline-queue') {
    event.waitUntil(syncOfflineQueue());
  }
});

async function syncOfflineQueue() {
  const clients = await self.clients.matchAll();
  clients.forEach(client => {
    client.postMessage({ type: 'SYNC_OFFLINE_QUEUE' });
  });
}

// Push Notifications
self.addEventListener('push', (event) => {
  let data = { title: 'ContainerFlow', body: 'Ny besked', icon: '/icon-192.png' };
  
  if (event.data) {
    try {
      data = event.data.json();
    } catch (e) {
      data.body = event.data.text();
    }
  }

  const options = {
    body: data.body || 'Ny besked',
    icon: '/icon-192.png',
    badge: '/icon-192.png',
    vibrate: [200, 100, 200],
    data: data.url || '/',
    actions: data.actions || [],
    // 2026-10-17: Samme tur/tråd erstatter den forrige notifikation.
    tag: data.tag || undefined,
    renotify: !!data.tag
  };

  event.waitUntil(
    self.registration.showNotification(data.title || 'ContainerFlow', options)
  );
});

// Notification click
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      if (clientList.length > 0) {
        return clientList[0].focus();
      }
      return self.clients.openWindow(event.notification.data || '/');
    })
  );
});
