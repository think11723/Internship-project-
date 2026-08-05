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

  console.log('\n=== STEP 1: Landing page ===');
  await page.goto('http://localhost:3009/', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await new Promise((r) => setTimeout(r, 2000));
  let title = await page.title();
  console.log('Title:', title);
  let body = await page.evaluate(() => document.body.innerText);
  console.log('Has "Generate my weekly report":', body.includes('Generate my weekly report'));

  console.log('\n=== STEP 2: Navigate to /resume ===');
  await page.goto('http://localhost:3009/resume', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await new Promise((r) => setTimeout(r, 2000));
  body = await page.evaluate(() => document.body.innerText);
  console.log('Has "Choose File":', body.includes('Choose File'));
  console.log('Has "Drop your resume here":', body.includes('Drop your resume here'));

  console.log('\n=== STEP 3: Upload resume ===');
  const fileChooserPromise = page.waitForFileChooser({ timeout: 5000 });
  const labelHandle = await page.evaluateHandle(() => document.querySelector('label[for="file-input"]'));
  await labelHandle.asElement().click();
  const fileChooser = await fileChooserPromise;
  await fileChooser.accept(['C:\\Users\\atulk\\OneDrive\\Desktop\\Pratik_Assignment\\frontend\\test.pdf']);
  console.log('File selected');
  await new Promise((r) => setTimeout(r, 1500));

  console.log('\n=== STEP 4: Click Analyze Resume ===');
  const analyzeBtn = await page.evaluateHandle(() => {
    const buttons = Array.from(document.querySelectorAll('button'));
    return buttons.find((b) => b.textContent.trim() === 'Analyze Resume');
  });
  const btn = analyzeBtn.asElement();
  if (btn) {
    await btn.click();
    console.log('Analyze Resume clicked');
  } else {
    console.log('Analyze Resume button not found');
  }

  // Wait for upload to complete
  console.log('=== Waiting for upload to complete ===');
  for (let i = 0; i < 12; i++) {
    await new Promise((r) => setTimeout(r, 5000));
    const text = await page.evaluate(() => document.body.innerText);
    if (text.includes('AI RECOMMENDED ROLES') || text.includes('TECH STACK BREAKDOWN')) {
      console.log(`Upload completed after ${(i + 1) * 5}s`);
      break;
    }
  }

  body = await page.evaluate(() => document.body.innerText);
  console.log('Has "AI RECOMMENDED ROLES":', body.includes('AI RECOMMENDED ROLES'));
  console.log('Has "TECH STACK BREAKDOWN":', body.includes('TECH STACK BREAKDOWN'));

  console.log('\n=== STEP 5: Navigate to /companies ===');
  await page.goto('http://localhost:3009/companies', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await new Promise((r) => setTimeout(r, 3000));
  body = await page.evaluate(() => document.body.innerText);
  const hasPerplexity = body.includes('Perplexity');
  const hasAnthropic = body.includes('Anthropic');
  console.log('Has "Perplexity":', hasPerplexity);
  console.log('Has "Anthropic":', hasAnthropic);

  console.log('\n=== STEP 6: Click a company card ===');
  const companyLinks = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('a')).filter(a => a.href.includes('/company/')).map(a => a.href);
  });
  console.log('Company links found:', companyLinks.length);
  if (companyLinks.length > 0) {
    await page.goto(companyLinks[0], { waitUntil: 'domcontentloaded', timeout: 30000 });
    await new Promise((r) => setTimeout(r, 3000));
    body = await page.evaluate(() => document.body.innerText);
    console.log('Has "COMPANY INTELLIGENCE":', body.includes('COMPANY INTELLIGENCE'));
    console.log('Has "AI MATCH ANALYSIS":', body.includes('AI MATCH ANALYSIS'));
    console.log('Has "PERSONALIZED COVER LETTER":', body.includes('PERSONALIZED COVER LETTER'));

    // Click "Generate AI Cover Letter"
    console.log('\n=== STEP 6b: Generate cover letter ===');
    const coverBtn = await page.evaluateHandle(() => {
      const buttons = Array.from(document.querySelectorAll('button'));
      return buttons.find((b) => b.textContent.trim().includes('Generate AI Cover Letter'));
    });
    const coverBtnEl = coverBtn.asElement();
    if (coverBtnEl) {
      await coverBtnEl.click();
      console.log('Generate AI Cover Letter clicked');
      // Wait for cover letter
      for (let i = 0; i < 15; i++) {
        await new Promise((r) => setTimeout(r, 5000));
        const text = await page.evaluate(() => document.body.innerText);
        if (text.includes('Dear Hiring Team')) {
          console.log(`Cover letter rendered after ${(i + 1) * 5}s`);
          break;
        }
      }
      body = await page.evaluate(() => document.body.innerText);
      console.log('Has "Dear Hiring Team":', body.includes('Dear Hiring Team'));
    }
  }

  console.log('\n=== STEP 7: Navigate to /dashboard and generate ===');
  await page.goto('http://localhost:3009/dashboard', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await new Promise((r) => setTimeout(r, 3000));
  const genBtn = await page.evaluateHandle(() => {
    const buttons = Array.from(document.querySelectorAll('button'));
    return buttons.find((b) => b.textContent.trim() === 'Generate Weekly Report');
  });
  const genBtnEl = genBtn.asElement();
  if (genBtnEl && !genBtnEl.disabled) {
    await genBtnEl.click();
    console.log('Generate Weekly Report clicked');
    // Wait for report
    for (let i = 0; i < 18; i++) {
      await new Promise((r) => setTimeout(r, 5000));
      const text = await page.evaluate(() => document.body.innerText);
      if (text.includes('TOP OPPORTUNITIES') || text.includes('AI Generated Cover Letter')) {
        console.log(`Report rendered after ${(i + 1) * 5}s`);
        break;
      }
    }
    body = await page.evaluate(() => document.body.innerText);
    console.log('Has "TOP OPPORTUNITIES":', body.includes('TOP OPPORTUNITIES'));
    console.log('Has "MARKET INTELLIGENCE":', body.includes('MARKET INTELLIGENCE'));
  }

  console.log('\n=== API CALLS ===');
  apiCalls.forEach((c) => console.log(c));

  console.log('\n=== ERRORS ===');
  errors.forEach((e) => console.log(e));

  await browser.close();
  console.log('\n=== END-TO-END COMPLETE ===');
})().catch((err) => {
  console.error('TEST FAILED:', err);
  process.exit(1);
});
