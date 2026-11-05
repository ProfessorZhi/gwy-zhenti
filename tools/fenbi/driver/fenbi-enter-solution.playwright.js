// Pass this file to Playwright MCP browser_run_code_unsafe.filename.
// Use only on the intended exercise and with user authorization to submit a blank attempt.
async (page) => {
  const url = new URL(page.url());
  if (url.hostname !== 'spa.fenbi.com' || !/^\/ti\/exam\/(exercise|solution)\//.test(url.pathname))
    throw new Error('Expected a Fenbi exercise or solution page');
  if (url.pathname.includes('/solution/'))
    return {status:'already_solution',url:page.url(),title:await page.title()};
  await page.locator('app-exercise app-ti').first().waitFor({state:'attached',timeout:30000});
  const submit = page.getByText('交卷',{exact:true});
  if (await submit.count() !== 1 || !await submit.isVisible()) throw new Error('Submit control not uniquely visible');
  // Background tabs can suspend the animation-frame stability check. The visible
  // control and the resulting confirmation dialog are checked explicitly instead.
  await submit.click({force:true,timeout:10000});
  const confirm=page.locator('app-modal-common').getByRole('button',{name:'确认',exact:true});
  await confirm.waitFor({state:'visible',timeout:10000});
  const dialogText=await page.locator('app-modal-common').innerText();
  if (!dialogText.includes('确认交卷')) throw new Error('Unexpected confirmation dialog');
  await confirm.click({force:true,timeout:10000});
  await page.locator('app-solution app-ti').first().waitFor({state:'attached',timeout:30000});
  return {status:'solution_opened',url:page.url(),title:await page.title(),
    note:'Run archive-jobs with source expectedCount; initial render may contain only a few questions'};
}
