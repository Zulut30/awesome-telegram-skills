import {referenceBridge} from './bridge.js';
import {referenceClient} from './client.js';
import {referenceDraft} from './draft.js';
import {referenceNative} from './native.js';
import {referenceErrors} from './errors.js';
import {referenceInitData} from './init-data.js';
import {referenceState} from './state.js';
import {referenceUi} from './ui.js';
import {referenceFlows} from './flows.js';

export async function runReference(document: Document): Promise<string[]> {
  referenceBridge(document); await referenceClient(); referenceDraft(); referenceNative(); referenceErrors();
  await referenceInitData();
  await referenceState();
  await referenceUi(document);
  await referenceFlows(document);
  return ['bridge', 'client', 'draft', 'native', 'errors', 'init_data', 'state', 'ui', 'flows'];
}
