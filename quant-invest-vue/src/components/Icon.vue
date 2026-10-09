<script setup>
const props = defineProps({
  name: { type: String, default: '' },
  size: { type: Number, default: 18 },
  className: { type: String, default: '' },
  style: { type: Object, default: null }
})

const paths = {
  market: 'M3 17l5-6 4 3 5-7 4 5M3 21h18M3 3v18',
  news: 'M4 5h13v14H6a2 2 0 01-2-2V5zM17 8h3v9a2 2 0 01-2 2M7 9h7M7 13h7M7 17h4',
  agent: 'M12 2a2 2 0 012 2v1h4a2 2 0 012 2v8a2 2 0 01-2 2H6a2 2 0 01-2-2V7a2 2 0 012-2h4V4a2 2 0 012-2zM9 11a1.5 1.5 0 100 3 1.5 1.5 0 000-3zm6 0a1.5 1.5 0 100 3 1.5 1.5 0 000-3zM2 12v3M22 12v3',
  strategy: 'M6 4h6v6H6zM6 14h6v6H6zM16 8a4 4 0 100 8 4 4 0 000-8zM12 7h2a2 2 0 012 2M12 17h2a2 2 0 002-2',
  account: 'M3 7h18v12H3zM3 7l2-3h14l2 3M3 11h18M16 15h2',
  prefs: 'M12 8a4 4 0 100 8 4 4 0 000-8zM3 12h2m14 0h2M12 3v2m0 14v2M5.6 5.6l1.4 1.4m10 10l1.4 1.4m0-12.8l-1.4 1.4m-10 10l-1.4 1.4',
  logout: 'M9 4H6a2 2 0 00-2 2v12a2 2 0 002 2h3M16 8l4 4-4 4M20 12H9',
  search: 'M11 4a7 7 0 100 14 7 7 0 000-14zM20 20l-4-4',
  bell: 'M18 9a6 6 0 10-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9M10 21h4',
  up: 'M5 15l7-7 7 7',
  down: 'M5 9l7 7 7-7',
  robot: 'M12 2v3M8 8h8a2 2 0 012 2v6a2 2 0 01-2 2H8a2 2 0 01-2-2v-6a2 2 0 012-2zM9 13h.01M15 13h.01M9 16h6M3 12v4M21 12v4',
  chart: 'M4 20V4M4 20h16M8 16v-4M12 16V8M16 16v-6',
  send: 'M22 2L11 13M22 2l-7 20-4-9-9-4 20-7z',
  plus: 'M12 5v14M5 12h14',
  close: 'M6 6l12 12M18 6L6 18',
  check: 'M5 13l4 4L19 7',
  shield: 'M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6l8-3z',
  bolt: 'M13 2L4 14h6l-1 8 9-12h-6l1-8z',
  wallet: 'M3 7h15a2 2 0 012 2v8a2 2 0 01-2 2H5a2 2 0 01-2-2V7zm0 0l1.5-3h11L18 7M16 13h.01',
  star: 'M12 3.6l2.47 5 5.53.8-4 3.9.94 5.53L12 16.9l-4.94 2.6.94-5.53-4-3.9 5.53-.8L12 3.6z',
  doc: 'M6 3h8l4 4v14H6zM14 3v4h4M9 12h6M9 16h6',
  upload: 'M12 16V4M8 8l4-4 4 4M4 16v2a2 2 0 002 2h12a2 2 0 002-2v-2',
  trash: 'M4 7h16M9 7V5h6v2M6 7l1 13h10l1-13M10 11v6M14 11v6',
  db: 'M12 3c4.4 0 8 1.34 8 3s-3.6 3-8 3-8-1.34-8-3 3.6-3 8-3zM4 6v12c0 1.66 3.6 3 8 3s8-1.34 8-3V6M4 12c0 1.66 3.6 3 8 3s8-1.34 8-3',
  refresh: 'M20 12a8 8 0 11-2.34-5.66M20 4v4h-4',
  sliders: 'M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6'
}
</script>

<template>
  <svg
    :width="size" :height="size" viewBox="0 0 24 24" fill="none"
    stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"
    :class="className" :style="style"
  >
    <path :d="paths[name] || ''" />
  </svg>
</template>