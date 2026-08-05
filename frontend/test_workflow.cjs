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
  const responses = [];
  page.on('response', (res) => {
    const url = res.url();
    if (url.includes('/api/')) {
      responses.push(`[${res.status()}] ${res.request().method()} ${url.replace('http://localhost:3009', '')}`);
    }
  });

  console.log('=== STEP 1: Landing ===');
  await page.goto('http://localhost:3009/', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await new Promise((r) => setTimeout(r, 2000));

  console.log('=== STEP 2: Navigate to Dashboard ===');
  await page.goto('http://localhost:3009/dashboard', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await new Promise((r) => setTimeout(r, 3000));

  // Click "Generate Weekly Report"
  console.log('=== STEP 3: Click Generate Weekly Report ===');
  const generateBtn = await page.evaluateHandle(() => {
    const buttons = Array.from(document.querySelectorAll('button'));
    return buttons.find((b) => b.textContent.trim() === 'Generate Weekly Report');
  });
  const btn = generateBtn.asElement();
  if (btn && !btn.disabled) {
    await btn.click();
    console.log('Generate Weekly Report clicked');
  } else {
    console.log('Button not found or disabled');
  }

  // Wait for the workflow to complete (could take 30s for cover letter)
  console.log('=== STEP 4: Wait for workflow to complete (up to 90s) ===');
  let completed = false;
  for (let i = 0; i < 18; i++) {
    await new Promise((r) => setTimeout(r, 5000));
    const text = await page.evaluate(() => document.body.innerText);
    const hasReport = text.includes('Companies Analyzed') ||
                      text.includes('Top Opportunities') ||
                      text.includes('Top Matches') ||
                      text.includes('AI Generated Cover Letter');
    const stillLoading = text.includes('Generating');
    if (hasReport && !stillLoading) {
      console.log(`Workflow completed after ${(i + 1) * 5}s`);
      completed = true;
      break;
    }
    console.log(`...still waiting (${(i + 1) * 5}s) - hasReport=${hasReport} stillLoading=${stillLoading}`);
  }
  if (!completed) console.log('TIMED OUT');

  const body = await page.evaluate(() => document.body.innerText);
  console.log('=== Body after workflow ===');
  console.log(body.substring(0, 2500));

  console.log('=== API responses ===');
  responses.forEach((r) => console.log(r));

  console.log('=== Errors ===');
  errors.forEach((e) => console.log(e));

  await browser.close();
  console.log('=== DONE ===');
})().catch((err) => {
  console.error('TEST FAILED:', err);
  process.exit(1);
});
