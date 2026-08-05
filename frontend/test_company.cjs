const puppeteer = require('puppeteer');

(async () => {
  const browser = await puppeteer.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });
  const page = await browser.newPage();

  const errors = [];
  const consoleLogs = [];
  page.on('console', (msg) => {
    consoleLogs.push(`[${msg.type()}] ${msg.text()}`);
  });
  page.on('pageerror', (err) => {
    errors.push(`PAGE ERROR: ${err.message}`);
  });

  const failedRequests = [];
  page.on('requestfailed', (req) => {
    failedRequests.push(`${req.url()} - ${req.failure()?.errorText}`);
  });

  const responses = {};
  page.on('response', (res) => {
    const url = res.url();
    if (url.includes('/api/')) {
      responses[url] = res.status();
    }
  });

  console.log('=== Navigate to /company/Anthropic ===');
  await page.goto('http://localhost:3009/company/Anthropic', { waitUntil: 'networkidle0', timeout: 15000 });
  await new Promise((r) => setTimeout(r, 2000));

  const body = await page.evaluate(() => document.body.innerText);
  console.log('=== Body on /company/Anthropic ===');
  console.log(body.substring(0, 2000));

  console.log('=== API responses ===');
  Object.entries(responses).forEach(([url, status]) => {
    console.log(`${status} ${url}`);
  });

  console.log('=== Failed requests ===');
  failedRequests.forEach((r) => console.log(r));

  console.log('=== Errors ===');
  errors.forEach((e) => console.log(e));

  // Try clicking "View Details" on a company card from /companies
  console.log('\n=== Navigate to /companies ===');
  await page.goto('http://localhost:3009/companies', { waitUntil: 'networkidle0', timeout: 15000 });
  await new Promise((r) => setTimeout(r, 2000));

  const buttons = await page.evaluate(() => {
    const links = Array.from(document.querySelectorAll('a'));
    return links.filter((a) => a.href.includes('/company/')).map((a) => a.href);
  });
  console.log('Company links found:', buttons.length);
  console.log('First few:', buttons.slice(0, 3));

  // Click first company card View Details
  if (buttons.length > 0) {
    console.log('=== Click first company link ===');
    await page.goto(buttons[0], { waitUntil: 'networkidle0', timeout: 15000 });
    await new Promise((r) => setTimeout(r, 2000));

    const body = await page.evaluate(() => document.body.innerText);
    console.log('=== Body on company details ===');
    console.log(body.substring(0, 2000));
  }

  console.log('=== Errors after navigation ===');
  errors.forEach((e) => console.log(e));

  await browser.close();
  console.log('=== DONE ===');
})().catch((err) => {
  console.error('TEST FAILED:', err);
  process.exit(1);
});
