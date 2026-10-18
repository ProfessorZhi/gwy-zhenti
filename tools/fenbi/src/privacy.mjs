import { load } from 'cheerio';

const SECRET_PARAMETER = /token|key|secret|auth|session|cookie|signature|credential|password|phone|mobile|verification|(^|_)code$/i;

export function sensitiveUrl(value) {
  try {
    const url = new URL(value, 'https://www.fenbi.com/');
    if (url.username || url.password || ['javascript:', 'data:'].includes(url.protocol)) return true;
    return [...url.searchParams.keys()].some(key => SECRET_PARAMETER.test(key)) || /(?:^#|[?&])[^=&]*(?:token|secret|password|cookie|auth)[^=&]*=/i.test(url.hash);
  } catch { return true; }
}

/** Preserve examination text; remove embedded credentials and active page elements before persistence. */
export function sanitizeHtml(html) {
  const $ = load(String(html ?? ''), null, false);
  let rejected = 0;
  $('script,style,iframe,object,embed,form,input,textarea,select,[data-account],.user-info,.account-info').each((_, el) => { rejected++; $(el).remove(); });
  $('*').each((_, el) => {
    for (const [name, value] of Object.entries(el.attribs || {})) {
      if (/^on/i.test(name) || /token|secret|password|cookie|authorization/i.test(name) || name === 'srcdoc' || name === 'style') {
        if (name === 'style' && /url\s*\(/i.test(value)) rejected++;
        $(el).removeAttr(name); continue;
      }
      if (['src', 'href', 'xlink:href', 'data-src', 'data-original'].includes(name) && sensitiveUrl(value)) {
        rejected++; $(el).removeAttr(name); $(el).attr('data-capture-rejected-reference', 'true');
      }
      if (name === 'srcset' && value.split(',').some(item => sensitiveUrl(item.trim().split(/\s+/)[0]))) {
        rejected++; $(el).removeAttr(name); $(el).attr('data-capture-rejected-reference', 'true');
      }
    }
  });
  return { html: $.html(), rejected };
}
