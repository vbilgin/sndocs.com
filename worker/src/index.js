const SECURITY_HEADERS = {
  "Content-Security-Policy-Report-Only":
    "default-src 'self'; img-src 'self' data: https:; style-src 'self' 'unsafe-inline'; " +
    "script-src 'self' 'unsafe-inline'; font-src 'self' data:; connect-src 'self'; " +
    "frame-ancestors 'self'; base-uri 'self'; object-src 'none'",
  "Permissions-Policy": "camera=(), geolocation=(), microphone=()",
  "Referrer-Policy": "strict-origin-when-cross-origin",
  "X-Content-Type-Options": "nosniff",
  "X-Frame-Options": "SAMEORIGIN",
};

const MIME_TYPES = {
  ".css": "text/css; charset=utf-8",
  ".eot": "application/vnd.ms-fontobject",
  ".html": "text/html; charset=utf-8",
  ".ico": "image/x-icon",
  ".jpeg": "image/jpeg",
  ".jpg": "image/jpeg",
  ".js": "text/javascript; charset=utf-8",
  ".json": "application/json; charset=utf-8",
  ".map": "application/json; charset=utf-8",
  ".mjs": "text/javascript; charset=utf-8",
  ".otf": "font/otf",
  ".pdf": "application/pdf",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".txt": "text/plain; charset=utf-8",
  ".ttf": "font/ttf",
  ".wasm": "application/wasm",
  ".webp": "image/webp",
  ".woff": "font/woff",
  ".woff2": "font/woff2",
  ".xml": "application/xml; charset=utf-8",
};
const manifestPromises = new Map();

function secure(response, env, releaseId) {
  const result = new Response(response.body, response);
  for (const [name, value] of Object.entries(SECURITY_HEADERS)) {
    result.headers.set(name, value);
  }
  result.headers.set("X-Sndocs-Release", releaseId || "unavailable");
  if (env.DEPLOYMENT_MODE === "preview") {
    result.headers.set("X-Robots-Tag", "noindex, nofollow");
  }
  return result;
}

function errorResponse(status, message, env, releaseId, extra = {}) {
  const headers = new Headers({
    "Content-Type": "text/plain; charset=utf-8",
    ...extra,
  });
  return secure(new Response(message, { status, headers }), env, releaseId);
}

async function readJson(bucket, key) {
  const object = await bucket.get(key);
  if (!object) {
    throw new Error(`required release object is missing: ${key}`);
  }
  try {
    return await object.json();
  } catch {
    return JSON.parse(await object.text());
  }
}

async function resolveRelease(env) {
  let releaseId = env.RELEASE_ID;
  if (env.DEPLOYMENT_MODE === "preview") {
    const pointer = await readJson(env.SITE_BUCKET, "pointers/preview.json");
    releaseId = pointer.release_id;
  }
  if (!/^[0-9a-f]{64}$/.test(releaseId || "")) {
    throw new Error("release ID is not configured");
  }
  const manifest = await loadReleaseManifest(env, releaseId);
  if (!validManifest(manifest, releaseId)) {
    throw new Error("release manifest is inconsistent");
  }
  return { releaseId, manifest };
}

async function loadReleaseManifest(env, releaseId) {
  if (manifestPromises.has(releaseId)) {
    return manifestPromises.get(releaseId);
  }
  const promise = (async () => {
    const cache = cacheApi(env);
    const cacheKey = new Request(
      `https://cache.sndocs.invalid/manifests/${releaseId}`,
    );
    if (cache) {
      const cached = await cache.match(cacheKey);
      if (cached) {
        return cached.json();
      }
    }
    const manifest = await readJson(
      env.SITE_BUCKET,
      `releases/${releaseId}.json`,
    );
    if (cache) {
      await cache.put(
        cacheKey,
        new Response(JSON.stringify(manifest), {
          headers: {
            "Content-Type": "application/json",
            "Cache-Control": "public, max-age=31536000, immutable",
          },
        }),
      );
    }
    return manifest;
  })();
  manifestPromises.set(releaseId, promise);
  try {
    return await promise;
  } catch (error) {
    manifestPromises.delete(releaseId);
    throw error;
  }
}

