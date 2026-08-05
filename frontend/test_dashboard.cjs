const puppeteer = require('puppeteer');

(async () => {
  const browser = await puppeteer.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });
  const page = await browser.newPage();

  const errors = [];
  page.on('pageerror', (err) => {
    errors.push(`PAGE ERROR: ${err.message}`);
  });

  page.on('response', (res) => {
    const url = res.url();
    if (url.includes('/api/') || url.includes('/api/workflow')) {
      console.log(`[${res.status()}] ${url}`);
    }
  });

  console.log('=== Navigate to /dashboard ===');
  await page.goto('http://localhost:3009/dashboard', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await new Promise((r) => setTimeout(r, 15000));

  const body = await page.evaluate(() => document.body.innerText);
  console.log('=== Body on /dashboard ===');
  console.log(body.substring(0, 2000));

  const buttonInfo = await page.evaluate(() => {
    const buttons = Array.from(document.querySelectorAll('button'));
    const genBtn = buttons.find((b) => b.textContent.trim() === 'Generate Weekly Report');
    return { found: !!genBtn, disabled: genBtn?.disabled, opacity: genBtn ? window.getComputedStyle(genBtn).opacity : 'n/a' };
  });
  console.log('=== Generate button ===');
  console.log(JSON.stringify(buttonInfo));

  console.log('=== Errors ===');
  errors.forEach((e) => console.log(e));

  await browser.close();
  console.log('=== DONE ===');
})().catch((err) => {
  console.error('TEST FAILED:', err);
  process.exit(1);
});
