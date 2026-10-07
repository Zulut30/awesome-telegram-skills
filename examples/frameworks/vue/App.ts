/** Vue view: useTelegramBridge returns a read-only ref that follows the bridge; it unsubscribes with the component. */
import {defineComponent, h, type PropType} from 'vue';
import type {TelegramBridge} from '@awesome-telegram/patterns';
import {useTelegramBridge} from '@awesome-telegram/patterns/vue';

export const App = defineComponent({
  props: {bridge: {type: Object as PropType<TelegramBridge>, required: true}},
  setup(props) {
    const snapshot = useTelegramBridge(props.bridge);
    return () => h('main', {'data-scheme': snapshot.value.colorScheme,
      style: {background: snapshot.value.theme['bg_color'], color: snapshot.value.theme['text_color']}}, [
      h('h1', snapshot.value.insideTelegram ? 'Telegram' : 'Browser'),
      h('p', `Scheme: ${snapshot.value.colorScheme}; height: ${snapshot.value.stableHeight ?? 'unknown'}`),
    ]);
  },
});
