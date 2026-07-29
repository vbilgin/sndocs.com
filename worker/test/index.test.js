import assert from "node:assert/strict";
import test from "node:test";

import { handleRequest } from "../src/index.js";

const RELEASE = "a".repeat(64);
const OTHER_RELEASE = "b".repeat(64);

class MockObject {
  constructor(body, { contentType, etag = '"etag"', range } = {}) {
    this._body = Buffer.from(body);
    this.body = this._body;
    this.size = this._body.length;
    this.httpEtag = etag;
    this.uploaded = new Date("2026-01-01T00:00:00Z");
    this.range = range;
    this.contentType = contentType;
  }

  async json() {
    return JSON.parse(this._body.toString());
  }

  async text() {
    return this._body.toString();
  }

  writeHttpMetadata(headers) {
    if (this.contentType) {
      headers.set("Content-Type", this.contentType);
    }
  }
}

class MockBucket {
  constructor(objects) {
    this.objects = new Map(Object.entries(objects));
    this.gets = [];
  }

  async head(key) {
    const value = this.objects.get(key);
    return value ? new MockObject(value.body, value.options) : null;
  }

  async get(key, options = {}) {
    this.gets.push(key);
    const value = this.objects.get(key);
    if (!value) {
      return null;
    }
    const base = new MockObject(value.body, value.options);
    const noneMatch = options.onlyIf?.get?.("If-None-Match");
    if (noneMatch && noneMatch === base.httpEtag) {
      base.body = undefined;
      return base;
    }
    const rangeHeader = options.range?.get?.("Range");
    if (rangeHeader) {
      const match = /^bytes=(\d+)-(\d+)?$/.exec(rangeHeader);
      if (match) {
        const offset = Number(match[1]);
        const end = match[2] ? Number(match[2]) : base.size - 1;
        const length = end - offset + 1;
        base.body = base._body.subarray(offset, end + 1);
        base.range = { offset, length };
      }
    }
    return base;
  }
}

function manifest(release = RELEASE) {
  return {
    schema_version: 1,
    release_id: release,
    latest: "zurich",
    root_prefix: `releases/${release}/root`,
    families: {
      zurich: {
        family: "zurich",
        prefix: `content/zurich/${"c".repeat(64)}`,
        archived: false,
      },
      yokohama: {
        family: "yokohama",
        prefix: `content/yokohama/${"d".repeat(64)}`,
        archived: true,
      },
    },
  };
}

function environment(mode = "production", release = RELEASE) {
  const releaseManifest = manifest(release);
  const objects = {
    [`releases/${release}.json`]: {
      body: JSON.stringify(releaseManifest),
      options: { contentType: "application/json" },
    },
    "pointers/preview.json": {
      body: JSON.stringify({ release_id: release }),
      options: { contentType: "application/json" },
    },
    [`releases/${release}/root/index.html`]: {
      body: "root",
      options: { contentType: "text/html; charset=utf-8" },
    },
    [`content/zurich/${"c".repeat(64)}/index.html`]: {
      body: "zurich",
      options: { contentType: "text/html; charset=utf-8" },
    },
    [`content/zurich/${"c".repeat(64)}/guide/index.html`]: {
      body: "guide",
      options: { contentType: "text/html; charset=utf-8" },
    },
    [`content/zurich/${"c".repeat(64)}/404.html`]: {
      body: "family missing",
      options: { contentType: "text/html; charset=utf-8" },
    },
    [`content/zurich/${"c".repeat(64)}/pagefind/pagefind.js`]: {
      body: "0123456789",
      options: { contentType: "text/javascript; charset=utf-8" },
    },
    [`content/zurich/${"c".repeat(64)}/pagefind/pagefind_bg.wasm`]: {
      body: "wasm",
      options: { contentType: "application/octet-stream" },
    },
    [`content/yokohama/${"d".repeat(64)}/index.html`]: {
      body: "yokohama",
      options: { contentType: "text/html; charset=utf-8" },
    },
    [`content/yokohama/${"d".repeat(64)}/404.html`]: {
      body: "archived missing",
      options: { contentType: "text/html; charset=utf-8" },
    },
  };
  return {
    DEPLOYMENT_MODE: mode,
    RELEASE_ID: release,
    SITE_BUCKET: new MockBucket(objects),
  };
}

