import {ApiClient, ApiError, safeErrorReport, type ClientOptions, type RequestOptions,
  type FailureKind, type FetchTransport} from '@awesome-telegram/patterns';
import {check} from './check.js';

/** Local Response fixture; never calls global fetch or an actual backend. */
export async function referenceClient(): Promise<void> {
  let calls = 0;
  const transport: FetchTransport = async () => { calls++; return Response.json({count: 1}); };
  const options: ClientOptions = {baseUrl: 'https://fixture.invalid', fetch: transport, headers: () => ({'X-Example': 'fixture'})};
  const request: RequestOptions = {method: 'GET', timeoutMs: 1000};
  const client = new ApiClient(options);
  const value = await client.request('/count', (body: unknown) => {
    if (typeof body !== 'object' || body === null || !('count' in body) || typeof body.count !== 'number') throw Error('Bad fixture schema');
    return body.count;
  }, request);
  check(value === 1 && calls === 1);
  let writes = 0;
  const unknown = new ApiClient({...options, fetch: async () => { writes++; throw Error('PRIVATE_FIXTURE'); }});
  try { await unknown.request('/orders', body => body, {method: 'POST', body: {product: 'public-id'}}); }
  catch (error) {
    check(error instanceof ApiError);
    const kind: FailureKind = error.kind;
    check(kind === 'network' && error.outcome === 'unknown' && safeErrorReport(error, 'write').recovery === 'reconcile');
    check(writes === 1); return;
  }
  throw Error('Unknown write outcome was not surfaced');
  // Headers/session/ACL/idempotency/сверку операции реализует backend приложения.
}
