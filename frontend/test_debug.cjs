const puppeteer = require('puppeteer');

(async () => {
  const browser = await puppeteer.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });
  const page = await browser.newPage();

  const allErrors = [];
  page.on('pageerror', (err) => allErrors.push(`PAGE ERROR: ${err.message}`));
  page.on('console', (msg) => {
    if (msg.type() === 'error') allErrors.push(`CONSOLE: ${msg.text()}`);
  });
  page.on('requestfailed', (req) => {
    allErrors.push(`REQUEST FAILED: ${req.url()} - ${req.failure()?.errorText}`);
  });
  page.on('response', (res) => {
    if (res.status() >= 400) {
      allErrors.push(`HTTP ${res.status()} ${res.url()}`);
    }
  });

  console.log('=== Navigating to / ===');
  await page.goto('http://localhost:3009/', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await new Promise((r) => setTimeout(r, 5000));

  console.log('=== ALL ERRORS ===');
  allErrors.forEach((e) => console.log(e));

  await browser.close();
})().catch((err) => {
  console.error('TEST FAILED:', err);
  process.exit(1);
});