async function request(path, options = {}, env = environment()) {
  return handleRequest(
    new Request(`https://sndocs.com${path}`, options),
    env,
    { waitUntil() {} },
  );
}

test("serves root, latest, archived, and deep clean URLs", async () => {
  assert.equal(await (await request("/")).text(), "root");
  assert.equal(await (await request("/zurich/")).text(), "zurich");
  assert.equal(await (await request("/yokohama/")).text(), "yokohama");
  assert.equal(await (await request("/zurich/guide/")).text(), "guide");
});

test("redirects valid slashless directories with 308", async () => {
  const family = await request("/zurich");
  assert.equal(family.status, 308);
  assert.equal(family.headers.get("location"), "https://sndocs.com/zurich/");
  const response = await request("/zurich/guide");
  assert.equal(response.status, 308);
  assert.equal(response.headers.get("location"), "https://sndocs.com/zurich/guide/");
});

test("supports HEAD, ETag conditionals, ranges, 404, and 405", async () => {
  const head = await request("/zurich/", { method: "HEAD" });
  assert.equal(head.status, 200);
  assert.equal(head.headers.get("content-length"), "6");
  assert.equal(await head.text(), "");

  const notModified = await request("/zurich/", {
    headers: { "If-None-Match": '"etag"' },
  });
  assert.equal(notModified.status, 304);

  const range = await request("/zurich/pagefind/pagefind.js", {
    headers: { Range: "bytes=2-5" },
  });
  assert.equal(range.status, 206);
  assert.equal(range.headers.get("content-range"), "bytes 2-5/10");
  assert.equal(await range.text(), "2345");

  const missing = await request("/yokohama/absent/");
  assert.equal(missing.status, 404);
  assert.equal(await missing.text(), "archived missing");

  const rejected = await request("/", { method: "POST" });
  assert.equal(rejected.status, 405);
  assert.equal(rejected.headers.get("allow"), "GET, HEAD");
});

test("sets MIME, release, cache, and baseline security headers", async () => {
  const wasm = await request("/zurich/pagefind/pagefind_bg.wasm");
  assert.equal(wasm.headers.get("content-type"), "application/wasm");
  assert.equal(wasm.headers.get("x-sndocs-release"), RELEASE);
  assert.match(wasm.headers.get("cache-control"), /s-maxage=31536000/);
  assert.equal(wasm.headers.get("x-content-type-options"), "nosniff");
  assert.ok(wasm.headers.get("content-security-policy-report-only"));

  const root = await request("/");
  assert.match(root.headers.get("cache-control"), /max-age=60/);
});

test("preview reads its pointer and adds no-index headers", async () => {
  const response = await request("/", {}, environment("preview"));
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("x-robots-tag"), "noindex, nofollow");
});

test("cache keys separate identical paths across releases", async () => {
  const keys = [];
  const cache = {
    async match() {
      return undefined;
    },
    async put(key) {
      keys.push(key.url);
    },
  };
  const first = environment("production", RELEASE);
  first.EDGE_CACHE = cache;
  const second = environment("production", OTHER_RELEASE);
  second.EDGE_CACHE = cache;
  await request("/zurich/", {}, first);
  await request("/zurich/", {}, second);
  const contentKeys = keys.filter((key) => key.includes(encodeURIComponent("content/")));
  assert.equal(contentKeys.length, 2);
  assert.notEqual(contentKeys[0], contentKeys[1]);
  assert.match(contentKeys[0], new RegExp(RELEASE));
  assert.match(contentKeys[1], new RegExp(OTHER_RELEASE));
});

test("immutable production manifests are not read from R2 on every request", async () => {
  const release = "e".repeat(64);
  const env = environment("production", release);
  await request("/zurich/", {}, env);
  await request("/yokohama/", {}, env);
  const manifestReads = env.SITE_BUCKET.gets.filter(
    (key) => key === `releases/${release}.json`,
  );
  assert.equal(manifestReads.length, 1);
});

test("fails closed when the release binding or manifest is invalid", async () => {
  const env = environment();
  env.RELEASE_ID = "mutable";
  const originalError = console.error;
  console.error = () => {};
  try {
    const response = await request("/", {}, env);
    assert.equal(response.status, 503);
    assert.equal(response.headers.get("cache-control"), "no-store");
  } finally {
    console.error = originalError;
  }
});
