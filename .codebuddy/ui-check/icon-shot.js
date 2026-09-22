const { chromium } = require('D:/tool/npm-global/node_modules/@playwright/cli/node_modules/playwright-core');
const DIR = 'D:/project/competitor-radar/.codebuddy/ui-check/';

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({
    viewport: { width: 1200, height: 900 },
    deviceScaleFactor: 2,
  });
  const failed = [];
  page.on('requestfailed', (r) => failed.push(r.url()));

  await page.goto('file:///' + DIR + 'icon-probe.html');
  await page.waitForLoadState('load');
  await page.evaluate(() =>
    Promise.all([...document.images].map((i) => i.decode().catch(() => null)))
  );

  const info = await page.evaluate(() => {
    const broken = [];
    for (const img of document.images) {
      if (!img.complete || img.naturalWidth === 0) {
        broken.push(img.getAttribute('alt') + ' :: ' + img.getAttribute('src'));
      }
    }
    const first = document.querySelector('#new .logo-new');
    const fi = first.querySelector('img');
    const b = first.getBoundingClientRect();
    const ib = fi.getBoundingClientRect();
    return {
      brokenImages: broken,
      logoBox: { w: +b.width.toFixed(2), h: +b.height.toFixed(2) },
      imgBox: { w: +ib.width.toFixed(2), h: +ib.height.toFixed(2) },
      logoBackground: getComputedStyle(first).backgroundColor,
      totalImages: document.images.length,
    };
  });

  await page.screenshot({ path: DIR + 'icon-probe.png', fullPage: true });
  console.log(JSON.stringify({ ...info, requestFailed: failed }, null, 2));
  await browser.close();
})();
