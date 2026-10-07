import {InvalidInitData, TELEGRAM_PUBLIC_KEYS, verifyInitDataSignature,
  type InitDataSignatureOptions, type SignedLaunch, type SignedObject} from '@awesome-telegram/patterns';
import {check} from './check.js';

// Независимый вектор из тестов aiogram: их собственная пара ключей и бот 42, не ключ Telegram.
const SIGNED = 'auth_date=1650385342&user=%7B%22id%22%3A42%2C%22first_name%22%3A%22Test%22%7D&query_id=test'
  + '&signature=JQ0JR2tjC65yq_jNZV0wuJVX6J-SWPMV0mprUXG34g-NvxL4RcF1Rz5n4VVo00VRghEUBf5t___uoeb1-jU_Cw';
const FIXTURE_KEY = '4112765021341e5415e772cd65903f6b94e3ea1c2ab669e6d3e18ee2db00da61';

export async function referenceInitData(): Promise<void> {
  const publicKey = Uint8Array.from(FIXTURE_KEY.match(/../g) ?? [], (pair) => Number.parseInt(pair, 16));
  const options: InitDataSignatureOptions = {publicKey, now: 1650385342};
  const launch: SignedLaunch = await verifyInitDataSignature(SIGNED, 42, options);
  const user: SignedObject = launch.user;
  check(launch.userId === 42 && user['first_name'] === 'Test' && launch.queryId === 'test');
  const otherBot = await verifyInitDataSignature(SIGNED, 43, options).then(() => null, (error: unknown) => error);
  check(otherBot instanceof InvalidInitData);
  check(TELEGRAM_PUBLIC_KEYS.production.length === 64); // настоящая initData: {environment: 'production'} без publicKey
  // Сессию, права на объект и защиту от повтора проверяет backend; токен бота здесь не нужен.
}