function validManifest(manifest, releaseId) {
  if (
    manifest.schema_version !== 1 ||
    manifest.release_id !== releaseId ||
    manifest.root_prefix !== `releases/${releaseId}/root` ||
    !manifest.families?.[manifest.latest]
  ) {
    return false;
  }
  for (const [family, record] of Object.entries(manifest.families)) {
    if (
      record.family !== family ||
      !/^[a-z0-9][a-z0-9-]*$/.test(family) ||
      !new RegExp(`^content/${family}/[0-9a-f]{64}$`).test(record.prefix) ||
      record.archived !== (family !== manifest.latest)
    ) {
      return false;
    }
  }
  return true;
}

function routeFor(pathname, manifest) {
  let decoded;
  try {
    decoded = decodeURIComponent(pathname);
  } catch {
    return { error: 400 };
  }
  if (decoded.includes("\0") || decoded.split("/").includes("..")) {
    return { error: 400 };
  }
  if (decoded === "/") {
    return {
      key: `${manifest.root_prefix}/index.html`,
      root: true,
      trailing: true,
    };
  }
  const relative = decoded.replace(/^\/+/, "");
  const parts = relative.split("/");
  const family = parts[0];
  const familyRecord = manifest.families[family];
  if (familyRecord) {
    const remainder = parts.slice(1).join("/");
    const trailing = decoded.endsWith("/");
    let key = familyRecord.prefix;
    if (trailing) {
      key = `${familyRecord.prefix}/${remainder}index.html`;
    } else if (remainder) {
      key = `${familyRecord.prefix}/${remainder}`;
    }
    return {
      family,
      key,
      prefix: familyRecord.prefix,
      trailing,
      publicPath: decoded,
    };
  }
  const trailing = decoded.endsWith("/");
  return {
    key: `${manifest.root_prefix}/${trailing ? `${relative}index.html` : relative}`,
    root: true,
    trailing,
    publicPath: decoded,
  };
}

function extension(path) {
  const name = path.split("/").at(-1);
  const index = name.lastIndexOf(".");
  return index > 0 ? name.slice(index).toLowerCase() : "";
}

function contentTypeFor(key) {
  return MIME_TYPES[extension(key)] || "application/octet-stream";
}

function cacheControl(root) {
  return root
    ? "public, max-age=60, s-maxage=300"
    : "public, max-age=300, s-maxage=31536000";
}

function objectHeaders(object, key, root, status = 200) {
  const headers = new Headers();
  object.writeHttpMetadata?.(headers);
  const knownType = MIME_TYPES[extension(key)];
  if (knownType) {
    headers.set("Content-Type", knownType);
  } else if (!headers.has("Content-Type")) {
    headers.set("Content-Type", "application/octet-stream");
  }
  if (object.httpEtag) {
    headers.set("ETag", object.httpEtag);
  }
  if (object.uploaded) {
    headers.set("Last-Modified", object.uploaded.toUTCString());
  }
  headers.set("Accept-Ranges", "bytes");
  headers.set("Cache-Control", cacheControl(root));
  if (status === 206 && object.range) {
    const offset = object.range.offset || 0;
    const length = object.range.length || object.size;
    headers.set(
      "Content-Range",
      `bytes ${offset}-${offset + length - 1}/${object.size}`,
    );
    headers.set("Content-Length", String(length));
  } else if (object.size !== undefined) {
    headers.set("Content-Length", String(object.size));
  }
  return headers;
}

async function directoryRedirect(request, env, route) {
  if (
    route.trailing ||
    route.publicPath.endsWith("/") ||
    extension(route.publicPath)
  ) {
    return null;
  }
  const index = await env.SITE_BUCKET.head(`${route.key}/index.html`);
  if (!index) {
    return null;
  }
  const url = new URL(request.url);
  url.pathname = `${url.pathname}/`;
  return new Response(null, {
    status: 308,
    headers: { Location: url.toString(), "Cache-Control": "public, max-age=300" },
  });
}

