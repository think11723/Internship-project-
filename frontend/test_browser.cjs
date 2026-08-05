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

  let failedRequest = false;
  page.on('requestfailed', (req) => {
    failedRequest = true;
    console.log('REQUEST FAILED:', req.url(), '-', req.failure()?.errorText);
  });

  console.log('=== Navigate to /resume ===');
  await page.goto('http://localhost:3009/resume', { waitUntil: 'networkidle0', timeout: 15000 });
  await new Promise((r) => setTimeout(r, 1000));

  // Click Choose File and upload
  console.log('=== Trigger file picker and upload ===');
  const fileChooserPromise = page.waitForFileChooser({ timeout: 5000 });
  const labelHandle = await page.evaluateHandle(() => document.querySelector('label[for="file-input"]'));
  await labelHandle.asElement().click();
  const fileChooser = await fileChooserPromise;
  await fileChooser.accept(['C:\\Users\\atulk\\OneDrive\\Desktop\\Pratik_Assignment\\frontend\\test.pdf']);
  await new Promise((r) => setTimeout(r, 1000));

  // Click "Analyze Resume" button
  console.log('=== Click Analyze Resume ===');
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

  // Wait for upload to complete and analysis view to show
  await new Promise((r) => setTimeout(r, 15000));

  const body = await page.evaluate(() => document.body.innerText);
  console.log('=== Body after Analyze Resume ===');
  console.log(body.substring(0, 2000));

  console.log('Failed request:', failedRequest);
  console.log('=== Errors ===');
  errors.forEach((e) => console.log(e));

  await browser.close();
  console.log('=== DONE ===');
})().catch((err) => {
  console.error('TEST FAILED:', err);
  process.exit(1);
});
