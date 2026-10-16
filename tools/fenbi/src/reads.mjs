const SAFE_QUERY = new Set(['labelId', 'toPage', 'page', 'pageSize', 'paperId', 'year', 'categoryId', 'provinceId', 'id', 'type',
  'questionIds', 'ids', 'exerciseId', 'app', 'kav', 'av', 'hav', 'version']);

export function observedReadUrl(value) {
  const url = new URL(value);
  if (url.protocol !== 'https:' || url.hostname !== 'tiku.fenbi.com' || url.username || url.password || url.hash) throw new Error('Invalid observed read URL');
  if (!/^\/api\/(xingce|shenlun)\//.test(url.pathname) || /(?:^|\/)(?:user[^/]*|history|member\w*|auth\w*|login|logout|current|selected|submit|records?|favorites?|category-exercises-unfinished)(?:\/|$)/i.test(url.pathname)) throw new Error('Account endpoints cannot be replayed');
  if (/\/exercises?(?:\/|$)/i.test(url.pathname) && !/^\/api\/(xingce|shenlun)\/exercises?\/[a-zA-Z0-9_-]+(?:\/(?:questions|answers|answercard|materials))?\/?$/.test(url.pathname)) throw new Error('Only existing exercise content can be read');
  for (const [key, val] of url.searchParams) if (!SAFE_QUERY.has(key) || !/^[\w,\[\].-]{0,2000}$/.test(val)) throw new Error('Read URL contains unsupported parameters');
  return url.toString();
}

/** Reuse cookies in the current browser context, but only for URLs previously observed there. */
export async function replayReads(context, urls, observedUrls, onPayload, { delayMs = 800, sleep = ms => new Promise(resolve => setTimeout(resolve, ms)) } = {}) {
  const registry = new Set(observedUrls.map(observedReadUrl));
  const results = [];
  for (const value of urls || []) {
    const url = observedReadUrl(value);
    if (!registry.has(url)) throw new Error('Read URL was not observed in this browser profile; inspect it first instead of guessing endpoints');
    let response;
    try {
      response = await context.request.get(url, { maxRedirects: 0, timeout: 45000 });
      const status = response.status();
      if (status < 200 || status >= 300) { results.push({ url, status, outcome: 'http_error' }); continue; }
      const headers = response.headers();
      if (!/application\/json|\+json/i.test(headers['content-type'] || '')) { results.push({ url, status, outcome: 'non_json' }); continue; }
      if (Number(headers['content-length']) > 8 * 1024 * 1024) { results.push({ url, status, outcome: 'oversized' }); continue; }
      const bytes = await response.body();
      if (bytes.length > 8 * 1024 * 1024) { results.push({ url, status, outcome: 'oversized' }); continue; }
      const payload = JSON.parse(bytes.toString('utf8'));
      const challenge = [payload?.code, payload?.msg, payload?.message].some(x => /captcha|验证码|人机验证/i.test(String(x || '')));
      if (challenge) { results.push({ url, status, outcome: 'captcha' }); continue; }
      await onPayload(payload, { url, subject: new URL(url).pathname.split('/')[2] });
      results.push({ url, status, outcome: 'accepted' });
    } catch { results.push({ url, outcome: 'failed' }); }
    finally { await response?.dispose?.().catch(() => {}); await sleep(delayMs); }
  }
  return results;
}
