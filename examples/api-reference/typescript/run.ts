import {referenceBridge} from './bridge.js';
import {referenceClient} from './client.js';
import {referenceDraft} from './draft.js';
import {referenceNative} from './native.js';
import {referenceErrors} from './errors.js';

export async function runReference(document: Document): Promise<string[]> {
  referenceBridge(document); await referenceClient(); referenceDraft(); referenceNative(); referenceErrors();
  return ['bridge', 'client', 'draft', 'native', 'errors'];
}
