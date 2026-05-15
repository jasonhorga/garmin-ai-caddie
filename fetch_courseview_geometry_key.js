#!/usr/bin/env node
"use strict";

const crypto = require("crypto");
const fs = require("fs");
const https = require("https");
const os = require("os");
const path = require("path");
const { execFileSync, spawnSync } = require("child_process");
const { URLSearchParams } = require("url");

const CONNECT_DI_CLIENT_ID = "GARMIN_CONNECT_MOBILE_ANDROID_DI";
const GOLF_DI_CLIENT_ID = "GOLF_MOBILE_ANDROID_DI";
const GOLF_IT_CLIENT_ID = "GOLF_MOBILE_ANDROID";
const FIXED_PASSWORD_SUFFIX = "d802989a-c373-43fb-afa0-ea831a905b9e";

function usage() {
  console.error(`Usage:
  node fetch_courseview_geometry_key.js --image-url <url-or-path> [options]

Options:
  --profile-id <id>       Garmin signed-in player profile id. If omitted, infer from data/summary.json.
  --token-file <path>     OAuth2 DI token cache. Default: .garmin_tokens/oauth2_token.json
  --zip <path>            Test the derived password against an encrypted prodgeometry zip.
  --extract <dir>         Extract the zip into this directory's parent when the password works.
  --password-out <path>   Write the derived password to a file.
  --print-password        Print the derived password to stdout. Avoid for logs/shared output.
  --use-full-image-url    Send the full image URL. Default sends URL.pathname, matching the app.
  --no-save-token         Do not update the token cache after refreshing it.
  --force-refresh         Refresh the Connect DI token even if it is still valid.
  --json                  Print machine-readable JSON only.
`);
}

function parseArgs(argv) {
  const args = {
    tokenFile: ".garmin_tokens/oauth2_token.json",
    saveToken: true,
    useFullImageUrl: false,
    forceRefresh: false,
    json: false,
  };
  for (let i = 2; i < argv.length; i += 1) {
    const a = argv[i];
    if (a === "--image-url") args.imageUrl = argv[++i];
    else if (a === "--profile-id") args.profileId = argv[++i];
    else if (a === "--token-file") args.tokenFile = argv[++i];
    else if (a === "--zip") args.zip = argv[++i];
    else if (a === "--extract") args.extract = argv[++i];
    else if (a === "--password-out") args.passwordOut = argv[++i];
    else if (a === "--print-password") args.printPassword = true;
    else if (a === "--use-full-image-url") args.useFullImageUrl = true;
    else if (a === "--no-save-token") args.saveToken = false;
    else if (a === "--force-refresh") args.forceRefresh = true;
    else if (a === "--json") args.json = true;
    else if (a === "-h" || a === "--help") {
      usage();
      process.exit(0);
    } else {
      throw new Error(`unknown argument: ${a}`);
    }
  }
  if (!args.imageUrl) throw new Error("--image-url is required");
  if (args.extract && !args.zip) throw new Error("--extract requires --zip");
  return args;
}

function log(args, message) {
  if (!args.json) console.error(message);
}

function postForm(url, bodyParams, headers = {}) {
  return request("POST", url, new URLSearchParams(bodyParams).toString(), {
    "Content-Type": "application/x-www-form-urlencoded",
    "User-Agent": "Garmin Golf/3.7.1 (com.garmin.android.apps.golf; Android)",
    "X-Garmin-User-Agent": "com.garmin.android.apps.golf/3.7.1",
    "Cache-Control": "no-cache",
    Connection: "keep-alive",
    ...headers,
  });
}

function request(method, url, body, headers = {}) {
  return new Promise((resolve, reject) => {
    const req = https.request(url, {
      method,
      headers: {
        ...headers,
        "Content-Length": body ? Buffer.byteLength(body) : 0,
      },
    }, (res) => {
      const chunks = [];
      res.on("data", (d) => chunks.push(d));
      res.on("end", () => {
        const responseBody = Buffer.concat(chunks);
        let json = null;
        try {
          json = JSON.parse(responseBody.toString("utf8"));
        } catch {
          // Some Garmin endpoints return raw encrypted base64.
        }
        resolve({ status: res.statusCode, headers: res.headers, body: responseBody, json });
      });
    });
    req.on("error", reject);
    if (body) req.write(body);
    req.end();
  });
}

function readJson(file) {
  return JSON.parse(fs.readFileSync(file, "utf8"));
}

function saveConnectToken(file, token) {
  const now = Math.floor(Date.now() / 1000);
  const out = {
    scope: token.scope,
    jti: token.jti,
    token_type: token.token_type,
    access_token: token.access_token,
    refresh_token: token.refresh_token,
    expires_in: token.expires_in,
    expires_at: now + Number(token.expires_in || 0),
    refresh_token_expires_in: token.refresh_token_expires_in,
    refresh_token_expires_at: now + Number(token.refresh_token_expires_in || 0),
  };
  const tmp = `${file}.tmp`;
  fs.writeFileSync(tmp, `${JSON.stringify(out, null, 2)}\n`, { mode: 0o600 });
  fs.renameSync(tmp, file);
}

