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

  console.log('=== STEP 1: Navigate to /resume ===');
  await page.goto('http://localhost:3009/resume', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await new Promise((r) => setTimeout(r, 3000));

  let body = await page.evaluate(() => document.body.innerText);
  console.log('Has "Current Resume":', body.includes('Current Resume'));
  console.log('Has "View Resume":', body.includes('View Resume'));
  console.log('Has "Replace Resume":', body.includes('Replace Resume'));
  console.log('Has "Delete Resume":', body.includes('Delete Resume'));

  console.log('\n=== STEP 2: Click View Resume ===');
  const viewBtn = await page.evaluateHandle(() => {
    const buttons = Array.from(document.querySelectorAll('button'));
    return buttons.find((b) => b.textContent.trim() === 'View Resume');
  });
  await viewBtn.asElement().click();
  await new Promise((r) => setTimeout(r, 3000));
  body = await page.evaluate(() => document.body.innerText);
  console.log('Modal opened:', body.includes('Close'));

  // Close modal
  const closeBtn = await page.evaluateHandle(() => {
    const buttons = Array.from(document.querySelectorAll('button'));
    return buttons.find((b) => b.textContent.trim() === 'Close');
  });
  await closeBtn.asElement().click();
  await new Promise((r) => setTimeout(r, 1000));

  console.log('\n=== STEP 3: Click Delete Resume → confirm ===');
  const deleteBtn = await page.evaluateHandle(() => {
    const buttons = Array.from(document.querySelectorAll('button'));
    return buttons.find((b) => b.textContent.trim() === 'Delete Resume');
  });
  await deleteBtn.asElement().click();
  await new Promise((r) => setTimeout(r, 1500));
  body = await page.evaluate(() => document.body.innerText);
  console.log('Confirm prompt visible:', body.includes('Yes, delete resume'));

  const confirmBtn = await page.evaluateHandle(() => {
    const buttons = Array.from(document.querySelectorAll('button'));
    return buttons.find((b) => b.textContent.trim() === 'Yes, delete resume');
  });
  await confirmBtn.asElement().click();
  await new Promise((r) => setTimeout(r, 5000));
  body = await page.evaluate(() => document.body.innerText);
  console.log('After delete - has "Current Resume":', body.includes('Current Resume'));
  console.log('After delete - has "Drop your resume":', body.includes('Drop your resume'));

  console.log('\n=== STEP 4: Verify backend has no resume ===');
  const result = await page.evaluate(async () => {
    const r = await fetch('/api/resume/latest');
    return { status: r.status, body: await r.json() };
  });
  console.log('GET /api/resume/latest status:', result.status);

  console.log('\n=== STEP 5: Verify Dashboard empty state ===');
  await page.goto('http://localhost:3009/dashboard', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await new Promise((r) => setTimeout(r, 3000));
  body = await page.evaluate(() => document.body.innerText);
  console.log('Dashboard has "No resume uploaded yet":', body.includes('No resume uploaded yet'));

  console.log('\n=== API Calls ===');
  apiCalls.forEach((c) => console.log(c));

  console.log('\n=== Errors ===');
  errors.forEach((e) => console.log(e));

  await browser.close();
  console.log('\n=== DONE ===');
})().catch((err) => {
  console.error('TEST FAILED:', err);
  process.exit(1);
});
