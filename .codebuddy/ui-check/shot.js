const { chromium } = require('D:/tool/npm-global/node_modules/@playwright/cli/node_modules/playwright-core');
const DIR = 'D:/project/competitor-radar/.codebuddy/ui-check/';

(async () => {
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 2 });
  await page.goto('file:///' + DIR + 'suffix-icon.html');
  await page.screenshot({ path: DIR + 'suffix-icon.png', fullPage: true });
  const m = await page.evaluate(() => {
    const out = {};
    for (const v of ['before', 'after']) {
      const rows = document.querySelectorAll('.' + v + ' .source-row');
      const box = rows[1]; // 应用商店页
      const icons = [...box.querySelectorAll('.el-input__suffix .el-icon')];
      const inner = box.querySelector('.el-input__inner');
      const si = box.querySelector('.el-input__suffix-inner');
      const r = icons.map((i) => {
        const b = i.getBoundingClientRect();
        return { w: +b.width.toFixed(2), h: +b.height.toFixed(2), left: +b.left.toFixed(2), right: +b.right.toFixed(2) };
      });
      out[v] = {
        inputHeight: +inner.getBoundingClientRect().height.toFixed(2),
        suffixFontSize: getComputedStyle(si).fontSize,
        gap: getComputedStyle(si).gap,
        icons: r,
        gapBetweenIcons: +(r[1].left - r[0].right).toFixed(2),
        rightPadding: +(box.querySelector('.el-input__wrapper').getBoundingClientRect().right - r[1].right).toFixed(2),
      };
    }
    return out;
  });
  console.log(JSON.stringify(m, null, 2));
  await browser.close();
})();