async function getConnectDiToken(args) {
  const token = readJson(args.tokenFile);
  const now = Math.floor(Date.now() / 1000);
  if (!args.forceRefresh && token.access_token && Number(token.expires_at || 0) > now + 300) {
    return token;
  }
  if (!token.refresh_token) throw new Error(`no refresh_token in ${args.tokenFile}`);
  const res = await postForm(
    "https://diauth.garmin.cn/di-oauth2-service/oauth/token",
    {
      grant_type: "refresh_token",
      client_id: CONNECT_DI_CLIENT_ID,
      refresh_token: token.refresh_token,
    },
    {
      Authorization: `Basic ${Buffer.from(`${CONNECT_DI_CLIENT_ID}:`).toString("base64")}`,
    },
  );
  if (res.status !== 200 || !res.json || !res.json.access_token) {
    throw new Error(`Connect DI refresh failed: HTTP ${res.status} ${safeError(res)}`);
  }
  if (args.saveToken) saveConnectToken(args.tokenFile, res.json);
  return res.json;
}

async function exchangeGolfDi(connectDiToken) {
  const res = await postForm(
    "https://diauth.garmin.cn/di-oauth2-service/oauth/token",
    {
      subject_token: connectDiToken.access_token,
      client_id: GOLF_DI_CLIENT_ID,
      subject_token_type: "urn:ietf:params:oauth:token-type:access_token",
      grant_type: "urn:ietf:params:oauth:grant-type:token-exchange",
    },
    {
      Authorization: `Basic ${Buffer.from(`${GOLF_DI_CLIENT_ID}:`).toString("base64")}`,
    },
  );
  if (res.status !== 200 || !res.json || !res.json.access_token) {
    throw new Error(`Golf DI exchange failed: HTTP ${res.status} ${safeError(res)}`);
  }
  return res.json;
}

async function exchangeIt(golfDiToken) {
  const body = `client_id=${encodeURIComponent(GOLF_IT_CLIENT_ID)}&connect_access_token=${encodeURIComponent(golfDiToken.access_token)}`;
  const res = await request(
    "POST",
    "https://services.garmin.cn/api/oauth/token?grant_type=connect2_exchange",
    body,
    {
      "Content-Type": "application/x-www-form-urlencoded",
      "Accept-Encoding": "en_US",
      "Accept-Charset": "UTF-8",
      "User-Agent": "Garmin Golf/3.7.1 (com.garmin.android.apps.golf; Android)",
      "X-Garmin-User-Agent": "com.garmin.android.apps.golf/3.7.1",
    },
  );
  if (res.status !== 200 || !res.json || !res.json.access_token) {
    throw new Error(`IT exchange failed: HTTP ${res.status} ${safeError(res)}`);
  }
  return res.json;
}

function normalizeImageUrl(imageUrl, useFullImageUrl) {
  if (useFullImageUrl) return imageUrl;
  try {
    return new URL(imageUrl).pathname;
  } catch {
    return imageUrl;
  }
}

function inferProfileId() {
  const candidates = ["data/summary.json"];
  for (const file of candidates) {
    if (!fs.existsSync(file)) continue;
    const text = fs.readFileSync(file, "utf8");
    const match = text.match(/"playerProfileId"\s*:\s*(\d+)/);
    if (match) return match[1];
  }
  return null;
}

async function fetchEncryptedImageKey(itToken, imageUrl, profileId) {
  const url = `https://omt.garmin.cn/CourseViewData/image-key/v2?imageUrl=${encodeURIComponent(imageUrl)}`;
  const headers = {
    Accept: "application/json; charset=utf-8",
    "Garmin-Client-Name": "Garmin-Golf",
    "Garmin-Client-Platform": "Android",
    "Garmin-Client-Version": "3.7.1",
    Authorization: `Bearer ${itToken.access_token}`,
  };
  if (profileId) headers["3D-Account-Id"] = String(profileId);
  const res = await request("GET", url, null, headers);
  if (res.status !== 200) {
    throw new Error(`image-key failed: HTTP ${res.status} ${safeError(res)}`);
  }
  return encryptedBody(res);
}

function encryptedBody(res) {
  const text = res.body.toString("utf8").trim();
  if (!res.json) return text;
  if (typeof res.json === "string") return res.json;
  for (const key of ["data", "secret", "key", "encryptedKey", "value"]) {
    if (typeof res.json[key] === "string") return res.json[key];
  }
  return text;
}

function sha256(buf) {
  return crypto.createHash("sha256").update(buf).digest();
}

