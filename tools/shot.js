/* 用 Playwright 真实渲染 Streamlit 页面并截图（视觉验收用）。
 * 运行：node tools/shot.js   （需先启动服务，默认 127.0.0.1:8531）
 */
const { chromium } = require('playwright-core');
const path = require('path');

const BASE = process.env.BGL_BASE || 'http://127.0.0.1:8531';
const OUT = 'C:/Users/dw/WorkBuddy/2026-10-10-12-31-09';

async function shot(page, file) {
  await page.screenshot({ path: path.join(OUT, file) });
  console.log('OK', file);
}

async function login(page, user, pwd) {
  await page.goto(BASE + '/', { waitUntil: 'domcontentloaded' });
  await page.waitForSelector('input', { timeout: 60000 });
  await page.waitForTimeout(1200);
  // 注意：侧边栏还有全局搜索框，必须按 aria-label 精确定位登录表单
  const u = page.locator('input[aria-label="用户名"]').first();
  const p = page.locator('input[aria-label="密码"]').first();
  await u.waitFor({ timeout: 30000 });
  await u.fill(user);
  await p.fill(pwd);
  await p.press('Enter');
  await page.waitForTimeout(4500);
  const loggedOut = await page.getByText('当前未登录').count();
  if (loggedOut > 0) {
    const errs = await page.locator('[data-testid="stException"], [data-baseweb="toast"], .stAlert').allTextContents();
    throw new Error('登录未生效 ' + JSON.stringify(errs).slice(0, 300));
  }
}

async function nav(page, label) {
  await page.getByRole('button', { name: label }).first().click();
  // 等 websocket 往返完成：先等网络空闲，再兜底等待
  await page.waitForLoadState('networkidle', { timeout: 20000 }).catch(() => {});
  await page.waitForTimeout(5000);
}

(async () => {
  const browser = await chromium.launch({
    executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe',
    headless: true,
  });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  try {
    await login(page, 'fangyuan', '123456');
    await shot(page, '_shot_1_dashboard.png');
    for (const [label, file] of [
      ['📚 AI 课程学习', '_shot_2_learn.png'],
      ['🧠 知识点讲解', '_shot_3_knowledge.png'],
      ['✍️ 练习测评', '_shot_4_quiz.png'],
      ['📰 AI 新闻', '_shot_5_news.png'],
      ['💬 讨论区', '_shot_6_forum.png'],
      ['🛒 课程商城', '_shot_7_store.png'],
      ['📺 直播课堂', '_shot_8_live.png'],
      ['📁 文件区', '_shot_9_files.png'],
      ['👤 个人中心', '_shot_10_profile.png'],
    ]) {
      await nav(page, label);
      await shot(page, file);
    }
    // 切换深色主题
    await page.getByRole('button', { name: '🌙 深色' }).first().click();
    await page.waitForTimeout(3000);
    await shot(page, '_shot_11_dark.png');

    // 管理员视角
    await page.getByRole('button', { name: '退出' }).first().click();
    await page.waitForTimeout(2500);
    await login(page, 'admin', '123456');
    await nav(page, '⚙️ 管理后台');
    await shot(page, '_shot_12_admin.png');
    console.log('ALL DONE');
  } catch (e) {
    console.error('FAIL', e.message);
    await page.screenshot({ path: path.join(OUT, '_shot_error.png') }).catch(() => {});
  } finally {
    await browser.close();
  }
})();
