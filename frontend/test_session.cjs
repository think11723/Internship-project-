const puppeteer = require('puppeteer');

(async () => {
  const browser = await puppeteer.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });
  const page = await browser.newPage();

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

  // Check sessionStorage
  const storageBefore = await page.evaluate(() => {
    const keys = Object.keys(sessionStorage);
    const data = {};
    keys.forEach((k) => {
      const v = sessionStorage.getItem(k);
      data[k] = v ? v.length : 0;
    });
    return { keys, sizes: data };
  });
  console.log('SessionStorage before reload:', JSON.stringify(storageBefore));

  console.log('\n=== Reload page ===');
  await page.reload({ waitUntil: 'domcontentloaded' });
  await new Promise((r) => setTimeout(r, 5000));

  const storageAfter = await page.evaluate(() => {
    const keys = Object.keys(sessionStorage);
    const data = {};
    keys.forEach((k) => {
      const v = sessionStorage.getItem(k);
      data[k] = v ? v.length : 0;
    });
    return { keys, sizes: data };
  });
  console.log('SessionStorage after reload:', JSON.stringify(storageAfter));

  body = await page.evaluate(() => document.body.innerText);
  console.log('After reload, has TOP OPPORTUNITIES:', body.includes('TOP OPPORTUNITIES'));
  console.log('After reload, has Awaits:', body.includes('Awaits'));
  console.log('Body preview:', body.substring(0, 500));

  await browser.close();
})().catch((err) => {
  console.error('TEST FAILED:', err);
  process.exit(1);
});
