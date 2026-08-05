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
  const failedRequests = [];
  page.on('response', (res) => {
    const url = res.url();
    if (url.includes('/api/')) {
      apiCalls.push(`[${res.status()}] ${res.request().method()} ${url.replace('http://localhost:3009', '')}`);
    }
  });
  page.on('requestfailed', (req) => {
    failedRequests.push(`${req.url()} - ${req.failure()?.errorText}`);
  });

  console.log('\n=== STEP 1: Landing ===');
  await page.goto('http://localhost:3009/', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await new Promise((r) => setTimeout(r, 2000));
  let body = await page.evaluate(() => document.body.innerText);
  console.log('Landing has "Generate my weekly report":', body.includes('Generate my weekly report'));

  console.log('\n=== STEP 2: Navigate to /resume ===');
  await page.goto('http://localhost:3009/resume', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await new Promise((r) => setTimeout(r, 2000));
  body = await page.evaluate(() => document.body.innerText);
  console.log('Resume page has "Choose File":', body.includes('Choose File'));

  console.log('\n=== STEP 3: Upload resume ===');
  const fileChooserPromise = page.waitForFileChooser({ timeout: 5000 });
  const labelHandle = await page.evaluateHandle(() => document.querySelector('label[for="file-input"]'));
  await labelHandle.asElement().click();
  const fileChooser = await fileChooserPromise;
  await fileChooser.accept(['C:\\Users\\atulk\\OneDrive\\Desktop\\Pratik_Assignment\\frontend\\test.pdf']);
  await new Promise((r) => setTimeout(r, 1500));

  console.log('\n=== STEP 4: Click Analyze Resume ===');
  const analyzeBtn = await page.evaluateHandle(() => {
    const buttons = Array.from(document.querySelectorAll('button'));
    return buttons.find((b) => b.textContent.trim() === 'Analyze Resume');
  });
  await analyzeBtn.asElement().click();

  // Wait for upload to complete
  for (let i = 0; i < 12; i++) {
    await new Promise((r) => setTimeout(r, 5000));
    const text = await page.evaluate(() => document.body.innerText);
    if (text.includes('AI RECOMMENDED ROLES') || text.includes('TECH STACK BREAKDOWN')) {
      break;
    }
  }
  body = await page.evaluate(() => document.body.innerText);
  console.log('Upload success - has "TECH STACK BREAKDOWN":', body.includes('TECH STACK BREAKDOWN'));

  console.log('\n=== STEP 5: Navigate to /companies ===');
  await page.goto('http://localhost:3009/companies', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await new Promise((r) => setTimeout(r, 3000));
  body = await page.evaluate(() => document.body.innerText);
  console.log('Companies page has "Anthropic":', body.includes('Anthropic'));
  console.log('Companies page has "Perplexity":', body.includes('Perplexity'));

  console.log('\n=== STEP 6: Click a company card ===');
  await page.goto('http://localhost:3009/company/Anthropic', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await new Promise((r) => setTimeout(r, 3000));
  body = await page.evaluate(() => document.body.innerText);
  console.log('Company details has "COMPANY INTELLIGENCE":', body.includes('COMPANY INTELLIGENCE'));

  console.log('\n=== STEP 6b: Generate cover letter ===');
  const coverBtn = await page.evaluateHandle(() => {
    const buttons = Array.from(document.querySelectorAll('button'));
    return buttons.find((b) => b.textContent.trim().includes('Generate AI Cover Letter'));
  });
  await coverBtn.asElement().click();
  console.log('Cover letter button clicked, waiting up to 90s...');
  for (let i = 0; i < 18; i++) {
    await new Promise((r) => setTimeout(r, 5000));
    const text = await page.evaluate(() => document.body.innerText);
    if (text.includes('Dear Hiring Team')) {
      console.log(`Cover letter rendered after ${(i + 1) * 5}s`);
      break;
    }
  }
  body = await page.evaluate(() => document.body.innerText);
  console.log('Has "Dear Hiring Team":', body.includes('Dear Hiring Team'));

  console.log('\n=== STEP 7: Dashboard ===');
  await page.goto('http://localhost:3009/dashboard', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await new Promise((r) => setTimeout(r, 3000));
  body = await page.evaluate(() => document.body.innerText);
  console.log('Dashboard loads:', body.includes('WEEKLY CAREER INTELLIGENCE'));

  console.log('\n=== ALL API CALLS ===');
  apiCalls.forEach((c) => console.log(c));

  console.log('\n=== FAILED REQUESTS ===');
  failedRequests.forEach((r) => console.log(r));

  console.log('\n=== PAGE ERRORS ===');
  errors.forEach((e) => console.log(e));

  await browser.close();
  console.log('\n=== END-TO-END TEST COMPLETE ===');
})().catch((err) => {
  console.error('TEST FAILED:', err);
  process.exit(1);
});
