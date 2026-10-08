<script>
  // Svelte view: the store follows the bridge; `$snapshot` subscribes and unsubscribes with the component.
  import {telegramBridgeStore} from '@awesome-telegram/patterns/svelte';
  let {bridge} = $props();
  const snapshot = $derived(telegramBridgeStore(bridge));
</script>

<main data-scheme={$snapshot.colorScheme} style:background={$snapshot.theme.bg_color} style:color={$snapshot.theme.text_color}>
  <h1>{$snapshot.insideTelegram ? 'Telegram' : 'Browser'}</h1>
  <p>Scheme: {$snapshot.colorScheme}; height: {$snapshot.stableHeight ?? 'unknown'}</p>
</main>
