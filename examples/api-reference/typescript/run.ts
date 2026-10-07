import {referenceBridge} from './bridge.js';
import {referenceClient} from './client.js';
import {referenceDraft} from './draft.js';
import {referenceNative} from './native.js';
import {referenceErrors} from './errors.js';
import {referenceInitData} from './init-data.js';

export async function runReference(document: Document): Promise<string[]> {
  referenceBridge(document); await referenceClient(); referenceDraft(); referenceNative(); referenceErrors();
  await referenceInitData();
  return ['bridge', 'client', 'draft', 'native', 'errors', 'init_data'];
}
