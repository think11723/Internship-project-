const puppeteer = require('puppeteer');

(async () => {
  const browser = await puppeteer.launch({
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox'],
  });
  const page = await browser.newPage();

  await page.goto('http://localhost:3009/company/Anthropic', { waitUntil: 'domcontentloaded', timeout: 30000 });
  await new Promise((r) => setTimeout(r, 3000));

  // Get the specific text around "match"
  const matchText = await page.evaluate(() => {
    const elem = Array.from(document.querySelectorAll('*')).find(
      (e) => e.textContent.trim().toLowerCase() === 'overall match'
    );
    if (elem) {
      return {
        tag: elem.tagName,
        text: elem.textContent,
        parentClass: elem.parentElement?.className,
        grandparentClass: elem.parentElement?.parentElement?.className,
      };
    }
    return null;
  });

  console.log('Match score element:', JSON.stringify(matchText, null, 2));

  // Look for the score number
  const scoreText = await page.evaluate(() => {
    const elements = Array.from(document.querySelectorAll('p, span, h1, h2, h3, h4'));
    return elements.filter((e) => /^\d{2,3}$/.test(e.textContent.trim())).map((e) => ({
      tag: e.tagName,
      text: e.textContent.trim(),
      class: e.className,
    }));
  });
  console.log('Score numbers:', JSON.stringify(scoreText, null, 2));

  // Get the heading outline
  const headings = await page.evaluate(() => {
    return Array.from(document.querySelectorAll('h1, h2, h3, h4, h5, h6')).map((h) => ({
      tag: h.tagName,
      text: h.textContent.trim(),
    }));
  });
  console.log('Heading outline:', JSON.stringify(headings, null, 2));

  await browser.close();
})().catch((err) => {
  console.error('TEST FAILED:', err);
  process.exit(1);
});
