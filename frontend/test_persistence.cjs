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

  console.log('=== STEP 1: Land on /dashboard ===');
  await page.goto('http://localhost:3009/dashboard', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await new Promise((r) => setTimeout(r, 5000));
  let body = await page.evaluate(() => document.body.innerText);
  console.log('Has "Generate Weekly Report":', body.includes('Generate Weekly Report'));
  console.log('Has "workflow":', body.includes('Workflow') || body.includes('Workflow'));

  console.log('\n=== STEP 2: Click Generate Weekly Report ===');
  const genBtn = await page.evaluateHandle(() => {
    const buttons = Array.from(document.querySelectorAll('button'));
    return buttons.find((b) => b.textContent.trim() === 'Generate Weekly Report');
  });
  const btn = genBtn.asElement();
  if (btn && !btn.disabled) {
    await btn.click();
    console.log('Generate clicked');
  } else {
    console.log('Button disabled or not found');
    console.log('Body snippet:', body.substring(0, 500));
  }

  // Wait for the report to render
  for (let i = 0; i < 24; i++) {
    await new Promise((r) => setTimeout(r, 5000));
    const text = await page.evaluate(() => document.body.innerText);
    if (text.includes('TOP OPPORTUNITIES') && !text.includes('Generating')) {
      console.log(`Report rendered after ${(i + 1) * 5}s`);
      break;
    }
  }

  // Capture the report signature
  const beforeNav = await page.evaluate(() => {
    const h1 = document.querySelector('h2');
    const opportunities = Array.from(document.querySelectorAll('h4')).map((h) => h.textContent.trim()).slice(0, 5);
    const bodyText = document.body.innerText;
    return {
      h1: h1?.textContent,
      topH4: opportunities,
      hasTopOpportunities: bodyText.includes('TOP OPPORTUNITIES'),
      hasAwaits: bodyText.includes('Awaits'),
    };
  });
  console.log('Report signature:', JSON.stringify(beforeNav));

  console.log('\n=== STEP 3: Navigate to /companies ===');
  await page.goto('http://localhost:3009/companies', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await new Promise((r) => setTimeout(r, 3000));

  console.log('\n=== STEP 4: Navigate to /resume ===');
  await page.goto('http://localhost:3009/resume', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await new Promise((r) => setTimeout(r, 3000));
  body = await page.evaluate(() => document.body.innerText);
  console.log('Has "Current Resume":', body.includes('Current Resume'));

  console.log('\n=== STEP 5: Back to /dashboard ===');
  await page.goto('http://localhost:3009/dashboard', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await new Promise((r) => setTimeout(r, 5000));
  body = await page.evaluate(() => document.body.innerText);

  const afterNav = await page.evaluate(() => {
    const h1 = document.querySelector('h2');
    const opportunities = Array.from(document.querySelectorAll('h4')).map((h) => h.textContent.trim()).slice(0, 5);
    const bodyText = document.body.innerText;
    return {
      h1: h1?.textContent,
      topH4: opportunities,
      hasTopOpportunities: bodyText.includes('TOP OPPORTUNITIES'),
      hasAwaits: bodyText.includes('Awaits'),
      bodyPreview: bodyText.substring(0, 300),
    };
  });
  console.log('Report signature after nav:', JSON.stringify(afterNav));

  // Verify the report is preserved (no 'Generating' shown, Top Opportunities present)
  const reportPreserved = afterNav.hasTopOpportunities && !afterNav.hasAwaits;
  console.log('Report preserved after navigation:', reportPreserved);

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
