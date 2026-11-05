import {spawn} from 'node:child_process';
import {mkdtemp, readFile, realpath, rm} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';

export async function ownedChrome(chromium, executablePath, noDefaults = true) {
  if (!executablePath) throw Error('Explicit Chrome executable is required for isolated lifecycle');
  const profile = await mkdtemp(path.join(os.tmpdir(), 'telegram-lifecycle-owned-'));
  const resolvedProfile = await realpath(profile), parent = await realpath(os.tmpdir());
  const flags = ['--headless=new', '--remote-debugging-port=0', `--user-data-dir=${profile}`,
    '--disable-background-networking', '--disable-component-update', '--no-first-run',
    '--no-default-browser-check', '--disable-default-apps', '--disable-extensions', 'about:blank'];
  const environment = Object.fromEntries(Object.entries(process.env).filter(([key]) =>
    ['PATH', 'PATHEXT', 'SYSTEMROOT', 'WINDIR', 'COMSPEC', 'TEMP', 'TMP', 'TMPDIR',
      'HOME', 'USERPROFILE', 'LOCALAPPDATA', 'LANG', 'LC_ALL', 'DISPLAY', 'XAUTHORITY'].includes(key.toUpperCase())));
  const child = spawn(executablePath, flags, {windowsHide: true, stdio: ['ignore', 'ignore', 'pipe'], env: environment});
  let exited = false, spawnError, stderr = '', browser;
  child.on('error', error => {spawnError = error;exited = true;});
  const exit = new Promise(resolve => child.once('exit', (code, signal) => {exited = true;resolve({code, signal});}));
  child.stderr.on('data', bytes => {stderr = (stderr + bytes.toString()).slice(-65536);});
  const cleanup = async () => {
    if (browser) {
      try {const session = await browser.newBrowserCDPSession();await session.send('Browser.close');} catch {}
      try {await browser.close();} catch {}
    }
    if (!exited) await Promise.race([exit, new Promise(resolve => setTimeout(resolve, 3000))]);
    if (!exited) {child.kill();await Promise.race([exit, new Promise(resolve => setTimeout(resolve, 3000))]);}
    let profileRemoved = false;
    if (exited && await realpath(profile) === resolvedProfile && path.dirname(resolvedProfile) === parent && path.basename(resolvedProfile).startsWith('telegram-lifecycle-owned-')) {
      await rm(resolvedProfile, {recursive: true, force: false, maxRetries: 10, retryDelay: 100});profileRemoved = true;
    }
    return {owned_process_exited: exited, owned_profile_removed: profileRemoved,
      stderr_has_devtools_listener: stderr.includes('DevTools listening')};
  };
  try {
    let endpoint;
    const deadline = performance.now() + 15000;
    while (performance.now() < deadline) {
      if (spawnError) throw spawnError;
      if (exited) throw Error('Owned Chrome exited before CDP ready');
      const port = await readFile(path.join(profile, 'DevToolsActivePort'), 'utf8').catch(() => '');
      const lines = port.trim().split(/\r?\n/);
      if (/^\d+$/.test(lines[0]) && /^\/devtools\/browser\/[a-z0-9-]+$/.test(lines[1] ?? '')) {
        endpoint = `ws://127.0.0.1:${lines[0]}${lines[1]}`;break;
      }
      await new Promise(resolve => setTimeout(resolve, 25));
    }
    if (!endpoint) throw Error('Owned Chrome CDP readiness timeout');
    browser = await chromium.connectOverCDP(endpoint, {noDefaults, timeout: 10000});
    return {browser, close: cleanup,
      profile: {owned: true, headless: true, noDefaults, backgrounding_disabling_flags: false}};
  } catch (error) {await cleanup();throw error;}
}
