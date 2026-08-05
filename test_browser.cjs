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
  page.on('requestfailed', (req) => {
    errors.push(`REQUEST FAILED: ${req.url()} - ${req.failure()?.errorText}`);
  });

  console.log('=== Navigating to http://localhost:3009 ===');
  await page.goto('http://localhost:3009', { waitUntil: 'networkidle0', timeout: 15000 });

  console.log('=== Landing page title ===');
  const title = await page.title();
  console.log('Title:', title);

  console.log('=== Console logs ===');
  consoleLogs.forEach((l) => console.log(l));

  console.log('=== Errors ===');
  errors.forEach((e) => console.log(e));

  // Navigate to /resume
  console.log('=== Navigate to /resume ===');
  await page.goto('http://localhost:3009/resume', { waitUntil: 'networkidle0', timeout: 15000 });
  await new Promise((r) => setTimeout(r, 1000));

  // Check what's on the page
  const bodyText = await page.evaluate(() => document.body.innerText);
  console.log('=== Body text on /resume (first 500 chars) ===');
  console.log(bodyText.substring(0, 500));

  // Check if file input exists
  const fileInputExists = await page.evaluate(() => {
    const input = document.getElementById('file-input');
    if (!input) return { exists: false };
    return {
      exists: true,
      type: input.type,
      accept: input.accept,
      hasOnChange: !!input.onchange,
      parentDisplay: window.getComputedStyle(input.parentElement).display,
      ownDisplay: window.getComputedStyle(input).display,
    };
  });
  console.log('=== File input ===');
  console.log(JSON.stringify(fileInputExists, null, 2));

  // Check if Choose File button exists
  const buttonInfo = await page.evaluate(() => {
    const buttons = Array.from(document.querySelectorAll('button'));
    const chooseBtn = buttons.find((b) => b.textContent.trim() === 'Choose File');
    if (!chooseBtn) return { exists: false };
    const rect = chooseBtn.getBoundingClientRect();
    return {
      exists: true,
      visible: rect.width > 0 && rect.height > 0,
      pointerEvents: window.getComputedStyle(chooseBtn).pointerEvents,
      position: window.getComputedStyle(chooseBtn).position,
      opacity: window.getComputedStyle(chooseBtn).opacity,
      disabled: chooseBtn.disabled,
      onClick: !!chooseBtn.onclick,
      rect: { x: rect.x, y: rect.y, width: rect.width, height: rect.height },
    };
  });
  console.log('=== Choose File button ===');
  console.log(JSON.stringify(buttonInfo, null, 2));

  // Try clicking it
  console.log('=== Clicking Choose File ===');
  let fileDialogOpened = false;
  page.on('filechooser', () => {
    fileDialogOpened = true;
    console.log('FILE CHOOSER OPENED!');
  });
  await page.click('button:has-text("Choose File")').catch((err) => {
    console.log('Click failed:', err.message);
  });
  await new Promise((r) => setTimeout(r, 500));
  console.log('File dialog opened:', fileDialogOpened);

  // Check final errors
  console.log('=== Final errors ===');
  errors.forEach((e) => console.log(e));

  await browser.close();
  console.log('=== DONE ===');
})().catch((err) => {
  console.error('TEST FAILED:', err);
  process.exit(1);
});
