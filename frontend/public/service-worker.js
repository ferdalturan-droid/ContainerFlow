const CACHE_NAME = 'containerflow-pwa-v3';
const STATIC_CACHE = 'containerflow-static-v3';
const DATA_CACHE = 'containerflow-data-v3';
const OFFLINE_QUEUE_KEY = 'ilk-offline-queue';

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

  // Skip non-GET requests (except for offline queue)
  if (request.method !== 'GET') {
    // For POST/PUT/DELETE - try network, if offline queue it
    if (request.method === 'POST' || request.method === 'PUT') {
      event.respondWith(
        fetch(request.clone()).catch(async () => {
          // Only queue API requests
          if (url.pathname.startsWith('/api/')) {
            const body = await request.clone().text();
            const queueItem = {
              url: request.url,
              method: request.method,
              headers: Object.fromEntries(request.headers.entries()),
              body: body,
              timestamp: Date.now()
            };
            // Store in IndexedDB via message to client
            const clients = await self.clients.matchAll();
            clients.forEach(client => {
              client.postMessage({ type: 'OFFLINE_QUEUE_ADD', data: queueItem });
            });
          }
          return new Response(JSON.stringify({ offline: true, queued: true }), {
            status: 200,
            headers: { 'Content-Type': 'application/json' }
          });
        })
      );
    }
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
          return caches.match(request).then((cached) => {
            if (cached) return cached;
            // Return offline fallback for API
            return new Response(JSON.stringify({ offline: true, message: 'Offline - viser cached data' }), {
              status: 200,
              headers: { 'Content-Type': 'application/json' }
            });
          });
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
