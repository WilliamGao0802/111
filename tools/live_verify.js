/* 线上验收：真实浏览器打开已发布链接，确认首启自举 + 登录链路可用。
 * 用法：BGL_BASE=https://xxx node tools/live_verify.js
 */
const { chromium } = require('playwright-core');

const BASE = process.env.BGL_BASE;
if (!BASE) { console.error('需要 BGL_BASE'); process.exit(2); }

(async () => {
  const browser = await chromium.launch({
    executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    headless: true,
  });
  const page = await browser.newPage({ viewport: { width: 1360, height: 950 } });
  const errs = [];
  page.on('pageerror', (e) => errs.push('pageerror: ' + e.message));
  page.on('console', (m) => { if (m.type() === 'error') errs.push('console: ' + m.text().slice(0, 200)); });

  try {
    const t0 = Date.now();
    await page.goto(BASE + '/', { waitUntil: 'domcontentloaded', timeout: 90000 });
    await page.waitForSelector('input', { timeout: 120000 });
    console.log('首屏可见 input 用时(ms):', Date.now() - t0);
    await page.waitForTimeout(5000);

    console.log('登录门已渲染:', (await page.getByText('当前未登录').count()) > 0);

    await page.locator('input[aria-label="用户名"]').first().fill('fangyuan');
    await page.locator('input[aria-label="密码"]').first().fill('123456');
    await page.locator('input[aria-label="密码"]').first().press('Enter');
    await page.waitForTimeout(12000);

    const ok = await page.getByText('欢迎回来').count();
    console.log('登录成功（欢迎横幅）:', ok > 0);
    const exc = await page.locator('[data-testid="stException"]').allTextContents();
    if (exc.length) console.log('页面异常:', JSON.stringify(exc).slice(0, 500));

    await page.screenshot({ path: 'C:/Users/dw/WorkBuddy/2026-10-10-12-31-09/_live_check.png' });
    console.log('已截图 _live_check.png');
    console.log('浏览器错误数:', errs.length);
    if (errs.length) console.log(errs.slice(0, 6).join('\n'));
    process.exitCode = ok > 0 ? 0 : 1;
  } catch (e) {
    console.error('FAIL', e.message);
    await page.screenshot({ path: 'C:/Users/dw/WorkBuddy/2026-10-10-12-31-09/_live_fail.png' }).catch(() => {});
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
