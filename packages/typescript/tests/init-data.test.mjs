import assert from 'node:assert/strict';
import {createHmac, generateKeyPairSync, sign} from 'node:crypto';
import test from 'node:test';
import {InvalidInitData, TELEGRAM_PUBLIC_KEYS, UnsupportedCapability, ValidationFailure, verifyInitDataSignature} from '../dist/index.js';

// Independent vector from aiogram's test suite (its own key pair, bot 42), not produced by this code.
const AIOGRAM_KEY = Uint8Array.from(Buffer.from('4112765021341e5415e772cd65903f6b94e3ea1c2ab669e6d3e18ee2db00da61', 'hex'));
const AIOGRAM_FIELDS = 'auth_date=1650385342&user=%7B%22id%22%3A42%2C%22first_name%22%3A%22Test%22%7D&query_id=test';
const AIOGRAM_RAW = `${AIOGRAM_FIELDS}&hash=123&signature=JQ0JR2tjC65yq_jNZV0wuJVX6J-SWPMV0mprUXG34g-NvxL4RcF1Rz5n4VVo00VRghEUBf5t___uoeb1-jU_Cw`;
const NOW = 1650385342;

function keyPair() {
  const {publicKey, privateKey} = generateKeyPairSync('ed25519');
  return {privateKey, raw: Uint8Array.from(Buffer.from(publicKey.export({format: 'jwk'}).x, 'base64url'))};
}

function signed(fields, privateKey, botId = 7, token = undefined) {
  const check = `${botId}:WebAppData\n` + Object.keys(fields).sort().map((key) => `${key}=${fields[key]}`).join('\n');
  const all = {...fields, signature: sign(null, Buffer.from(check), privateKey).toString('base64url')};
  if (token !== undefined) { // the bot owner's hash covers every field but hash, signature included
    const secret = createHmac('sha256', 'WebAppData').update(token).digest();
    const data = Object.keys(all).sort().map((key) => `${key}=${all[key]}`).join('\n');
    all.hash = createHmac('sha256', secret).update(data).digest('hex');
  }
  return new URLSearchParams(all).toString();
}

test('published keys match the documentation and are frozen', () => {
  assert.equal(TELEGRAM_PUBLIC_KEYS.production, 'e7bf03a2fa4602af4580703d88dda5bb59f32ed8b02a56c187fe7d34caed242d');
  assert.equal(TELEGRAM_PUBLIC_KEYS.test, '40055058a4ee38156a06562e52eece92a771bcd8346a8c4615cb7376eddf72ec');
  assert.ok(Object.isFrozen(TELEGRAM_PUBLIC_KEYS));
});

test('independent aiogram vector passes and every change fails', async () => {
  const launch = await verifyInitDataSignature(AIOGRAM_RAW, 42, {publicKey: AIOGRAM_KEY, now: NOW});
  assert.deepEqual([launch.userId, launch.user.first_name, launch.queryId, launch.authDate], [42, 'Test', 'test', NOW]);
  assert.ok(Object.isFrozen(launch) && Object.isFrozen(launch.user));
  for (const [raw, botId] of [[AIOGRAM_RAW, 43], [AIOGRAM_RAW.replace('-jU_Cw', '-j1U_w'), 42],
    [AIOGRAM_RAW.replace('query_id=test', 'query_id=tesT'), 42], [AIOGRAM_FIELDS, 42]]) {
    await assert.rejects(verifyInitDataSignature(raw, botId, {publicKey: AIOGRAM_KEY, now: NOW}), InvalidInitData);
  }
  for (const environment of ['production', 'test']) {
    await assert.rejects(verifyInitDataSignature(AIOGRAM_RAW, 42, {environment, now: NOW}), InvalidInitData);
  }
});

test('all signed fields; the same launch also carries the bot owner hash', async () => {
  const {privateKey, raw: key} = keyPair();
  const fields = {auth_date: '1000', query_id: 'AAF', chat_type: 'sender', chat_instance: '-77', start_param: 'ref_1', can_send_after: '5',
    user: JSON.stringify({id: 42, first_name: 'Анна', username: 'a&b=c'}), chat: JSON.stringify({id: -100, type: 'group', title: 'Чат'}),
    receiver: JSON.stringify({id: 9, first_name: 'B'})};
  const launch = await verifyInitDataSignature(signed(fields, privateKey, 7, '7:TOKEN'), 7, {publicKey: key, now: 1001});
  assert.deepEqual([launch.user.first_name, launch.chat.title, launch.receiver.id, launch.canSendAfter, launch.chatType, launch.startParam],
    ['Анна', 'Чат', 9, 5, 'sender', 'ref_1']);
});

test('freshness, identity and ambiguity are checked after the signature', async () => {
  const {privateKey, raw: key} = keyPair();
  const raw = signed({auth_date: '1000', user: JSON.stringify({id: 42})}, privateKey);
  for (const [value, now] of [[raw, 1000 + 3600], [raw, 1000 - 31], [signed({auth_date: '1000'}, privateKey), 1001],
    [raw + '&auth_date=1000', 1001], [raw.replace('signature=', 'signature=%2B'), 1001], [raw + '&', 1001], [raw + '&x=%E0%A4', 1001]]) {
    await assert.rejects(verifyInitDataSignature(value, 7, {publicKey: key, now}), InvalidInitData);
  }
});

test('configuration errors and missing Ed25519 support are not launch errors', async () => {
  const {privateKey, raw: key} = keyPair();
  const raw = signed({auth_date: '1000', user: JSON.stringify({id: 42})}, privateKey);
  for (const [botId, options] of [[0, {}], [1.5, {}], ['7', {}], [7, {environment: 'staging'}], [7, {publicKey: key.slice(1)}],
    [7, {publicKey: key, maxAgeSeconds: 0}], [7, {publicKey: key, now: -1}]]) {
    const rejection = await verifyInitDataSignature(raw, botId, {now: 1001, ...options}).then(() => null, (error) => error);
    assert.ok(rejection instanceof ValidationFailure && !(rejection instanceof InvalidInitData), String(botId));
  }
  const noEd25519 = {importKey: async () => { throw new DOMException('Unrecognized name', 'NotSupportedError'); }};
  await assert.rejects(verifyInitDataSignature(raw, 7, {publicKey: key, now: 1001, subtle: noEd25519}), UnsupportedCapability);
});