function deriveKeyIv(accessToken) {
  let key = Buffer.from(accessToken, "utf8");
  for (let i = 0; i < 3; i += 1) key = sha256(key);
  let iv = Buffer.from(key);
  for (let i = 0; i < 5; i += 1) iv = sha256(iv);
  return { key, iv: iv.subarray(11, 27) };
}

function decryptPrefix(encryptedKey, itAccessToken) {
  const { key, iv } = deriveKeyIv(itAccessToken);
  const decipher = crypto.createDecipheriv("aes-256-cbc", key, iv);
  return Buffer.concat([
    decipher.update(Buffer.from(encryptedKey, "base64")),
    decipher.final(),
  ]).toString("utf8");
}

function archiveMembers(zipFile) {
  const out = execFileSync("bsdtar", ["-tf", zipFile], { encoding: "utf8" });
  return out.split(/\r?\n/).filter((line) => line && !line.endsWith("/"));
}

function archiveTopDir(zipFile) {
  const members = archiveMembers(zipFile);
  const roots = new Set();
  for (const member of members) {
    const parts = member.split("/");
    if (parts.length < 2 || !parts[0]) return null;
    roots.add(parts[0]);
  }
  return roots.size === 1 ? [...roots][0] : null;
}

function testZipPassword(zipFile, password) {
  const member = archiveMembers(zipFile)[0];
  if (!member) throw new Error(`zip has no file members: ${zipFile}`);
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "garmin-keytest-"));
  try {
    const res = spawnSync("bsdtar", ["--passphrase", password, "-xf", zipFile, "-C", tmp, member], {
      encoding: "utf8",
    });
    return res.status === 0;
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
}

function extractZip(zipFile, extractTarget, password) {
  const target = path.resolve(extractTarget);
  const parent = path.dirname(target);
  const topDir = archiveTopDir(zipFile);
  fs.mkdirSync(parent, { recursive: true });
  fs.rmSync(target, { recursive: true, force: true });

  const extractDir = topDir && path.basename(target) !== topDir
    ? fs.mkdtempSync(path.join(parent, ".extract-"))
    : parent;
  const res = spawnSync("bsdtar", ["--passphrase", password, "-xf", zipFile, "-C", extractDir], {
    encoding: "utf8",
  });
  try {
    if (res.status !== 0) {
      throw new Error(`extract failed: ${res.stderr || res.stdout}`);
    }
    if (extractDir !== parent) {
      const extractedRoot = path.join(extractDir, topDir);
      if (!fs.existsSync(extractedRoot)) {
        throw new Error(`expected extracted root not found: ${extractedRoot}`);
      }
      fs.renameSync(extractedRoot, target);
    }
  } finally {
    if (extractDir !== parent) {
      fs.rmSync(extractDir, { recursive: true, force: true });
    }
  }
}

function safeError(res) {
  if (res.json) {
    const copy = { ...res.json };
    for (const key of Object.keys(copy)) {
      if (/token|secret|authorization/i.test(key)) copy[key] = "<redacted>";
    }
    return JSON.stringify(copy).slice(0, 500);
  }
  return res.body.toString("utf8").slice(0, 500);
}

async function main() {
  const args = parseArgs(process.argv);
  const profileId = args.profileId || inferProfileId();
  if (!profileId) throw new Error("could not infer profile id; pass --profile-id");
  const imageUrl = normalizeImageUrl(args.imageUrl, args.useFullImageUrl);

  log(args, "refreshing/exchanging Garmin tokens");
  const connectDi = await getConnectDiToken(args);
  const golfDi = await exchangeGolfDi(connectDi);
  const it = await exchangeIt(golfDi);

  log(args, `fetching image key for ${imageUrl}`);
  const encryptedKey = await fetchEncryptedImageKey(it, imageUrl, profileId);
  const prefix = decryptPrefix(encryptedKey, it.access_token);
  const password = `${prefix}${FIXED_PASSWORD_SUFFIX}`;

  let zipPasswordWorks = null;
  if (args.zip) {
    zipPasswordWorks = testZipPassword(args.zip, password);
    if (!zipPasswordWorks) throw new Error("derived password did not decrypt zip");
  }
  if (args.extract) extractZip(args.zip, args.extract, password);
  if (args.passwordOut) {
    fs.writeFileSync(args.passwordOut, password, { mode: 0o600 });
  }

  const result = {
    imageUrl,
    profileId,
    prefixLength: prefix.length,
    passwordLength: password.length,
    zipPasswordWorks,
    extractedTo: args.extract || null,
    passwordOut: args.passwordOut || null,
  };
  if (args.printPassword) result.password = password;
  if (args.json) {
    console.log(JSON.stringify(result, null, 2));
  } else {
    if (args.printPassword) console.log(`password: ${password}`);
    console.log(JSON.stringify(result, null, 2));
  }
}

main().catch((err) => {
  console.error(err.message || err);
  process.exit(1);
});
