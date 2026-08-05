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

  const apiCalls = [];
  page.on('response', (res) => {
    const url = res.url();
    if (url.includes('/api/')) {
      apiCalls.push(`[${res.status()}] ${res.request().method()} ${url.replace('http://localhost:3009', '')}`);
    }
  });

  const consoleLogs = [];
  page.on('console', (msg) => {
    consoleLogs.push(`[${msg.type()}] ${msg.text()}`);
  });

  console.log('=== Navigate to /company/Perplexity%20AI ===');
  await page.goto('http://localhost:3009/company/Perplexity%20AI', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await new Promise((r) => setTimeout(r, 3000));

  // Find the button and check its state
  const buttonInfo = await page.evaluate(() => {
    const buttons = Array.from(document.querySelectorAll('button'));
    const coverBtn = buttons.find((b) => b.textContent.trim().includes('Generate AI Cover Letter'));
    if (!coverBtn) return { found: false };
    const rect = coverBtn.getBoundingClientRect();
    return {
      found: true,
      text: coverBtn.textContent.trim(),
      disabled: coverBtn.disabled,
      visible: rect.width > 0 && rect.height > 0,
      rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
      // Check what's on top at the button's center
      elementAtPoint: (() => {
        const el = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2);
        return el ? el.tagName + (el.id ? '#' + el.id : '') + (el.className ? '.' + (el.className || '').toString().split(' ')[0] : '') : 'null';
      })(),
    };
  });
  console.log('=== Button info ===');
  console.log(JSON.stringify(buttonInfo, null, 2));

  // Click the button via direct click
  console.log('\n=== Click button ===');
  await page.evaluate(() => {
    const buttons = Array.from(document.querySelectorAll('button'));
    const coverBtn = buttons.find((b) => b.textContent.trim().includes('Generate AI Cover Letter'));
    if (coverBtn) {
      console.log('FOUND button, clicking');
      coverBtn.click();
    } else {
      console.log('NOT FOUND');
    }
  });

  await new Promise((r) => setTimeout(r, 30000));

  // Check button state after click
  const afterClick = await page.evaluate(() => {
    const buttons = Array.from(document.querySelectorAll('button'));
    const coverBtn = buttons.find((b) => b.textContent.trim().includes('Cover Letter') || b.textContent.trim().includes('Generating'));
    return { text: coverBtn?.textContent.trim(), disabled: coverBtn?.disabled };
  });
  console.log('=== After click ===');
  console.log(JSON.stringify(afterClick, null, 2));

  console.log('\n=== API CALLS ===');
  apiCalls.forEach((c) => console.log(c));

  console.log('\n=== CONSOLE LOGS ===');
  consoleLogs.forEach((c) => console.log(c));

  console.log('\n=== ERRORS ===');
  errors.forEach((e) => console.log(e));

  await browser.close();
  console.log('\n=== DONE ===');
})().catch((err) => {
  console.error('TEST FAILED:', err);
  process.exit(1);
});
