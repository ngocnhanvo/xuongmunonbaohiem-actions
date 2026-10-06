import { chromium } from 'playwright';

const ADMIN_URL = process.env.WP_ADMIN_URL;
const USERNAME = process.env.WP_ADMIN_USERNAME;
const PASSWORD = process.env.WP_ADMIN_PASSWORD;

if (!ADMIN_URL || !USERNAME || !PASSWORD) {
  throw new Error('Missing WP_ADMIN_URL / WP_ADMIN_USERNAME / WP_ADMIN_PASSWORD secrets.');
}

const origin = new URL(ADMIN_URL).origin;
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
const page = await context.newPage();

async function visible(locator) {
  try {
    return await locator.first().isVisible({ timeout: 1000 });
  } catch {
    return false;
  }
}

function solveArithmetic(text) {
  const match = text.match(/(\d+)\s*([+\-x×*])\s*(\d+)\s*(?:=|\?)/i)
    || text.match(/(\d+)\s*([+\-x×*])\s*(\d+)/i);
  if (!match) return null;
  const a = Number(match[1]);
  const b = Number(match[3]);
  switch (match[2]) {
    case '+': return a + b;
    case '-': return a - b;
    case 'x':
    case '×':
    case '*': return a * b;
    default: return null;
  }
}

async function findCaptchaInput() {
  const selectors = [
    'input[name*="captcha" i]',
    'input[id*="captcha" i]',
    'input[name*="math" i]',
    'input[id*="math" i]',
    'input[name*="arith" i]',
    'input[id*="arith" i]',
    'input[type="number"]',
  ];

  for (const selector of selectors) {
    const candidate = page.locator(`#loginform ${selector}`).first();
    if (await visible(candidate)) return candidate;
  }

  const candidates = page.locator('#loginform input:visible:not(#user_login):not(#user_pass):not(#wp-submit):not([type="hidden"]):not([type="checkbox"]):not([type="submit"])');
  const count = await candidates.count();
  if (count === 1) return candidates.first();

  if (count > 1) {
    for (let index = 0; index < count; index += 1) {
      const candidate = candidates.nth(index);
      const type = (await candidate.getAttribute('type') || '').toLowerCase();
      const autocomplete = (await candidate.getAttribute('autocomplete') || '').toLowerCase();
      if (type === 'number' || autocomplete === 'off') return candidate;
    }
  }

  return null;
}

async function login() {
  await page.goto(`${origin}/wp-admin/`, { waitUntil: 'domcontentloaded', timeout: 60000 });
  const userInput = page.locator('#user_login');

  if (!(await visible(userInput))) {
    if (page.url().includes('/wp-admin/')) return;
    throw new Error(`Unexpected WordPress login page: ${page.url()}`);
  }

  await userInput.fill(USERNAME);
  await page.locator('#user_pass').fill(PASSWORD);

  const answer = solveArithmetic(await page.locator('body').innerText());
  if (answer !== null) {
    const captchaInput = await findCaptchaInput();
    if (!captchaInput) throw new Error('Arithmetic CAPTCHA detected but input was not found.');
    await captchaInput.fill(String(answer));
  }

  await Promise.all([
    page.waitForLoadState('domcontentloaded'),
    page.locator('#wp-submit').click(),
  ]);

  if (page.url().includes('wp-login.php') || await visible(page.locator('#login_error'))) {
    const loginError = await page.locator('#login_error').textContent().catch(() => '');
    throw new Error(`WordPress login failed. ${loginError || ''}`.trim());
  }
}

try {
  await login();
  await page.goto(`${origin}/wp-admin/admin.php?page=vcs-build-trigger`, {
    waitUntil: 'domcontentloaded',
    timeout: 60000,
  });

  await page.waitForFunction(() => Boolean(globalThis.vcsBuild?.ajax_url && globalThis.vcsBuild?.nonce), null, {
    timeout: 30000,
  });

  const result = await page.evaluate(async () => {
    const body = new URLSearchParams({
      action: 'vcs_trigger_build',
      nonce: globalThis.vcsBuild.nonce,
    });

    const response = await fetch(globalThis.vcsBuild.ajax_url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8' },
      body: body.toString(),
    });

    const raw = await response.text();
    let payload;
    try {
      payload = JSON.parse(raw);
    } catch {
      payload = { raw };
    }

    return { status: response.status, payload };
  });

  if (result.status !== 200 || result.payload?.success !== true) {
    const message = result.payload?.data?.message || result.payload?.raw || JSON.stringify(result.payload);
    throw new Error(`Build Website trigger failed (HTTP ${result.status}): ${message}`);
  }

  console.log(`WordPress Build Website accepted the GitHub dispatch: ${result.payload?.data?.message || 'success'}`);
} finally {
  await browser.close();
}
