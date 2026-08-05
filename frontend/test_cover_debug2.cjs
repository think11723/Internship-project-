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

  const allRequests = [];
  page.on('request', (req) => {
    const url = req.url();
    if (url.includes('/api/')) {
      allRequests.push(`REQUEST ${req.method()} ${url.replace('http://localhost:3009', '')}`);
    }
  });
  const allResponses = [];
  page.on('response', (res) => {
    const url = res.url();
    if (url.includes('/api/')) {
      allResponses.push(`RESPONSE [${res.status()}] ${res.request().method()} ${url.replace('http://localhost:3009', '')}`);
    }
  });
  const requestFailed = [];
  page.on('requestfailed', (req) => {
    requestFailed.push(`FAILED ${req.method()} ${req.url()} - ${req.failure()?.errorText}`);
  });

  console.log('=== Navigate to /company/Anthropic ===');
  await page.goto('http://localhost:3009/company/Anthropic', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await new Promise((r) => setTimeout(r, 3000));

  console.log('\n=== Click Generate AI Cover Letter ===');
  await page.evaluate(() => {
    const buttons = Array.from(document.querySelectorAll('button'));
    const coverBtn = buttons.find((b) => b.textContent.trim().includes('Generate AI Cover Letter'));
    if (coverBtn) {
      coverBtn.click();
      console.log('CLICKED');
    }
  });

  // Wait but capture all requests
  console.log('\n=== Waiting 200s ===');
  for (let i = 0; i < 40; i++) {
    await new Promise((r) => setTimeout(r, 5000));
    const text = await page.evaluate(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      const coverBtn = buttons.find((b) => b.textContent.trim().includes('Cover Letter') || b.textContent.trim().includes('Generating'));
      return {
        button: coverBtn?.textContent.trim(),
        hasLetter: document.body.innerText.includes('Dear Hiring Team'),
      };
    });
    console.log(`${(i + 1) * 5}s - button: ${text.button}, hasLetter: ${text.hasLetter}`);
    if (text.hasLetter) break;
  }

  console.log('\n=== ALL REQUESTS ===');
  allRequests.forEach((r) => console.log(r));
  console.log('\n=== ALL RESPONSES ===');
  allResponses.forEach((r) => console.log(r));
  console.log('\n=== FAILED REQUESTS ===');
  requestFailed.forEach((r) => console.log(r));

  console.log('\n=== ERRORS ===');
  errors.forEach((e) => console.log(e));

  await browser.close();
  console.log('\n=== DONE ===');
})().catch((err) => {
  console.error('TEST FAILED:', err);
  process.exit(1);
});
