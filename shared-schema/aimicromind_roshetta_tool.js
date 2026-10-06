// shared-schema/aimicromind_roshetta_tool.js  (paste into the OpenAPI Toolkit's code box)
// Runs the call the toolkit built from /ai/openapi.json ($url, $options) and adds what the
// model must never supply: the Bearer token. Response safety lives on the server (/ai
// response models); this code only authenticates, pins the host, and reports errors clearly.
// The AiMicroMind sandbox has no global URL or AbortController (probe, Session 62), so the
// URL is parsed with a regex and the timeout uses node-fetch's own option.
//
// Values: the workspace variables (or a per-request override sent by the Roshetta server) $vars.ROSHETTA_API_BASE and $vars.ROSHETTA_TOKEN win when
// they exist. If the Variables page cannot be used, set TEST_BASE and TEST_TOKEN below, in the
// toolkit's code box only. Never save or commit a real rsh1. token in this repo file
// (tokens live 12 hours). The toolkit's Headers field does NOT fill $vars.
//
// Session 109 (W8 e): every error text now says what the model should do next, a timeout has
// its own message, and Arabic-Indic or Persian digits in the URL (an id or a day typed in
// Arabic) are turned into ASCII digits before the call, so FastAPI's integer and date
// parsing accepts them.

const fetch = require('node-fetch');

const TEST_BASE = 'https://guiltless-inadequately-wilda.ngrok-free.dev';
const TEST_TOKEN = 'test123';

const MAX_CHARS = 12000;
const TIMEOUT_MS = 10000;
const out = (o) => JSON.stringify(o);
// Token diagnostics (Session 125): a fingerprint (FNV-1a 32, 8 hex) and the length, never the token.
// The server logs the same fingerprint for the token it sends and for the token it receives.
const fp = (s) => {
	let h = 0x811c9dc5;
	s = String(s || '');
	for (let i = 0; i < s.length; i++) { h ^= (s.charCodeAt(i) & 0xff); h = Math.imul(h, 0x01000193) >>> 0; }
	return ('00000000' + h.toString(16)).slice(-8);
};
const split = (u) => {
	const m = /^(https?:\/\/[^\/?#]+)(\/[^?#]*)?/i.exec(String(u || ''));
	return m ? { origin: m[1].toLowerCase(), path: m[2] || '/' } : null;
};
const asciiDigits = (u) => String(u || '')
	.replace(/[\u0660-\u0669]/g, (d) => String(d.charCodeAt(0) - 0x0660))
	.replace(/[\u06F0-\u06F9]/g, (d) => String(d.charCodeAt(0) - 0x06F0));

try {
	const vars = (typeof $vars === 'object' && $vars) ? $vars : {};
	const baseRaw = vars.ROSHETTA_API_BASE || TEST_BASE;
	const token = vars.ROSHETTA_TOKEN || TEST_TOKEN;
	const tokenFrom = vars.ROSHETTA_TOKEN ? 'variable' : 'test constant'; // names the source only, never the value
	if (!baseRaw || !token) return out({ ok: false, error: 'Tool is not configured: create the variables ROSHETTA_API_BASE and ROSHETTA_TOKEN.' });

	const url = asciiDigits($url);
	const target = split(url);
	const base = split(baseRaw);
	if (!target) return out({ ok: false, error: 'The tool URL is not absolute. Re-import https://<host>/ai/openapi.json in the toolkit.', url: String($url) });
	if (!base) return out({ ok: false, error: 'ROSHETTA_API_BASE must look like https://host (no path).' });
	if (target.origin !== base.origin) return out({ ok: false, error: 'Blocked: the spec points at a different host than ROSHETTA_API_BASE. Re-import /ai/openapi.json.', host: target.origin });
	if (target.path.indexOf('/ai/') !== 0) return out({ ok: false, error: 'Blocked: only /ai routes are allowed.', path: target.path });

	const options = $options || {};
	const method = String(options.method || 'GET').toUpperCase();
	if (method !== 'GET' && method !== 'POST') return out({ ok: false, error: 'Blocked: method not allowed.' });

	const headers = {};
	if (options.headers) {
		if (typeof options.headers.entries === 'function') {
			for (const [k, v] of options.headers.entries()) headers[k] = v;
		} else Object.assign(headers, options.headers);
	}
	for (const k of Object.keys(headers)) if (k.toLowerCase() === 'authorization') delete headers[k];
	headers['Authorization'] = 'Bearer ' + token;
	headers['Accept'] = 'application/json';
	if (target.origin.indexOf('ngrok') !== -1) headers['ngrok-skip-browser-warning'] = 'true';

	const response = await fetch(url, Object.assign({}, options, { method, headers, redirect: 'error', timeout: TIMEOUT_MS }));
	const raw = await response.text();

	const status = response.status;
	if (!response.ok) {
		const reason = {
			401: 'Authentication failed or the token expired. Tell the user to send the message again.',
			403: 'This account lacks the required scope. Say that this role cannot do this and the pharmacy owner can.',
			404: 'Not found. Check the name or id with a search first.',
			409: 'The token has no pharmacy selected. Tell the user to open a pharmacy first.',
			422: 'Invalid arguments. Fix them (days as YYYY-MM-DD, ids from a search result) and try once more.',
			429: 'Too many requests. Tell the user to try again in a minute.',
		}[status] || 'Request failed. Tell the user to try again later.';
		return out({ ok: false, status, error: reason, tokenFrom, tokenLen: String(token).length, tokenFp: fp(token), tokenFormat: String(token).indexOf('rsh1.') === 0 ? 'rsh1' : 'not-rsh1', host: target.origin });
	}

	let parsed;
	try {
		parsed = JSON.parse(raw);
	} catch (e) {
		return out({ ok: false, status, error: 'Response was not JSON (proxy or tunnel page?).', contentType: response.headers.get('content-type'), bodyStart: raw.slice(0, 300) });
	}
	const text = JSON.stringify(parsed);
	if (text.length > MAX_CHARS) return out({ ok: true, truncated: true, dataText: text.slice(0, MAX_CHARS) });
	return text;
} catch (error) {
	const msg = String(error && error.message ? error.message : error);
	if (/timeout|timed out|ETIMEDOUT|ESOCKETTIMEDOUT/i.test(msg)) return out({ ok: false, error: 'The server took too long. Ask a narrower question (one product, one day) or try again in a minute.' });
	return out({ ok: false, error: 'Request failed: ' + msg.slice(0, 200) });
}