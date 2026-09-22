const { chromium } = require('D:/tool/npm-global/node_modules/@playwright/cli/node_modules/playwright-core');
const DIR = 'D:/project/competitor-radar/.codebuddy/ui-check/';

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 2 });
  await page.goto('file:///' + DIR + 'suffix-icon.html');
  const shots = [
    ['before', '.before .source-row:nth-child(2)', 'crop-before.png'],
    ['after', '.after .source-row:nth-child(2)', 'crop-after.png'],
  ];
  for (const [, sel, file] of shots) {
    await page.locator(sel).screenshot({ path: DIR + file });
  }
  console.log('ok');
  await browser.close();
})();
