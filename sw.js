const CACHE_NAME = 'digest-v2';
const STATIC_ASSETS = [
  './',
  './style.css',
  './manifest.json',
  './search.html'
];

// Install: cache static assets
self.addEventListener('install', event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

// Activate: clean old caches
self.addEventListener('activate', event => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(keys.filter(k => k !== CACHE_NAME).map(k => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Fetch: network-first for HTML (always get latest digest), cache-first for static assets
self.addEventListener('fetch', event => {
  const url = new URL(event.request.url);

  if (event.request.destination === 'document' || url.pathname.endsWith('/') || url.pathname.endsWith('.html')) {
    // Network-first for HTML — always try to get the latest digest
    event.respondWith(
      fetch(event.request)
        .then(response => {
          const clone = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(event.request, clone));
          return response;
        })
        .catch(() => caches.match(event.request))
    );
  } else {
    // Cache-first for static assets (CSS, icons, manifest)
    event.respondWith(
      caches.match(event.request).then(cached => cached || fetch(event.request))
    );
  }
});
