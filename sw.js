/**
 * sw.js — LiftLog Service Worker
 * Cache First para assets de la app shell.
 * Los datos viven en IndexedDB, no en cache.
 */

const CACHE_NAME = "liftlog-v1";
const APP_SHELL  = [
    "./index.html",
    "./manifest.json",
    "./sw.js",
    "./icon-192.svg",
    "./icon-512.svg",
];

// Instalación: cachear app shell completa
self.addEventListener("install", (event) => {
    event.waitUntil(
        caches
            .open(CACHE_NAME)
            .then((cache) => cache.addAll(APP_SHELL))
            .then(() => self.skipWaiting())
    );
});

// Activación: limpiar caches anteriores
self.addEventListener("activate", (event) => {
    event.waitUntil(
        caches
            .keys()
            .then((keys) =>
                Promise.all(
                    keys
                        .filter((k) => k !== CACHE_NAME)
                        .map((k) => caches.delete(k))
                )
            )
            .then(() => self.clients.claim())
    );
});

// Fetch: Cache First → si no está en cache, intentar red
self.addEventListener("fetch", (event) => {
    if (!event.request.url.startsWith(self.location.origin)) return;

    event.respondWith(
        caches.match(event.request).then((cached) => {
            if (cached) return cached;
            return fetch(event.request).then((response) => {
                if (response && response.status === 200) {
                    const clone = response.clone();
                    caches
                        .open(CACHE_NAME)
                        .then((cache) => cache.put(event.request, clone));
                }
                return response;
            });
        })
    );
});