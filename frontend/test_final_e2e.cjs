const puppeteer = require('puppeteer');

(async () => {
  const browser = await puppeteer.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });
  const page = await browser.newPage();

  const errors = [];
  page.on('pageerror', (err) => errors.push(`PAGE ERROR: ${err.message}`));
  const consoleErrors = [];
  page.on('console', (msg) => {
    if (msg.type() === 'error') consoleErrors.push(msg.text());
  });

  console.log('=== STEP 1: Landing ===');
  await page.goto('http://localhost:3009/', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await new Promise((r) => setTimeout(r, 2000));
  let body = await page.evaluate(() => document.body.innerText);
  console.log('Has "Generate my weekly report":', body.includes('Generate my weekly report'));
  console.log('Has "AI Career Intelligence":', body.includes('AI Career Intelligence'));

  console.log('\n=== STEP 2: Navigation (Resume) ===');
  await page.goto('http://localhost:3009/resume', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await new Promise((r) => setTimeout(r, 3000));
  body = await page.evaluate(() => document.body.innerText);
  console.log('Has "Choose File":', body.includes('Choose File'));
  console.log('Has "Current Resume" (if exists):', body.includes('Current Resume'));

  console.log('\n=== STEP 3: Navigation (Companies) ===');
  await page.goto('http://localhost:3009/companies', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await new Promise((r) => setTimeout(r, 3000));
  body = await page.evaluate(() => document.body.innerText);
  console.log('Has "Discover Funded AI Startups":', body.includes('Discover Funded AI Startups'));
  console.log('Has "Anthropic":', body.includes('Anthropic'));

  console.log('\n=== STEP 4: Company Details ===');
  await page.goto('http://localhost:3009/company/Anthropic', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await new Promise((r) => setTimeout(r, 3000));
  body = await page.evaluate(() => document.body.innerText);
  console.log('Has "COMPANY INTELLIGENCE":', body.includes('COMPANY INTELLIGENCE'));
  console.log('Has "AI MATCH ANALYSIS":', body.includes('AI MATCH ANALYSIS'));
  console.log('Has "Overall Match":', body.includes('Overall Match'));

  console.log('\n=== STEP 5: Dashboard ===');
  await page.goto('http://localhost:3009/dashboard', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await new Promise((r) => setTimeout(r, 3000));
  body = await page.evaluate(() => document.body.innerText);
  console.log('Has "WEEKLY CAREER INTELLIGENCE":', body.includes('WEEKLY CAREER INTELLIGENCE'));

  console.log('\n=== Accessibility Audit ===');
  const audit = await page.evaluate(() => {
    const buttons = document.querySelectorAll('button');
    const links = document.querySelectorAll('a[href]');
    const landmarks = document.querySelectorAll('nav, main, header, footer');
    const headings = document.querySelectorAll('h1, h2, h3, h4, h5, h6');

    const buttonInfo = Array.from(buttons).slice(0, 5).map((b) => ({
      text: b.textContent.trim().substring(0, 30),
      hasLabel: b.hasAttribute('aria-label') || b.textContent.trim().length > 0,
      focusable: b.tabIndex >= 0,
    }));

    const linkInfo = Array.from(links).slice(0, 5).map((l) => ({
      text: l.textContent.trim().substring(0, 30),
      hasHref: l.hasAttribute('href'),
    }));

    return {
      buttonCount: buttons.length,
      linkCount: links.length,
      landmarkCount: landmarks.length,
      headingCount: headings.length,
      headingOutline: Array.from(headings).map((h) => `${h.tagName}: ${h.textContent.trim().substring(0, 40)}`),
      buttonsSample: buttonInfo,
      linksSample: linkInfo,
    };
  });
  console.log('Buttons:', audit.buttonCount);
  console.log('Links:', audit.linkCount);
  console.log('Landmarks:', audit.landmarkCount);
  console.log('Headings:', audit.headingCount);
  console.log('First 5 buttons:', JSON.stringify(audit.buttonsSample, null, 2));
  console.log('Heading outline:');
  audit.headingOutline.forEach((h) => console.log('  ', h));

  console.log('\n=== ERRORS ===');
  console.log('Page errors:', errors.length);
  errors.forEach((e) => console.log(e));
  console.log('Console errors:', consoleErrors.length);
  consoleErrors.forEach((e) => console.log(e));

  await browser.close();
  console.log('\n=== DONE ===');
})().catch((err) => {
  console.error('TEST FAILED:', err);
  process.exit(1);
});
