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

  console.log('=== Navigate to /company/Perplexity%20AI ===');
  await page.goto('http://localhost:3009/company/Perplexity%20AI', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await new Promise((r) => setTimeout(r, 3000));

  // Click Generate AI Cover Letter
  console.log('=== Click Generate AI Cover Letter ===');
  const coverBtn = await page.evaluateHandle(() => {
    const buttons = Array.from(document.querySelectorAll('button'));
    return buttons.find((b) => b.textContent.trim().includes('Generate AI Cover Letter'));
  });
  const coverBtnEl = coverBtn.asElement();
  if (coverBtnEl) {
    await coverBtnEl.click();
    console.log('Clicked');
  }

  // Wait up to 3 minutes
  console.log('=== Waiting for cover letter (up to 3 min) ===');
  for (let i = 0; i < 36; i++) {
    await new Promise((r) => setTimeout(r, 5000));
    const text = await page.evaluate(() => document.body.innerText);
    if (text.includes('Dear Hiring Team')) {
      console.log(`Cover letter rendered after ${(i + 1) * 5}s`);
      break;
    }
    if (i % 6 === 5) console.log(`...still waiting ${(i + 1) * 5}s`);
  }

  const body = await page.evaluate(() => document.body.innerText);
  console.log('Has "Dear Hiring Team":', body.includes('Dear Hiring Team'));
  console.log('Has "Copied!" or "Copy to Clipboard":', body.includes('Copy to Clipboard'));

  console.log('\n=== API CALLS ===');
  apiCalls.forEach((c) => console.log(c));

  console.log('\n=== ERRORS ===');
  errors.forEach((e) => console.log(e));

  await browser.close();
  console.log('\n=== DONE ===');
})().catch((err) => {
  console.error('TEST FAILED:', err);
  process.exit(1);
});