async function nearest404(env, manifest, route) {
  const key = route.family
    ? `${manifest.families[route.family].prefix}/404.html`
    : `${manifest.root_prefix}/404.html`;
  return { key, object: await env.SITE_BUCKET.get(key) };
}

function cacheApi(env) {
  if (env.EDGE_CACHE) {
    return env.EDGE_CACHE;
  }
  return globalThis.caches?.default;
}

function canUseCache(request) {
  return (
    request.method === "GET" &&
    !request.headers.has("Range") &&
    !request.headers.has("If-None-Match") &&
    !request.headers.has("If-Modified-Since")
  );
}

async function serve(request, env, context, releaseId, manifest, route) {
  const cache = cacheApi(env);
  const cacheKey = new Request(
    `https://cache.sndocs.invalid/${releaseId}/${encodeURIComponent(route.key)}`,
  );
  if (cache && canUseCache(request)) {
    const cached = await cache.match(cacheKey);
    if (cached) {
      return secure(cached, env, releaseId);
    }
  }

  if (request.method === "HEAD") {
    const object = await env.SITE_BUCKET.head(route.key);
    if (object) {
      const requestedEtag = request.headers.get("If-None-Match");
      if (requestedEtag && requestedEtag === object.httpEtag) {
        return secure(
          new Response(null, {
            status: 304,
            headers: objectHeaders(object, route.key, route.root),
          }),
          env,
          releaseId,
        );
      }
      return secure(
        new Response(null, {
          status: 200,
          headers: objectHeaders(object, route.key, route.root),
        }),
        env,
        releaseId,
      );
    }
  } else {
    const options = {};
    if (request.headers.has("Range")) {
      options.range = request.headers;
    }
    if (
      request.headers.has("If-None-Match") ||
      request.headers.has("If-Match") ||
      request.headers.has("If-Modified-Since") ||
      request.headers.has("If-Unmodified-Since")
    ) {
      options.onlyIf = request.headers;
    }
    const object = await env.SITE_BUCKET.get(route.key, options);
    if (object) {
      if (object.body === undefined) {
        const matched = request.headers.has("If-None-Match");
        return secure(
          new Response(null, {
            status: matched ? 304 : 412,
            headers: objectHeaders(object, route.key, route.root),
          }),
          env,
          releaseId,
        );
      }
      const status = request.headers.has("Range") && object.range ? 206 : 200;
      const response = new Response(object.body, {
        status,
        headers: objectHeaders(object, route.key, route.root, status),
      });
      if (cache && status === 200 && canUseCache(request)) {
        context.waitUntil(cache.put(cacheKey, response.clone()));
      }
      return secure(response, env, releaseId);
    }
  }

  const redirect = await directoryRedirect(request, env, route);
  if (redirect) {
    return secure(redirect, env, releaseId);
  }
  const fallback = await nearest404(env, manifest, route);
  if (fallback.object) {
    return secure(
      new Response(request.method === "HEAD" ? null : fallback.object.body, {
        status: 404,
        headers: objectHeaders(
          fallback.object,
          fallback.key,
          route.root,
        ),
      }),
      env,
      releaseId,
    );
  }
  return errorResponse(404, "Not found", env, releaseId);
}

export async function handleRequest(request, env, context = { waitUntil() {} }) {
  if (!["GET", "HEAD"].includes(request.method)) {
    return errorResponse(405, "Method not allowed", env, null, {
      Allow: "GET, HEAD",
    });
  }
  let release;
  try {
    release = await resolveRelease(env);
  } catch (error) {
    console.error(error);
    return errorResponse(503, "Release temporarily unavailable", env, null, {
      "Cache-Control": "no-store",
    });
  }
  const route = routeFor(new URL(request.url).pathname, release.manifest);
  if (route.error) {
    return errorResponse(route.error, "Invalid request path", env, release.releaseId);
  }
  return serve(
    request,
    env,
    context,
    release.releaseId,
    release.manifest,
    route,
  );
}

export default {
  fetch: handleRequest,
};
