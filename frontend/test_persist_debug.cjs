const puppeteer = require('puppeteer');

(async () => {
  const browser = await puppeteer.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });
  const page = await browser.newPage();

  page.on('pageerror', (err) => console.log('PAGE ERROR:', err.message));

  console.log('=== Generate report ===');
  await page.goto('http://localhost:3009/dashboard', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await new Promise((r) => setTimeout(r, 5000));

  const genBtn = await page.evaluateHandle(() => {
    const buttons = Array.from(document.querySelectorAll('button'));
    return buttons.find((b) => b.textContent.trim() === 'Generate Weekly Report');
  });
  await genBtn.asElement().click();

  for (let i = 0; i < 24; i++) {
    await new Promise((r) => setTimeout(r, 5000));
    const text = await page.evaluate(() => document.body.innerText);
    if (text.includes('TOP OPPORTUNITIES') && !text.includes('Generating')) {
      console.log(`Report rendered after ${(i + 1) * 5}s`);
      break;
    }
  }

  // Check sessionStorage RIGHT after generate
  let storage = await page.evaluate(() => {
    const v = sessionStorage.getItem('fundflow:report');
    return v ? { size: v.length, preview: v.substring(0, 200) } : null;
  });
  console.log('SessionStorage after generate:', JSON.stringify(storage));

  // Navigate to /companies
  console.log('\n=== Navigate to /companies ===');
  await page.goto('http://localhost:3009/companies', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await new Promise((r) => setTimeout(r, 1000));

  storage = await page.evaluate(() => {
    const v = sessionStorage.getItem('fundflow:report');
    return v ? { size: v.length } : null;
  });
  console.log('SessionStorage after /companies:', JSON.stringify(storage));

  // Navigate to /resume
  console.log('\n=== Navigate to /resume ===');
  await page.goto('http://localhost:3009/resume', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await new Promise((r) => setTimeout(r, 3000));

  storage = await page.evaluate(() => {
    const v = sessionStorage.getItem('fundflow:report');
    return v ? { size: v.length } : null;
  });
  console.log('SessionStorage after /resume:', JSON.stringify(storage));

  // Navigate to /dashboard
  console.log('\n=== Navigate back to /dashboard ===');
  await page.goto('http://localhost:3009/dashboard', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await new Promise((r) => setTimeout(r, 5000));

  storage = await page.evaluate(() => {
    const v = sessionStorage.getItem('fundflow:report');
    return v ? { size: v.length } : null;
  });
  console.log('SessionStorage after /dashboard:', JSON.stringify(storage));

  let body = await page.evaluate(() => document.body.innerText);
  console.log('Has TOP OPPORTUNITIES:', body.includes('TOP OPPORTUNITIES'));
  console.log('Has Awaits:', body.includes('Awaits'));
  console.log('Body preview:', body.substring(0, 500));

  await browser.close();
})().catch((err) => {
  console.error('TEST FAILED:', err);
  process.exit(1);
});
